"""Serve the real app on a given database with the fake LLM and fake embeddings behind their ports.

    DATABASE_URL=... REDIS_URL=... EMBED_MODEL=... poetry run python scripts/verify/serve_fakes.py --port 8011

Used by scripts/verify/stale_vectors.py, which restarts it with another EMBED_MODEL. The fake embeddings report the
configured EMBED_MODEL as their model, exactly like the real adapter would. The product code has no fake switch:
the fakes are passed to `create_app(adapter_overrides=...)` here.
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8011)
    args = parser.parse_args()

    import uvicorn

    from api.main import create_app
    from tests.fakes import FakeEmbeddings, FakeLLM

    llm = FakeLLM()
    uvicorn.run(
        create_app(adapter_overrides={"llm": llm, "chat": llm, "embeddings": FakeEmbeddings()}),
        host="127.0.0.1", port=args.port, log_level="warning",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
