"""Run the reference-company M0 journey against an explicitly verified fixture tenant."""

import base64
import builtins
import json
import os
import re
import signal
import socket
import stat
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import cast
from urllib.parse import urlsplit

try:
    import httpx
except ModuleNotFoundError:
    raise SystemExit("FAIL m0: selected Python lacks project dependencies; use the Poetry environment or SHOWCASE_PYTHON") from None

try:
    from core.identity.admin import admin_connection, inspect_credential, list_kbs
    from core.models_files import load_models_lock
    from gateway.admin import PolicyConflict, set_policy, show_policy
    from gateway.policy import DEFAULT_POLICY
    from scripts.showcase.policy_restore import restore_policy
    from scripts.verify.poc_drill import REQUIRED_MARKERS, STACK_NAME
    from scripts.verify.receipt import verify_receipt
except ModuleNotFoundError:
    raise SystemExit("FAIL m0: selected Python lacks project dependencies; use the Poetry environment or SHOWCASE_PYTHON") from None

STATE = Path(".showcase")
DRILL = Path(__file__).resolve().parents[1] / "verify" / "poc-drill.sh"
DEFAULT_STACK = "m0drill"


def private_state(name):
    directory = STATE.lstat()
    if not stat.S_ISDIR(directory.st_mode) or directory.st_uid != os.getuid() or stat.S_IMODE(directory.st_mode) != 0o700:
        raise ValueError("showcase state directory must be owned and mode 0700")
    fd = os.open(STATE / name, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, encoding="utf-8") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
            raise ValueError("showcase state files must be owned and mode 0600")
        return stream.read()


class ProxyServer(ThreadingHTTPServer):
    upstream: str


class Proxy(BaseHTTPRequestHandler):
    count = 0
    lock = threading.Lock()

    def log_message(self, format, *args):
        return

    def forward(self):
        if self.path.split("?", 1)[0] in {"/api/generate", "/api/chat", "/api/embed", "/api/embeddings"}:
            with self.lock:
                type(self).count += 1
            self.send_error(503, "Inference blocked by showcase recorder")
            return
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        try:
            response = httpx.request(self.command, cast(ProxyServer, self.server).upstream + self.path, content=body, timeout=30)
            self.send_response(response.status_code)
            self.send_header("Content-Type", response.headers.get("content-type", "application/json"))
            self.end_headers()
            self.wfile.write(response.content)
        except httpx.HTTPError:
            self.send_error(502)

    do_GET = forward
    do_POST = forward


def verified_fixture(dsn, manifest):
    with admin_connection(dsn) as conn:
        record = inspect_credential(conn, os.environ["SHOWCASE_FIXTURE_KEY"])
        if record["tenant_id"] != manifest["tenant_id"] or record["tenant_slug"] != manifest["tenant_slug"]:
            raise ValueError("fixture credential does not match manifest tenant")
        knowledge_bases = [kb["slug"] for kb in list_kbs(conn, record["tenant_slug"])]
    if not knowledge_bases:
        raise ValueError("fixture tenant has no knowledge base")
    return record["tenant_slug"], knowledge_bases


def recorded_decision(client, auditor, request_id, reason):
    cursor = None
    while True:
        params = {"request_id": request_id}
        if cursor:
            params["cursor"] = cursor
        response = client.get("/v1/decisions", headers=auditor, params=params)
        response.raise_for_status()
        page = response.json()
        for row in page["items"]:
            if row["reason"] == reason:
                return row["id"]
        cursor = page["next_cursor"]
        if cursor is None:
            raise RuntimeError("expected decision was not recorded")


def publish_journey_policy(conn, slug, knowledge_bases, alias):
    current = show_policy(conn, slug)
    baseline = current["document"] if current is not None else DEFAULT_POLICY.model_dump(mode="json")
    allowed_kbs = baseline["allowed_kbs"]
    kb = next((name for name in knowledge_bases if allowed_kbs == "*" or name in allowed_kbs), None)
    if kb is None:
        raise ValueError("baseline policy does not allow a fixture knowledge base")
    baseline_version = set_policy(conn, slug, baseline, "showcase-baseline",
                                  expected_version=current["version"] if current else 0)
    models = baseline["allowed_models"]
    deny_models = [entry.alias for entry in load_models_lock() if entry.alias != alias] if models == "*" else [model for model in models if model != alias]
    journey = set_policy(conn, slug, {**baseline, "allowed_models": deny_models}, "showcase-deny",
                         expected_version=baseline_version)
    return baseline, journey, kb


