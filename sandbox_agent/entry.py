"""The agent program that runs inside the sandbox (Sprint 009, ADR-0009).

It has no model key and no database. Its one network route is the platform gateway (`GATEWAY_URL`), and it
authenticates with a run token (`RUN_TOKEN`) that is valid for this run only. Every tool call and every model call
is an HTTP call to `/v1/sandbox/runs/{EXECUTION_ID}/...`, so the gateway decides each one (`enforce()`), records it
and applies the policy, including the tool argument schemas. Files are written only under `WORK_DIR`.

Standard library only. The runtime hands this file to the sandbox as `python3 -c <source> <command>`:
- `answer` (default): retrieve, then answer from what was retrieved. The task arrives on stdin as JSON.
- `check`: try a direct call to a model provider and a read outside the work directory. Both must fail inside a
  sandbox. It prints what happened and exits 0. `CHECK_OUTSIDE_PATH` names another file to read. `scripts/verify/openshell.sh` and the tests use it.

The last line on stdout is one JSON object (the run's output). Everything else goes to stderr. Neither the token nor
the question text is ever printed.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from typing import Any, TextIO

HttpPost = Callable[[str, dict[str, Any], Mapping[str, str]], tuple[int, dict[str, Any]]]
OpenFile = Callable[..., Any]

PROVIDER_PROBE_URL = "https://api.openai.com/v1/models"  # the check sends no credential
# A file that exists and is world-readable on a Debian or Ubuntu image, and is outside OpenShell's baseline read paths (which
# include /etc), so only the sandbox policy stops the read. Another image may set CHECK_OUTSIDE_PATH.
OUTSIDE_PROBE_PATH = "/var/lib/dpkg/status"
TOP_K = 5
MAX_CONTEXT_CHARS = 6000


def http_post(url: str, body: dict[str, Any], headers: Mapping[str, str]) -> tuple[int, dict[str, Any]]:
    """POST JSON, return (status, JSON body). A refusal from the gateway is a status, not an exception."""
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url, data=data, method="POST", headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 (the url is the gateway)
            status, raw = response.status, response.read()
    except urllib.error.HTTPError as exc:
        status, raw = exc.code, exc.read()
    try:
        parsed = json.loads(raw.decode("utf-8") or "{}")
    except ValueError:
        parsed = {}
    return status, parsed if isinstance(parsed, dict) else {}


class Gateway:
    """The agent's only route out: calls under this run's own path, with its run token."""

    def __init__(self, base_url: str, execution_id: str, token: str, post: HttpPost) -> None:
        self._base = f"{base_url.rstrip('/')}/v1/sandbox/runs/{execution_id}"
        self._headers = {"Authorization": f"Bearer {token}"}
        self._post = post

    def call(self, path: str, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        return self._post(f"{self._base}/{path}", body, self._headers)


class Denied(Exception):
    """The gateway refused a call. `reason` is its reason code."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


_REASON_RE = re.compile(r"\(reason: ([a-z_]+)\)")


def _reason_of(status: int, body: dict[str, Any]) -> str:
    """The gateway's reason code. A deny reads `Denied by policy (reason: <code>)`; a deny with its own status has the code."""
    error = body.get("error")
    if isinstance(error, dict):
        found = _REASON_RE.search(str(error.get("message", "")))
        return found.group(1) if found else str(error.get("code") or f"http_{status}")
    return f"http_{status}"


def call_tool(gateway: Gateway, name: str, arguments: dict[str, Any]) -> Any:
    status, body = gateway.call(f"tools/{name}", {"arguments": arguments})
    if status == 200:
        return body.get("result")
    if status == 403:
        raise Denied(_reason_of(status, body))
    raise RuntimeError(f"tool {name} failed: http {status}")


def call_model(gateway: Gateway, messages: list[dict[str, str]]) -> dict[str, Any]:
    status, body = gateway.call("model", {"messages": messages})
    if status == 200:
        return body
    if status == 403:
        raise Denied(_reason_of(status, body))
    raise RuntimeError(f"model call failed: http {status}")


def _context_of(chunks: list[dict[str, Any]]) -> str:
    parts = [f"[{i + 1}] ({c.get('source_filename', 'unknown')}) {c.get('content', '')}" for i, c in enumerate(chunks)]
    return "\n\n".join(parts)[:MAX_CONTEXT_CHARS]


_CONFIDENCE_RE = re.compile(r"\n?\s*Confidence:\s*([01](?:\.\d+)?)\s*$", re.IGNORECASE)


def _split_confidence(text: str) -> tuple[str, float]:
    """The answer without its closing `Confidence: x` line, and x (0.0 when the model did not state one)."""
    found = _CONFIDENCE_RE.search(text)
    if found is None:
        return text.strip(), 0.0
    return text[: found.start()].strip(), min(1.0, float(found.group(1)))


