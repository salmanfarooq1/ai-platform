"""WP4: the M0 recovery drill is a required step of the M0 entry path.

The drill (`scripts/verify/poc-drill.sh` -> `scripts/verify/poc_drill.py`) runs up -> seed -> deny receipt -> baseline ->
backup -> checked down -> restore up -> compare counts and heads -> saved receipts offline -> a new governed call -> full
teardown, through the public `poc` commands, the public API and the offline receipt verifier only. Here a fake world
stands in for all three, so every step can be made to fail. A missing drill, a missing prerequisite or any failed step
must end in a nonzero exit and never in a SKIP.
"""
import json
import re
import stat
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from scripts.showcase import m0
from scripts.verify import poc_drill
from scripts.verify.poc_drill import Drill, Ports, Proc

ROOT = Path(__file__).resolve().parents[3]
CHAT = "ollama/qwen3:4b-instruct-2507-q4_K_M"
SNAPSHOT = "9f" * 32
COUNTS = {"tenants": 1, "principals": 3, "gateway_decisions": 4, "policies": 3}
HEADS = [["tenant-1", 4, "a" * 64]]
CHECKPOINTS = [["tenant-1", 0, "b" * 64, "genesis"]]
REQUIRED_PASS = ["PASS up", "PASS seed", "PASS deny receipt saved", "PASS baseline restored", "PASS backup", "PASS checked down",
                 "PASS restored counts and heads", "PASS saved receipts offline", "PASS new governed call",
                 "PASS fixture teardown", "PASS restore drill"]


class FakeRuntime:
    """The metadata-only model runtime the drill starts: a URL for the stack and a count of refused inference requests."""

    url = "http://host.docker.internal:45678"

    def __init__(self, inference=0):
        self.inference, self.closed = inference, False

    def inference_requests(self):
        return self.inference

    def close(self):
        self.closed = True


