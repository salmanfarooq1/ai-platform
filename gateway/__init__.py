"""The gateway: one governance path (`enforce()`) for every model, tool and knowledge-base call.

A top-level package so it can split into its own service later. This module re-exports the public API only.
"""
from gateway.boundary import BoundaryWidenError, ExecutionBoundary, build_boundary
from gateway.context import build_context
from gateway.enforce import enforce, require
from gateway.guardrails import check_output
from gateway.policy import PolicyDocument, PolicyEngine, PolicyError, PythonPolicyEngine, load_active_policy
from gateway.types import (
    Action,
    ActionKind,
    Decision,
    DependencyUnavailable,
    EnforcementContext,
    GatewayDenied,
    GatewayRuntime,
)

__all__ = [
    "Action", "ActionKind", "BoundaryWidenError", "Decision", "DependencyUnavailable", "EnforcementContext",
    "ExecutionBoundary", "GatewayDenied", "GatewayRuntime", "PolicyDocument", "PolicyEngine", "PolicyError",
    "PythonPolicyEngine", "build_boundary", "build_context", "check_output", "enforce", "load_active_policy", "require",
]
