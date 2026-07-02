"""
Ingest the synthetic compliance corpus into the RAG platform.
Namespace: legal — isolates compliance data from other namespaces.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.pipeline.db_ingest import ingestion_pipeline

CORPUS_DIR = Path("data/compliance")
NAMESPACE = "legal"

FILES = [
    ("gdpr_policy.md",       "gdpr-policy-v1"),
    ("employee_handbook.txt", "employee-handbook-v3"),
    ("compliance_api.json",   "compliance-api-spec-v2"),
]


async def main():
    print(f"Ingesting compliance corpus → namespace='{NAMESPACE}'\n")
    total_chunks = 0

    for filename, document_id in FILES:
        path = CORPUS_DIR / filename
        if not path.exists():
            print(f"[skip] {filename} not found — run generate_compliance_corpus.py first")
            continue

        print(f"[ingesting] {filename} (document_id={document_id})")
        metrics = await ingestion_pipeline(
            input_file_path=str(path),
            document_id=document_id,
            namespace=NAMESPACE,
        )
        print(f"  chunks={metrics['total_chunks']} "
              f"time={metrics['total_time_seconds']}s "
              f"throughput={metrics['throughput_chunks_per_second']} chunks/s")
        total_chunks += metrics['total_chunks']

    print(f"\nDone. Total chunks ingested: {total_chunks}")
    print(f"Query with namespace='{NAMESPACE}' in /search")


if __name__ == "__main__":
    asyncio.run(main())