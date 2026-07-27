import os
import sys
import asyncio
import argparse
import requests
import xml.etree.ElementTree as ET
from pathlib import Path
from core.pipeline.db_ingest import ingestion_pipeline

KYC_DIR = Path("data/compliance/real/kyc_aml")

def fetch_and_parse_xml(part: str, date: str = "2026-07-01") -> list[dict]:
    """Fetches a CFR part from eCFR XML API and parses it into sections."""
    url = f"https://www.ecfr.gov/api/versioner/v1/full/{date}/title-31.xml?part={part}"
    print(f"Fetching {url}...")
    
    headers = {"User-Agent": "ComplianceRAGBot/1.0", "Accept": "application/xml"}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    
    print(f"Successfully downloaded {len(response.content) / 1024:.2f} KB")
    
    root = ET.fromstring(response.content)
    sections = []
    
    # DIV8 is a section in eCFR XML (e.g., § 1010.230)
    for div8 in root.findall(".//DIV8"):
        section_number = div8.get("N") # e.g., "1010.230"
        if not section_number:
            continue
            
        head = div8.find("HEAD")
        title = head.text.strip() if head is not None and head.text else f"§ {section_number}"
        
        paragraphs = []
        for p in div8.findall(".//P"):
            text = "".join(p.itertext()).strip()
            if text:
                paragraphs.append(text)
                
        content = f"# {title}\n\n" + "\n\n".join(paragraphs)
        
        doc_id = f"cfr_{section_number.replace('.', '_')}"
        filename = f"{doc_id}.md"
        
        sections.append({
            "doc_id": doc_id,
            "filename": filename,
            "content": content
        })
        
    return sections

async def stage_ingest(documents: list[dict]):
    """Ingests the generated markdown files into PostgreSQL."""
    print(f"\nIngesting {len(documents)} documents to PostgreSQL...")
    totals = 0
    errors = []
    
    for doc in documents:
        filepath = KYC_DIR / doc["filename"]
        doc_id = doc["doc_id"]
        
        print(f"  [INGEST] {doc['filename']:<35} (namespace=kyc_aml, doc_id={doc_id})")
        
        try:
            metrics = await ingestion_pipeline(
                input_file_path=str(filepath),
                document_id=doc_id,
                namespace="kyc_aml"
            )
            chunks = metrics["total_chunks"]
            elapsed = metrics["total_time_seconds"]
            throughput = metrics["throughput_chunks_per_second"]
            print(f"    ✓ chunks={chunks}  time={elapsed}s  throughput={throughput} chunks/s")
            totals += chunks
        except Exception as e:
            print(f"    ✗ ERROR: {e}")
            errors.append(doc['filename'])

    print(f"\n  Ingest summary:")
    print(f"    namespace=kyc_aml    → {totals} chunks")
    if errors:
        print(f"  Errors ({len(errors)}): {errors}")
    else:
        print("  No errors.")

async def main(args):
    KYC_DIR.mkdir(parents=True, exist_ok=True)
    
    parts = ["1010", "1020"]
    all_documents = []
    
    if not args.ingest_only:
        print("=== STAGE 1: ACQUIRE & PARSE XML ===")
        for part in parts:
            try:
                sections = fetch_and_parse_xml(part)
                for sec in sections:
                    filepath = KYC_DIR / sec["filename"]
                    filepath.write_text(sec["content"], encoding="utf-8")
                    all_documents.append(sec)
                print(f"  Saved {len(sections)} sections for Part {part}")
            except Exception as e:
                print(f"Failed to fetch Part {part}: {e}")
                sys.exit(1)
    else:
        print("=== STAGE 1: SKIPPED (Ingest Only) ===")
        # Gather existing files
        for f in KYC_DIR.glob("cfr_*.md"):
            doc_id = f.stem
            all_documents.append({
                "doc_id": doc_id,
                "filename": f.name
            })
            
    print("\n=== STAGE 2: INGEST ===")
    if not args.fetch_only:
        if not all_documents:
            print("No documents to ingest.")
            return
        await stage_ingest(all_documents)
    else:
        print("Skipped ingestion (--fetch-only)")

    print("\n" + "="*60)
    print("DONE")
    print("="*60)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch and ingest KYC/AML corpus via eCFR XML API")
    parser.add_argument("--fetch-only", action="store_true", help="Fetch and parse only")
    parser.add_argument("--ingest-only", action="store_true", help="Ingest existing markdown files only")
    args = parser.parse_args()
    
    if args.fetch_only and args.ingest_only:
        print("Error: mutually exclusive flags")
        sys.exit(1)
        
    asyncio.run(main(args))
