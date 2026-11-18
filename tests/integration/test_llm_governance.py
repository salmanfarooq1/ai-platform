from unittest.mock import AsyncMock

import pytest

from api.services.llm import generate_with_citations
from api.services.model_calls import ModelCaller
from core.settings import Settings
from gateway import GatewayDenied
from ports.llm import Completion, ProviderRateLimitError
from ports.models import ModelUse
from tests.fakes import FakeCatalog, FakeDecisionSink, FakeModelLimitStore, fake_resolved_model
from tests.integration.test_gateway import context_for, decision_rows, publish

pytestmark = pytest.mark.integration


async def test_citation_generation_records_every_attempt(database_url, db_pool, owner_pool, tenant_a):
    alias = "ollama/test"
    resolved = fake_resolved_model(alias, ModelUse.COMPLETION)
    provider = AsyncMock()
    provider.complete_resolved.side_effect = [ProviderRateLimitError(), Completion(
        text='{"answer":"answer","confidence":0.8,"citations":[{"document_id":"x","chunk_index":0,"relevance_score":0,"excerpt":""}]}',
        model=alias, tokens_in=12, tokens_out=3, cost_usd=0.1)]
    caller = ModelCaller(FakeCatalog({alias: resolved}), provider, FakeModelLimitStore(),
                         settings=Settings(), sleep=AsyncMock())
    chunks = [{"document_id": "a", "text": "context"}]
    ctx = await context_for(db_pool, tenant_a)
    answer, usage = await generate_with_citations(provider, "q", chunks, model=alias, caller=caller, ctx=ctx)
    assert answer.citations[0].document_id == "a"
    assert (usage["prompt_tokens"], usage["completion_tokens"], usage["total_cost"]) == (12, 3, 0.1)
    assert provider.complete_resolved.await_count == 2
    assert len(await decision_rows(owner_pool, tenant_a)) == 2
    publish(database_url, tenant_a, {"allowed_kbs": "*", "allowed_tools": "*", "allowed_models": []})
    denied = await context_for(db_pool, tenant_a)
    provider.complete_resolved.reset_mock()
    with pytest.raises(GatewayDenied):
        await generate_with_citations(provider, "q", chunks, model=alias, caller=caller, ctx=denied)
    provider.complete_resolved.assert_not_awaited()
    publish(database_url, tenant_a, {"allowed_kbs": "*", "allowed_tools": "*", "allowed_models": "*"})
    failed = await context_for(db_pool, tenant_a)
    sink = FakeDecisionSink()
    sink.fail = True
    failed.runtime.decisions = sink
    with pytest.raises(GatewayDenied) as exc:
        await generate_with_citations(provider, "q", chunks, model=alias, caller=caller, ctx=failed)
    assert exc.value.decision.reason == "decision_unrecorded"
    provider.complete_resolved.assert_not_awaited()