class FakeWorld:
    """The three public surfaces the drill may use, with a failure switch for each step."""

    def __init__(self, *, fail=None, existing=False, restored_counts=None, restored_heads=None, tamper=False,
                 allow_search=False, second_allow=False, deny_reason="model_not_allowed", probe_exit=3, racer=False,
                 phase="admission", name=CHAT, usage_requests=0, runtime_inference=0):
        self.fail = fail
        self.stack_exists = existing
        self.running = False
        self.restored = False
        self.backups = 0
        self.destroyed = 0
        self.poc_calls = []
        self.policies = []
        self.decisions = []
        self.restored_counts = restored_counts
        self.restored_heads = restored_heads
        self.tamper = tamper
        self.allow_search = allow_search
        self.deny_reason = deny_reason
        self.second_allow = second_allow
        self.searches = 0
        self.secrets = []
        self.position = 3
        self.verify_calls = []
        self.events = []
        self.probe_exit = probe_exit
        self.racer = racer  # another creator makes the stack between the drill's probe and its `up --create-only`
        self.phase, self.name = phase, name
        self.usage_requests = usage_requests
        self.runtime = FakeRuntime(runtime_inference)
        self.owner_token = None
        self.refused_destroys = 0

    # --- the poc CLI ----------------------------------------------------------------------------------------------
    def poc(self, args, env=None, stdin=None):
        args = list(args)
        self.poc_calls.append((tuple(args), dict(env or {}), stdin))
        verb = args[0]
        self.events.append(("poc", verb, self.restored_pending() if verb == "up" else None))
        key = f"{verb}:{args[2] if verb == 'admin' else ''}"
        if verb == "admin" and args[2] == "set-policy":
            key = f"set-policy:{len(self.policies) + 1}"
        if verb == "up" and self.restored_pending():
            key = "up:restore"
        if self.fail in (verb, key) or (self.fail == "up:restore" and key == "up:restore"):
            return Proc(1, "", f"{verb} refused: injected failure")
        if verb == "status":
            if not self.stack_exists:
                return Proc(self.probe_exit, "", "poc status refused: no stack marker")
            return Proc(0, json.dumps(self.status_body()), "")
        if verb == "up":
            if "--create-only" in args:
                assert (env or {}).get("POC_OWNER_TOKEN"), "a create-only up carries the owner token"
                if self.racer or self.stack_exists:
                    self.stack_exists = True
                    return Proc(2, "", "poc up refused: stack already exists")
                self.owner_token = env["POC_OWNER_TOKEN"]
            assert (env or {}).get("POC_OLLAMA_BASE_URL") == self.runtime.url, "every up points the stack at the metadata runtime"
            restoring = self.restored_pending()  # decided before the stack starts, as the real `up` does
            self.stack_exists = True
            self.running = True
            out = "UP demo api=http://127.0.0.1:18999 project=ai-platform-poc-demo\n"
            if restoring:
                self.restored = True
                out += f"RESTORED snapshot={SNAPSHOT[:8]} objects=0 cost_counters=0 lost_in_valkey=sessions\n"
            return Proc(0, out, "")
        if verb == "admin":
            return self.admin(args, stdin)
        if verb == "backup":
            self.backups += 1
            return Proc(0, f"BACKUP demo snapshot={SNAPSHOT[:8]} POC_RECOVERY_REF={SNAPSHOT}\n", "")
        if verb == "down":
            if (env or {}).get("POC_RECOVERY_REF") != SNAPSHOT:
                return Proc(1, "", "poc down refused: POC_RECOVERY_REF is not the latest backup")
            self.running = False
            return Proc(0, f"DOWN demo removed runtime data; kept key, repository and marker; restored from snapshot={SNAPSHOT[:8]} on the next `poc up demo`\n", "")
        if verb == "destroy":
            if args[2:] != ["--confirm", args[1]]:
                return Proc(1, "", "poc destroy refused: confirm")
            if self.owner_token is None or (env or {}).get("POC_OWNER_TOKEN") != self.owner_token:
                self.refused_destroys += 1
                return Proc(1, "", "poc destroy refused: the owner token does not match this stack")
            self.destroyed += 1
            self.stack_exists = False
            return Proc(0, "DESTROYED demo\n", "")
        raise AssertionError(f"the drill used a command that is not public: {args}")

    def restored_pending(self):
        return self.backups > 0 and not self.running and self.stack_exists

    def status_body(self):
        body = {"stack": "demo", "services": {"api": {"state": "running", "health": "healthy"}} if self.running else {},
                "latest_backup": None, "last_restore": None, "restore_pending": None}
        if self.backups:
            body["latest_backup"] = {"snapshot_id": SNAPSHOT, "counts": dict(COUNTS), "heads": HEADS, "checkpoints": CHECKPOINTS}
        if self.restored:
            body["last_restore"] = {"snapshot_id": SNAPSHOT, "verified_state": {
                "counts": self.restored_counts or dict(COUNTS), "heads": self.restored_heads or HEADS, "checkpoints": CHECKPOINTS},
                "writers_started_at": "2026-11-17T12:00:00+00:00"}
        return body

    def admin(self, args, stdin):
        command = args[2]
        if command == "create-principal":
            return Proc(0, f"principal {args[-1]} created: id={uuid.uuid4()}\n", "")
        if command == "create-key":
            secret = f"drillkey-{len(self.secrets)}-{uuid.uuid4().hex}"
            self.secrets.append(secret)
            return Proc(0, f"key created: prefix=abc scopes=x\nKEY (shown once, store it now): {secret}\n", "")
        if command == "set-policy":
            assert args[-1] == "-" and stdin, "a policy goes in through stdin"
            self.policies.append(json.loads(stdin))
            return Proc(0, f"policy version {len(self.policies)} is now active for tenant default\n", "")
        raise AssertionError(args)

    # --- the public API --------------------------------------------------------------------------------------------
    def http(self, base, method, path, key, body=None):
        assert base == "http://127.0.0.1:18999" and key in self.secrets, "an unknown or missing key"
        if not self.running:
            raise ConnectionRefusedError("the API is down")
        route = path.split("?")[0]
        self.events.append(("http", route, self.restored))
        if (method, route) == ("GET", "/v1/config"):
            return 200, {}, {"namespaces": {"legal": "Legal"}}
        if (method, route) == ("POST", "/v1/search"):
            self.searches += 1
            allowed = self.policies[-1]["allowed_models"]
            denied = self.deny_reason != "model_not_allowed" or (allowed != "*" and CHAT not in allowed)
            if self.fail == f"search:{self.searches}" and denied:
                denied = False
            if (self.allow_search and self.searches == 1) or (self.second_allow and self.searches == 2):
                denied = False
            if not denied:
                return 200, {"x-request-id": "req"}, {"answer": "x"}
            request_id = f"req-{self.searches}"
            self.position += 1
            self.decisions.append({"id": f"dec-{self.searches}", "request_id": request_id, "reason": self.deny_reason,
                                   "position": self.position})
            return 403, {"x-request-id": request_id}, {"error": {"code": "policy_denied", "request_id": request_id,
                                                                  "message": f"Denied by policy (reason: {self.deny_reason})"}}
        if (method, route) == ("GET", "/v1/decisions"):
            wanted = path.split("request_id=")[1].split("&")[0]
            return 200, {}, {"items": [{"id": d["id"], "reason": d["reason"]} for d in self.decisions if d["request_id"] == wanted],
                             "next_cursor": None}
        if (method, route) == ("GET", "/v1/usage/summary"):
            return 200, {}, {"days": 1, "totals": {"requests": self.usage_requests, "tokens": 0, "cost_usd": 0.0},
                             "denied": {"rate": 0, "budget": 0, "policy": len(self.decisions)}}
        if (method, route) == ("GET", "/v1/receipts/keys"):
            return 200, {}, [{"key_id": "k1", "alg": "Ed25519", "public_key": "AAAA", "active": True}]
        if method == "GET" and route.startswith("/v1/receipts/"):
            decision = next(d for d in self.decisions if d["id"] == route.rsplit("/", 1)[1])
            return 200, {}, {"decision": {"id": decision["id"], "reason": decision["reason"],
                                          "extensions": {"model": self.model_extension()}},
                             "chain": {"position": decision["position"], "row_hash": "c" * 64, "prev_hash": "d" * 64},
                             "signature": "sig", "key_id": "k1", "alg": "Ed25519", "canonical": "{}"}
        raise AssertionError(f"the drill used a route that is not public API: {method} {path}")

    def model_extension(self):
        extension = {"name": self.name, "source": "local"}
        if self.phase is not None:
            extension["phase"] = self.phase
        return extension

    # --- the offline receipt verifier --------------------------------------------------------------------------------
    def verify(self, receipt, keys):
        self.verify_calls.append((Path(receipt).name, Path(keys).name))
        self.events.append(("verify", Path(receipt).name, None))
        assert Path(receipt).is_file() and Path(keys).is_file()
        return 1 if (self.tamper or self.fail == "verify") else 0


