import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_hosted_smoke_skips_without_credentials():
    env = {key: value for key, value in os.environ.items() if not key.endswith("_CREDENTIAL_REF")}
    for key in ("AZURE_OPENAI_CREDENTIAL_REF", "BEDROCK_CREDENTIAL_REF", "ANTHROPIC_CREDENTIAL_REF",
                "GEMINI_CREDENTIAL_REF", "GROQ_CREDENTIAL_REF", "OPENAI_COMPATIBLE_CREDENTIAL_REF"):
        env.pop(key, None)
    result = subprocess.run([str(ROOT / "scripts/verify/hosted.sh")], cwd=ROOT, env=env,
                            capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert "SKIP" in result.stdout
    assert "PASS" not in result.stdout + result.stderr


def test_no_nightly_model_workflow():
    assert not (ROOT / ".github/workflows/nightly-models.yml").exists()
