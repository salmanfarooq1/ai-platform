"""
scripts/fetch_real_compliance_corpus.py
==========================================
Fetches the REAL, official statutory text for the specific citations the
Week 7 eval corpus depends on (see deep_dataset_enhancement_research_v2.md,
Section 1), and saves each as a clean markdown file under
data/compliance/real/, ready for the existing ingestion pipeline.

WHY THIS EXISTS
----------------
The current corpus (data/compliance/gdpr_policy.md etc.) was LLM-generated
via generate_compliance_corpus.py — a synthetic approximation of GDPR/
CCPA/HIPAA. That's a real risk for eval ground truth: a paraphrase can
drift from what the law actually says, silently. This pulls the real,
verbatim text instead.

LEGAL NOTE: statutes and federal/EU regulations are government works, not
copyrighted, in the US or EU. Safe to ingest verbatim — this is different
from scraping news/commentary content.

SOURCES
--------
GDPR (this script, verified working):
    gdpr-info.eu — clean per-article pages, URL pattern
    https://gdpr-info.eu/art-{N}-gdpr/. Cross-checked against gdpr.eu and
    gdpr-text.com for consistency on Art. 15 before building this.

HIPAA + CCPA (NOT auto-fetched here — see checklist at the bottom of this
file instead):
    Only 4 citations total between them. A fragile scraper for 4 pages
    isn't worth the risk of silently grabbing the wrong DOM region on a
    government site I haven't verified the structure of. Copy these by
    hand from the official source — faster and safer than debugging a
    scraper for 4 pages.

USAGE
------
    pip install requests beautifulsoup4 --break-system-packages
    python scripts/fetch_real_compliance_corpus.py

Writes one .md file per GDPR article to data/compliance/real/.
Does NOT touch the ingestion pipeline — run ingest_real_corpus.py
against this directory separately, once you're satisfied with the output.
"""

import re
import sys
import time
from datetime import date
from pathlib import Path

import requests
from bs4 import BeautifulSoup

OUTPUT_DIR = Path("data/compliance/real")
FETCH_DELAY = 1.5  # seconds between requests — be a polite scraper

# Citations mapped from deep_dataset_enhancement_research_v2.md Section 1.
# (article_number, which eval question(s) this supports)
GDPR_ARTICLES = [
    (4,  "Q3 — definition of personal data"),
    (5,  "Q8 — data minimisation"),
    (6,  "Q4 — lawful bases"),
    (12, "Q1 — data subject rights (Ch. III)"),
    (13, "Q1 — data subject rights (Ch. III)"),
    (14, "Q1 — data subject rights (Ch. III)"),
    (15, "Q1 — data subject rights (Ch. III)"),
    (16, "Q1 — data subject rights (Ch. III)"),
    (17, "Q1 — data subject rights (Ch. III)"),
    (18, "Q1 — data subject rights (Ch. III)"),
    (20, "Q1 — data subject rights (Ch. III)"),
    (21, "Q1 — data subject rights (Ch. III)"),
    (22, "Q1 — data subject rights (Ch. III)"),
    (25, "Q10 — privacy by design"),
    (33, "Q5 — breach notification (supervisory authority)"),
    (34, "Q5 — breach notification (data subject)"),
    (37, "Q9 — DPO designation"),
    (38, "Q9 — DPO position"),
    (39, "Q9 — DPO tasks"),
    (83, "Q2 — administrative fines"),
]


