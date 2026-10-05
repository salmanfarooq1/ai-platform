"""Sprint 009 units that need no database: run token format, event cleaning and classification, the settings and the
composition root for `AGENT_RUNTIME=openshell`, and the entry program's parsing."""
import io
import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from adapters.openshell_events import classify, event_from_log, event_from_platform, keep
from adapters.openshell_runtime import OpenShellAgentRuntime
from adapters.registry import build_adapters, build_local_runtime
from adapters.sandbox_events import DETAIL_BYTES, clean_detail, redact
from core.identity.models import Principal
from core.identity.run_tokens import RunGrant, generate_run_token, is_run_token, parse_run_token
from core.settings import Settings
from ports import SandboxEventKind
from sandbox_agent import entry

pytestmark = pytest.mark.unit
NOW = datetime.now(timezone.utc)


# ---------------------------------------------------------------------------------------------- run tokens

def test_a_run_token_has_its_own_tag_and_parses_back_into_prefix_and_secret():
    prefix, token, secret_hash = generate_run_token()
    assert token.startswith("grt_") and is_run_token(token) and not is_run_token("gap_abcdefgh_" + "x" * 43)
    parsed = parse_run_token(token)
    assert parsed is not None and parsed[0] == prefix and len(secret_hash) == 64
    assert token not in secret_hash and parsed[1] not in secret_hash  # only a hash is kept
    assert generate_run_token()[1] != token


@pytest.mark.parametrize("bad", ["", "grt_", "grt_short_" + "x" * 40, "grt_abcdefgh_short", "grt_abcdefgh_" + "x" * 40 + "\n", "gap_abcdefgh_" + "x" * 43])
def test_a_malformed_run_token_does_not_parse(bad):
    assert parse_run_token(bad) is None


def test_a_grant_covers_only_the_routes_of_its_own_run():
    run, other = uuid4(), uuid4()
    grant = RunGrant(Principal(uuid4(), uuid4(), "agent", frozenset({"agent"})), run, {}, uuid4(), NOW)
    assert grant.covers(f"/v1/sandbox/runs/{run}/model") and grant.covers(f"/v1/sandbox/runs/{run}/tools/retrieve_chunks")
    for path in (f"/v1/sandbox/runs/{other}/model", "/v1/agent/runs", "/v1/search", f"/v1/sandbox/runs/{run}", f"/v1/sandbox/runs/{run}x/model", "/v1/decisions"):
        assert not grant.covers(path), path


def test_the_token_is_not_in_the_repr_of_what_holds_it():
    from core.identity.run_tokens import IssuedRunToken

    _, token, _ = generate_run_token()
    assert token not in repr(IssuedRunToken(token=token))


# ---------------------------------------------------------------------------------------------- event details

def test_unknown_keys_and_nested_values_are_dropped():
    detail = clean_detail({"host": "api.example.com", "port": 443, "environment": {"K": "V"}, "stdin": "the question", "message": "refused"})
    assert detail == {"host": "api.example.com", "port": 443, "message": "refused"}


def test_values_are_cut_and_the_whole_detail_stays_under_the_table_limit():
    detail = clean_detail({"host": "h" * 5000, "path": "/p" * 5000, "message": "m" * 5000, "reason": "r" * 5000, "limit": "l" * 5000})
    assert all(len(v) <= 300 for v in detail.values() if isinstance(v, str))
    assert len(json.dumps(detail)) <= DETAIL_BYTES < 2048


def test_credentials_are_replaced_in_every_value_and_the_runs_own_token_always():
    _, token, _ = generate_run_token()
    text = f"call to https://x.test/a?api_key=SECRETVALUE with Bearer abc.def and {token} and gap_abcdefgh_{'k' * 30} and custom-secret-1"
    cleaned = clean_detail({"message": text, "path": token}, secrets=["custom-secret-1"])
    blob = json.dumps(cleaned)
    for leaked in ("SECRETVALUE", "abc.def", token, "custom-secret-1", "gap_abcdefgh_"):
        assert leaked not in blob
    assert "[redacted]" in blob and redact("plain text") == "plain text"


# ---------------------------------------------------------------------------------------------- what OpenShell says

