#!/usr/bin/env python3
"""The M0 recovery drill (Sprint 015, WP4). Run it as `scripts/verify/poc-drill.sh <stack>`.

One fixture-owned local stack goes through the whole journey a client's laptop would: a status probe (exit 3 = absent, any
other failure aborts), `poc up --create-only` (it never adopts a stack and stamps the run's owner token), seed an operator
and an auditor, deny the chat alias by POLICY (`model_not_allowed`, nothing else is accepted) with a signed receipt that
carries the alias and the admission phase, save that receipt and the public keys, restore the baseline policy, `poc backup`,
a checked `poc down`, `poc up` (which restores), a comparison of the restored row counts and chain heads with the backup
before any new traffic, an offline check of the saved receipt, one new governed policy deny whose receipt also verifies with
the SAVED keys, and last `poc destroy` with the owner token (a stack this run did not create is refused). Each deny is
checked for zero inference twice: at the metadata-only model runtime the stack is pointed at, and in the public usage summary.

It uses only public seams (Rule 10): the `poc` commands as a subprocess, the public HTTP API and the offline receipt
verifier `scripts/verify/receipt.py`. It imports nothing from the product, runs no SQL, and overrides no SDK. Every step
prints exactly one marker line, `PASS <step>` or `FAIL <step>: <reason>`; there is no SKIP. The first failed step stops the
run; the stack is still torn down; the exit status is nonzero. Reasons never contain a key or a password.
"""
import importlib.util
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
import threading
import time

try:
    import tomllib
except ModuleNotFoundError:
    print("FAIL prerequisites: selected Python lacks project dependencies or Python 3.11", flush=True)
    sys.exit(1)
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Protocol

REQUIRED_MARKERS = ("PASS backup", "PASS checked down", "PASS restored counts and heads", "PASS saved receipts offline",
                    "PASS new governed call", "PASS restore drill")
STACK_NAME = re.compile(r"[a-z][a-z0-9-]{2,30}")
TENANT = "default"  # the tenant every fresh stack is migrated with
BASELINE = {"allowed_kbs": "*", "allowed_tools": "*", "allowed_models": "*"}
QUESTION = "What is the retention policy?"
# The one accepted denial: the tenant policy omits the chat alias. The alias must RESOLVE first (the gateway checks the model's
# identity before the policy and fails closed on an unknown one), so the stack is pointed at a metadata-only model runtime
# that lists the reviewed digests and refuses any inference. A `model_digest_mismatch` or another reason is a failed step.
DENY_REASON = "model_not_allowed"
ABSENT = 3  # `poc status` exit code for "no such stack"; anything else nonzero is a failed probe
EXISTS = 2  # `poc up --create-only` exit code for "this stack already exists"
ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Proc:
    returncode: int
    stdout: str
    stderr: str


class Runtime(Protocol):
    """A model runtime outside the stack: it lists model digests and counts every request that is not a metadata read."""

    url: str

    def inference_requests(self) -> int: ...
    def close(self) -> None: ...


class MetadataRuntime:
    """The Ollama metadata endpoint the catalog reads (`GET /api/tags`), built from the reviewed `models.lock`.

    Any other request (a generate, chat or embed call) is refused with 503 and counted: the drill needs proof that none
    arrived. It listens on all interfaces because the stack's containers reach the host through `host.docker.internal`;
    it serves only the public digests of the lock and lives for the length of the drill."""

    def __init__(self, models_lock: Path, host_name: str = "host.docker.internal") -> None:
        entries = tomllib.loads(models_lock.read_text())["model"]
        tags = [{"name": e["alias"].removeprefix("ollama/"), "digest": e["digest"].removeprefix("sha256:")}
                for e in entries if e.get("runtime") == "ollama"]
        body = json.dumps({"models": tags}).encode()
        owner = self
        self._count, self._lock = 0, threading.Lock()

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - the base class signature
                return

            def do_GET(self) -> None:  # noqa: N802
                if self.path.split("?", 1)[0] == "/api/tags":
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                else:
                    self.refuse()

            def do_POST(self) -> None:  # noqa: N802
                self.refuse()

            def refuse(self) -> None:
                with owner._lock:
                    owner._count += 1
                self.send_error(503, "inference is not available")

        # Not 127.0.0.1: `host.docker.internal:host-gateway` resolves to the Docker bridge gateway (here 172.17.0.1, a
        # non-loopback address), and a socket bound to loopback does not accept connections that arrive on that address,
        # so the containers could not reach it. The exposure is the public digests of the lock for the length of the drill;
        # an outside peer can only raise the request counter (a false FAIL, never a false PASS).
        self._server = ThreadingHTTPServer(("0.0.0.0", 0), Handler)  # noqa: S104
        self.url = f"http://{host_name}:{self._server.server_address[1]}"
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    def inference_requests(self) -> int:
        with self._lock:
            return self._count

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()


