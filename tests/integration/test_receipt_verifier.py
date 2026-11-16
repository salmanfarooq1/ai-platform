import base64
import importlib.util
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("receipt_verifier_wp4", ROOT / "scripts/verify/receipt.py")
assert SPEC is not None and SPEC.loader is not None
VERIFIER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFIER)


def _receipt(private: Ed25519PrivateKey, version: int, extensions: dict) -> dict:
    tenant_id, decision_id = str(uuid4()), str(uuid4())
    created = datetime.now(timezone.utc).isoformat()
    decision = {
        "id": decision_id, "tenant": {"id": tenant_id}, "principal": {"id": str(uuid4())},
        "request_id": "receipt-test", "action": "model.invoke", "resource": "ollama/qwen", "outcome": "allow",
        "stage": "allow", "reason": "allowed", "policy_version": 1, "input_sha256": "a" * 64,
        "execution_id": None, "created_at": created, "record_version": version, "extensions": extensions,
    }
    record = VERIFIER.decision_record(decision)
    previous = VERIFIER.genesis_hash(tenant_id)
    row_hash = VERIFIER.row_hash_of(record, previous)
    chain = {"prev_hash": previous, "row_hash": row_hash, "position": 1}
    canonical = VERIFIER.canonical_json({"chain": chain, "decision": record})
    public = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return {
        "alg": "Ed25519", "key_id": VERIFIER.key_id_of(public), "canonical": canonical,
        "signature": base64.b64encode(private.sign(canonical.encode())).decode(), "decision": decision, "chain": chain,
    }


def test_model_and_stages_extensions_verify(tmp_path):
    private = Ed25519PrivateKey.generate()
    model = {
        "name": "ollama/qwen", "provider": "ollama", "source": "local", "digest": "sha256:" + "a" * 64,
        "processing_scope": "eu", "region": "eu", "route": "sha256:" + "b" * 64, "phase": "admission",
    }
    stages = [
        {"stage": name, "status": "passed" if name in {"principal", "module", "boundary", "model", "policy"} else "skipped",
         "reason": None, "duration_us": 1}
        for name in ("principal", "module", "boundary", "model", "policy", "guardrails", "rate", "budget", "cost")
    ]
    public = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    for index, receipt in enumerate((_receipt(private, 2, {"model": model, "stages": stages}), _receipt(private, 1, {}))):
        path = tmp_path / f"receipt-{index}.json"
        path.write_text(json.dumps(receipt), encoding="utf-8")
        run = subprocess.run(
            [sys.executable, str(ROOT / "scripts/verify/receipt.py"), "receipt", str(path),
             "--public-key", base64.b64encode(public).decode()], text=True, capture_output=True, check=False,
        )
        assert run.returncode == 0, run.stdout + run.stderr
        assert "VALID" in run.stdout
        if index == 0:
            assert "stages" in run.stdout and "principal: passed" in run.stdout
