"""Response models of the trust endpoints (Sprint 008): receipts, receipt verification and the trust summary."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from api.models.console import DecisionDetail


class ReceiptChain(BaseModel):
    """Where the decision sits in the tenant's hash chain."""

    prev_hash: str
    row_hash: str
    position: int


class Receipt(BaseModel):
    """A signed receipt. `canonical` is the exact text that was signed: the canonical JSON of the chain link and the
    decision record. It holds no input text, only the SHA-256 that is on the decision."""

    decision: DecisionDetail
    chain: ReceiptChain
    signature: str = Field(description="Base64 Ed25519 signature over the UTF-8 bytes of `canonical`")
    key_id: str
    alg: Literal["Ed25519"]
    canonical: str


class ReceiptKey(BaseModel):
    key_id: str
    alg: Literal["Ed25519"]
    public_key: str = Field(description="Base64 of the 32 raw public key bytes")
    active: bool


class VerifyCheck(BaseModel):
    name: str
    ok: bool
    detail: str


class VerifyResult(BaseModel):
    valid: bool
    checks: list[VerifyCheck]


class EvalGate(BaseModel):
    """The latest run of the eval regression gate."""

    status: Literal["passed", "failed"]
    baseline: dict[str, float]
    latest: dict[str, float]
    run_at: datetime


class TrustSummary(BaseModel):
    retention_days: int
    retention_is_default: bool
    oldest_decision_at: datetime | None
    last_purge_at: datetime | None
    eval_gate: EvalGate | None
    # The last runs of the gate, newest first (at most 20). Empty when the gate has never been recorded.
    eval_history: list[EvalGate]
    metrics_public: bool
    # Where Grafana is, when the observability profile is running and GRAFANA_URL is set. Otherwise None.
    grafana_url: str | None
