"""Write the generated sections of the reference documents from the code.

    poetry run python scripts/docs/generate.py            # rewrite the generated blocks
    poetry run python scripts/docs/generate.py --check    # exit 1 when a block is out of date

A generated block sits between `<!-- BEGIN GENERATED: name -->` and `<!-- END GENERATED: name -->`. Everything
inside is replaced. Text outside the markers is written by hand. The blocks are:

- `settings` in `docs/configuration.md`, from `core.settings.Settings`
- `reason-codes` in `docs/api/README.md`, from `gateway.reasons`
- `event-types` in `docs/contracts/README.md`, from `ports.events.EVENT_CATALOGUE`
- `port-<Name>` in `docs/contracts/ports.md`, from the port Protocols and their dataclasses
"""
import dataclasses
import enum
import inspect
import re
import sys
import typing
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from pydantic.fields import FieldInfo  # noqa: E402

import ports  # noqa: E402
from api.errors import _DENY_STATUS  # noqa: E402
from core.settings import Settings  # noqa: E402
from gateway.reasons import all_reasons  # noqa: E402

CONFIGURATION = ROOT / "docs" / "configuration.md"
API_README = ROOT / "docs" / "api" / "README.md"
CONTRACTS = ROOT / "docs" / "contracts" / "README.md"
PORTS_DOC = ROOT / "docs" / "contracts" / "ports.md"

# Settings groups, in reading order: (title, exact names, prefixes). A setting that matches none goes to "Other".
GROUPS: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = (
    ("Mode and data stores", ("mode", "database_url", "migration_database_url", "redis_url"), ()),
    ("Models and embeddings", ("llm_model", "embed_model", "embedding_dim", "embed_fallback_models"), ("azure_", "groq_")),
    ("Object store", (), ("object_store", "s3_")),
    ("Events", ("event_bus",), ("kafka_", "outbox_")),
    ("Agent runtime and sandbox", ("enabled_modules",), ("agent_", "sandbox_", "openshell_")),
    ("Jobs and workers", (), ("job_", "worker_", "embedded_")),
    ("Limits and guardrails", ("max_query_length", "confidence_floor"), ("rate_limit_", "daily_")),
    ("Receipts and retention", ("decision_retention_days", "purge_batch_size"), ("receipt_", "retention_")),
    ("Identity and web edge", ("frontend_url", "preview_principal_id", "deploy_shape"), ("jwt_",)),
    ("Observability and process", ("metrics_public", "grafana_url", "log_level", "web_concurrency"), ("otel_",)),
)


def _begin(name: str) -> str:
    return f"<!-- BEGIN GENERATED: {name} -->"


def _end(name: str) -> str:
    return f"<!-- END GENERATED: {name} -->"


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ").strip()


def is_secret(info: FieldInfo) -> bool:
    extra = info.json_schema_extra
    return isinstance(extra, dict) and extra.get("secret") is True


def _default(info: FieldInfo) -> str:
    value = info.default
    if value is None:
        return "unset"
    if isinstance(value, bool):
        return "`true`" if value else "`false`"
    if isinstance(value, str):
        return f"`{value}`"
    return f"`{value:_}`".replace("_", ",") if isinstance(value, int) else f"`{value}`"


def _group_of(name: str) -> str:
    for title, names, prefixes in GROUPS:
        if name in names or any(name.startswith(p) for p in prefixes):
            return title
    return "Other"


def settings_block() -> str:
    by_group: dict[str, list[str]] = {title: [] for title, _, _ in GROUPS}
    by_group["Other"] = []
    for name, info in Settings.model_fields.items():
        row = f"| `{name.upper()}` | {_default(info)} | {'yes' if is_secret(info) else 'no'} | {_cell(info.description or '')} |"
        by_group[_group_of(name)].append(row)
    parts: list[str] = []
    for title, rows in by_group.items():
        if rows:
            parts.append(f"### {title}\n\n| Setting | Default | Secret | Purpose |\n|---|---|---|---|\n" + "\n".join(rows))
    return "\n\n".join(parts)


def _http(code: str) -> str:
    """The HTTP status and error code a deny answers with (`api.errors.decision_response`)."""
    if code == "allowed":
        return "none"
    status = _DENY_STATUS.get(code)
    return f"{status} `{code}`" if status else "403 `policy_denied`"


def reasons_block() -> str:
    rows = [
        f"| `{r.code}` | {r.stage} | {_cell(r.title)} | {_cell(r.sentence)} | {f'`{r.policy_field}`' if r.policy_field else 'none'} | {_http(r.code)} |"
        for r in all_reasons()
    ]
    head = "| Code | Stage | Title | Meaning | Policy field | HTTP answer |\n|---|---|---|---|---|---|\n"
    return head + "\n".join(rows)