@pytest.mark.parametrize("level, message, fields, kind", [
    ("WARN", "network connection denied by policy", {"host": "api.example.com", "port": "443"}, SandboxEventKind.NETWORK_DENIED),
    ("INFO", "proxy: CONNECT blocked for host evil.test", {}, SandboxEventKind.NETWORK_DENIED),
    ("WARN", "landlock: read of /etc/hostname denied", {"path": "/etc/hostname"}, SandboxEventKind.FILE_DENIED),
    ("ERROR", "filesystem access not allowed", {"path": "/root/x"}, SandboxEventKind.FILE_DENIED),
    ("ERROR", "process killed: out of memory", {}, SandboxEventKind.LIMIT_HIT),
    ("INFO", "sandbox ready", {}, SandboxEventKind.LOG),
    ("INFO", "listening on the proxy port", {}, SandboxEventKind.LOG),            # a network word alone is not a denial
    ("INFO", "request denied", {}, SandboxEventKind.LOG),                          # a deny word alone is not a network or file denial
    ("INFO", "memory limit is 512Mi", {}, SandboxEventKind.LOG),                  # a limit word at INFO is not a limit hit
])
def test_log_lines_are_classified_conservatively_and_unknown_lines_stay_logs(level, message, fields, kind):
    assert classify(level, message, fields)[0] is kind


def test_a_denied_connection_keeps_the_host_and_port_from_the_fields():
    event = event_from_log("WARN", "egress denied", {"dst_host": "api.example.com", "dst_port": "443"}, NOW)
    assert event.kind is SandboxEventKind.NETWORK_DENIED and event.detail["host"] == "api.example.com" and event.detail["port"] == 443


def test_a_platform_event_is_classified_from_its_reason_and_message():
    event = event_from_platform("Warning", "NetworkDenied", "connection to evil.test refused", {"host": "evil.test"}, NOW)
    assert event is not None and event.kind is SandboxEventKind.NETWORK_DENIED
    assert event_from_platform("Normal", "Started", "container started", {}, NOW) is None  # plumbing: no row


# Lines copied from a live OpenShell 0.1.2 gateway on a Docker driver (the direct provider call of the check probe), and from
# the project's "Sandbox Logging" page for the shapes this run did not produce.
LIVE_LINES = [
    ("NET:OPEN [MED] DENIED /usr/bin/python3.10(0) -> api.openai.com:443 [reason:transparent_tcp_policy_denied]", SandboxEventKind.NETWORK_DENIED, "api.openai.com", 443),
    ("NET:REFUSE [MED] DENIED api.openai.com [reason:policy_dns_ineligible]", SandboxEventKind.NETWORK_DENIED, "api.openai.com", None),
    ("Denied staged transparent connection", SandboxEventKind.NETWORK_DENIED, None, None),
    ("NET:OPEN [MED] DENIED /usr/bin/curl(1618) -> 169.254.169.254:80 [policy:- engine:ssrf] [reason:resolves to always-blocked address]", SandboxEventKind.NETWORK_DENIED, "169.254.169.254", 80),
    ("HTTP:POST [MED] DENIED POST http://api.github.com/user/repos [policy:github_api engine:opa]", SandboxEventKind.NETWORK_DENIED, None, None),
]
PLUMBING = [
    "SSH:OPEN [INFO] ALLOWED", "EVENT [INFO] ssh relay open (channel_id=1, target=unix:/run/openshell/ssh.sock)", "NET:LISTEN [INFO] 127.0.0.1:3128",
    "CONFIG:LOADED [INFO] Acknowledged initial policy revision as loaded [version:2] [hash:a5be]", "Isolation boundary attached",
    "CONFIG:OBSERVATION [INFO] Policy DNS staged unapproved name api.openai.com synthetic=198.18.0.2 for TCP policy review",
    "NET:OPEN [INFO] ALLOWED /usr/bin/curl(58) -> api.github.com:443 [policy:github_api engine:opa]",
]


@pytest.mark.parametrize("line, kind, host, port", LIVE_LINES)
def test_the_lines_a_real_gateway_wrote_for_a_refusal_are_network_denials_with_the_host_and_port(line, kind, host, port):
    event = event_from_log("INFO", line, {}, NOW)
    assert event is not None and event.kind is kind
    assert event.detail.get("host") == host and event.detail.get("port") == port


@pytest.mark.parametrize("line", PLUMBING)
def test_supervisor_plumbing_and_allowed_calls_are_not_kept_as_rows(line):
    assert event_from_log("INFO", line, {}, NOW) is None


def test_a_warning_or_a_medium_severity_line_that_is_not_a_refusal_is_kept_as_a_log():
    assert keep(SandboxEventKind.LOG, "WARN", "something odd") and keep(SandboxEventKind.LOG, "INFO", "OCSF CONFIG:OTHER [MED] Skipping inaccessible Landlock path")
    assert not keep(SandboxEventKind.LOG, "INFO", "plain startup line") and keep(SandboxEventKind.NETWORK_DENIED, "INFO", "x")
    assert event_from_log("INFO", "CONFIG:OTHER [MED] Skipping inaccessible Landlock path (best-effort) [path:/opt/data]", {}, NOW).kind is SandboxEventKind.LOG  # type: ignore[union-attr]