def fetch_article(article_num: int) -> str | None:
    """
    Fetches one GDPR article page and extracts the statutory text between
    the article heading and the 'Suitable Recitals' section (verified
    against Art. 15's actual page structure before writing this).
    """
    url = f"https://gdpr-info.eu/art-{article_num}-gdpr/"
    try:
        resp = requests.get(url, timeout=15, headers={"User-Agent": "ai-platform-corpus-fetch/1.0"})
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  [ERROR] Art. {article_num}: fetch failed — {e}")
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    text = soup.get_text("\n")

    # Extract between the article heading line and "Suitable Recitals"
    # (the consistent end-of-content marker observed on gdpr-info.eu pages).
    start_pattern = rf"Art\.\s*{article_num}\s+GDPR"
    start_match = re.search(start_pattern, text)
    end_match = re.search(r"Suitable Recitals", text)

    if not start_match:
        print(f"  [WARN] Art. {article_num}: couldn't find heading — page structure may differ, check manually")
        return None

    end_idx = end_match.start() if end_match else len(text)
    article_text = text[start_match.start():end_idx].strip()

    if len(article_text) < 50:
        print(f"  [WARN] Art. {article_num}: extracted text suspiciously short ({len(article_text)} chars) — verify manually")

    return article_text


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()

    print(f"Fetching {len(GDPR_ARTICLES)} GDPR articles from gdpr-info.eu...")
    ok, failed = 0, []

    for article_num, note in GDPR_ARTICLES:
        out_path = OUTPUT_DIR / f"gdpr_art_{article_num}.md"
        if out_path.exists():
            print(f"  Art. {article_num} — already exists, skipping (delete file to re-fetch)")
            ok += 1
            continue

        print(f"  Art. {article_num} ({note})...")
        content = fetch_article(article_num)

        if content is None:
            failed.append(article_num)
            time.sleep(FETCH_DELAY)
            continue

        # IMPORTANT: frontmatter is written as an HTML comment block, not YAML.
        # The ingestion pipeline uses header_aware_split() on .md files, which
        # reads everything as content text. A YAML --- block would get ingested
        # verbatim as chunk text and pollute embeddings. HTML comments are
        # stripped by the text extractor and never embedded.
        out_path.write_text(
            f"<!-- regulation_id: GDPR_REG_2016 | article: {article_num} "
            f"| source_url: https://gdpr-info.eu/art-{article_num}-gdpr/ "
            f"| fetched: {today} | eval_question: {note} -->\n\n"
            f"{content}\n",
            encoding="utf-8",
        )
        print(f"    → saved {out_path} ({len(content)} chars)")
        ok += 1
        time.sleep(FETCH_DELAY)

    print(f"\nDone: {ok}/{len(GDPR_ARTICLES)} fetched. Saved to {OUTPUT_DIR}/")
    if failed:
        print(f"FAILED (fetch manually from gdpr-info.eu): articles {failed}")
        sys.exit(1)


if __name__ == "__main__":
    main()


# =============================================================================
# MANUAL CHECKLIST — HIPAA + CCPA (4 citations, not auto-fetched, see docstring)
# =============================================================================
#
# For each: open the URL, copy the actual statutory text (not site commentary),
# save as data/compliance/real/{slug}.md. Use an HTML comment for metadata
# (NOT YAML frontmatter --- blocks) so the ingestion pipeline doesn't embed them.
#
# Format template:
#   <!-- regulation_id: X | citation: Y | source_url: Z | fetched: YYYY-MM-DD -->
#
#   <paste full statutory text here>
#
# HIPAA (source: ecfr.gov — official, government-run, continuously updated):
#   [ ] 45 CFR 164.502(b)  — minimum necessary standard
#       https://www.ecfr.gov/current/title-45/subtitle-A/subchapter-C/part-164/subpart-E/section-164.502
#       Save as: data/compliance/real/hipaa_164_502b.md
#
#   [ ] 45 CFR 164.514(d)  — minimum necessary implementation specifications
#       https://www.ecfr.gov/current/title-45/subtitle-A/subchapter-C/part-164/subpart-E/section-164.514
#       Save as: data/compliance/real/hipaa_164_514d.md
#
# CCPA (source: leginfo.legislature.ca.gov — official CA source):
#   [ ] Civil Code 1798.82 — breach notification, 30-day deadline (SB 446,
#       effective Jan 1 2026). THE NEW CITATION needed for Suite 2.
#       https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=CIV&sectionNum=1798.82.
#       Save as: data/compliance/real/ccpa_1798_82.md
#
#   [ ] Civil Code 1798.29 — agency-equivalent breach notification
#       https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=CIV&sectionNum=1798.29.
#       Save as: data/compliance/real/ccpa_1798_29.md
