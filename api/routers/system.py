"""System metadata exposed to session-aware clients."""
from fastapi import APIRouter, Depends, Request

from api.auth import require_any_scope
from api.gateway_deps import gateway_context
from api.models.system import ModuleInfo, ModuleList
from core.identity.models import ALL_SCOPES, Scope
from core.modules import edition_for, module_metadata
from gateway import Action, ActionKind, EnforcementContext, require

router = APIRouter(tags=["system"])


@router.get("/system/modules", response_model=ModuleList)
async def get_modules(
    request: Request,
    _principal=Depends(require_any_scope(*(Scope(scope) for scope in sorted(ALL_SCOPES)))),
    ctx: EnforcementContext = Depends(gateway_context),
):
    """Return edition and module availability after identity and scope authorization."""
    await require(ctx, Action(ActionKind.SYSTEM_READ, resource="system/modules"))
    enabled = request.app.state.gateway_runtime.enabled_modules
    return ModuleList(
        edition=edition_for(enabled),
        deploy_shape=request.app.state.deploy_shape,
        modules=[ModuleInfo(**item) for item in module_metadata(enabled)],
    )