def run_drill(tmp_path, world):
    lines = []
    work = tmp_path / "work"
    ports = Ports(poc=world.poc, http=world.http, verify=world.verify, emit=lines.append, work_dir=work,
                  models_lock=ROOT / "models.lock", start_runtime=lambda: world.runtime)
    drill = Drill("demo", ports)
    code = drill.run()
    return code, lines, drill


def markers(lines):
    return [line for line in lines if re.match(r"(PASS|FAIL|SKIP) ", line)]


def verbs(world):
    return [call[0][0] if call[0][0] != "admin" else f"admin {call[0][2]}" for call in world.poc_calls]


# --- the happy path -----------------------------------------------------------------------------------------------------

def test_drill_runs_every_step_in_order_through_public_seams_only(tmp_path):
    world = FakeWorld()
    code, lines, drill = run_drill(tmp_path, world)
    found = markers(lines)
    assert code == 0, lines
    assert [m.split(" tables=")[0] for m in found] == REQUIRED_PASS, found
    assert not [line for line in lines if line.startswith(("SKIP", "FAIL"))]
    order = [v for v in verbs(world) if v not in ("status",)]
    assert order == ["up", "admin create-principal", "admin create-key", "admin create-principal", "admin create-key",
                     "admin set-policy", "admin set-policy", "admin set-policy", "backup", "down", "up", "admin set-policy",
                     "destroy"], order
    assert world.destroyed == 1 and not world.stack_exists
    assert world.verify_calls[0] == ("deny-receipt.json", "receipt-keys.json")  # saved before the backup, checked after the restore
    assert world.verify_calls[-1][1] == "receipt-keys.json"  # the new receipt is checked with the SAVED public keys
    assert world.searches == 2 and len(world.decisions) == 2
    assert drill.report["restored_equals_backup"] is True
    assert drill.report["new_decision_position"] > drill.report["saved_decision_position"]
    assert drill.report["inference_requests"] == 0


