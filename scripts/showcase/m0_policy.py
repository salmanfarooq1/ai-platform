"""Operator policy setup and compare-and-swap cleanup for the browser journey."""
import argparse
import json
import os
from pathlib import Path

from config import LLM_CONFIG
from core.identity.admin import admin_connection
from gateway.admin import show_policy
from scripts.showcase.m0 import publish_journey_policy
from scripts.showcase.policy_restore import restore_policy


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("status", "deny", "restore"))
    parser.add_argument("state_dir", type=Path)
    args = parser.parse_args()
    state = json.loads((args.state_dir / "state.json").read_text())
    journal = args.state_dir / "policy-journal.json"
    owner_dsn = state["owner_dsn"]
    with admin_connection(owner_dsn) as conn:
        if args.action == "status":
            head = show_policy(conn, state["tenant"])
            if head is None or head["document"]["allowed_models"] != "*":
                raise RuntimeError("baseline does not allow models")
            print("baseline allowed")
        elif args.action == "deny":
            if journal.exists():
                raise RuntimeError("policy journal already exists")
            baseline, version, _ = publish_journey_policy(conn, state["tenant"], [state["allowed_kb"]], LLM_CONFIG["model"])
            try:
                fd = os.open(journal, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "w") as out:
                    json.dump({"baseline": baseline, "version": version}, out)
            except BaseException:
                restore_policy(conn, state["tenant"], version, baseline)
                raise
            print("journey deny")
        else:
            saved = json.loads(journal.read_text())
            restored = restore_policy(conn, state["tenant"], saved["version"], saved["baseline"])
            if restored is None:
                raise RuntimeError("policy head changed; restore refused")
    if args.action == "restore":
        journal.unlink()
        print("baseline restored as new version")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