def key_headers(keys, name):
    return {"Authorization": "Bearer " + keys["SHOWCASE_KEY_" + name]}


def server_environment(environ, recorder, fd):
    env = dict(environ)
    env.update(ENABLED_MODULES="gateway", SHOWCASE_API_FD=str(fd), SHOWCASE_OLLAMA_PROXY=recorder,
               OLLAMA_BASE_URL=recorder)
    return env


def open_server_log():
    directory = STATE.lstat()
    if not stat.S_ISDIR(directory.st_mode) or directory.st_uid != os.getuid() or stat.S_IMODE(directory.st_mode) != 0o700:
        raise ValueError("showcase state directory must be owned and mode 0700")
    def opener(path, flags):
        fd = os.open(path, flags | os.O_NOFOLLOW, 0o600)
        os.fchmod(fd, 0o600)
        return fd

    # Exclusive creation refuses old logs and symlinks, preserving private diagnostics.
    return open(STATE / "m0-server.log", "x+", encoding="utf-8", errors="replace", opener=opener)


SERVER_EXCEPTION_NAMES = frozenset(name for name, value in vars(builtins).items()
                                   if isinstance(value, type) and issubclass(value, Exception))


def server_failure(stderr, reason):
    exception_name = "ServerReadinessError"
    if stderr is not None:
        stderr.flush()
        # A separate descriptor leaves the child's write offset undisturbed.
        with open(stderr.name, encoding="utf-8", errors="replace") as log:
            for line in log:
                match = re.match(r"^([A-Za-z]+):", line.strip())
                if match and match[1] in SERVER_EXCEPTION_NAMES:
                    exception_name = match[1]
    return f"FAIL journey: {reason} ({exception_name})"[:300]


class ServerReadinessError(Exception):
    def __init__(self, *, timed_out=False):
        self.reason = "Gateway-only API did not become ready" if timed_out else "Gateway-only API exited before readiness"
        super().__init__()


class JourneyInterrupted(Exception):
    def __init__(self, signum):
        self.signum = signum
        super().__init__(f"signal {signum}")


def interrupt_journey(signum, frame):
    raise JourneyInterrupted(signum)


def prerequisites():
    for name in ("manifest.json", "keys.env"):
        try:
            content = private_state(name)
        except FileNotFoundError:
            return None, None, "state" if not STATE.exists() else name
        try:
            if name == "manifest.json":
                manifest = json.loads(content)
                if not isinstance(manifest, dict) or not all(manifest.get(field) for field in ("tenant_id", "tenant_slug")):
                    return None, None, "manifest.json (incomplete)"
            else:
                keys = dict(line.split("=", 1) for line in content.splitlines() if line)
                if not all(keys.get("SHOWCASE_KEY_" + field) for field in ("CONSUMER", "AUDITOR", "AGENT_DEVELOPER")):
                    return None, None, "keys.env (incomplete)"
        except (ValueError, TypeError):
            return None, None, name + " (incomplete)"
    for name in ("SHOWCASE_FIXTURE_KEY", "MIGRATION_DATABASE_URL"):
        if not os.environ.get(name):
            return None, None, name
    return manifest, keys, None


def stack_from(argv, environ):
    """The fixture stack the drill owns: the one command-line argument, else POC_STACK, else `m0drill`."""
    if len(argv) > 1:
        raise ValueError("usage: m0.sh [stack]")
    stack = argv[0] if argv else environ.get("POC_STACK") or DEFAULT_STACK
    if STACK_NAME.fullmatch(stack) is None:
        raise ValueError("invalid stack name: use 3-31 characters of a-z, 0-9 and '-', starting with a letter")
    return stack


