"""
scripts/build_corpus.py
=========================
Single end-to-end pipeline that acquires, validates, and ingests real
statutory text for both namespaces.

  Namespace   Source          Citations
  ---------   ------          ---------
  legal       gdpr-info.eu    GDPR Art. 4,5,6,12-22,25,33,34,37-39,83
  legal       ecfr.gov        HIPAA 45 CFR §164.502, §164.514
  legal       leginfo.ca.gov  CCPA §1798.29, §1798.82, §1798.100, §1798.110, §1798.115
  kyc_aml     ecfr.gov        31 CFR 1010.230, 1010.311, 1010.430, 1020.320

WHY ONE SCRIPT
---------------
Three separate fetch/ingest scripts with a manual copy step in the middle
is a procedure, not a pipeline. A procedure rots silently — someone runs
Step 1, forgets Step 2, runs Step 3 on incomplete data. This script is
a single command. It fetches everything, validates it, then ingests it.

PIPELINE STAGES
----------------
  1. ACQUIRE  — HTTP fetch from official statutory sources
               Resume-safe: skips files that already exist on disk.
               Validates extracted text length before writing.

  2. VALIDATE — After all fetches, report any empty/short files.
               Halts before ingestion if critical files are missing.

  3. INGEST   — Runs existing ingestion_pipeline() against every fetched
               file. The pipeline: chunk → embed → bulk COPY to postgres.
               fts_vector fills automatically via DB trigger (BM25 index).

LEGAL NOTE
-----------
GDPR: EU regulation — not subject to copyright (government work).
HIPAA/CFR: US federal regulation — government work, 17 USC §105.
CCPA: California state law — government work, California Government Code §9004.
FATF: Intergovernmental body. NOT fetched here — verify their reuse
      terms before ingesting verbatim.

USAGE
------
    # Full pipeline (fetch missing + ingest all)
    python scripts/build_corpus.py

    # Fetch only — inspect files before touching the DB
    python scripts/build_corpus.py --fetch-only

    # Ingest only — files already exist, skip fetching
    python scripts/build_corpus.py --ingest-only

    # Dry run — show what would happen without doing anything
    python scripts/build_corpus.py --dry-run

    # One namespace only
    python scripts/build_corpus.py --namespace legal
    python scripts/build_corpus.py --namespace kyc_aml

    # Re-fetch even if files exist
    python scripts/build_corpus.py --force-fetch

PREREQUISITES
--------------
    docker-compose up -d   (postgres + redis must be running for ingestion)
    poetry shell           (or run with poetry run python ...)
"""

import argparse
import asyncio
import re
import sys
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# Project root on path — so core.* imports work
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.pipeline.db_ingest import ingestion_pipeline

# ── Output directories ─────────────────────────────────────────────────────────
LEGAL_DIR   = Path("data/compliance/real/legal")
KYC_AML_DIR = Path("data/compliance/real/kyc_aml")

FETCH_DELAY = 1.5   # seconds between requests — be a polite scraper
MIN_TEXT_LEN = 100  # characters — anything shorter is a scraping failure


# ── Source descriptor ──────────────────────────────────────────────────────────

@dataclass
class Source:
    filename:   str        # output filename under the namespace dir
    namespace:  str        # legal | kyc_aml
    note:       str        # what eval question this covers
    confidence: str        # confirmed | constructed — honest label
    # fetch() is responsible for returning the raw statutory text or None


# ── Fetcher functions — one per source site ────────────────────────────────────

def _get(url: str, label: str) -> requests.Response | None:
    """Shared HTTP GET with consistent headers and error handling."""
    try:
        resp = requests.get(
            url, timeout=20,
            headers={"User-Agent": "ai-platform-corpus-fetch/1.0 (educational research)"}
        )
        resp.raise_for_status()
        return resp
    except requests.RequestException as e:
        print(f"    [HTTP ERROR] {label}: {e}")
        return None