# ---------------------------------------------------------------------------------------------- settings and registry

def hosted(**env):
    return Settings(mode="local", agent_runtime="openshell", sandbox_gateway_url="http://gateway.internal:8000", **env)


def test_the_default_runtime_is_unchanged_and_openshell_is_opt_in():
    assert Settings(mode="local").agent_runtime == "queued"
    assert hosted().agent_runtime == "openshell"


def test_openshell_needs_a_gateway_url_the_sandbox_can_reach():
    with pytest.raises(ValueError, match="SANDBOX_GATEWAY_URL"):
        Settings(mode="local", agent_runtime="openshell")
    for bad in ("gateway.internal:8000", "ftp://gateway", "http://", "not a url"):
        with pytest.raises(ValueError, match="SANDBOX_GATEWAY_URL"):
            Settings(mode="local", agent_runtime="openshell", sandbox_gateway_url=bad)


@pytest.mark.parametrize("url, egress", [
    ("http://gateway.internal:8000", ("gateway.internal", 8000)), ("http://gateway.internal", ("gateway.internal", 80)),
    ("https://api.example.com/base", ("api.example.com", 443)),
])
def test_the_egress_route_is_the_host_and_port_of_the_gateway_url(url, egress):
    assert Settings(mode="local", sandbox_gateway_url=url).sandbox_egress() == egress


@pytest.mark.parametrize("env", [{"sandbox_network_binaries": ""}, {"sandbox_network_binaries": "python3"}, {"sandbox_work_dir": "work"}, {"sandbox_work_dir": "/"}, {"sandbox_read_only_paths": "usr"}, {"sandbox_wall_seconds": 0}, {"sandbox_wall_seconds": 4000}])
def test_bad_sandbox_limits_and_paths_are_refused(env):
    with pytest.raises(ValueError):
        Settings(mode="local", **env)


def test_the_queue_runtime_serves_the_api_and_the_worker_gets_the_sandbox_runtime(tmp_path):
    from adapters.job_runtime import JobAgentRuntime
    from tests.fake_sandbox import FakeSandboxDriver

    settings = hosted(object_store_dir=str(tmp_path))
    assert isinstance(build_adapters(settings, pool=object()).runtime, JobAgentRuntime)  # the API queues the run
    local = build_local_runtime(settings, runner=None, pool=object(), sandbox_driver=FakeSandboxDriver(lambda p: None))  # type: ignore[arg-type,return-value]
    assert isinstance(local, OpenShellAgentRuntime)
    default = build_local_runtime(Settings(mode="local"), runner=None, pool=object())
    assert not isinstance(default, OpenShellAgentRuntime)


# ---------------------------------------------------------------------------------------------- the entry program

class Recorder:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []

    def __call__(self, url, body, headers):
        self.calls.append((url, body, dict(headers)))
        return self.responses.pop(0)


ENV = {"GATEWAY_URL": "http://gateway.internal:8000/", "RUN_TOKEN": "grt_abcdefgh_" + "t" * 43, "EXECUTION_ID": str(uuid4()), "WORK_DIR": "/sandbox/work"}


def run_entry(argv, stdin, post, env=None, files=None):
    out, err = io.StringIO(), io.StringIO()
    opened = {}

    def open_file(path, mode="r", **kwargs):
        if path not in (files or {}) and "w" not in mode:
            raise PermissionError(path)
        opened[path] = io.StringIO()
        handle = opened[path]
        handle.close = lambda: None  # type: ignore[method-assign]
        return handle

    code = entry.main(argv, ENV if env is None else env, io.StringIO(stdin), out, err, post, open_file)
    return code, out.getvalue(), err.getvalue(), opened