@dataclass
class Ports:
    """What the drill touches. All are public surfaces; tests replace them with fakes."""

    poc: Callable[[Sequence[str], Mapping[str, str] | None, str | None], Proc]
    http: Callable[[str, str, str, str, Any], tuple[int, Mapping[str, str], Any]]  # base, method, path, key, body
    verify: Callable[[Path, Path], int]  # saved receipt, saved public keys -> exit status of the offline verifier
    emit: Callable[[str], None]
    work_dir: Path
    models_lock: Path
    start_runtime: Callable[[], Runtime]
    sleep: Callable[[float], None] = field(default=time.sleep)


class StepFailed(Exception):
    def __init__(self, step: str, reason: str) -> None:
        super().__init__(reason)
        self.step, self.reason = step, reason


def _tail(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines[-1][:200] if lines else "no message"


def _normal_heads(rows: Any) -> list[tuple[str, int, str]]:
    return sorted((str(r[0]), int(r[1]), str(r[2])) for r in rows)


def _normal_checkpoints(rows: Any) -> list[tuple[str, int, str, str]]:
    return sorted((str(r[0]), int(r[1]), str(r[2]), str(r[3])) for r in rows)


class Drill:
    def __init__(self, stack: str, ports: Ports) -> None:
        self.stack, self.ports = stack, ports
        self.base = ""
        self.created = False
        self.owner_token = secrets.token_hex(16)  # stamped on the stack by `up --create-only`; `destroy` must present it
        self.runtime: Runtime | None = None
        self.secrets: list[str] = [self.owner_token]
        self.keys: dict[str, str] = {}
        self.namespace = ""
        self.chat_alias = ""
        self.deny_models: list[str] = []
        self.ref = ""
        self.backup_state: dict[str, Any] = {}
        self.saved: dict[str, Any] = {}
        self.denials = 0
        self.report: dict[str, Any] = {"inference_requests": None, "usage_requests": None, "deny_phases": []}

    # ------------------------------------------------------------------------------------------------ plumbing
    def _scrub(self, text: str) -> str:
        for secret in self.secrets:
            text = text.replace(secret, "***")
        return text

    def _poc(self, verb: str, *args: str, env: Mapping[str, str] | None = None, stdin: str | None = None) -> Proc:
        return self.ports.poc([verb, self.stack, *args], env, stdin)

    def _poc_ok(self, step: str, verb: str, *args: str, env: Mapping[str, str] | None = None, stdin: str | None = None) -> str:
        done = self._poc(verb, *args, env=env, stdin=stdin)
        if done.returncode != 0:
            raise StepFailed(step, self._scrub(f"poc {verb} failed: {_tail(done.stderr or done.stdout)}"))
        return done.stdout

    def _status(self, step: str) -> dict[str, Any]:
        out = self._poc_ok(step, "status", "--json")
        try:
            body = json.loads(out)
        except ValueError:
            raise StepFailed(step, "poc status did not print JSON") from None
        if not isinstance(body, dict):
            raise StepFailed(step, "poc status did not print a JSON object")
        return body

    def _call(self, step: str, method: str, path: str, key: str, body: Any = None) -> tuple[int, Mapping[str, str], Any]:
        for attempt in range(6):  # the platform's own rate limit is a feature: wait it out, never bypass it
            status, headers, payload = self.ports.http(self.base, method, path, key, body)
            if status != 429 or attempt == 5:
                return status, headers, payload
            self.ports.sleep(5)
        raise StepFailed(step, "unreachable")

    def _save(self, name: str, document: Any) -> Path:
        path = self.ports.work_dir / name
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(document, stream, indent=2, sort_keys=True)
        return path

    def _step(self, name: str, action: Callable[[], str | None]) -> None:
        try:
            detail = action()
        except StepFailed as exc:
            self.ports.emit(f"FAIL {name}: {self._scrub(exc.reason)}")
            raise
        except Exception as exc:  # noqa: BLE001 - any surprise is a failed step; only the class name is shown
            self.ports.emit(f"FAIL {name}: {type(exc).__name__}")
            raise StepFailed(name, type(exc).__name__) from None
        self.ports.emit(f"PASS {name}" + (f" {detail}" if detail else ""))

    # ------------------------------------------------------------------------------------------------ the run
    def run(self) -> int:
        self.ports.work_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.ports.work_dir, 0o700)
        code = 0
        try:
            self.runtime = self.ports.start_runtime()
        except Exception as exc:  # noqa: BLE001 - the class name is the whole message
            self.ports.emit(f"FAIL up: the metadata runtime did not start ({type(exc).__name__})")
            return 1
        try:
            code = self._run_steps()
        finally:
            self.runtime.close()
        if code == 0:
            self.ports.emit("PASS restore drill")
        return code

    def _run_steps(self) -> int:
        code = 0
        try:
            self._step("up", self._up)
            self._step("seed", self._seed)
            self._step("deny receipt saved", self._deny_and_save)
            self._step("baseline restored", self._restore_baseline)
            self._step("backup", self._backup)
            self._step("checked down", self._down)
            self._step("restored counts and heads", self._restore_and_compare)
            self._step("saved receipts offline", self._saved_receipts_offline)
            self._step("new governed call", self._new_call)
        except StepFailed:
            code = 1
        if self.created and not self._teardown():
            code = 1
        return code

    def _teardown(self) -> bool:
        try:  # the token proves this run created the stack: `destroy` refuses any other
            self._poc_ok("fixture teardown", "destroy", "--confirm", self.stack, env={"POC_OWNER_TOKEN": self.owner_token})
        except StepFailed as exc:
            self.ports.emit(f"FAIL fixture teardown: {self._scrub(exc.reason)}")
            return False
        self.ports.emit("PASS fixture teardown")
        return True

    # ------------------------------------------------------------------------------------------------ steps
    def _runtime_env(self) -> dict[str, str]:
        assert self.runtime is not None
        return {"POC_OLLAMA_BASE_URL": self.runtime.url}  # set on every `up` of the stack (documented)

    def _probe(self) -> int:
        return self.ports.poc(["status", self.stack, "--json"], None, None).returncode

    def _up(self) -> None:
        probe = self.ports.poc(["status", self.stack, "--json"], None, None)
        if probe.returncode == 0:
            raise StepFailed("up", "the stack already exists; the drill never adopts a stack "
                                   f"(run: poc destroy {self.stack} --confirm {self.stack}, or choose another name)")
        if probe.returncode != ABSENT:  # a failed probe is not proof of absence
            raise StepFailed("up", self._scrub(f"the status probe failed (exit {probe.returncode}: "
                                               f"{_tail(probe.stderr or probe.stdout)}); the drill does not guess"))
        done = self._poc("up", "--create-only", env={**self._runtime_env(), "POC_OWNER_TOKEN": self.owner_token})
        if done.returncode == EXISTS:
            raise StepFailed("up", "another creator made this stack first; the drill never adopts or destroys it")
        if done.returncode != 0:
            self.created = self._probe() == 0  # state exists after the failure: it can only be torn down with our token
            raise StepFailed("up", self._scrub(f"poc up failed: {_tail(done.stderr or done.stdout)}"))
        self.created = True
        self.base = self._base_of(done.stdout)

    @staticmethod
    def _base_of(stdout: str) -> str:
        found = re.search(r"api=(http://127\.0\.0\.1:\d+)", stdout)
        if found is None:
            raise StepFailed("up", "poc up did not report the API address")
        return found.group(1)

    def _principal_key(self, name: str, scopes: Sequence[str]) -> str:
        out = self._poc_ok("seed", "admin", "create-principal", TENANT, "user", name)
        match = re.search(r"id=([0-9a-fA-F-]{36})", out)
        if match is None:
            raise StepFailed("seed", "create-principal did not print an id")
        out = self._poc_ok("seed", "admin", "create-key", match.group(1), "--scopes", *scopes)
        token = re.search(r"KEY \(shown once, store it now\): (\S+)", out)
        if token is None:
            raise StepFailed("seed", "create-key did not print a key")
        self.secrets.append(token.group(1))
        return token.group(1)

    def _publish(self, step: str, document: Mapping[str, Any]) -> None:
        out = self._poc_ok(step, "admin", "set-policy", TENANT, "-", stdin=json.dumps(document))
        if "is now active" not in out:
            raise StepFailed(step, "the policy was not reported active")

    def _seed(self) -> None:
        self.keys["consumer"] = self._principal_key("drill-consumer", ["query", "kb:read"])
        self.keys["auditor"] = self._principal_key("drill-auditor", ["audit:read"])
        status, _, body = self._call("seed", "GET", "/v1/config", self.keys["consumer"])
        namespaces = list((body or {}).get("namespaces", {})) if status == 200 else []
        if not namespaces:
            raise StepFailed("seed", "the tenant has no knowledge base to ask")
        self.namespace = namespaces[0]
        try:
            entries = tomllib.loads(self.ports.models_lock.read_text())["model"]
        except (OSError, ValueError, KeyError):
            raise StepFailed("seed", "the reviewed model lock cannot be read") from None
        chat = [e["alias"] for e in entries if "chat" in e.get("use", [])]
        if not chat:
            raise StepFailed("seed", "the model lock has no chat model")
        self.chat_alias = chat[0]
        self.deny_models = [e["alias"] for e in entries if e["alias"] != self.chat_alias]
        self._publish("seed", BASELINE)

    def _deny_once(self, step: str) -> dict[str, Any]:
        """One search that must be denied at admission by the POLICY; returns its signed receipt and the public keys."""
        status, headers, body = self._call(step, "POST", "/v1/search", self.keys["consumer"],
                                           {"query": QUESTION, "namespace": self.namespace})
        if status != 403 or DENY_REASON not in json.dumps(body):
            said = str(((body or {}).get("error") or {}).get("message", ""))[:120] if isinstance(body, dict) else ""
            raise StepFailed(step, f"the search was not denied with {DENY_REASON} (HTTP {status}: {said})")
        request_id = str((body.get("error") or {}).get("request_id") or headers.get("x-request-id") or "")
        if not request_id:
            raise StepFailed(step, "the denial carried no request id")
        decision_id, cursor = None, ""
        while decision_id is None:
            path = "/v1/decisions?request_id=" + request_id + (("&cursor=" + cursor) if cursor else "")
            code, _, page = self._call(step, "GET", path, self.keys["auditor"])
            if code != 200:
                raise StepFailed(step, f"the auditor could not read the decisions (HTTP {code})")
            decision_id = next((row["id"] for row in page["items"] if row["reason"] == DENY_REASON), None)
            cursor = page.get("next_cursor") or ""
            if decision_id is None and not cursor:
                raise StepFailed(step, "the denial was not recorded as a decision")
        code, _, receipt = self._call(step, "GET", "/v1/receipts/" + str(decision_id), self.keys["auditor"])
        key_code, _, public_keys = self._call(step, "GET", "/v1/receipts/keys", self.keys["auditor"])
        if code != 200 or key_code != 200:
            raise StepFailed(step, "the receipt or the public keys could not be read")
        model = (receipt["decision"].get("extensions") or {}).get("model") or {}
        if "phase" not in model:  # no default for a missing phase: the receipt must say it
            raise StepFailed(step, "the signed receipt carries no model phase")
        if receipt["decision"].get("reason") != DENY_REASON or model["phase"] != "admission":
            raise StepFailed(step, "the signed receipt does not show a model_not_allowed denial at the admission phase")
        if model.get("name") != self.chat_alias:
            raise StepFailed(step, "the signed receipt does not name the denied chat alias")
        self.denials += 1
        self._assert_no_inference(step)
        self.report.setdefault("deny_reasons", []).append(DENY_REASON)
        self.report["deny_phases"].append(model["phase"])
        return {"receipt": receipt, "keys": public_keys, "decision_id": str(decision_id),
                "position": int(receipt["chain"]["position"]), "row_hash": receipt["chain"]["row_hash"]}

    def _assert_no_inference(self, step: str) -> None:
        """Zero inference, observed twice: by the model runtime, and through the public usage summary (the auditor's read)."""
        assert self.runtime is not None
        seen = self.runtime.inference_requests()
        code, _, usage = self._call(step, "GET", "/v1/usage/summary?days=1", self.keys["auditor"])
        if code != 200 or not isinstance(usage, dict):
            raise StepFailed(step, f"the usage summary could not be read (HTTP {code})")
        requests = int(usage["totals"]["requests"])
        self.report.update(inference_requests=seen, usage_requests=requests)
        if seen != 0 or requests != 0:
            raise StepFailed(step, f"a model was reached: runtime inference requests={seen}, usage requests={requests}")
        if int(usage["denied"]["policy"]) < self.denials:
            raise StepFailed(step, "the usage summary does not count the policy denials")

    def _deny_and_save(self) -> None:
        self._publish("deny receipt saved", {**BASELINE, "allowed_models": self.deny_models})
        saved = self._deny_once("deny receipt saved")
        self.saved = saved
        self._save("deny-receipt.json", saved["receipt"])
        self._save("receipt-keys.json", saved["keys"])
        self.report.update(saved_decision_id=saved["decision_id"], saved_decision_position=saved["position"])

    def _restore_baseline(self) -> None:
        self._publish("baseline restored", BASELINE)

    def _backup(self) -> None:
        out = self._poc_ok("backup", "backup")
        found = re.search(r"POC_RECOVERY_REF=([0-9a-f]{64})", out)
        if found is None:
            raise StepFailed("backup", "poc backup did not print a recovery reference")
        self.ref = found.group(1)
        latest = self._status("backup").get("latest_backup")
        if not isinstance(latest, dict) or latest.get("snapshot_id") != self.ref:
            raise StepFailed("backup", "poc status does not list the new backup as the latest")
        if not (latest.get("counts") and "heads" in latest and "checkpoints" in latest):
            raise StepFailed("backup", "poc status does not list the backup's counts and heads")
        self.backup_state = {"counts": {str(k): int(v) for k, v in latest["counts"].items()},
                             "heads": _normal_heads(latest["heads"]), "checkpoints": _normal_checkpoints(latest["checkpoints"])}

    def _down(self) -> None:
        out = self._poc_ok("checked down", "down", env={"POC_RECOVERY_REF": self.ref})
        if not out.startswith("DOWN"):
            raise StepFailed("checked down", "poc down did not report a teardown")
        running = [name for name, info in (self._status("checked down").get("services") or {}).items()
                   if (info or {}).get("state") == "running"]
        if running:
            raise StepFailed("checked down", "services are still running after the checked down: " + ", ".join(sorted(running)))

    def _restore_and_compare(self) -> str:
        out = self._poc_ok("restored counts and heads", "up", env=self._runtime_env())
        if "RESTORED snapshot=" not in out:
            raise StepFailed("restored counts and heads", "poc up did not restore the backup")
        self.base = self._base_of(out)
        status = self._status("restored counts and heads")
        last = status.get("last_restore")
        if not isinstance(last, dict) or not str(last.get("snapshot_id", "")).startswith(self.ref[:8]) or last.get("snapshot_id") != self.ref:
            raise StepFailed("restored counts and heads", "the restore report does not name the backup that was taken")
        if status.get("restore_pending"):
            raise StepFailed("restored counts and heads", "a restore is still pending")
        state = last.get("verified_state") or {}
        counts = {str(k): int(v) for k, v in (state.get("counts") or {}).items()}
        if counts != self.backup_state["counts"]:
            wrong = sorted(k for k in set(counts) | set(self.backup_state["counts"]) if counts.get(k) != self.backup_state["counts"].get(k))
            raise StepFailed("restored counts and heads", "row counts differ from the backup in: " + ", ".join(wrong))
        if _normal_heads(state.get("heads") or []) != self.backup_state["heads"]:
            raise StepFailed("restored counts and heads", "the chain heads differ from the backup")
        if _normal_checkpoints(state.get("checkpoints") or []) != self.backup_state["checkpoints"]:
            raise StepFailed("restored counts and heads", "the chain checkpoints differ from the backup")
        self.report.update(restored_equals_backup=True, compared_tables=len(counts), compared_heads=len(self.backup_state["heads"]),
                           compared_checkpoints=len(self.backup_state["checkpoints"]))
        return (f"tables={len(counts)} rows={sum(counts.values())} heads={len(self.backup_state['heads'])} "
                f"checkpoints={len(self.backup_state['checkpoints'])}")

    def _saved_receipts_offline(self) -> None:
        step = "saved receipts offline"
        ok = self.ports.verify(self.ports.work_dir / "deny-receipt.json", self.ports.work_dir / "receipt-keys.json") == 0
        self.report["saved_receipt_offline"] = ok
        if not ok:
            raise StepFailed(step, "the saved receipt does not verify offline with the saved public keys")
        code, _, again = self._call(step, "GET", "/v1/receipts/" + self.saved["decision_id"], self.keys["auditor"])
        if code != 200 or again["chain"]["row_hash"] != self.saved["row_hash"] or int(again["chain"]["position"]) != self.saved["position"]:
            raise StepFailed(step, "the restored platform does not return the saved decision unchanged")

    def _new_call(self) -> None:
        step = "new governed call"
        self._publish(step, {**BASELINE, "allowed_models": self.deny_models})
        fresh = self._deny_once(step)
        saved_ids = {k["key_id"] for k in json.loads((self.ports.work_dir / "receipt-keys.json").read_text())}
        if fresh["receipt"]["key_id"] not in saved_ids:
            raise StepFailed(step, "the new receipt is signed with a key that was not saved before the backup")
        if fresh["decision_id"] == self.saved["decision_id"] or fresh["position"] <= self.saved["position"]:
            raise StepFailed(step, "the new call did not add a decision after the saved one")
        path = self._save("new-receipt.json", fresh["receipt"])
        ok = self.ports.verify(path, self.ports.work_dir / "receipt-keys.json") == 0
        self.report.update(new_receipt_offline=ok, new_decision_id=fresh["decision_id"], new_decision_position=fresh["position"])
        if not ok:
            raise StepFailed(step, "the new receipt does not verify offline with the saved public keys")


