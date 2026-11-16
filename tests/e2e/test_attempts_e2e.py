"""Agent reasoning and verifier attempts have separate model records."""

from tests.e2e.test_search_flow import GDPR
from tests.jobs_helpers import post_ingest


def _extensions(row):
    import json

    return row["extensions"] if isinstance(row["extensions"], dict) else json.loads(row["extensions"])


async def test_agent_reasoning_and_verifier_each_recorded(client, pool, fake_llm, fake_embeddings):
    from api.routers.search import LLM_CONFIG

    fake_llm.agent_namespace = "legal"
    await post_ingest(client, params={"namespace": "legal"}, files={"file": ("gdpr.md", GDPR, "text/markdown")})
    response = await client.post("/v1/agent/query", json={
        "question": "What is the breach notification deadline?", "namespace": "legal",
        "enable_verifier": True,
    })
    assert response.status_code == 200, response.text
    rows = await pool.fetch(
        "SELECT action, resource, outcome, extensions FROM gateway_decisions WHERE request_id = $1 ORDER BY created_at, id",
        response.headers["X-Request-ID"],
    )
    model_rows = [row for row in rows if row["action"] == "model.invoke"]
    admissions = [row for row in model_rows if _extensions(row).get("model", {}).get("phase") == "admission"]
    attempts = [row for row in model_rows if _extensions(row).get("model", {}).get("phase") == "attempt"]
    assert {row["resource"] for row in admissions} >= {LLM_CONFIG["model"]}
    # This run also embeds the retrieval query and synthesizes the final answer; those are physical calls too.
    assert len(attempts) == 5
    assert fake_llm.kinds.count("agent_tool_call") + fake_llm.kinds.count("agent_final") == 2
    assert fake_llm.kinds.count("verifier") == 1
