"""Contract suite for DataAccess, currently implemented by the disabled-module adapter."""
from uuid import uuid4

import pytest

from adapters.noop_modules import DisabledDataAccess
from ports import DataAccess, ModuleDisabled


@pytest.fixture(params=["disabled"])
def data_access(request) -> DataAccess:
    del request
    return DisabledDataAccess()


async def test_disabled_data_access_fails_closed(data_access: DataAccess) -> None:
    with pytest.raises(ModuleDisabled):
        await data_access.read(tenant_id=uuid4(), resource="warehouse/catalog")


def test_result_rows_are_owned_and_immutable() -> None:
    from ports import DataResult

    row = {"nested": {"values": [1, "two"]}}
    result = DataResult(columns=("nested",), rows=(row,))
    row["nested"]["values"].append("later")
    assert result.rows[0]["nested"]["values"] == (1, "two")
    with pytest.raises(TypeError):
        result.rows[0]["another"] = "value"  # type: ignore[index]
