"""
scripts/test_deepeval_hybrid_smoke.py
======================================
1-question end-to-end smoke test:
- Local generation using Ollama (qwen2.5)
- Cloud evaluation using Gemini (gemini-3.5-flash)
"""

import asyncio
import json
import sys
import time
import urllib.request
import urllib.error

from pathlib import Path

# DeepEval uses asyncio internally, setting telemetry opt out avoids event loop conflicts
import os
os.environ["DEEPEVAL_TELEMETRY_OPT_OUT"] = "YES"

sys.path.insert(0, str(Path(__file__).parent.parent))

from deepeval.models.base_model import DeepEvalBaseLLM
from deepeval.metrics import FaithfulnessMetric, ContextualPrecisionMetric
from deepeval.test_case import LLMTestCase

from core.database.pool import create_pool
from api.services.cache import embed_query
from api.services.retriever import retrieve, RetrieverConfig
from api.services.llm import generate_with_citations
from config import LLM_CONFIG

# Force Gemini-3.5-Flash for generation in the RAG pipeline
LLM_CONFIG["model"] = "gemini/gemini-3.5-flash"


# Resolve Gemini API Key
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
if not GEMINI_KEY:
    GEMINI_KEY = LLM_CONFIG.get("gemini_key", "") or os.environ.get("GOOGLE_API_KEY", "")

if not GEMINI_KEY:
    # Try parsing .env.local manually
    env_local = Path("C:/Users/salman.farooq/.gemini/antigravity/brain/6ff6280b-9166-4b94-bd57-47c276fb42bb/../../../../config") # global
    # Actually just read from our workspace .env.local
    try:
        lines = Path(".env.local").read_text().splitlines()
        for line in lines:
            if line.startswith("GEMINI_API_KEY"):
                GEMINI_KEY = line.split("=")[1].replace('"', '').strip()
                os.environ["GEMINI_API_KEY"] = GEMINI_KEY
                os.environ["GOOGLE_API_KEY"] = GEMINI_KEY
    except Exception:
        pass

class GeminiJudge(DeepEvalBaseLLM):
    def __init__(self, model_name: str, api_key: str):
        self.model_name = model_name
        self.api_key = api_key
        super().__init__(model_name)

    def load_model(self):
        return self.model_name

    def generate(self, prompt: str, schema=None) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent?key={self.api_key}"
        contents = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.0}
        }
        if schema is not None:
            contents["generationConfig"]["responseMimeType"] = "application/json"

        req = urllib.request.Request(
            url,
            data=json.dumps(contents).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req) as response:
                    res = json.loads(response.read().decode("utf-8"))
                    text = res["candidates"][0]["content"]["parts"][0]["text"]
                    print(f"    [gemini-judge raw output]: {text}")
                    return text
            except urllib.error.HTTPError as e:
                try:
                    body = e.read().decode("utf-8")
                except Exception:
                    body = str(e)
                print(f"    [gemini-judge] HTTP Error {e.code}: {body[:150]}")
                time.sleep(10.0)
            except Exception as e:
                print(f"    [gemini-judge] Error: {e}")
                time.sleep(10.0)
        return "{}" if schema is not None else ""



    async def a_generate(self, prompt: str, schema=None) -> str:
        return self.generate(prompt, schema)

    def get_model_name(self) -> str:
        return self.model_name


async def main():
    print("=== Hybrid End-to-End Smoke Test ===")
    print(f"Gen Model (Gemini)  : {LLM_CONFIG['model']}")
    print(f"Judge Model (Gemini): gemini-2.5-pro")
    print(f"Gemini Key Present : {bool(GEMINI_KEY)}")


    if not GEMINI_KEY:
        print("ERROR: GEMINI_API_KEY is not set. Please set it in .env.local first.")
        return

    # 1. Run local retrieval and generation (Q1)
    pool = await create_pool()
    question = "What is the maximum fine for a serious GDPR violation?"
    ground_truth = "The maximum fine for a serious GDPR violation is 20 million euros or 4% of the company's total global annual turnover of the preceding financial year, whichever is higher."
    
    print("\n[Step 1] Retrieving and Generating locally...")
    embedding = await embed_query(question)
    
    config = RetrieverConfig(top_k=5, mode="hybrid", rerank=False)
    chunks = await retrieve(
        pool=pool,
        query=question,
        query_embedding=embedding,
        namespace="legal",
        config=config,
    )
    
    print(f"  Retrieved {len(chunks)} chunks.")
    
    db_chunks = [
        {
            "document_id": c["document_id"],
            "source_filename": c.get("source_filename") or "unknown",
            "text": c["content"],
            "score": c.get("rrf_score", 0.0),
        }
        for c in chunks
    ]
    
    answer_obj, _ = await generate_with_citations(question, db_chunks)
    print(f"  Generated Answer: {answer_obj.answer}")
    
    await pool.close()

    # 2. Run DeepEval evaluation using Gemini
    print("\n[Step 2] Evaluating via cloud Gemini...")
    judge = GeminiJudge(model_name="gemini-2.5-pro", api_key=GEMINI_KEY)

    
    test_case = LLMTestCase(
        input=question,
        actual_output=answer_obj.answer,
        expected_output=ground_truth,
        retrieval_context=[c["content"] for c in chunks]
    )
    
    faithfulness = FaithfulnessMetric(threshold=0.5, model=judge, include_reason=True)
    precision = ContextualPrecisionMetric(threshold=0.5, model=judge, include_reason=True)
    
    print("  Measuring Faithfulness...")
    faithfulness.measure(test_case)
    print(f"  * Faithfulness Score: {faithfulness.score:.2f}")
    print(f"    Reason: {faithfulness.reason}")
    
    print("  Measuring Contextual Precision...")
    precision.measure(test_case)
    print(f"  * Precision Score: {precision.score:.2f}")
    print(f"    Reason: {precision.reason}")
    
    print("\nSmoke test successfully completed.")

if __name__ == "__main__":
    asyncio.run(main())