def test_drill_prints_one_marker_per_step_and_no_secret(tmp_path):
    world = FakeWorld()
    code, lines, _ = run_drill(tmp_path, world)
    assert code == 0
    names = [re.sub(r" tables=.*", "", m) for m in markers(lines)]
    assert len(names) == len(set(names))  # exactly one marker line per step
    blob = "\n".join(lines) + json.dumps([(c[0], c[1]) for c in world.poc_calls])
    for secret in world.secrets:
        assert secret not in blob, "an API key reached stdout, an argument or an environment value"
    assert world.secrets  # the drill did create keys, and kept them out of every argument
    assert all("--dsn" not in call[0] for call in world.poc_calls)


def test_drill_work_files_are_private_and_hold_no_private_key(tmp_path):
    world = FakeWorld()
    code, _, _ = run_drill(tmp_path, world)
    assert code == 0
    work = tmp_path / "work"
    assert stat.S_IMODE(work.stat().st_mode) == 0o700
    for path in work.iterdir():
        assert stat.S_IMODE(path.stat().st_mode) == 0o600, path.name
        assert not any(secret in path.read_text() for secret in world.secrets), path.name


def test_the_deny_policy_omits_only_the_chat_alias(tmp_path):
    world = FakeWorld()
    run_drill(tmp_path, world)
    baseline, deny, again = world.policies[0], world.policies[1], world.policies[2]
    assert baseline["allowed_models"] == "*" and again == baseline  # restored before the backup
    assert CHAT not in deny["allowed_models"] and len(deny["allowed_models"]) >= 1
    assert {k: v for k, v in deny.items() if k != "allowed_models"} == {k: v for k, v in baseline.items() if k != "allowed_models"}
    assert world.policies[3] == deny  # the new governed call denies the same alias again


# --- every step is fatal ------------------------------------------------------------------------------------------------

FAILURES = {
    "up": ("up", "FAIL up"),
    "create-principal": ("admin:create-principal", "FAIL seed"),
    "create-key": ("admin:create-key", "FAIL seed"),
    "baseline policy": ("set-policy:1", "FAIL seed"),
    "deny policy": ("set-policy:2", "FAIL deny receipt saved"),
    "baseline restore": ("set-policy:3", "FAIL baseline restored"),
    "backup": ("backup", "FAIL backup"),
    "down": ("down", "FAIL checked down"),
    "restore up": ("up:restore", "FAIL restored counts and heads"),
    "first search not denied": ("search:1", "FAIL deny receipt saved"),
    "verify": ("verify", "FAIL saved receipts offline"),
    "second search not denied": ("search:2", "FAIL new governed call"),
    "new deny policy": ("set-policy:4", "FAIL new governed call"),
}


@pytest.mark.parametrize("label", sorted(FAILURES))
def test_every_failed_step_is_fatal_prints_one_fail_and_still_tears_down(tmp_path, label):
    switch, expected = FAILURES[label]
    world = FakeWorld(fail=switch)
    code, lines, _ = run_drill(tmp_path, world)
    found = markers(lines)
    assert code != 0, found
    fails = [m for m in found if m.startswith("FAIL")]
    assert [f.split(":")[0] for f in fails] == [expected], found
    assert "PASS restore drill" not in found and not [m for m in found if m.startswith("SKIP")]
    steps = [line.replace("PASS ", "") for line in REQUIRED_PASS]
    failed_step = expected.replace("FAIL ", "")
    for step in steps[steps.index(failed_step) + 1:]:
        if step not in ("fixture teardown", "restore drill"):
            assert not any(m.startswith("PASS " + step) for m in found), f"{step} ran after the failure"
    if label != "up":
        assert world.destroyed == 1, "the fixture stack must still be torn down"
        assert "PASS fixture teardown" in found


def test_a_failed_first_up_leaves_nothing_to_tear_down(tmp_path):
    world = FakeWorld(fail="up")
    code, lines, _ = run_drill(tmp_path, world)
    assert code != 0 and world.destroyed == 0 and not world.stack_exists
    assert not [m for m in markers(lines) if "teardown" in m]


def test_a_failed_teardown_is_fatal_even_when_everything_else_passed(tmp_path):
    world = FakeWorld(fail="destroy")
    code, lines, _ = run_drill(tmp_path, world)
    found = markers(lines)
    assert code != 0 and "FAIL fixture teardown" in " ".join(found) and "PASS restore drill" not in found
    assert [m for m in found if m.startswith("PASS")][-1].startswith("PASS new governed call")


