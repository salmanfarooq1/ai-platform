"""Contract suite for lineage emitters; current no-op counts dropped events only."""
from uuid import uuid4

import pytest

from adapters.noop_modules import DroppingLineageEmitter
from ports import CloudEvent, LineageEmitter


@pytest.fixture(params=["disabled"])
def lineage_emitter(request) -> LineageEmitter:
    del request
    return DroppingLineageEmitter()


async def test_disabled_emitter_drops_and_counts_without_publication(lineage_emitter: LineageEmitter) -> None:
    event = CloudEvent(type="platform.lineage.test.v1", source="/test", subject=None, tenantid=str(uuid4()), data={})
    await lineage_emitter.emit(event)
    assert isinstance(lineage_emitter, DroppingLineageEmitter)
    assert lineage_emitter.dropped_count == 1
