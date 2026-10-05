"""Check that the OpenShell SDK surface `adapters/openshell_driver.py` uses exists in the installed `openshell` package.

This needs no gateway and no sandbox: it imports the pinned SDK, checks the version, checks that every call and message
field the driver uses is there, builds the sandbox policy message the driver sends, and round-trips it through protobuf.
It says nothing about whether a real gateway accepts the policy (that is `scripts/verify/openshell.sh`).

Usage: PYTHONPATH=<dir with the openshell wheel unpacked> python scripts/verify/openshell_sdk_surface.py
"""
import inspect
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

PINNED = "0.1.2"
checks: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, note: str = "") -> None:
    checks.append((name, ok, note))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  ' + note) if note else ''}")


def main() -> int:
    try:
        import openshell
        from openshell import SandboxClient
        from openshell._proto import openshell_pb2, sandbox_pb2
    except ImportError as exc:
        print(f"SKIP  the openshell package is not importable ({exc}); see docs/operations.md")
        return 2
    check("openshell version is the pinned one", openshell.__version__ == PINNED, openshell.__version__)
    for method in ("create_from_template", "exec_stream", "exec", "delete", "wait_ready", "sandbox_templates", "close", "from_active_cluster"):
        check(f"SandboxClient.{method} exists", hasattr(SandboxClient, method))
    params = inspect.signature(SandboxClient.exec_stream).parameters
    check("exec_stream takes workdir, env, stdin, timeout_seconds", {"workdir", "env", "stdin", "timeout_seconds"} <= set(params))
    template_params = inspect.signature(openshell.SandboxTemplateClient.create).parameters
    check("template create takes image, cpu, memory", {"image", "cpu", "memory"} <= set(template_params))
    for message, fields in (
        (sandbox_pb2.SandboxPolicy, ("filesystem", "landlock", "process", "network_policies")),
        (sandbox_pb2.FilesystemPolicy, ("include_workdir", "read_only", "read_write")),
        (sandbox_pb2.NetworkEndpoint, ("host", "port", "protocol", "enforcement")),
        (sandbox_pb2.NetworkPolicyRule, ("name", "endpoints", "binaries")),
        (openshell_pb2.SandboxSpec, ("policy", "template", "environment")),
        (openshell_pb2.WatchSandboxRequest, ("sandbox", "follow_logs", "follow_events", "workspace_scope")),
        (openshell_pb2.SandboxLogLine, ("level", "message", "fields", "event_time")),
        (openshell_pb2.PlatformEvent, ("type", "reason", "message", "metadata", "event_time")),
    ):
        names = {f.name for f in message.DESCRIPTOR.fields}
        check(f"{message.DESCRIPTOR.name} has {', '.join(fields)}", set(fields) <= names)

    from adapters.openshell_driver import SdkMessages
    from ports.sandbox import EgressRule, SandboxLaunch, SandboxLimits, SandboxPolicy

    launch = SandboxLaunch(
        run_id="00000000-0000-4000-8000-000000000000", command=("python3", "-c", "pass", "answer"),
        policy=SandboxPolicy(egress=(EgressRule("gateway.internal", 8000),), work_dir="/sandbox/work", limits=SandboxLimits("1", "512Mi", 300), network_binaries=("/usr/bin/python3*",)),
    )
    policy = SdkMessages().policy(launch)
    check("the policy has one network route, to the gateway", list(policy.network_policies) == ["gateway"]
          and [(e.host, e.port) for e in policy.network_policies["gateway"].endpoints] == [("gateway.internal", 8000)])
    check("the policy names the interpreter as the only binary that may use the route", [b.path for b in policy.network_policies["gateway"].binaries] == ["/usr/bin/python3*"])
    check("the policy has one read-write directory", list(policy.filesystem.read_write) == ["/sandbox/work"] and not policy.filesystem.include_workdir)
    spec = SdkMessages().spec(launch)
    request = SdkMessages().watch_request("default", launch.run_id)
    check("the watch request follows logs and events of this sandbox", request.follow_logs and request.follow_events and request.sandbox == launch.run_id)
    again = openshell_pb2.SandboxSpec.FromString(spec.SerializeToString())
    check("the sandbox spec survives a protobuf round trip", again == spec)

    from adapters.openshell_events import event_from_log

    event = event_from_log("WARN", "network connection denied", {"host": "api.example.com", "port": "443"}, datetime.now(timezone.utc))
    check("a denied-connection log line is classified (rule check only)", event.kind.value == "network_denied")
    failed = [name for name, ok, _ in checks if not ok]
    print(f"\n{len(checks) - len(failed)} of {len(checks)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