def test_the_drill_never_adopts_a_stack_that_already_exists(tmp_path):
    world = FakeWorld(existing=True)
    code, lines, _ = run_drill(tmp_path, world)
    assert code != 0 and "FAIL up" in " ".join(markers(lines))
    assert world.destroyed == 0 and verbs(world) == ["status"]  # nothing was started, seeded or destroyed


def test_a_search_that_is_not_denied_fails_the_step_not_the_process(tmp_path):
    world = FakeWorld(allow_search=True)
    code, lines, _ = run_drill(tmp_path, world)
    assert code != 0 and any(m.startswith("FAIL deny receipt saved") for m in markers(lines))


def test_restored_counts_or_heads_that_differ_from_the_backup_fail(tmp_path):
    cases = ({"restored_counts": {**COUNTS, "gateway_decisions": 5}}, {"restored_counts": {**COUNTS, "extra_table": 0}},
                   {"restored_heads": [["tenant-1", 5, "a" * 64]]}, {"restored_heads": [["tenant-1", 4, "f" * 64]]})
    for index, kwargs in enumerate(cases):
        world = FakeWorld(**kwargs)
        code, lines, _ = run_drill(tmp_path / str(index), world)
        found = markers(lines)
        assert code != 0 and any(m.startswith("FAIL restored counts and heads") for m in found), (kwargs, found)
        assert not any(m.startswith(("PASS saved receipts offline", "PASS new governed call")) for m in found)
        assert world.searches == 1  # no new traffic before the comparison passed


def test_the_comparison_is_made_before_any_new_traffic(tmp_path):
    world = FakeWorld()
    code, _, _ = run_drill(tmp_path, world)
    assert code == 0
    restore_up = next(i for i, e in enumerate(world.events) if e[:2] == ("poc", "up") and e[2])  # the `up` that restores
    compared = next(i for i, e in enumerate(world.events) if e[:2] == ("poc", "status") and i > restore_up)
    new_traffic = [i for i, e in enumerate(world.events) if i > restore_up and (e[:2] == ("http", "/v1/search") or e[:2] == ("poc", "admin"))]
    assert new_traffic and compared < min(new_traffic), "counts and heads must be compared before any new governed call or policy change"
    first_verify = next(i for i, e in enumerate(world.events) if e[0] == "verify")
    assert first_verify > compared


def test_a_tampered_saved_receipt_fails_offline_verification(tmp_path):
    world = FakeWorld(tamper=True)
    code, lines, _ = run_drill(tmp_path, world)
    assert code != 0 and any(m.startswith("FAIL saved receipts offline") for m in markers(lines))


def test_a_decision_that_is_not_new_fails_the_new_call_step(tmp_path):
    world = FakeWorld()
    original = world.http

    def stale(base, method, path, key, body=None):
        status, headers, payload = original(base, method, path, key, body)
        if method == "GET" and path.startswith("/v1/receipts/dec-2"):
            payload["chain"]["position"] = 1  # a chain position that did not advance
        return status, headers, payload

    world.http = stale
    code, lines, _ = run_drill(tmp_path, world)
    assert code != 0 and any(m.startswith("FAIL new governed call") for m in markers(lines))


# --- the M0 entry path --------------------------------------------------------------------------------------------------

DRILL_OUT = [
    "PASS up", "PASS seed", "PASS deny receipt saved", "PASS baseline restored", "PASS backup", "PASS checked down",
    "PASS restored counts and heads tables=4 tenants=1", "PASS saved receipts offline", "PASS new governed call",
    "PASS fixture teardown", "PASS restore drill"]


def entry(tmp_path, *, drill_exists=True, result=(0, DRILL_OUT), interrupted=False, failed=False, stack="m0drill"):
    printed = []
    called = []
    drill = tmp_path / "poc-drill.sh"
    if drill_exists:
        drill.write_text("#!/usr/bin/env bash\n")

    def fake_run(path, name, emit):
        called.append((Path(path).name, name))
        for line in result[1]:
            emit(line)  # the real runner streams the drill's lines as they come
        return result[0]

    status = m0.finish_with_drill(failed=failed, interrupted=interrupted, stack=stack, drill=drill, run_drill=fake_run,
                                  out=printed.append)
    return status, printed, called