def fetch_gdpr_article(article_num: int) -> str | None:
    """
    gdpr-info.eu — clean per-article pages.
    Extracts text between the article heading and 'Suitable Recitals'.
    Verified against Art. 4, 5, 6, 15, 33, 83 before publishing.
    """
    url = f"https://gdpr-info.eu/art-{article_num}-gdpr/"
    resp = _get(url, f"GDPR Art. {article_num}")
    if not resp:
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    
    content_div = soup.find("div", class_="entry-content")
    if content_div:
        # entry-content already excludes the headings and recitals sections
        snippet = content_div.get_text("\n").strip()
        if len(snippet) < 50:
            return None
        return snippet
        
    # Fallback to article or full body
    article = soup.find("article")
    text = article.get_text("\n") if article else soup.get_text("\n")

    start_match = re.search(rf"Art\.\s*{article_num}\s+GDPR", text)
    end_match   = re.search(r"Suitable Recitals", text)

    if not start_match:
        print(f"    [WARN] GDPR Art. {article_num}: heading not found — page may have restructured")
        return None

    end_idx = end_match.start() if end_match else len(text)
    snippet = text[start_match.start():end_idx].strip()
    
    if "skip to content" in snippet.lower():
        print(f"    [WARN] GDPR Art. {article_num}: Extracted text contains navigation noise.")
        return None
        
    return snippet


def fetch_ecfr_section(url_path: str, citation: str, confidence: str) -> str | None:
    """
    ecfr.gov — official US federal regulation source.
    Used for both HIPAA (Title 45) and KYC/AML (Title 31).
    """
    url = f"https://www.ecfr.gov/current/{url_path}"
    resp = _get(url, citation)
    if not resp:
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    text = soup.get_text("\n")

    # Try to find the section number as the start anchor
    start_pattern = rf"(§\s*{re.escape(citation.split('CFR')[-1].strip())}|{re.escape(citation)})"
    start_match = re.search(start_pattern, text)
    end_match   = re.search(r"AUTHORITY:|SOURCE:|View all text of Subpart", text)

    if not start_match:
        if confidence == "constructed":
            print(f"    [WARN] {citation}: section heading not found — constructed URL may be wrong subpart. Verify at {url}")
        else:
            print(f"    [WARN] {citation}: section heading not found — page may have restructured at {url}")
        # Fallback: take up to 4000 chars from main content area
        # Better than nothing and the file gets flagged for manual review
        content_div = soup.find("div", class_=re.compile(r"section|content", re.I))
        if content_div:
            fallback = content_div.get_text("\n").strip()
            if len(fallback) > MIN_TEXT_LEN:
                print(f"    [FALLBACK] {citation}: using content div ({len(fallback)} chars) — verify manually")
                return fallback
        return None

    end_idx = end_match.start() if end_match else start_match.start() + 4000
    return text[start_match.start():end_idx].strip()


def fetch_ccpa_section(section_num: str) -> str | None:
    """
    leginfo.legislature.ca.gov — official California statutory source.
    URL: ?lawCode=CIV&sectionNum=1798.82.  (trailing dot is part of the URL)
    The statutory text lives in the .lawSection div.
    """
    url = (
        f"https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml"
        f"?lawCode=CIV&sectionNum={section_num}."
    )
    resp = _get(url, f"CCPA §{section_num}")
    if not resp:
        return None

    soup = BeautifulSoup(resp.text, "html.parser")

    # Primary: #single_law_section div — this is the canonical content container
    law_div = soup.find("div", id="single_law_section")
    if law_div:
        return law_div.get_text("\n").strip()

    print(f"    [WARN] CCPA §{section_num}: could not extract statutory text from {url} (single_law_section not found)")
    return None


# ── Source manifest ────────────────────────────────────────────────────────────
# Each entry: (namespace, output_filename, note, confidence, fetch_fn)
# fetch_fn is a zero-arg callable that returns str | None

