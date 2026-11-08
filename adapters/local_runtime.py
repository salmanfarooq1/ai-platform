"""Build the in-process or sandboxed runtime used by a worker to execute agent runs."""
from adapters.inprocess_runtime import InProcessAgentRuntime
from adapters.openshell_runtime import OpenShellAgentRuntime, SandboxConfig
from core.database.tenant import DbPool
from core.settings import Settings
from ports import AgentRuntime, EgressRule, Runner, SandboxDriver, SandboxLimits


def build_local_runtime(
    settings: Settings, *, runner: Runner | None, pool: DbPool, sandbox_driver: SandboxDriver | None = None,
) -> AgentRuntime:
    """Build the runtime that executes an agent run inside the worker that claims it."""
    if settings.agent_runtime != "openshell":
        return InProcessAgentRuntime(runner)
    from adapters.openshell_driver import OpenShellSdkDriver

    egress = settings.sandbox_egress()
    if egress is None:
        raise ValueError("SANDBOX_GATEWAY_URL is not a usable URL")
    driver = sandbox_driver or OpenShellSdkDriver(
        endpoint=settings.openshell_endpoint, workspace=settings.openshell_workspace, image=settings.openshell_image,
    )
    return OpenShellAgentRuntime(driver, pool, SandboxConfig(
        gateway_url=str(settings.sandbox_gateway_url), egress=EgressRule(*egress),
        limits=SandboxLimits(settings.sandbox_cpu, settings.sandbox_memory, settings.sandbox_wall_seconds),
        work_dir=settings.sandbox_work_dir, read_only=settings.sandbox_read_only,
        network_binaries=settings.sandbox_network_binaries_list,
    ))