def events_block() -> str:
    rows = []
    for info in ports.EVENT_CATALOGUE:
        topic = "platform." + re.sub(r"\.v\d+$", "", info.type).removeprefix("platform.")
        fields = ", ".join(f"`{f}`" for f in info.data_fields)
        rows.append(
            f"| `{info.type}` | `{topic}` | `{info.source}` | {info.subject} | {_cell(info.summary)} | {fields} |"
        )
    head = "| Type | Kafka topic | Source | Subject | Meaning | Data fields |\n|---|---|---|---|---|---|\n"
    return head + "\n".join(rows)


def _type_name(tp: object) -> str:
    return tp.__name__ if isinstance(tp, type) else _clean(str(tp).replace("typing.", ""))


def _clean(annotation: str) -> str:
    """Drop module prefixes from a printed annotation: `ports.events.CloudEvent` becomes `CloudEvent`."""
    text = re.sub(r"\b(?:[a-z_][a-z0-9_]*\.)+(?=[A-Za-z_])", "", annotation)
    return text.replace("NoneType", "None").replace("'", "")


def _signature(func: typing.Callable[..., object]) -> str:
    sig = inspect.signature(func)
    params = [p for name, p in sig.parameters.items() if name != "self"]
    text = str(sig.replace(parameters=params))
    prefix = "async " if inspect.iscoroutinefunction(func) else ""
    return prefix + _clean(text)


def _doc_line(func: typing.Callable[..., object]) -> str:
    doc = inspect.getdoc(func) or ""
    return " ".join(doc.split())


def _protocol_methods(proto: type) -> list[tuple[str, typing.Callable[..., object]]]:
    return [(n, f) for n, f in vars(proto).items() if inspect.isfunction(f) and not n.startswith("_")]


def _fields_table(cls: type) -> str:
    hints = typing.get_type_hints(cls)
    rows = []
    for f in dataclasses.fields(cls):  # type: ignore[arg-type]
        has_default = f.default is not dataclasses.MISSING or f.default_factory is not dataclasses.MISSING
        rows.append(f"| `{f.name}` | `{_cell(_type_name(hints[f.name]))}` | {'optional' if has_default else 'required'} |")
    return f"**`{cls.__name__}`**\n\n| Field | Type | |\n|---|---|---|\n" + "\n".join(rows)


def _enum_line(cls: type[enum.Enum]) -> str:
    return f"**`{cls.__name__}`** values: " + ", ".join(f"`{m.value}`" for m in cls)


PORT_TYPES: dict[str, tuple[type, tuple[type, ...]]] = {
    "EventBus": (ports.EventBus, (ports.CloudEvent,)),
    "AgentRuntime": (
        ports.AgentRuntime,
        (ports.RunSpec, ports.RunHandle, ports.RunStatus, ports.RunResult, ports.RunState),
    ),
    "SandboxDriver": (
        ports.SandboxDriver,
        (
            ports.SandboxLaunch, ports.SandboxPolicy, ports.SandboxLimits, ports.EgressRule, ports.SandboxEvent,
            ports.SandboxEventKind, ports.SandboxOutput, ports.SandboxExit,
        ),
    ),
    "ObjectStore": (ports.ObjectStore, ()),
}


def port_block(name: str) -> str:
    proto, types = PORT_TYPES[name]
    rows = [
        f"| `{m}` | `{_cell(_signature(f))}` | {_cell(_doc_line(f))} |"
        for m, f in _protocol_methods(proto)
    ]
    parts = ["| Method | Signature | Contract |\n|---|---|---|\n" + "\n".join(rows)]
    for t in types:
        parts.append(_enum_line(t) if isinstance(t, type) and issubclass(t, enum.Enum) else _fields_table(t))
    return "\n\n".join(parts)


def blocks() -> dict[Path, dict[str, str]]:
    return {
        CONFIGURATION: {"settings": settings_block()},
        API_README: {"reason-codes": reasons_block()},
        CONTRACTS: {"event-types": events_block()},
        PORTS_DOC: {f"port-{n}": port_block(n) for n in PORT_TYPES},
    }


def replace_block(text: str, name: str, content: str) -> str:
    """The text with the block `name` replaced. Raises ValueError when its markers are missing."""
    begin, end = _begin(name), _end(name)
    if begin not in text or end not in text:
        raise ValueError(f"missing markers for generated block {name!r}")
    head, rest = text.split(begin, 1)
    _, tail = rest.split(end, 1)
    return f"{head}{begin}\n{content}\n{end}{tail}"


def render(path: Path) -> str:
    """The content `path` should have: its current text with every generated block rewritten."""
    text = path.read_text()
    for name, content in blocks()[path].items():
        text = replace_block(text, name, content)
    return text


def stale() -> list[Path]:
    return [p for p in blocks() if not p.exists() or p.read_text() != render(p)]


def main(argv: list[str]) -> int:
    if "--check" in argv:
        out_of_date = stale()
        for p in out_of_date:
            print(f"out of date: {p.relative_to(ROOT)}. Run: poetry run python scripts/docs/generate.py")
        return 1 if out_of_date else 0
    for p in blocks():
        new = render(p)
        if not p.exists() or p.read_text() != new:
            p.write_text(new)
            print(f"wrote {p.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
