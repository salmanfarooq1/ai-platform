import json

import pytest

from scripts.showcase import m0


@pytest.mark.parametrize("missing", ["state", "manifest.json", "keys.env", "manifest incomplete", "keys incomplete", "SHOWCASE_FIXTURE_KEY", "MIGRATION_DATABASE_URL"])
def test_missing_prerequisite_reports_recovery(tmp_path, monkeypatch, capsys, missing):
    state = tmp_path / "state"
    if missing != "state":
        state.mkdir(mode=0o700)
        for name, content in (("manifest.json", json.dumps({"tenant_id": "tenant", "tenant_slug": "fixture"})),
                              ("keys.env", "\n".join(f"SHOWCASE_KEY_{name}=placeholder" for name in
                                                    ("CONSUMER", "AUDITOR", "AGENT_DEVELOPER")))):
            if name != missing:
                if (name == "manifest.json" and missing == "manifest incomplete") or (name == "keys.env" and missing == "keys incomplete"):
                    content = "{}" if name == "manifest.json" else "SHOWCASE_KEY_CONSUMER=placeholder"
                (state / name).write_text(content)
                (state / name).chmod(0o600)
    monkeypatch.setattr(m0, "STATE", state)
    for name in ("SHOWCASE_FIXTURE_KEY", "MIGRATION_DATABASE_URL"):
        if name == missing:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, "placeholder")

    assert m0.main() != 0
    output = capsys.readouterr().out.strip()
    assert len(output.splitlines()) == 1
    assert (missing.replace(" incomplete", ".json" if missing.startswith("manifest") else ".env")) in output
    assert "scripts/showcase/setup_personas.sh" in output
    assert "README" in output
    assert "Error" not in output and str(tmp_path) not in output