def test_required_drill_failure_is_fatal(tmp_path):
    status, printed, called = entry(tmp_path)
    assert status == 0 and called == [("poc-drill.sh", "m0drill")]
    assert [line for line in printed if line.startswith("PASS")] == DRILL_OUT  # the drill's own markers are shown as they are
    # a missing drill is a failure, never a SKIP
    (tmp_path / "none").mkdir()
    status, printed, called = entry(tmp_path / "none", drill_exists=False)
    assert status == 1 and called == [] and printed == ["FAIL restore drill: scripts/verify/poc-drill.sh is missing"]
    # the journey itself failed: fatal, and the expensive drill is not started over a failed journey
    status, printed, called = entry(tmp_path, failed=True)
    assert status == 1 and called == [] and printed == ["INFO restore drill: not run because the journey failed"]


@pytest.mark.parametrize("label,result,reason", [
    ("nonzero exit", (1, DRILL_OUT[:5]), "exited with status 1"),
    ("exit 0 but a required marker is missing", (0, [m for m in DRILL_OUT if m != "PASS new governed call"]), "PASS new governed call"),
    ("exit 0 but no markers at all", (0, []), "PASS backup"),
    ("exit 0 with a SKIP", (0, [*DRILL_OUT, "SKIP something: prerequisite did not complete"]), "SKIP"),
    ("exit 0 with a FAIL line", (0, [*DRILL_OUT, "FAIL up"]), "FAIL"),
])
def test_a_drill_that_fails_or_does_not_prove_every_step_fails_the_entry_path(tmp_path, label, result, reason):
    status, printed, _ = entry(tmp_path, result=result)
    assert status == 1, label
    assert printed[-1].startswith("FAIL restore drill") and reason in printed[-1], printed[-1]
    assert not [line for line in printed if line.startswith("SKIP")] or label == "exit 0 with a SKIP"


def test_an_interrupted_journey_is_a_failure_not_a_skip(tmp_path):
    status, printed, called = entry(tmp_path, interrupted=True, failed=True)
    assert status == 1 and called == [] and printed == ["INFO restore drill: not run because the journey was interrupted"]


def test_the_entry_path_takes_the_stack_from_the_command_line_or_the_environment(monkeypatch):
    assert m0.stack_from(["mystack"], {}) == "mystack"
    assert m0.stack_from([], {"POC_STACK": "envstack"}) == "envstack"
    assert m0.stack_from([], {}) == "m0drill"
    for bad in (["a", "b"], ["Bad Name"], ["../x"], [""]):
        with pytest.raises(ValueError):
            m0.stack_from(bad, {})


