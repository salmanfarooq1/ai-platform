"""Signed receipts for decisions (Sprint 008, ADR-0012). All routes need `audit:read` and write a decision row.

`GET /receipts/{decision_id}` signs the decision with its chain link. A foreign id and a missing id give the same
404. A decision recorded before receipts existed (or a deny whose chain step failed) has no chain link: 409
`receipt_unavailable`. `GET /receipts/keys` lists the public keys, the active one first. `POST /receipts/verify` runs
the same checks as `scripts/verify/receipt.py`.
"""
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request

from api.auth import require_scope
from api.gateway_deps import gateway_context
from api.models.trust import Receipt, ReceiptChain, ReceiptKey, VerifyCheck, VerifyResult
from api.routers.console import fetch_decision_detail, get_db_pool
from core.database.tenant import DbPool, tenant_connection
from core.identity.models import Principal, Scope
from evidence.chain import compute_row_hash
from evidence.receipts import Keyring, record_of, sign_receipt, verify_receipt
from gateway import Action, ActionKind, EnforcementContext, require

router = APIRouter(tags=["receipts"])
logger = logging.getLogger("api.receipts")


def keyring_of(request: Request) -> Keyring:
    keyring: Keyring = request.app.state.receipt_keys
    return keyring


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Receipt not found")


@router.get("/receipts/keys", response_model=list[ReceiptKey])
async def list_receipt_keys(
    request: Request,
    principal: Principal = Depends(require_scope(Scope.AUDIT_READ)),
    ctx: EnforcementContext = Depends(gateway_context),
) -> list[ReceiptKey]:
    """The public keys receipts may be signed with. No secret is ever returned."""
    await require(ctx, Action(ActionKind.AUDIT_READ, resource="receipts"))
    return [
        ReceiptKey(key_id=k.key_id, alg="Ed25519", public_key=k.public_key, active=k.active)
        for k in keyring_of(request).public_keys()
    ]


@router.get("/receipts/{decision_id}", response_model=Receipt)
async def get_receipt(
    request: Request,
    decision_id: str,
    pool: DbPool = Depends(get_db_pool),
    principal: Principal = Depends(require_scope(Scope.AUDIT_READ)),
    ctx: EnforcementContext = Depends(gateway_context),
) -> Receipt:
    """The signed receipt of one decision of the caller's tenant."""
    await require(ctx, Action(ActionKind.AUDIT_READ, resource="receipts"))
    try:
        wanted = UUID(decision_id)
    except ValueError:
        raise _not_found() from None
    detail = await fetch_decision_detail(pool, principal.tenant_id, wanted)
    if detail is None:
        raise _not_found()
    async with tenant_connection(pool, principal.tenant_id) as conn:
        link = await conn.fetchrow(
            "SELECT chain_position, prev_hash, row_hash FROM gateway_decisions WHERE id = $1", wanted,
        )
    if link is None:
        raise _not_found()
    if link["row_hash"] is None or link["prev_hash"] is None or link["chain_position"] is None:
        raise HTTPException(status_code=409, detail={
            "error": "receipt_unavailable",
            "reason": "This decision has no chain link, so it cannot be signed. It was recorded before receipts existed.",
        })
    chain = {"prev_hash": link["prev_hash"], "row_hash": link["row_hash"], "position": int(link["chain_position"])}
    record = record_of(detail.model_dump(mode="json"))
    if compute_row_hash(record, chain["prev_hash"]) != chain["row_hash"]:
        # The stored row no longer hashes to its own row hash. Never sign that.
        logger.error("decision %s does not match its chain hash, receipt refused", wanted)
        raise HTTPException(status_code=409, detail={
            "error": "chain_mismatch", "reason": "The stored decision does not match its chain hash, so no receipt was signed.",
        })
    signed = sign_receipt(keyring_of(request), record, chain)
    return Receipt(decision=detail, chain=ReceiptChain(**chain), **signed)  # type: ignore[arg-type]


@router.post("/receipts/verify", response_model=VerifyResult)
async def verify_a_receipt(
    request: Request,
    receipt: Receipt,
    principal: Principal = Depends(require_scope(Scope.AUDIT_READ)),
    ctx: EnforcementContext = Depends(gateway_context),
) -> VerifyResult:
    """Run the receipt checks on a receipt the caller holds. It does not matter whose tenant it names: the checks
    use only the receipt and the public keys."""
    await require(ctx, Action(ActionKind.AUDIT_READ, resource="receipts"))
    checks = verify_receipt(receipt.model_dump(mode="json"), keyring_of(request).public_map())
    return VerifyResult(
        valid=all(c.ok for c in checks), checks=[VerifyCheck(name=c.name, ok=c.ok, detail=c.detail) for c in checks],
    )
