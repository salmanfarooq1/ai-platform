"""Parsing and validation for reviewed model and provider metadata files."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from ports.models import ModelUse

MODEL_FILES_ROOT = Path(__file__).resolve().parents[1]

PROVIDER_PREFIX_TO_KEY = {
    "azure": "azure-openai",
    "openai": "openai-compatible",
    "ollama": "ollama",
    "gemini": "gemini",
    "groq": "groq",
    "bedrock": "bedrock",
    "anthropic": "anthropic",
}


class ModelFileError(ValueError):
    """A model metadata file is invalid or incomplete."""


@dataclass(frozen=True)
class LockedModel:
    alias: str
    runtime: str
    digest: str
    licence: str
    source: str
    size_bytes: int
    use: tuple[ModelUse, ...]


@dataclass(frozen=True)
class ProviderEntry:
    key: str
    name: str
    trains_on_data: str
    retention: str
    processing_scopes: dict[str, dict[str, str]]
    storage_geography: str
    sources: tuple[str, ...]
    reviewed: str


def load_models_lock(path: str | Path | None = None) -> tuple[LockedModel, ...]:
    """Load a TOML lock, refusing malformed or duplicate aliases."""
    source_path = Path(path) if path is not None else MODEL_FILES_ROOT / "models.lock"
    try:
        payload = tomllib.loads(source_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ModelFileError(f"cannot read model lock: {exc}") from None
    if payload.get("version") != 1 or not isinstance(payload.get("model"), list):
        raise ModelFileError("model lock requires version 1 and [[model]] entries")
    result: list[LockedModel] = []
    seen: set[str] = set()
    for row in payload["model"]:
        if not isinstance(row, dict):
            raise ModelFileError("model lock entries must be tables")
        required = {"alias", "runtime", "digest", "licence", "source", "size_bytes", "use"}
        if set(row) != required:
            raise ModelFileError("model lock entry has missing or unknown fields")
        alias, runtime, digest = row["alias"], row["runtime"], row["digest"]
        if not all(isinstance(value, str) and value for value in (alias, runtime, digest, row["licence"], row["source"])):
            raise ModelFileError("model lock text fields must be non-empty strings")
        if re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None:
            raise ModelFileError(f"invalid digest for {alias}")
        if alias in seen:
            raise ModelFileError(f"duplicate model alias {alias}")
        seen.add(alias)
        uses = row["use"]
        if not isinstance(uses, list) or not uses:
            raise ModelFileError(f"model {alias} must list at least one use")
        try:
            parsed_uses = tuple(ModelUse(item) for item in uses)
        except (ValueError, TypeError):
            raise ModelFileError(f"invalid use for {alias}") from None
        if len(set(parsed_uses)) != len(parsed_uses):
            raise ModelFileError(f"duplicate use for {alias}")
        if not isinstance(row["size_bytes"], int) or row["size_bytes"] <= 0:
            raise ModelFileError(f"invalid size_bytes for {alias}")
        source_url = urlparse(row["source"])
        if source_url.scheme != "https" or not source_url.netloc:
            raise ModelFileError(f"source for {alias} must be an https URL")
        result.append(LockedModel(alias, runtime, digest, row["licence"], row["source"], row["size_bytes"], parsed_uses))
    return tuple(result)


def validate_lock_licences(models: tuple[LockedModel, ...], allowlist: set[str] | None = None) -> None:
    """Use the 011 supply-chain OSI SPDX allowlist for model licences."""
    if allowlist is None:
        allowlist = {
            line.strip()
            for line in (MODEL_FILES_ROOT / "scripts/supply_chain/osi-licences.txt").read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
    for model in models:
        if model.licence not in allowlist:
            raise ModelFileError(f"licence {model.licence!r} for {model.alias} is not in the OSI allowlist")


def load_provider_register(path: str | Path | None = None) -> dict[str, ProviderEntry]:
    """Load and validate the reviewed provider register."""
    source_path = Path(path) if path is not None else MODEL_FILES_ROOT / "providers.register.toml"
    try:
        payload = tomllib.loads(source_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ModelFileError(f"cannot read provider register: {exc}") from None
    providers = payload.get("provider")
    if payload.get("version") != 1 or not isinstance(providers, dict):
        raise ModelFileError("provider register requires version 1 and [provider.*] entries")
    result: dict[str, ProviderEntry] = {}
    for key, row in providers.items():
        if not isinstance(row, dict):
            raise ModelFileError(f"provider {key} must be a table")
        required = {"name", "trains_on_data", "retention", "processing_scopes", "storage_geography", "sources", "reviewed"}
        if set(row) != required:
            raise ModelFileError(f"provider {key} has missing or unknown fields")
        if row["trains_on_data"] not in {"yes", "no", "unknown"}:
            raise ModelFileError(f"provider {key} has invalid trains_on_data")
        scopes = row["processing_scopes"]
        if not isinstance(scopes, dict) or not scopes:
            raise ModelFileError(f"provider {key} requires described processing scopes")
        parsed_scopes: dict[str, dict[str, str]] = {}
        for scope, details in scopes.items():
            if not isinstance(scope, str) or not scope or not isinstance(details, dict):
                raise ModelFileError(f"provider {key} has an invalid processing scope")
            if set(details) not in ({"description"}, {"region", "description"}):
                raise ModelFileError(f"provider {key} scope {scope} has missing or unknown fields")
            description, region = details.get("description"), details.get("region")
            if not isinstance(description, str) or not description:
                raise ModelFileError(f"provider {key} scope {scope} requires a description")
            if region is not None and (not isinstance(region, str) or re.fullmatch(r"[a-z][a-z0-9-]*", region) is None):
                raise ModelFileError(f"provider {key} scope {scope} has an invalid region")
            if scope == "unknown" and region != "unknown":
                raise ModelFileError(f"provider {key} unknown scope must have region unknown")
            if scope == "local" and region is not None:
                raise ModelFileError(f"provider {key} local scope must not have a region")
            parsed_scopes[scope] = dict(details)
        sources = row["sources"]
        if not isinstance(sources, list) or not sources or any(
            not isinstance(url, str) or urlparse(url).scheme != "https" or not urlparse(url).netloc
            for url in sources
        ):
            raise ModelFileError(f"provider {key} sources must be https URLs")
        reviewed = row["reviewed"]
        try:
            date.fromisoformat(reviewed)
        except (TypeError, ValueError):
            raise ModelFileError(f"provider {key} reviewed must be an ISO date") from None
        for field in ("name", "retention", "storage_geography"):
            if not isinstance(row[field], str) or not row[field]:
                raise ModelFileError(f"provider {key} requires {field}")
        result[key] = ProviderEntry(key, row["name"], row["trains_on_data"], row["retention"], parsed_scopes, row["storage_geography"], tuple(sources), reviewed)
    return result


def configured_provider_prefixes(settings: object, completion_fallbacks: tuple[str, ...] = ()) -> set[str]:
    """Provider prefixes used by the selected and all mode defaults plus fallbacks."""
    aliases = [getattr(settings, "llm_model", None), getattr(settings, "embed_model", None)]
    aliases.extend(getattr(settings, "embed_fallbacks", []))
    aliases.extend(completion_fallbacks)
    aliases.append(getattr(settings, "verifier_model", None) or getattr(settings, "llm_model", None))
    keys = {str(alias).split("/", 1)[0] for alias in aliases if alias}
    return {PROVIDER_PREFIX_TO_KEY.get(key, key) for key in keys}


def require_registered_providers(settings: object, register: dict[str, ProviderEntry], completion_fallbacks: tuple[str, ...] = ()) -> None:
    missing = sorted(configured_provider_prefixes(settings, completion_fallbacks) - set(register))
    if missing:
        raise ModelFileError(f"configured model provider is missing from providers.register.toml: {', '.join(missing)}")


def validate_model_files(settings: object, *, completion_fallbacks: tuple[str, ...] = ()) -> None:
    """Run startup gates: the lock parses and every configured provider is registered. Licences are checked in CI."""
    load_models_lock()
    register = load_provider_register()
    require_registered_providers(settings, register, completion_fallbacks)