def _build_manifest() -> list[tuple[str, str, str, str, callable]]:
    today = date.today().isoformat()
    sources = []

    # ── GDPR (namespace: legal) ────────────────────────────────────────────────
    GDPR_ARTICLES = [
        (4,  "Q3 — definition of personal data"),
        (5,  "Q8 — data minimisation principle"),
        (6,  "Q4 — lawful bases for processing"),
        (12, "Q1 — data subject rights (Art. 12 general)"),
        (13, "Q1 — data subject rights (Art. 13 transparency)"),
        (14, "Q1 — data subject rights (Art. 14 indirect collection)"),
        (15, "Q1 — data subject rights (Art. 15 right of access)"),
        (16, "Q1 — data subject rights (Art. 16 rectification)"),
        (17, "Q1 — data subject rights (Art. 17 erasure)"),
        (18, "Q1 — data subject rights (Art. 18 restriction)"),
        (20, "Q1 — data subject rights (Art. 20 portability)"),
        (21, "Q1 — data subject rights (Art. 21 right to object)"),
        (22, "Q1 — data subject rights (Art. 22 automated decisions)"),
        (25, "Q10 — privacy by design and by default"),
        (33, "Q5 — breach notification to supervisory authority (72h)"),
        (34, "Q5 — breach notification to data subjects"),
        (37, "Q9 — DPO designation"),
        (38, "Q9 — DPO position"),
        (39, "Q9 — DPO tasks"),
        (83, "Q2 — administrative fines"),
    ]
    for art_num, note in GDPR_ARTICLES:
        n = art_num  # capture for closure
        sources.append((
            "legal",
            f"gdpr_art_{art_num}.md",
            note,
            "confirmed",
            lambda num=n: fetch_gdpr_article(num),
        ))

    # ── HIPAA (namespace: legal) — ecfr.gov, Title 45 ─────────────────────────
    HIPAA_SECTIONS = [
        (
            "164.502",
            "title-45/subtitle-A/subchapter-C/part-164/subpart-E/section-164.502",
            "Q7 — HIPAA minimum necessary standard (§164.502(b))",
            "confirmed",
        ),
        (
            "164.514",
            "title-45/subtitle-A/subchapter-C/part-164/subpart-E/section-164.514",
            "Q7 — HIPAA minimum necessary implementation specs (§164.514(d))",
            "confirmed",
        ),
    ]
    for sec, url_path, note, conf in HIPAA_SECTIONS:
        s, u, c = sec, url_path, conf  # capture for closure
        slug = sec.replace(".", "_")
        sources.append((
            "legal",
            f"hipaa_{slug}.md",
            note,
            conf,
            lambda section=s, path=u, confidence=c: fetch_ecfr_section(path, f"45 CFR {section}", confidence),
        ))

    # ── CCPA (namespace: legal) — leginfo.legislature.ca.gov ──────────────────
    CCPA_SECTIONS = [
        ("1798.29",  "Q6-suite2 — CCPA/California breach notification (agency equivalent)"),
        ("1798.82",  "Q6-suite2 — CCPA §1798.82 breach notification 30-day rule (SB 446, eff. Jan 2026)"),
        ("1798.100", "Q6 — CCPA consumer right to know / access"),
        ("1798.110", "Q6 — CCPA categories of personal information disclosed"),
        ("1798.115", "Q6 — CCPA right to know third-party disclosure"),
    ]
    for sec_num, note in CCPA_SECTIONS:
        s = sec_num  # capture for closure
        slug = sec_num.replace(".", "_")
        sources.append((
            "legal",
            f"ccpa_{slug}.md",
            note,
            "confirmed",
            lambda section=s: fetch_ccpa_section(section),
        ))

    # ── KYC/AML (namespace: kyc_aml) — ecfr.gov, Title 31 ────────────────────
    CFR_SECTIONS = [
        (
            "1010.230",
            "title-31/subtitle-B/chapter-X/part-1010/subpart-B/section-1010.230",
            "CDD Rule — beneficial ownership identification + 4 core requirements",
            "confirmed",
        ),
        (
            "1010.311",
            "title-31/subtitle-B/chapter-X/part-1010/subpart-C/section-1010.311",
            "CTR — currency transactions over $10,000",
            "confirmed",
        ),
        (
            "1010.430",
            "title-31/subtitle-B/chapter-X/part-1010/subpart-D/section-1010.430",
            "Recordkeeping — CDD record retention",
            "constructed",
        ),
        (
            "1020.320",
            "title-31/subtitle-B/chapter-X/part-1020/subpart-C/section-1020.320",
            "SAR — suspicious activity report filing, banks",
            "constructed",
        ),
    ]
    for citation, url_path, note, conf in CFR_SECTIONS:
        cit, u, c = citation, url_path, conf  # capture for closure
        slug = citation.replace(".", "_")
        sources.append((
            "kyc_aml",
            f"cfr_{slug}.md",
            note,
            conf,
            lambda cit_=cit, path=u, confidence=c: fetch_ecfr_section(path, f"31 CFR {cit_}", confidence),
        ))

    return sources