def test_the_agent_calls_only_the_runs_own_gateway_routes_with_its_token_and_prints_one_json_result():
    chunk = {"document_id": "gdpr.md", "source_filename": "gdpr.md", "chunk_index": 0, "score": 0.5, "content": "Notify within 72 hours."}
    post = Recorder([(200, {"result": json.dumps({"count": 1, "chunks": [chunk]})}), (200, {"text": "72 hours [1].\nConfidence: 0.8", "model": "m", "usage": {"prompt_tokens": 5}})])
    code, out, err, opened = run_entry(["answer"], json.dumps({"input": {"question": "deadline?", "namespace": "legal"}}), post)
    assert code == 0 and err == ""
    base = f"http://gateway.internal:8000/v1/sandbox/runs/{ENV['EXECUTION_ID']}"
    assert [c[0] for c in post.calls] == [f"{base}/tools/retrieve_chunks", f"{base}/model"]
    assert all(c[2]["Authorization"] == f"Bearer {ENV['RUN_TOKEN']}" for c in post.calls)
    assert post.calls[0][1] == {"arguments": {"query": "deadline?", "namespace": "legal", "top_k": 5, "mode": "hybrid"}}
    result = json.loads(out.strip().splitlines()[-1])["result"]
    assert result["answer"] == "72 hours [1]." and result["confidence"] == 0.8 and result["tool_calls"] == 1 and result["denied"] is None
    assert result["citations"][0]["source_filename"] == "gdpr.md"
    assert ENV["RUN_TOKEN"] not in out and "deadline?" not in out  # neither the token nor the question is printed
    assert "/sandbox/work/notes.json" in opened  # the only file it writes is under the work directory


def test_a_gateway_deny_ends_the_run_with_a_partial_answer_that_names_the_reason():
    deny = (403, {"error": {"code": "policy_denied", "message": "Denied by policy (reason: tool_argument_not_allowed)", "request_id": "r"}})
    code, out, _, _ = run_entry(["answer"], json.dumps({"input": {"question": "q"}}), Recorder([deny]))
    result = json.loads(out)["result"]
    assert code == 0 and result["denied"] == "tool_argument_not_allowed" and result["tool_calls"] == 0 and result["confidence"] == 0.0


def test_no_chunks_means_no_model_call():
    post = Recorder([(200, {"result": json.dumps({"count": 0, "result": "No relevant chunks found"})})])
    code, out, _, _ = run_entry(["answer"], json.dumps({"input": {"question": "q"}}), post)
    assert code == 0 and len(post.calls) == 1 and json.loads(out)["result"]["confidence"] == 0.0


def test_a_missing_environment_is_a_clear_exit_not_a_crash_and_prints_no_result():
    code, out, err, _ = run_entry(["answer"], "{}", Recorder([]), env={"GATEWAY_URL": "http://x"})
    assert code == 2 and out == "" and "RUN_TOKEN" in err and "EXECUTION_ID" in err


def test_a_failure_prints_the_exception_type_only():
    def boom(url, body, headers):
        raise RuntimeError("the question was: secret text")

    code, out, err, _ = run_entry(["answer"], json.dumps({"input": {"question": "secret text"}}), boom)
    assert code == 1 and out == "" and err.strip() == "agent failed: RuntimeError"


def test_the_check_reports_what_failed_and_exits_zero():
    def refuse(url, body, headers):
        raise ConnectionRefusedError("refused")

    code, out, _, _ = run_entry(["check"], "", refuse)
    assert code == 0 and json.loads(out)["result"] == {
        "provider_call": "failed (ConnectionRefusedError)", "outside_read": "failed (PermissionError)", "outside_path": "/var/lib/dpkg/status"}
    open_post = Recorder([(200, {})])
    code, out, _, _ = run_entry(["check"], "", open_post, files={"/var/lib/dpkg/status": True})
    assert json.loads(out)["result"]["provider_call"] == "succeeded" and json.loads(out)["result"]["outside_read"] == "succeeded"  # a leaky sandbox is reported as such


def test_the_check_reads_another_file_when_told_to_and_a_missing_file_is_not_a_pass():
    def refuse(url, body, headers):
        raise ConnectionRefusedError("refused")

    code, out, _, opened = run_entry(["check"], "", refuse, env={**ENV, "CHECK_OUTSIDE_PATH": "/srv/data"}, files={"/srv/data": True})
    assert json.loads(out)["result"]["outside_path"] == "/srv/data" and json.loads(out)["result"]["outside_read"] == "succeeded"

    def missing(path, mode="r", **kwargs):
        raise FileNotFoundError(path)

    result = entry.check(refuse, missing, "/nope")
    assert result["outside_read"] == "failed (FileNotFoundError)"  # the verify script requires PermissionError: this is inconclusive


def test_an_unknown_command_is_refused():
    code, out, err, _ = run_entry(["rm"], "", Recorder([]))
    assert code == 2 and out == "" and "unknown command" in err


def test_the_entry_file_is_standard_library_only():
    import ast
    from pathlib import Path

    tree = ast.parse(Path(entry.__file__).read_text())
    modules = {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    modules |= {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    import sys

    assert modules <= set(sys.stdlib_module_names), modules - set(sys.stdlib_module_names)
