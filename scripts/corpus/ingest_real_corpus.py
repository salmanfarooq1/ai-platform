"""
scripts/ingest_real_corpus.py
================================
Ingests the real statutory text files produced by:
    fetch_real_compliance_corpus.py  → data/compliance/real/*.md
    fetch_real_kyc_aml_corpus.py     → data/compliance/real/kyc_aml/*.md

WHAT THIS DOES DIFFERENTLY FROM ingest_compliance_corpus.py
-------------------------------------------------------------
The original script has a hardcoded list of three synthetic files.
This one scans a directory for every .md file and ingests them all,
using the filename (without extension) as the document_id.

Two namespaces are handled:
  - legal   → data/compliance/real/*.md         (GDPR/CCPA/HIPAA)
  - kyc_aml → data/compliance/real/kyc_aml/*.md (KYC/AML/CFR)

USAGE
------
    # Make sure the API's DB (PostgreSQL + pgvector) is running first:
    #   docker-compose up -d
    #
    # Then run from the project root:
    python scripts/ingest_real_corpus.py

    # Dry-run (list files that WOULD be ingested, without touching DB):
    python scripts/ingest_real_corpus.py --dry-run

    # Ingest one namespace only:
    python scripts/ingest_real_corpus.py --namespace legal
    python scripts/ingest_real_corpus.py --namespace kyc_aml

IMPORTANT: Run the fetch scripts first.
    python scripts/fetch_real_compliance_corpus.py
    python scripts/fetch_real_kyc_aml_corpus.py
    # Then fill in the manual checklist items in each fetch script (HIPAA, CCPA, PEP, OFAC).
    # Then run this script.
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.pipeline.db_ingest import ingestion_pipeline

# ── Namespace → directory mapping ─────────────────────────────────────────────
NAMESPACES = {
    "legal":   Path("data/compliance/real"),
    "kyc_aml": Path("data/compliance/real/kyc_aml"),
}


def collect_files(namespace: str) -> list[tuple[Path, str]]:
    """
    Scan the namespace directory for .md files.
    Returns list of (path, document_id) tuples.
    document_id = filename without extension (e.g. gdpr_art_4 → "gdpr_art_4").
    Files inside a subdirectory are excluded — e.g. the kyc_aml/ subdir is
    excluded when scanning the legal/ directory so namespaces don't bleed.
    """
    base_dir = NAMESPACES[namespace]
    if not base_dir.exists():
        return []

    files = []
    for path in sorted(base_dir.iterdir()):
        if path.is_file() and path.suffix == ".md":
            doc_id = path.stem  # e.g. "gdpr_art_4", "hipaa_164_502b"
            files.append((path, doc_id))

    return files


async def ingest_namespace(namespace: str, files: list[tuple[Path, str]], dry_run: bool) -> int:
    """Ingest all files for one namespace. Returns total chunk count."""
    total_chunks = 0
    for path, doc_id in files:
        if dry_run:
            print(f"  [DRY RUN] would ingest {path.name} → namespace={namespace} document_id={doc_id}")
            continue

        print(f"  [ingesting] {path.name} (document_id={doc_id}, namespace={namespace})")
        try:
            metrics = await ingestion_pipeline(
                input_file_path=str(path),
                document_id=doc_id,
                namespace=namespace,
            )
            print(f"    chunks={metrics['total_chunks']} "
                  f"time={metrics['total_time_seconds']}s "
                  f"throughput={metrics['throughput_chunks_per_second']} chunks/s")
            total_chunks += metrics["total_chunks"]
        except Exception as e:
            print(f"    [ERROR] {path.name}: {e}")
            # Don't abort — log the failure and continue with remaining files.

    return total_chunks


async def main(target_namespace: str | None, dry_run: bool):
    namespaces_to_run = [target_namespace] if target_namespace else list(NAMESPACES)

    grand_total = 0
    for namespace in namespaces_to_run:
        base_dir = NAMESPACES[namespace]
        files = collect_files(namespace)

        print(f"\n{'='*60}")
        print(f"Namespace: {namespace}  ({base_dir})")
        print(f"{'='*60}")

        if not files:
            if not base_dir.exists():
                print(f"  [SKIP] directory does not exist — run the fetch script first")
            else:
                print(f"  [SKIP] no .md files found in {base_dir}")
            continue

        print(f"Found {len(files)} file(s) to ingest:")
        for path, doc_id in files:
            size_kb = path.stat().st_size / 1024
            print(f"  {path.name:<40} ({size_kb:.1f} KB) → document_id={doc_id}")

        print()
        chunks = await ingest_namespace(namespace, files, dry_run)
        grand_total += chunks

        if not dry_run:
            print(f"\n  Namespace '{namespace}' done. Total chunks: {chunks}")

    if not dry_run:
        print(f"\n{'='*60}")
        print(f"All namespaces done. Grand total chunks ingested: {grand_total}")
        print(f"Query with namespace='legal' or namespace='kyc_aml' in /search")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest real statutory corpus into RAG platform")
    parser.add_argument("--namespace", choices=list(NAMESPACES), help="Ingest one namespace only")
    parser.add_argument("--dry-run", action="store_true", help="List files without touching the DB")
    args = parser.parse_args()

    asyncio.run(main(args.namespace, args.dry_run))
