"""Typed vocabulary of the gateway: actions, decisions and the per-request enforcement context."""
import hashlib
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any
from uuid import UUID

from core.identity.models import Principal
from ports import CachePort, DecisionSink, EventBus

if TYPE_CHECKING:
    from gateway.boundary import ExecutionBoundary


class ActionKind(str, Enum):
    KB_READ = "kb.read"
    KB_WRITE = "kb.write"
    MODEL_INVOKE = "model.invoke"
    TOOL_CALL = "tool.call"
    AGENT_RUN = "agent.run"
    FEEDBACK_WRITE = "feedback.write"
    ANALYTICS_READ = "analytics.read"
    AUDIT_READ = "audit.read"
    SYSTEM_READ = "system.read"


@dataclass(frozen=True)
class Action:
    """One thing a caller wants to do.

    `resource` is a KB slug, a model id or a tool name (None when the action has no single resource).
    `input_text` is what the input guardrails read and what `input_hash` is computed from; it is never
    stored, logged or shown in `repr`. `rate` and `budget` mark the entry actions that count against the
    per-principal rate limit and the per-tenant daily token budget (internal calls inside an agent run do
    not, exactly as the middleware only counted whole requests).
    """

    kind: ActionKind
    resource: str | None = None
    estimated_tokens: int | None = None
    input_text: str | None = field(default=None, repr=False, compare=False)
    rate: bool = False
    budget: bool = False
    # What a tool call passes to the tool. Checked against the policy's `tool_arguments` schema. Like `input_text`
    # it is never stored, logged or shown in `repr`: a deny records the reason code only.
    arguments: Mapping[str, Any] | None = field(default=None, repr=False, compare=False)

    @property
    def input_hash(self) -> str | None:
        if self.input_text is None:
            return None
        return hashlib.sha256(self.input_text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Decision:
    """The outcome of `enforce()`. `reason` is a stable code; `message` is the text a caller may see."""

    allowed: bool
    stage: str
    reason: str
    policy_version: int | None = None
    message: str = ""
    headers: Mapping[str, str] = field(default_factory=dict)


ALLOW_REASON = "allowed"


class GatewayDenied(Exception):
    """Raised by `require()` when `enforce()` denies."""

    def __init__(self, decision: Decision) -> None:
        super().__init__(f"{decision.stage}: {decision.reason}")
        self.decision = decision


class DependencyUnavailable(Exception):
    """A dependency a stage needs (Redis) failed. The stage turns it into a deny, never an allow."""


Recorder = Callable[["EnforcementContext", Action, Decision], Awaitable[None]]


@dataclass
class GatewayRuntime:
    """Process-wide handles the gateway needs: the (app-role) pool, the cache port (rate limit and budget
    counters) and the event bus that gets one `platform.gateway.decision.v1` event per recorded decision."""

    pool: Any
    cache: CachePort
    decisions: DecisionSink
    enabled_modules: frozenset[str]
    events: EventBus | None = None


@dataclass
class EnforcementContext:
    """Per-request context. The boundary is fixed at request start; the counters live for the request."""

    principal: Principal | None
    request_id: str
    trace_id: str
    boundary: "ExecutionBoundary"
    runtime: GatewayRuntime
    # Headers a stage wants on the eventual response (rate limit remaining). FinOps applies them.
    headers: dict[str, str] = field(default_factory=dict)
    tool_calls: int = 0
    denials: list[Decision] = field(default_factory=list)
    halted: str | None = None  # set by the agent when a denial ends its loop
    # The run this request belongs to (ADR-0009). Written into every decision the run causes.
    execution_id: UUID | None = None
    required_module: str | None = None