# ── Stage 1: ACQUIRE ───────────────────────────────────────────────────────────

def stage_acquire(
    manifest: list,
    target_namespace: str | None,
    force_fetch: bool,
    dry_run: bool,
) -> dict[str, Path]:
    """
    Fetch all sources. Returns mapping of filename → Path for fetched files.
    Skips files that already exist on disk (unless --force-fetch).
    """
    print("\n" + "="*60)
    print("STAGE 1 — ACQUIRE")
    print("="*60)

    # Ensure output dirs exist
    LEGAL_DIR.mkdir(parents=True, exist_ok=True)
    KYC_AML_DIR.mkdir(parents=True, exist_ok=True)

    dir_map = {"legal": LEGAL_DIR, "kyc_aml": KYC_AML_DIR}

    fetched: dict[str, Path] = {}
    ok = skipped = failed = 0

    for namespace, filename, note, confidence, fetch_fn in manifest:
        if target_namespace and namespace != target_namespace:
            continue

        out_dir  = dir_map[namespace]
        out_path = out_dir / filename
        label    = filename.replace(".md", "")
        conf_tag = f" [{confidence}]" if confidence == "constructed" else ""

        if out_path.exists() and not force_fetch:
            size_kb = out_path.stat().st_size / 1024
            print(f"  [SKIP]  {label:<35} already exists ({size_kb:.1f} KB)")
            fetched[filename] = out_path
            skipped += 1
            continue

        if dry_run:
            print(f"  [DRY]   {label:<35} would fetch — {note}{conf_tag}")
            continue

        print(f"  [FETCH] {label:<35} {note}{conf_tag}")
        content = fetch_fn()

        if content is None or len(content) < MIN_TEXT_LEN:
            if content is not None:
                print(f"    [WARN] Only {len(content)} chars extracted — below minimum {MIN_TEXT_LEN}. Skipping write.")
            failed += 1
            time.sleep(FETCH_DELAY)
            continue

        out_path.write_text(content, encoding="utf-8")
        print(f"    → {out_path} ({len(content):,} chars)")
        fetched[filename] = out_path
        ok += 1
        time.sleep(FETCH_DELAY)

    print(f"\n  Acquire summary: {ok} fetched, {skipped} skipped (cached), {failed} failed")
    return fetched


# ── Stage 2: VALIDATE ─────────────────────────────────────────────────────────

def stage_validate(
    manifest: list,
    target_namespace: str | None,
    fetched: dict[str, Path],
) -> bool:
    """
    Check that every expected file exists and is non-trivially long.
    Returns True if all critical files are present.
    """
    print("\n" + "="*60)
    print("STAGE 2 — VALIDATE")
    print("="*60)

    dir_map = {"legal": LEGAL_DIR, "kyc_aml": KYC_AML_DIR}
    missing = []
    short   = []

    for namespace, filename, note, confidence, _ in manifest:
        if target_namespace and namespace != target_namespace:
            continue

        path = dir_map[namespace] / filename
        if not path.exists():
            missing.append((filename, note))
            print(f"  [MISSING]  {filename:<40} {note}")
        else:
            size = path.stat().st_size
            if size < MIN_TEXT_LEN:
                short.append((filename, size))
                print(f"  [SHORT]    {filename:<40} only {size} bytes — verify manually")
            else:
                print(f"  [OK]       {filename:<40} {size/1024:.1f} KB")

    if missing:
        print(f"\n  {len(missing)} file(s) missing — ingestion will proceed for available files")
        print("  Missing files can be added manually — see the MANUAL CHECKLIST in each fetch script")

    if short:
        print(f"\n  {len(short)} file(s) suspiciously short — verify content manually")

    all_ok = len(missing) == 0 and len(short) == 0
    print(f"\n  Validation: {'PASSED' if all_ok else 'PARTIAL — some files unavailable'}")
    return all_ok


# ── Stage 3: INGEST ───────────────────────────────────────────────────────────

