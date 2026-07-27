"""
scripts/fetch_real_kyc_aml_corpus.py
========================================
Fetches REAL, official KYC/AML regulatory text for the new `kyc_aml`
namespace, mirroring fetch_real_compliance_corpus.py's approach for the
existing `legal` namespace (GDPR/CCPA/HIPAA).

WHY THIS DOMAIN, WHY THESE SPECIFIC CITATIONS
------------------------------------------------
Deliberately excludes Corporate Transparency Act / Beneficial Ownership
Information reporting (31 CFR Chapter I, FinCEN's BOI registry) — that
rule has been through court injunctions, a March 2025 interim rule
exempting all US domestic companies, and is still unsettled as of the
most recent reporting available. Bad candidate for eval ground truth:
the answer could change again before this corpus is even ingested.

Uses the CDD Rule (31 CFR 1010.230) instead — a different, older (2016),
stable regulation: it governs how BANKS identify beneficial owners of
THEIR OWN customers, which is the actual KYC process, as opposed to BOI's
company-reports-to-FinCEN-directly registry. Don't conflate the two.

LEGAL NOTE: same as the GDPR script — federal regulations are government
works, not copyrighted. Safe to ingest verbatim.

SOURCES — verified confidence noted per citation
---------------------------------------------------
eCFR (ecfr.gov) — official, government-run, continuously updated. Same
source type already verified working for HIPAA manual checklist.

CONFIRMED (URL directly verified via search before writing this):
  - 31 CFR 1010.230 — CDD Rule / beneficial ownership (Part 1010, Subpart B)
  - 31 CFR 1010.311 — CTR, >$10,000 currency transactions (Part 1010, Subpart C)

CONSTRUCTED FROM PATTERN, NOT INDIVIDUALLY VERIFIED — script will WARN,
not silently save garbage, if these don't match:
  - 31 CFR 1010.430 — recordkeeping (guessed Subpart D — Part 1010 Subpart C
    is confirmed to only cover ss1010.300-380, so 430 must be a later subpart,
    but the exact letter wasn't individually confirmed)
  - 31 CFR 1020.320 — SAR filing, banks (Part 1020 Subpart C is confirmed to
    be "Reports Required To Be Made By Banks", so this is a reasonable
    placement, but the exact URL wasn't individually fetched)

NOT AUTO-FETCHED — see manual checklist at the bottom of this file:
  PEP enhanced due diligence and OFAC SDN screening don't have a single
  clean CFR citation the way CDD/CTR do — they're a mix of guidance
  documents and cross-references. FATF Recommendation 10 is a different
  kind of source entirely (international body, not a national government —
  verify FATF's own reuse terms before ingesting verbatim).

USAGE
------
    pip install requests beautifulsoup4 --break-system-packages
    python scripts/fetch_real_kyc_aml_corpus.py

Writes one .md file per citation to data/compliance/real/kyc_aml/.
Run ingest_real_corpus.py against this directory separately once done.
"""

import re
import sys
import time
from datetime import date
from pathlib import Path

import requests
from bs4 import BeautifulSoup

OUTPUT_DIR = Path("data/compliance/real/kyc_aml")
FETCH_DELAY = 1.5  # seconds between requests — be a polite scraper

# (citation, url_path, eval-question note, confidence)
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
        "Recordkeeping — CDD record retention period",
        "constructed — verify subpart letter on first run",
    ),
    (
        "1020.320",
        "title-31/subtitle-B/chapter-X/part-1020/subpart-C/section-1020.320",
        "SAR — suspicious activity report filing, banks",
        "constructed — verify subpart letter and dollar threshold on first run",
    ),
]