def test_main_without_prerequisites_still_exits_nonzero_and_never_skips(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(m0, "STATE", tmp_path / "absent")
    assert m0.main(["m0drill"]) != 0
    out = capsys.readouterr().out
    assert "SKIP" not in out and out.startswith("FAIL prerequisites")


def test_the_shell_entry_has_no_skip_branch_and_the_old_placeholder_is_gone():
    source = (ROOT / "scripts/showcase/m0.py").read_text()
    assert "SKIP restore drill" not in source and "Sprint 015" not in source


# --- the shell scripts ---------------------------------------------------------------------------------------------------

def test_drill_shell_without_a_stack_or_a_python_fails_and_never_skips(tmp_path):
    script = str(ROOT / "scripts/verify/poc-drill.sh")
    assert subprocess.run(["bash", "-n", script], check=False).returncode == 0
    (tmp_path / "dirname").symlink_to("/usr/bin/dirname")
    env = {"PATH": str(tmp_path)}
    none = subprocess.run(["/bin/bash", script], capture_output=True, text=True, env=env, check=False)
    assert none.returncode != 0 and none.stdout.startswith("FAIL prerequisites") and "SKIP" not in none.stdout + none.stderr
    missing = subprocess.run(["/bin/bash", script, "demo"], capture_output=True, text=True, env=env, check=False)
    assert missing.returncode != 0 and missing.stdout.startswith("FAIL prerequisites") and "poetry" in missing.stdout
    assert "SKIP" not in missing.stdout + missing.stderr


@pytest.mark.parametrize("runner", ["poetry", "override"])
def test_drill_and_entry_shells_pass_the_stack_to_the_resolved_runner(tmp_path, runner):
    (tmp_path / "dirname").symlink_to("/usr/bin/dirname")
    shim = tmp_path / ("poetry" if runner == "poetry" else "python-override")
    shim.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
    shim.chmod(0o700)
    env = {"PATH": str(tmp_path)}
    if runner == "override":
        env["SHOWCASE_PYTHON"] = str(shim)
    prefix = ["run", "python"] if runner == "poetry" else []
    drill = subprocess.run(["/bin/bash", str(ROOT / "scripts/verify/poc-drill.sh"), "demo"], env=env, capture_output=True, text=True, check=False)
    assert drill.returncode == 0 and drill.stdout.splitlines() == [*prefix, "scripts/verify/poc_drill.py", "demo"]
    entry_run = subprocess.run(["/bin/bash", str(ROOT / "scripts/showcase/m0.sh"), "demo"], env=env, capture_output=True, text=True, check=False)
    assert entry_run.returncode == 0 and entry_run.stdout.splitlines() == [*prefix, "-m", "scripts.showcase.m0", "demo"]


def test_public_python_in_the_drill_is_this_interpreter_and_never_a_shell(tmp_path):
    source = (ROOT / "scripts/verify/poc_drill.py").read_text()
    assert "shell=True" not in source and "os.system" not in source and sys.executable
    assert "from core" not in source and "import core" not in source and "psycopg" not in source


def test_poc_drill_module_exposes_the_markers_the_runner_checks():
    runner = (ROOT / "planning/sprints/015-local-poc-lifecycle/accept.sh").read_text()
    for marker in ("PASS backup", "PASS checked down", "PASS restored counts and heads", "PASS saved receipts offline",
                   "PASS new governed call", "PASS restore drill"):
        assert marker in runner and marker in poc_drill.REQUIRED_MARKERS


def test_any_other_denial_reason_fails_the_step(tmp_path):
    world = FakeWorld(deny_reason="kb_not_allowed")
    code, lines, _ = run_drill(tmp_path, world)
    assert code != 0 and any(m.startswith("FAIL deny receipt saved") for m in markers(lines))


def test_probe_failure_never_starts_or_destroys(tmp_path):
    for probe_exit in (1, 2, 4, 127):  # anything but "absent" (3) and "exists" (0) is a failed probe
        world = FakeWorld(probe_exit=probe_exit)
        code, lines, _ = run_drill(tmp_path / str(probe_exit), world)
        assert code != 0 and any(m.startswith("FAIL up") and "probe failed" in m for m in markers(lines)), lines
        assert not any(call[0][0] in {"up", "destroy"} for call in world.poc_calls)


def test_a_stack_that_existed_before_the_drill_is_never_destroyed(tmp_path):
    world = FakeWorld(existing=True)
    code, _lines, _ = run_drill(tmp_path, world)
    assert code != 0 and world.destroyed == 0 and world.refused_destroys == 0 and world.stack_exists
    assert not any(call[0][0] in {"up", "destroy"} for call in world.poc_calls)


def test_a_creator_racing_between_probe_and_up_makes_create_only_refuse_and_is_never_destroyed(tmp_path):
    world = FakeWorld(racer=True)
    code, lines, _ = run_drill(tmp_path, world)
    assert code != 0 and any(m.startswith("FAIL up") and "another creator" in m for m in markers(lines)), lines
    ups = [call for call in world.poc_calls if call[0][0] == "up"]
    assert len(ups) == 1 and "--create-only" in ups[0][0]  # the drill's only way to start a stack never adopts one
    assert world.destroyed == 0 and world.refused_destroys == 0 and world.stack_exists
    assert not any(call[0][0] == "destroy" for call in world.poc_calls)


def test_destroy_carries_the_same_owner_token_the_stack_was_created_with(tmp_path):
    world = FakeWorld()
    code, _lines, drill = run_drill(tmp_path, world)
    assert code == 0 and world.destroyed == 1 and world.refused_destroys == 0
    created = next(call for call in world.poc_calls if call[0][0] == "up")
    destroyed = next(call for call in world.poc_calls if call[0][0] == "destroy")
    assert created[1]["POC_OWNER_TOKEN"] == destroyed[1]["POC_OWNER_TOKEN"] == drill.owner_token
    assert all(drill.owner_token not in " ".join(call[0]) for call in world.poc_calls)  # in the environment, never argv


def test_a_stack_made_while_a_failed_create_only_up_was_running_is_only_torn_down_with_our_token(tmp_path):
    class FailsAfterCreating(FakeWorld):
        def poc(self, args, env=None, stdin=None):
            done = super().poc(args, env, stdin)
            if args[0] == "up" and done.returncode == 0 and not self.restored_pending():
                return Proc(1, "", "poc up refused: services not healthy")
            return done

    world = FailsAfterCreating()
    code, _lines, _ = run_drill(tmp_path, world)
    assert code != 0 and world.destroyed == 1 and world.refused_destroys == 0 and not world.stack_exists


# --- the deny must be the POLICY'S, with a signed alias and phase, and no inference -------------------------------------------

def fail_line(lines, step="deny receipt saved"):
    found = [m for m in markers(lines) if m.startswith(f"FAIL {step}")]
    assert len(found) == 1, found
    return found[0]


@pytest.mark.parametrize("reason", ["model_digest_mismatch", "model_unknown", "kb_not_allowed"])
def test_only_model_not_allowed_is_accepted_as_the_policy_deny(tmp_path, reason):
    world = FakeWorld(deny_reason=reason)
    code, lines, _ = run_drill(tmp_path, world)
    assert code != 0
    assert fail_line(lines) == ("FAIL deny receipt saved: the search was not denied with model_not_allowed "
                                f"(HTTP 403: Denied by policy (reason: {reason}))")
    assert not any(m.startswith(("PASS backup", "PASS restore drill")) for m in markers(lines))


MISSING_PHASE = "FAIL deny receipt saved: the signed receipt carries no model phase"
WRONG_PHASE = "FAIL deny receipt saved: the signed receipt does not show a model_not_allowed denial at the admission phase"


@pytest.mark.parametrize("phase,message", [(None, MISSING_PHASE), ("attempt", WRONG_PHASE), ("", WRONG_PHASE)])
def test_a_receipt_without_a_model_phase_or_with_another_phase_fails(tmp_path, phase, message):
    world = FakeWorld(phase=phase)
    code, lines, _ = run_drill(tmp_path, world)
    assert code != 0 and fail_line(lines) == message, (phase, lines)
    assert "KeyError" not in " ".join(lines)


def test_a_receipt_that_names_another_alias_fails(tmp_path):
    world = FakeWorld(name="ollama/qwen3:1.7b")
    code, lines, _ = run_drill(tmp_path, world)
    assert code != 0 and any(m.startswith("FAIL deny receipt saved") and "alias" in m for m in markers(lines))


def test_any_inference_request_seen_by_the_runtime_or_the_usage_summary_fails(tmp_path):
    for index, kwargs in enumerate(({"runtime_inference": 1}, {"usage_requests": 1})):
        world = FakeWorld(**kwargs)
        code, lines, _ = run_drill(tmp_path / str(index), world)
        assert code != 0 and any(m.startswith("FAIL deny receipt saved") and "model was reached" in m for m in markers(lines)), lines


def test_the_drill_reports_an_observed_zero_inference_count(tmp_path):
    world = FakeWorld()
    code, _lines, drill = run_drill(tmp_path, world)
    assert code == 0 and drill.report["inference_requests"] == 0 and drill.report["usage_requests"] == 0
    assert drill.report["deny_reasons"] == ["model_not_allowed"] * 2 and drill.report["deny_phases"] == ["admission"] * 2
    assert world.runtime.closed


def test_the_metadata_runtime_lists_the_locked_digests_and_counts_every_other_request(tmp_path):
    import urllib.error
    import urllib.request

    runtime = poc_drill.MetadataRuntime(ROOT / "models.lock", host_name="127.0.0.1")
    try:
        tags = json.loads(urllib.request.urlopen(runtime.url + "/api/tags", timeout=5).read())  # noqa: S310
        names = {m["name"]: m["digest"] for m in tags["models"]}
        assert names["qwen3:4b-instruct-2507-q4_K_M"] == "0edcdef34593eac1aa2be9c7d06c432dcf81945adca5eca2f27662c18f168ba0"
        assert runtime.inference_requests() == 0  # metadata reads are not inference
        for path in ("/api/generate", "/api/chat", "/api/embed"):
            with pytest.raises(urllib.error.HTTPError):
                urllib.request.urlopen(urllib.request.Request(runtime.url + path, data=b"{}", method="POST"), timeout=5)  # noqa: S310
        assert runtime.inference_requests() == 3
    finally:
        runtime.close()
