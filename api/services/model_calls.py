"""Resolve, admit and record every physical model request."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any, Literal, TypeVar, cast
from urllib.parse import urlparse

from api.services.model_limits import ModelLimitCheck, prepare_attempt, release_attempt
from config import completion_fallbacks_for_mode
from core.settings import Settings
from gateway import Action, ActionKind, Decision, EnforcementContext, GatewayDenied, enforce
from gateway.types import ModelLimitOutcome
from ports import Adapters
from ports.cache import CacheUnavailable
from ports.embeddings import EmbeddingDimensionMismatch, EmbeddingPort, Embeddings
from ports.errors import ModelDigestMismatch, ModelHostNotAllowed, ResidencyUnknown, UnknownModel, UnpricedModel
from ports.llm import LLMPort, ProviderCallError, ProviderRateLimitError
from ports.model_limits import ModelLimitStore
from ports.models import ModelCatalog, ModelUse, ResolvedModel

logger = logging.getLogger("api.services.model_calls")
T = TypeVar("T")
_CATALOG_FAILURES = (UnknownModel, ModelDigestMismatch, ModelHostNotAllowed, UnpricedModel, ResidencyUnknown)
_TIMEOUT_TYPES = {"Timeout", "APITimeoutError", "ConnectTimeout", "TimeoutError"}


class ModelCallFailed(RuntimeError):
    """Sanitized provider failure suitable for a client response."""

    def __init__(
        self, alias: str, category: str, *, expected_dim: int | None = None, returned_dim: int | None = None,
    ) -> None:
        self.alias = alias
        self.category = category
        self.expected_dim = expected_dim
        self.returned_dim = returned_dim
        super().__init__(f"{alias} failed ({category})")


def embedding_provenance(model: ResolvedModel) -> str:
    """Stable identity for vectors, derived from the exact resolved route used to make them."""
    identity_value = model.identity.digest or model.identity.provider_model_id
    if identity_value is None:
        raise RuntimeError("resolved embedding identity is incomplete")
    return f"{model.identity.alias}@{identity_value}"


class _ResolvedFailure(Exception):
    def __init__(self, resolved: ResolvedModel, cause: Exception) -> None:
        self.resolved = resolved
        self.cause = cause
        super().__init__("provider call failed")


class ModelCaller:
    """The sole request-path owner of model alias admission, retries and fallback."""

    def __init__(
        self,
        catalog: ModelCatalog,
        provider: LLMPort | EmbeddingPort,
        model_limits: ModelLimitStore,
        *,
        settings: Settings,
        allowed_hosts: Sequence[str] = (),
        completion_fallbacks: Sequence[str] = (),
        embedding_fallbacks: Sequence[str] = (),
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.catalog = catalog
        self.provider = provider
        self.allowed_hosts = frozenset(host.lower() for host in allowed_hosts)
        self.completion_fallbacks = tuple(completion_fallbacks)
        self.embedding_fallbacks = tuple(embedding_fallbacks)
        self._sleep = sleep
        self.settings = settings
        self.model_limits = model_limits

    @staticmethod
    def _warn_limit_store(
        operation: str, ctx: EnforcementContext, *, fingerprint: str | None = None, tenant_id: str | None = None,
    ) -> None:
        logger.warning(
            "model limit store unavailable: operation=%s fingerprint=%s tenant_id=%s execution_id=%s",
            operation, fingerprint or "-", tenant_id or "-", ctx.execution_id or "-",
        )

    async def _decide(
        self,
        ctx: EnforcementContext,
        alias: str,
        use: ModelUse,
        phase: Literal["admission", "attempt"],
        *,
        estimated_tokens: int | None,
        input_text: str | None,
        input_origin: Literal["caller", "platform"],
        role: Literal["primary", "verifier"],
    ) -> tuple[Decision, ResolvedModel | None, ModelLimitCheck]:
        resolved: ResolvedModel | None = None
        failure: Exception | None = None
        limit_check = ModelLimitCheck(None)
        try:
            resolved = await self.catalog.resolve(alias, use=use)
            if resolved.identity.source == "hosted":
                host = resolved.route.host or urlparse(resolved.route.endpoint).hostname
                if host is None or host.lower() not in self.allowed_hosts:
                    failure = ModelHostNotAllowed("model endpoint host is not in MODEL_ALLOWED_HOSTS")
        except _CATALOG_FAILURES as exc:
            failure = exc

        if phase == "attempt" and resolved is not None and failure is None:
            if ctx.principal is None:
                raise RuntimeError("model attempt requires an authenticated principal")
            try:
                limit_check = await prepare_attempt(self.model_limits, ctx.principal.tenant_id, resolved)
            except CacheUnavailable:
                limit_check = ModelLimitCheck(ModelLimitOutcome.DEPENDENCY_UNAVAILABLE)

        decision = await enforce(ctx, Action(
            ActionKind.MODEL_INVOKE, alias, estimated_tokens=estimated_tokens,
            input_text=input_text, input_origin=input_origin,
            resolved_model=resolved if failure is None else None,
            model_failure=failure if isinstance(failure, _CATALOG_FAILURES) else None,
            model_role=role,
            model_phase=phase,
            model_limit_outcome=limit_check.outcome,
        ))
        if not decision.allowed and limit_check.lease_id is not None:
            try:
                await release_attempt(self.model_limits, limit_check)
            except CacheUnavailable:
                self._warn_limit_store(
                    "release_after_deny", ctx, fingerprint=limit_check.route_fingerprint,
                    tenant_id=str(limit_check.tenant_id) if limit_check.tenant_id else None,
                )
        return decision, resolved, limit_check

    async def admit(
        self,
        ctx: EnforcementContext,
        alias: str,
        use: ModelUse,
        *,
        input_text: str | None = None,
        estimated_tokens: int | None = None,
        role: Literal["primary", "verifier"] = "primary",
    ) -> ResolvedModel:
        decision, resolved, _ = await self._decide(
            ctx, alias, use, "admission", estimated_tokens=estimated_tokens,
            input_text=input_text, input_origin="caller" if input_text is not None else "platform",
            role=role,
        )
        if not decision.allowed:
            raise GatewayDenied(decision)
        if resolved is None:
            raise RuntimeError("unreachable: allowed admission without a resolved model")
        return resolved

    async def _attempt(
        self,
        ctx: EnforcementContext,
        alias: str,
        use: ModelUse,
        invoke: Callable[[ResolvedModel], Awaitable[T]],
        *,
        estimated_tokens: int | None,
        input_text: str | None,
        input_origin: Literal["caller", "platform"],
        role: Literal["primary", "verifier"],
    ) -> tuple[T, ResolvedModel, ModelLimitCheck]:
        decision, resolved, limit_check = await self._decide(
            ctx, alias, use, "attempt", estimated_tokens=estimated_tokens,
            input_text=input_text, input_origin=input_origin,
            role=role,
        )
        if not decision.allowed:
            raise GatewayDenied(decision)
        if resolved is None:
            raise RuntimeError("unreachable: allowed attempt without a resolved model")
        try:
            result = await asyncio.wait_for(invoke(resolved), timeout=self.settings.model_call_timeout_seconds)
            if limit_check.route_fingerprint is not None:
                try:
                    await self.model_limits.record_success(limit_check.route_fingerprint)
                except CacheUnavailable:
                    self._warn_limit_store("record_success", ctx, fingerprint=limit_check.route_fingerprint)
            return result, resolved, limit_check
        except Exception as exc:
            if limit_check.route_fingerprint is not None:
                if self._is_rate_limit(exc) or isinstance(exc, EmbeddingDimensionMismatch):
                    if limit_check.half_open_trial:
                        try:
                            await self.model_limits.release_trial(limit_check.route_fingerprint)
                        except CacheUnavailable:
                            self._warn_limit_store("release_trial", ctx, fingerprint=limit_check.route_fingerprint)
                else:
                    try:
                        await self.model_limits.record_failure(limit_check.route_fingerprint)
                    except CacheUnavailable:
                        self._warn_limit_store("record_failure", ctx, fingerprint=limit_check.route_fingerprint)
            raise _ResolvedFailure(resolved, exc) from None
        finally:
            if limit_check.lease_id is not None:
                try:
                    await release_attempt(self.model_limits, limit_check)
                except CacheUnavailable:
                    # The lease's score expiry bounds a lost release when Valkey is unavailable.
                    self._warn_limit_store(
                        "release", ctx, fingerprint=limit_check.route_fingerprint,
                        tenant_id=str(limit_check.tenant_id) if limit_check.tenant_id else None,
                    )

    @staticmethod
    def _is_rate_limit(error: Exception) -> bool:
        return isinstance(error, ProviderRateLimitError) or getattr(error, "status_code", None) == 429

    @staticmethod
    def _retry_after(error: Exception, backoff: float) -> float:
        value: Any = getattr(error, "retry_after", None)
        if value is None:
            response = getattr(error, "response", None)
            headers = getattr(response, "headers", None)
            if headers is not None:
                value = headers.get("Retry-After")
        if value is None:
            return min(2.0, backoff)
        try:
            retry = float(value)
        except (TypeError, ValueError):
            retry = backoff
        return min(2.0, max(backoff, retry))

    @staticmethod
    def _category(error: Exception) -> str:
        if isinstance(error, EmbeddingDimensionMismatch):
            return "dimension_mismatch"
        if isinstance(error, ProviderRateLimitError) or getattr(error, "status_code", None) == 429:
            return "rate_limited"
        if isinstance(error, (TimeoutError, asyncio.TimeoutError)) or type(error).__name__ in _TIMEOUT_TYPES:
            return "timeout"
        if isinstance(error, ProviderCallError) and error.failure_type in _TIMEOUT_TYPES:
            return "timeout"
        return "provider_error"

    async def _run_aliases(
        self,
        ctx: EnforcementContext,
        aliases: Sequence[tuple[str, ModelUse]],
        invoke: Callable[[ResolvedModel], Awaitable[T]],
        *,
        estimated_tokens: int | None,
        input_text: str | None,
        input_origin: Literal["caller", "platform"],
        role: Literal["primary", "verifier"] = "primary",
    ) -> T:
        last: Exception | None = None
        last_breaker_deny: GatewayDenied | None = None
        last_alias = aliases[0][0]
        last_model: ResolvedModel | None = None
        for alias, use in aliases:
            last_alias = alias
            waited = 0.0
            for attempt in range(3):
                try:
                    result, last_model, _ = await self._attempt(
                        ctx, alias, use, invoke, estimated_tokens=estimated_tokens,
                        input_text=input_text, input_origin=input_origin,
                        role=role,
                    )
                    return result
                except GatewayDenied as denied:
                    if denied.decision.reason == "model_breaker_open":
                        last_breaker_deny = denied
                        break
                    raise
                except _ResolvedFailure as failed:
                    last_model = failed.resolved
                    exc = failed.cause
                    last = exc
                    if self._is_rate_limit(exc) and attempt < 2:
                        delay = min(self._retry_after(exc, 0.25 * (2 ** attempt)), 2.0 - waited)
                        await self._sleep(delay)
                        waited += delay
                        continue
                    break
            # Every failed alias exhausts independently; the next configured fallback gets its own decision.
        if last is not None:
            category = self._category(last)
            provider = last_model.identity.provider if last_model is not None else "unknown"
            safe_failure = ModelCallFailed(
                last_alias, category,
                expected_dim=last.expected_dim if isinstance(last, EmbeddingDimensionMismatch) else None,
                returned_dim=last.returned_dim if isinstance(last, EmbeddingDimensionMismatch) else None,
            )
            if isinstance(last, EmbeddingDimensionMismatch) and last_model is not None:
                self._log_dimension_refusal(last_alias, last_model, ctx, last)
                raise safe_failure from None
            logger.error(
                "model call failed: alias=%s provider=%s phase=attempt execution_id=%s category=%s cause=%s operation=%s",
                last_alias, provider, ctx.execution_id, category, type(last).__name__,
                getattr(last, "operation", "provider.request"),
            )
            raise safe_failure from None
        if last_breaker_deny is not None:
            raise last_breaker_deny
        raise RuntimeError("model call did not produce a result")

    @staticmethod
    def _log_dimension_refusal(
        alias: str, resolved: ResolvedModel, ctx: EnforcementContext, error: EmbeddingDimensionMismatch,
    ) -> None:
        logger.error(
            "embedding provider refused: model=%s provider=%s phase=attempt execution_id=%s "
            "category=dimension_mismatch cause=%s expected_width=%s returned_width=%s",
            alias, resolved.identity.provider, ctx.execution_id, type(error).__name__,
            error.expected_dim, error.returned_dim,
        )

    async def complete(
        self,
        ctx: EnforcementContext,
        alias: str,
        messages: Sequence[Mapping[str, Any]],
        *,
        max_tokens: int,
        estimated_tokens: int | None = None,
        input_text: str | None = None,
        input_origin: Literal["caller", "platform"] = "platform",
        response_format: Any = None,
        fallbacks: Sequence[str] | None = None,
    ) -> Any:
        aliases = ((alias, ModelUse.COMPLETION), *((target, ModelUse.COMPLETION)
                   for target in (self.completion_fallbacks if fallbacks is None else fallbacks)))

        async def invoke(model: ResolvedModel) -> Any:
            return await cast(LLMPort, self.provider).complete_resolved(
                model, messages, max_tokens=max_tokens, response_format=response_format,
            )

        return await self._run_aliases(ctx, aliases, invoke, estimated_tokens=estimated_tokens,
                                       input_text=input_text, input_origin=input_origin)

    async def chat(
        self,
        ctx: EnforcementContext,
        alias: str,
        messages: Any,
        invoke: Callable[[ResolvedModel, Any], Awaitable[T]],
        *,
        estimated_tokens: int | None = None,
        input_text: str | None = None,
        input_origin: Literal["caller", "platform"] = "caller",
        role: Literal["primary", "verifier"] = "primary",
    ) -> T:
        async def call(model: ResolvedModel) -> T:
            return await invoke(model, messages)

        return await self._run_aliases(ctx, ((alias, ModelUse.CHAT),), call,
                                       estimated_tokens=estimated_tokens, input_text=input_text,
                                       input_origin=input_origin, role=role)

    async def embed(
        self,
        ctx: EnforcementContext,
        alias: str,
        texts: list[str],
        *,
        estimated_tokens: int | None = None,
        input_text: str | None = None,
        input_origin: Literal["caller", "platform"] = "caller",
        fallbacks: Sequence[str] | None = None,
    ) -> Any:
        aliases = tuple((target, ModelUse.EMBEDDING)
                        for target in (alias, *(self.embedding_fallbacks if fallbacks is None else fallbacks)))

        async def invoke(model: ResolvedModel) -> Any:
            result = await cast(EmbeddingPort, self.provider).embed_resolved(model, texts)
            return Embeddings(
                vectors=result.vectors, model=embedding_provenance(model), dim=result.dim,
                route_fingerprint=result.route_fingerprint,
            )

        return await self._run_aliases(ctx, aliases, invoke, estimated_tokens=estimated_tokens,
                                       input_text=input_text, input_origin=input_origin)


def build_model_caller(adapters: Adapters, settings: Settings, provider: LLMPort | EmbeddingPort) -> ModelCaller:
    """Create the request's caller with its process catalog and configured routing limits."""
    return ModelCaller(
        adapters.model_catalog, provider, adapters.model_limits, settings=settings,
        allowed_hosts=settings.model_allowed_host_list,
        completion_fallbacks=completion_fallbacks_for_mode(settings.mode),
        embedding_fallbacks=settings.embed_fallbacks,
    )