def fetch_section(citation: str, url_path: str, confidence: str) -> str | None:
    """
    Fetches one eCFR section page and extracts the regulatory text.
    eCFR pages consistently include an 'authoritative but unofficial'
    disclaimer line right before the real content — used as a start
    anchor, same idea as the 'Suitable Recitals' end-anchor used for
    the GDPR script.
    """
    url = f"https://www.ecfr.gov/current/{url_path}"
    try:
        resp = requests.get(url, timeout=15, headers={"User-Agent": "ai-platform-corpus-fetch/1.0"})
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  [ERROR] {citation}: fetch failed — {e}")
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    text = soup.get_text("\n")

    # Start anchor: the section number itself, formatted like eCFR does
    # (e.g. "§ 1010.311" or "31 CFR 1010.311").
    start_pattern = rf"(§\s*{re.escape(citation)}|31\s+CFR\s+{re.escape(citation)})"
    start_match = re.search(start_pattern, text)
    # End anchor: eCFR pages show 'AUTHORITY:' or 'SOURCE:' after the
    # operative text, or a 'View all text of Subpart' nav link.
    end_match = re.search(r"AUTHORITY:|SOURCE:|View all text of Subpart", text)

    if not start_match:
        print(f"  [WARN] {citation}: couldn't find section heading — page structure may differ, verify manually at {url}")
        if confidence == "confirmed":
            print(f"    !! This URL was confirmed — the page may have restructured. Check manually.")
        else:
            print(f"    !! This was a constructed URL ({confidence}) — likely wrong subpart letter.")
        return None

    end_idx = end_match.start() if end_match else start_match.start() + 3000
    section_text = text[start_match.start():end_idx].strip()

    if len(section_text) < 50:
        print(f"  [WARN] {citation}: extracted text suspiciously short ({len(section_text)} chars) — verify manually at {url}")

    return section_text


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()

    print(f"Fetching {len(CFR_SECTIONS)} KYC/AML regulatory sections from ecfr.gov...")
    print("NOTE: 1010.430 and 1020.320 use constructed URLs — read [WARN] lines carefully.\n")
    ok, failed = 0, []

    for citation, url_path, note, confidence in CFR_SECTIONS:
        slug = citation.replace(".", "_")
        out_path = OUTPUT_DIR / f"cfr_{slug}.md"

        if out_path.exists():
            print(f"  31 CFR {citation} — already exists, skipping (delete file to re-fetch)")
            ok += 1
            continue

        print(f"  31 CFR {citation} ({note}) [{confidence}]...")
        content = fetch_section(citation, url_path, confidence)

        if content is None:
            failed.append(citation)
            time.sleep(FETCH_DELAY)
            continue

        # HTML comment metadata — NOT YAML frontmatter. See compliance script for why.
        out_path.write_text(
            f"<!-- regulation_id: 31_CFR_{slug} | citation: 31 CFR {citation} "
            f"| source_url: https://www.ecfr.gov/current/{url_path} "
            f"| fetched: {today} | eval_question: {note} "
            f"| source_confidence: {confidence} -->\n\n"
            f"{content}\n",
            encoding="utf-8",
        )
        print(f"    → saved {out_path} ({len(content)} chars)")
        ok += 1
        time.sleep(FETCH_DELAY)

    print(f"\nDone: {ok}/{len(CFR_SECTIONS)} fetched. Saved to {OUTPUT_DIR}/")
    if failed:
        print(f"FAILED (fetch/verify manually): {failed}")

    print("\nIMPORTANT: check output above for [WARN] lines even on 'successful' "
          "fetches — 1010.430 and 1020.320 use constructed URLs that weren't "
          "individually verified. Read those two files before trusting them.")

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()


# =============================================================================
# MANUAL CHECKLIST — not auto-fetched, different source types (see docstring)
# =============================================================================
#
# Use the same HTML comment metadata format, NOT YAML --- frontmatter blocks.
#
# [ ] PEP (Politically Exposed Persons) enhanced due diligence
#     No single clean CFR citation. Start at:
#     https://www.ffiec.gov/bsa_aml_infobase/pages_manual/OLM_015.htm
#     (FFIEC BSA/AML Examination Manual — PEP section)
#     Also check 31 CFR 1010.620 (private banking due diligence, where PEP
#     scrutiny is most concretely codified for US banks).
#     Save as: data/compliance/real/kyc_aml/pep_due_diligence.md
#
# [ ] OFAC SDN list screening obligation
#     Not a single CFR section — OFAC's sanctions programs are spread across
#     31 CFR Chapter V (parts 500-599), one part per sanctioned
#     country/program. The screening obligation itself is closer to supervisory
#     expectation + program-specific rules. Source from:
#     https://ofac.treasury.gov/faqs/topic/1486
#     Save as: data/compliance/real/kyc_aml/ofac_sdn_screening.md
#
# [ ] FATF Recommendation 10 (international CDD standard)
#     DIFFERENT LEGAL CATEGORY — FATF is an intergovernmental standard-setting
#     body, not a national government. Check FATF's own reuse/copyright terms
#     on fatf-gafi.org before ingesting verbatim — don't assume the same
#     "government work, public domain" status that applies to CFR text.
#     If reuse is permitted: https://www.fatf-gafi.org/en/topics/fatf-recommendations.html
#     Save as: data/compliance/real/kyc_aml/fatf_recommendation_10.md
