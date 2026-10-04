"""Starting the real app with a superuser DATABASE_URL fails (acceptance A5), in every mode."""
import pytest
from asgi_lifespan import LifespanManager

from core.database.guard import UnsafeDatabaseRoleError


@pytest.mark.parametrize("mode", ["local", "public-preview", "prod"])
async def test_app_lifespan_fails_when_connected_as_a_superuser(platform_config, database_url, monkeypatch, mode):
    import api.main
    import core.database.pool

    monkeypatch.setitem(core.database.pool.DATABASE_CONFIG, "url", database_url)  # the owner role: a superuser
    monkeypatch.setattr(api.main.settings, "mode", mode)  # the guard is not mode-dependent
    application = api.main.create_app()

    with pytest.raises(UnsafeDatabaseRoleError, match="Row-level security does not apply"):
        async with LifespanManager(application):
            pytest.fail("the app must not finish starting")