def run_drill(path, stack, emit):
    """Run the drill script, handing each output line to `emit` as it comes (the drill takes minutes). Returns its exit status."""
    env = dict(os.environ, SHOWCASE_PYTHON=sys.executable)  # the drill uses the interpreter this journey runs in
    process = subprocess.Popen(["bash", str(path), stack], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
    assert process.stdout is not None
    for line in process.stdout:
        emit(line.rstrip("\n"))
    return process.wait()


def finish_with_drill(*, failed, interrupted, stack, drill=DRILL, run_drill=run_drill, out=None):
    """The required last step of M0: the recovery drill. It never skips. A missing drill, an interrupted journey, a drill
    that exits nonzero, prints a SKIP or FAIL line, or does not print every required marker makes the entry path fail."""
    out = out or (lambda line: print(line, flush=True))
    if interrupted:
        out("INFO restore drill: not run because the journey was interrupted")
        return 1
    if failed:  # the exit status is already nonzero; the drill builds and destroys a whole stack: it only runs after a journey that passed
        out("INFO restore drill: not run because the journey failed")
        return 1
    if not Path(drill).is_file():
        out("FAIL restore drill: scripts/verify/poc-drill.sh is missing")
        return 1
    lines = []

    def emit(line):
        lines.append(line)
        out(line)

    status = run_drill(drill, stack, emit)
    reason = None
    if status != 0:
        reason = f"the drill exited with status {status}"
    elif any(line.startswith("SKIP") for line in lines):
        reason = "the drill printed a SKIP line"
    elif any(line.startswith("FAIL") for line in lines):
        reason = "the drill reported a FAIL line"
    else:
        reason = next((f"required marker missing: {marker}" for marker in REQUIRED_MARKERS
                       if not any(line.startswith(marker) for line in lines)), None)
    if reason:
        out(f"FAIL restore drill: {reason}")
        return 1
    return 0


def main(argv=()):
    try:
        stack = stack_from(list(argv), os.environ)
    except ValueError as exc:
        print(f"FAIL prerequisites: {exc}", flush=True)
        return 1
    try:
        manifest, keys, missing = prerequisites()
    except (OSError, ValueError):
        print("FAIL prerequisites: invalid or inaccessible state; run scripts/showcase/setup_personas.sh, see scripts/showcase/README.md", flush=True)
        return 1
    if missing:
        print(f"FAIL prerequisites: missing {missing}; run scripts/showcase/setup_personas.sh, see scripts/showcase/README.md", flush=True)
        return 1
    server = None
    server_stderr = None
    proxy = None
    proxy_started = False
    journey = None
    baseline = None
    slug = None
    failed = False
    interrupted = False
    completed = set()
    old_handlers = {signum: signal.signal(signum, interrupt_journey) for signum in (signal.SIGTERM, signal.SIGINT)}
    try:
        dsn = os.environ["MIGRATION_DATABASE_URL"]
        slug, knowledge_bases = verified_fixture(dsn, manifest)
        print("PASS fixture: tenant credential and manifest verified", flush=True)
        completed.add("fixture")
        upstream = os.environ.get("SHOWCASE_OLLAMA_UPSTREAM", "http://127.0.0.1:11434").rstrip("/")
        parsed_upstream = urlsplit(upstream)
        if parsed_upstream.scheme != "http" or parsed_upstream.hostname not in {"127.0.0.1", "localhost", "::1"} or parsed_upstream.username or parsed_upstream.password or parsed_upstream.path or parsed_upstream.query or parsed_upstream.fragment:
            raise ValueError("Ollama upstream must be a local HTTP origin")
        proxy = ProxyServer(("127.0.0.1", 0), Proxy)
        proxy.upstream = upstream
        threading.Thread(target=proxy.serve_forever, daemon=True).start()
        proxy_started = True
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen(128)
            port = listener.getsockname()[1]
            env = server_environment(os.environ, f"http://127.0.0.1:{proxy.server_port}", listener.fileno())
            server_stderr = open_server_log()
            print(f"INFO gateway: private server log at {STATE / 'm0-server.log'}", flush=True)
            server = subprocess.Popen([sys.executable, "-m", "scripts.showcase.m0_server"], env=env,
                                      pass_fds=(listener.fileno(),), stdout=subprocess.DEVNULL, stderr=server_stderr)
        base = f"http://127.0.0.1:{port}"
        with httpx.Client(base_url=base, timeout=10) as client:
            for _ in range(100):
                try:
                    if client.get("/v1/health").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                if server.poll() is not None:
                    raise ServerReadinessError()
                time.sleep(0.2)
            else:
                raise ServerReadinessError(timed_out=True)
            print("PASS gateway: owned Gateway-only API started", flush=True)
            completed.add("gateway")
            from config import LLM_CONFIG

            alias = str(LLM_CONFIG["model"])
            if not alias.startswith("ollama/"):
                raise ValueError("M0 requires a local Ollama chat model")
            with admin_connection(dsn) as conn:
                baseline, journey, kb = publish_journey_policy(conn, slug, knowledge_bases, alias)
            print("PASS policy: baseline and deny versions recorded", flush=True)
            completed.add("policy")
            before = Proxy.count
            response = client.post("/v1/search", headers=key_headers(keys, "CONSUMER"),
                                   json={"query": "What is the retention policy?", "namespace": kb})
            if response.status_code != 403 or "model_not_allowed" not in response.text or Proxy.count != before:
                raise RuntimeError("search was not denied at admission with zero Ollama inference requests")
            request_id = response.headers["x-request-id"]
            print("PASS search: model admission denied; Ollama request count unchanged", flush=True)
            completed.add("search")
            auditor = key_headers(keys, "AUDITOR")
            decision_id = recorded_decision(client, auditor, request_id, "model_not_allowed")
            receipt_response = client.get(f"/v1/receipts/{decision_id}", headers=auditor)
            key_response = client.get("/v1/receipts/keys", headers=auditor)
            receipt_response.raise_for_status()
            key_response.raise_for_status()
            receipt = receipt_response.json()
            public_keys = {item["key_id"]: base64.b64decode(item["public_key"]) for item in key_response.json()}
            model = receipt["decision"]["extensions"]["model"]
            locked = next((entry for entry in load_models_lock() if entry.alias == alias), None)
            if locked is None:
                raise ValueError("local model is not in the reviewed lock")
            if not all(check[1] for check in verify_receipt(receipt, public_keys)) or model["name"] != alias or model["source"] != "local" or model["digest"] != locked.digest or model["phase"] != "admission":
                raise RuntimeError("offline receipt signature or model identity verification failed")
            print("PASS receipt: offline signature and local model identity verified", flush=True)
            completed.add("receipt")
            modules = client.get("/v1/system/modules", headers=key_headers(keys, "CONSUMER"))
            modules.raise_for_status()
            if next(item for item in modules.json()["modules"] if item["name"] == "agents")["enabled"]:
                raise RuntimeError("agents module is enabled")
            disabled = client.post("/v1/agent/query", headers=key_headers(keys, "AGENT_DEVELOPER"),
                                   json={"question": "Check the policy", "namespace": kb})
            if disabled.status_code != 404 or "module_disabled" not in disabled.text:
                raise RuntimeError("agent request did not produce module_disabled")
            recorded_decision(client, auditor, disabled.headers["x-request-id"], "module_disabled")
            print("PASS modules: agents off and disabled response recorded", flush=True)
            completed.add("modules")
    except ServerReadinessError as exc:
        print(server_failure(server_stderr, exc.reason)[:300], flush=True)
        failed = True
    except JourneyInterrupted as exc:
        print(f"FAIL journey: interrupted by signal {exc.signum}", flush=True)
        failed = True
        interrupted = True
    except PolicyConflict as exc:
        print(f"FAIL journey: policy head changed ({type(exc).__name__})"[:300], flush=True)
        failed = True
    except Exception as exc:
        print(f"FAIL journey: journey failed ({type(exc).__name__})"[:300], flush=True)
        failed = True
    finally:
        for signum in old_handlers:
            signal.signal(signum, signal.SIG_IGN)
        if journey is not None and baseline is not None and slug is not None:
            completed.add("restore")
            try:
                with admin_connection(dsn) as conn:
                    restored = restore_policy(conn, slug, journey, baseline)
                if restored is None:
                    print("FAIL restore: policy head changed", flush=True)
                    failed = True
                else:
                    print("PASS restore: baseline appended as a new policy version", flush=True)
            except Exception as exc:
                print(f"FAIL restore: policy restoration failed ({type(exc).__name__})"[:300], flush=True)
                failed = True
        try:
            if server is not None:
                try:
                    server.terminate()
                    try:
                        server.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        server.kill()
                        server.wait()
                except Exception as exc:
                    if not failed:
                        print(f"FAIL journey: server cleanup failed ({type(exc).__name__})"[:300], flush=True)
                    failed = True
        finally:
            if server_stderr is not None:
                server_stderr.close()
        if proxy is not None:
            if proxy_started:
                proxy.shutdown()
            proxy.server_close()
        for step in ("fixture", "gateway", "policy", "search", "receipt", "modules", "restore"):
            if step not in completed:
                print(f"SKIP {step}: prerequisite did not complete", flush=True)
        for signum, handler in old_handlers.items():
            signal.signal(signum, handler)
    return finish_with_drill(failed=failed, interrupted=interrupted, stack=stack)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