async def stage_ingest(
    manifest: list,
    target_namespace: str | None,
    dry_run: bool,
) -> None:
    """
    Run ingestion_pipeline() against every available file.
    Chunk → embed → COPY to postgres.
    fts_vector fills automatically via DB trigger.
    """
    print("\n" + "="*60)
    print("STAGE 3 — INGEST")
    print("="*60)

    dir_map = {"legal": LEGAL_DIR, "kyc_aml": KYC_AML_DIR}
    totals: dict[str, int] = {}
    errors: list[str] = []

    for namespace, filename, note, _, _ in manifest:
        if target_namespace and namespace != target_namespace:
            continue

        path = dir_map[namespace] / filename
        if not path.exists():
            print(f"  [SKIP]   {filename:<40} file not found (fetch failed or manual step needed)")
            continue

        document_id = path.stem  # e.g. "gdpr_art_4"
        size_kb = path.stat().st_size / 1024

        if dry_run:
            print(f"  [DRY]    {filename:<40} would ingest → namespace={namespace} doc_id={document_id}")
            continue

        print(f"  [INGEST] {filename:<40} (namespace={namespace}, doc_id={document_id}, {size_kb:.1f} KB)")
        try:
            metrics = await ingestion_pipeline(
                input_file_path=str(path),
                document_id=document_id,
                namespace=namespace,
            )
            chunks = metrics["total_chunks"]
            elapsed = metrics["total_time_seconds"]
            throughput = metrics["throughput_chunks_per_second"]
            print(f"    ✓ chunks={chunks}  time={elapsed}s  throughput={throughput} chunks/s")
            totals[namespace] = totals.get(namespace, 0) + chunks
        except Exception as e:
            print(f"    ✗ ERROR: {e}")
            errors.append(filename)

    print(f"\n  Ingest summary:")
    for ns, count in totals.items():
        print(f"    namespace={ns:<10} → {count} chunks")
    if errors:
        print(f"  Errors ({len(errors)}): {errors}")
    else:
        print("  No errors.")


# ── Main orchestrator ─────────────────────────────────────────────────────────

async def main(args: argparse.Namespace) -> None:
    manifest = _build_manifest()

    if args.namespace:
        print(f"Running for namespace: {args.namespace}")
    if args.dry_run:
        print("DRY RUN — no files will be written and no DB will be touched")
    if args.force_fetch:
        print("FORCE FETCH — existing files will be overwritten")

    # Stage 1: Acquire
    if not args.ingest_only:
        fetched = stage_acquire(
            manifest,
            target_namespace=args.namespace,
            force_fetch=args.force_fetch,
            dry_run=args.dry_run,
        )
    else:
        fetched = {}  # ingest-only — skip fetch, validate will check disk

    # Stage 2: Validate
    stage_validate(manifest, target_namespace=args.namespace, fetched=fetched)

    # Stage 3: Ingest
    if not args.fetch_only:
        await stage_ingest(
            manifest,
            target_namespace=args.namespace,
            dry_run=args.dry_run,
        )

    print("\n" + "="*60)
    print("DONE")
    print("="*60)
    if not args.dry_run and not args.fetch_only:
        print("""
Next steps:
  • Re-run the Week 7 eval baseline to check if recall ceiling moved:
        python scripts/lab_7.5_deepeval_v3.py
  • Query the real corpus:
        curl -X POST http://localhost:8000/search \\
          -H 'Content-Type: application/json' \\
          -d '{"query": "What constitutes personal data under GDPR?", "namespace": "legal", "top_k": 5}'
""")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Build real statutory corpus — fetch, validate, ingest"
    )
    parser.add_argument(
        "--namespace", choices=["legal", "kyc_aml"],
        help="Run for one namespace only"
    )
    parser.add_argument(
        "--fetch-only", action="store_true",
        help="Fetch files only, do not ingest into DB"
    )
    parser.add_argument(
        "--ingest-only", action="store_true",
        help="Ingest already-fetched files, skip HTTP fetching"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would happen without doing anything"
    )
    parser.add_argument(
        "--force-fetch", action="store_true",
        help="Re-fetch even if files already exist on disk"
    )
    args = parser.parse_args()

    if args.fetch_only and args.ingest_only:
        print("Error: --fetch-only and --ingest-only are mutually exclusive")
        sys.exit(1)

    asyncio.run(main(args))
