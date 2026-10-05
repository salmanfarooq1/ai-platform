"""Turn what OpenShell streams about a sandbox into `SandboxEvent`s (Sprint 009).

The SDK (`openshell` 0.1.2) exposes the stream as `SandboxStreamEvent`: a `SandboxLogLine` (level, target, message, source, a
string map of fields) or a `PlatformEvent` (type, reason, message, metadata). The sandbox log has two formats (the project's
"Sandbox Logging" page, at tag v0.1.2): plain tracing lines, and OCSF lines in a shorthand such as
`NET:OPEN [MED] DENIED /usr/bin/python3.10(0) -> api.openai.com:443 [reason:transparent_tcp_policy_denied]`.
The rules below were written from that page and checked against a live 0.1.2 gateway on a Docker driver: a direct call to
a model provider came through as `NET:REFUSE ... DENIED api.openai.com [reason:policy_dns_ineligible]` and the `NET:OPEN
... DENIED` line above, and both are `network_denied`.

What is NOT in the stream: OpenShell logs no event when Landlock refuses a file read (the process only gets EACCES). So a
`file_denied` event does not come from OpenShell. The runtime records one for the check probe from the probe's own report
(`source: agent_check`), and a real agent run has none: say so wherever file denials are described.

`classify` is conservative: anything it does not recognise is a `log`, never a denial. `keep` then drops the log lines that
are plumbing (ssh relays, policy load, startup), so a run's timeline shows the start, the exit and what was refused or went
wrong, not thirty lines of supervisor chatter.

This module imports no SDK: it takes plain values, so it can be tested without OpenShell.
"""
import re
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from ports.sandbox import SandboxEvent, SandboxEventKind

_DENY_WORDS = ("denied", "deny", "blocked", "refused", "refuse", "not allowed", "forbidden", "violation")
_ARROW = re.compile(r"->\s*([A-Za-z0-9_.\-]+):(\d{1,5})\b")
_REFUSE_HOST = re.compile(r"(?:REFUSE|DENIED)\s+([A-Za-z0-9_.\-]+\.[A-Za-z0-9_.\-]+|\d{1,3}(?:\.\d{1,3}){3})\b")
_REASON = re.compile(r"\[reason:([^\]]{1,80})\]")
_SEVERITY = re.compile(r"\[(INFO|LOW|MED|HIGH|CRIT|FATAL)\]")
_NETWORK_WORDS = ("network", "connect", "egress", "proxy", "host", "dns", "tcp", "endpoint")
_FILE_WORDS = ("landlock", "filesystem", "file ", "path", "open ", "read ", "write ", "eacces", "permission denied")
_LIMIT_WORDS = ("oom", "out of memory", "memory limit", "cpu limit", "time limit", "timed out", "timeout", "killed")
_HOST_KEYS = ("host", "dst_host", "dest_host", "destination_host", "domain")
_PORT_KEYS = ("port", "dst_port", "dest_port", "destination_port")
_PATH_KEYS = ("path", "file", "filename", "target_path")


def _first(fields: Mapping[str, str], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = fields.get(key)
        if value:
            return value
    return None


def classify(level: str, message: str, fields: Mapping[str, str]) -> tuple[SandboxEventKind, dict[str, Any]]:
    """(kind, detail) for one log line or platform event. A denial needs a deny word and a network or file word."""
    text = message.lower()
    detail: dict[str, Any] = {"message": message}
    host, port, path = _first(fields, _HOST_KEYS), _first(fields, _PORT_KEYS), _first(fields, _PATH_KEYS)
    if host:
        detail["host"] = host
    if port and port.isdigit():
        detail["port"] = int(port)
    if path:
        detail["path"] = path
    arrow = _ARROW.search(message)
    if arrow and "host" not in detail:
        detail["host"], detail["port"] = arrow.group(1), int(arrow.group(2))
    elif "host" not in detail and (named := _REFUSE_HOST.search(message)):
        detail["host"] = named.group(1)
    if (why := _REASON.search(message)):
        detail["reason"] = why.group(1)
    denied = any(w in text for w in _DENY_WORDS)
    host = host or detail.get("host")
    if denied and (host or text.startswith(("net:", "http:")) or any(w in text for w in _NETWORK_WORDS)) and not path:
        return SandboxEventKind.NETWORK_DENIED, detail
    if denied and (path or any(w in text for w in _FILE_WORDS)):
        return SandboxEventKind.FILE_DENIED, detail
    if (any(w in text for w in _LIMIT_WORDS) or text.startswith("proc:") and "timeout" in text) and (
        level.upper() in ("WARN", "WARNING", "ERROR", "FATAL") or any(f"[{s}]" in message for s in ("CRIT", "FATAL", "HIGH"))
    ):
        return SandboxEventKind.LIMIT_HIT, detail
    return SandboxEventKind.LOG, detail


def keep(kind: SandboxEventKind, level: str, message: str) -> bool:
    """Whether an event is worth a row. Denials and limits always are. A log line is kept only when it is a warning or
    error, or its OCSF severity is MED or higher: the rest is supervisor plumbing."""
    if kind is not SandboxEventKind.LOG:
        return True
    if level.upper() in ("WARN", "WARNING", "ERROR", "FATAL"):
        return True
    found = _SEVERITY.search(message)
    return found is not None and found.group(1) in ("MED", "HIGH", "CRIT", "FATAL")


def event_from_log(level: str, message: str, fields: Mapping[str, str], at: datetime) -> SandboxEvent | None:
    """None when the line is plumbing (see `keep`)."""
    kind, detail = classify(level, message, fields)
    return SandboxEvent(kind, at, detail) if keep(kind, level, message) else None


def event_from_platform(type_: str, reason: str, message: str, metadata: Mapping[str, str], at: datetime) -> SandboxEvent | None:
    text = " ".join(part for part in (reason, message) if part)
    level = "WARN" if type_.lower() == "warning" else "INFO"
    kind, detail = classify(level, text, metadata)
    return SandboxEvent(kind, at, detail) if keep(kind, level, text) else None
