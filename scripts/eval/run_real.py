#!/usr/bin/env python3
"""The manual eval run with real providers (Sprint 008). It spends money and is never run in CI.

    REAL_EVAL=1 poetry run python scripts/eval/run_real.py

It runs the same fixed corpus and questions as the gate (`suite.py`), but with the real embedding model and the real
LLM from `.env.local` (LLM_MODEL, EMBED_MODEL and the provider key environment variables, which are never printed).
The retrieval store stays in memory, so nothing is written to a database. It prints the scores and the baseline next to
each other. It does not gate, and it does not record: a real model scores differently from the fake one, so the
stored baseline is not a target for it.

It refuses to start unless REAL_EVAL=1 is set, so a script that imports or lists it cannot spend by accident.
"""
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))  # the repository root, when run as a script


async def main() -> int:
    if os.environ.get("REAL_EVAL") != "1":
        print("refused: this run calls real providers and spends money. Set REAL_EVAL=1 to run it.", file=sys.stderr)
        return 2
    import config
    from adapters.litellm_embeddings import LitellmEmbeddings
    from adapters.litellm_llm import LitellmLLM
    from core.settings import get_settings
    from scripts.eval.suite import NAMESPACE, SUITE, TENANT, run_suite
    from tests.fakes import FakeKnowledgeStore

    settings = get_settings()
    print(f"suite {SUITE}: LLM {settings.llm_model}, embeddings {settings.embed_model}")
    store = FakeKnowledgeStore(kbs={TENANT: {NAMESPACE: "fixed eval corpus"}})
    embeddings = LitellmEmbeddings(str(settings.embed_model), settings.embedding_dim, settings.embed_fallbacks)
    scores = await run_suite(store, embeddings, LitellmLLM(config.MODEL_PRICING))
    baseline = json.loads((Path(__file__).resolve().parent / "baseline.json").read_text(encoding="utf-8"))["scores"]
    for metric, score in scores.items():
        print(f"  {metric}: {score} (fake baseline {baseline.get(metric)})")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