# ---------------------------------------------------------------------------------------------------- real ports

def real_ports(root: Path, work_dir: Path, emit: Callable[[str], None] = print) -> Ports:
    def poc(args: Sequence[str], env: Mapping[str, str] | None, stdin: str | None) -> Proc:
        done = subprocess.run([sys.executable, str(root / "scripts/poc"), *args], cwd=root, shell=False, text=True,
                              input=stdin, capture_output=True, env={**os.environ, **(env or {})}, check=False)
        return Proc(done.returncode, done.stdout, done.stderr)

    def http(base: str, method: str, path: str, key: str, body: Any) -> tuple[int, Mapping[str, str], Any]:
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(base + path, data=data, method=method, headers={
            "Authorization": "Bearer " + key, **({"Content-Type": "application/json"} if data else {})})
        try:
            with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 - a loopback URL the stack reported
                return response.status, {k.lower(): v for k, v in response.headers.items()}, json.loads(response.read() or b"null")
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            return exc.code, {k.lower(): v for k, v in exc.headers.items()}, (json.loads(raw) if raw else None)

    def verify(receipt: Path, keys: Path) -> int:
        return subprocess.run([sys.executable, str(root / "scripts/verify/receipt.py"), "receipt", str(receipt), "--keys", str(keys)],
                              cwd=root, shell=False, capture_output=True, check=False).returncode

    return Ports(poc=poc, http=http, verify=verify, emit=lambda line: emit(line), work_dir=work_dir,
                 models_lock=root / "models.lock", start_runtime=lambda: MetadataRuntime(root / "models.lock"))


def main(argv: Sequence[str]) -> int:
    if len(argv) != 1 or STACK_NAME.fullmatch(argv[0]) is None:
        print("FAIL prerequisites: usage: poc-drill.sh <stack> (3-31 characters of a-z, 0-9 and '-', starting with a letter)", flush=True)
        return 2
    if any(importlib.util.find_spec(name) is None for name in ("cryptography", "yaml", "pydantic", "httpx")):
        print("FAIL prerequisites: selected Python lacks project dependencies; use the Poetry environment or SHOWCASE_PYTHON", flush=True)
        return 1
    missing = [name for name in ("scripts/poc", "scripts/verify/receipt.py", "models.lock") if not (ROOT / name).is_file()]
    if missing:
        print("FAIL prerequisites: missing " + ", ".join(missing), flush=True)
        return 1
    with tempfile.TemporaryDirectory(prefix="poc-drill-") as directory:
        return Drill(argv[0], real_ports(ROOT, Path(directory) / "work", emit=lambda line: print(line, flush=True))).run()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