def answer(task: dict[str, Any], gateway: Gateway, work_dir: str, open_file: OpenFile = open) -> dict[str, Any]:
    """Retrieve through the gateway, keep the notes in the work directory, answer through the gateway."""
    question = str(task.get("question", ""))
    namespace = str(task.get("namespace", "default"))
    steps: list[str] = []
    result: dict[str, Any] = {"steps": steps, "tool_calls": 0, "citations": [], "usage": {}, "denied": None}
    try:
        steps.append("Called tool: retrieve_chunks")
        retrieved = call_tool(gateway, "retrieve_chunks", {"query": question, "namespace": namespace, "top_k": TOP_K, "mode": "hybrid"})
        result["tool_calls"] = 1
        parsed = json.loads(retrieved) if isinstance(retrieved, str) else (retrieved or {})
        chunks = [c for c in parsed.get("chunks", []) if isinstance(c, dict)]
        steps.append(f"Tool result: {len(chunks)} chunks")
        with open_file(os.path.join(work_dir, "notes.json"), "w", encoding="utf-8") as notes:
            json.dump({"chunk_count": len(chunks)}, notes)
        if not chunks:
            result.update(answer="No relevant documents were found for this question.", confidence=0.0)
            return result
        steps.append("Called model: answer from the retrieved text")
        completion = call_model(gateway, [
            {"role": "system", "content": (
                "Answer the question using only the numbered passages. Cite them as [n]. Say so if they do not answer it. "
                "End with one line: Confidence: <a number from 0 to 1>."
            )},
            {"role": "user", "content": f"Passages:\n{_context_of(chunks)}\n\nQuestion: {question}"},
        ])
        text, confidence = _split_confidence(str(completion.get("text", "")))
        result.update(
            answer=text, model=str(completion.get("model", "")), usage=completion.get("usage", {}), confidence=confidence,
            citations=[
                {"document_id": c.get("document_id", ""), "source_filename": c.get("source_filename", "unknown"),
                 "chunk_index": int(c.get("chunk_index", 0)), "relevance_score": float(c.get("score", 0.0)),
                 "excerpt": str(c.get("content", ""))[:300]}
                for c in chunks
            ],
        )
    except Denied as exc:
        steps.append(f"The gateway refused a call: {exc.reason}")
        result.update(denied=exc.reason, answer="The run was cut short by policy. The answer is partial.", confidence=0.0)
    return result


def check(post: HttpPost, open_file: OpenFile = open, outside_path: str = OUTSIDE_PROBE_PATH) -> dict[str, Any]:
    """Two things a sandbox must stop: a direct call to a model provider, and a read outside the work directory.

    A read that fails with `PermissionError` is the sandbox refusing it. Any other failure (a missing file, say) says nothing
    about the sandbox, and the report names it, so a probe on the wrong image is not mistaken for a pass."""
    outcome: dict[str, Any] = {"provider_call": "succeeded", "outside_read": "succeeded"}
    try:
        post(PROVIDER_PROBE_URL, {}, {})
    except Exception as exc:  # any failure to connect counts: the sandbox refused or dropped the call
        outcome["provider_call"] = f"failed ({type(exc).__name__})"
    try:
        with open_file(outside_path, "r", encoding="utf-8", errors="replace") as handle:
            handle.read(1)
    except Exception as exc:
        outcome["outside_read"] = f"failed ({type(exc).__name__})"
    outcome["outside_path"] = outside_path
    return outcome


def main(
    argv: list[str], env: Mapping[str, str], stdin: TextIO, stdout: TextIO, stderr: TextIO,
    post: HttpPost = http_post, open_file: OpenFile = open,
) -> int:
    command = argv[0] if argv else "answer"
    try:
        if command == "check":
            output: dict[str, Any] = check(post, open_file, env.get("CHECK_OUTSIDE_PATH") or OUTSIDE_PROBE_PATH)
        elif command == "answer":
            task = json.loads(stdin.read() or "{}")
            work_dir = env.get("WORK_DIR", "")
            missing = [n for n in ("GATEWAY_URL", "RUN_TOKEN", "EXECUTION_ID") if not env.get(n)]
            if missing or not work_dir:
                stderr.write(f"missing environment: {', '.join(missing or ['WORK_DIR'])}\n")
                return 2
            gateway = Gateway(env["GATEWAY_URL"], env["EXECUTION_ID"], env["RUN_TOKEN"], post)
            output = answer(task.get("input", task), gateway, work_dir, open_file)
        else:
            stderr.write(f"unknown command: {command}\n")
            return 2
    except Exception as exc:  # the type only: a message could hold input text
        stderr.write(f"agent failed: {type(exc).__name__}\n")
        return 1
    stdout.write(json.dumps({"result": output}) + "\n")
    stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:], os.environ, sys.stdin, sys.stdout, sys.stderr))
