"""`poc admin <stack> <command> ...`: the identity and policy CLI, run against one stack's own Postgres.

A POC stack publishes no database port, so the host cannot reach it with `scripts/admin/identity.py` directly. This runs
that same CLI inside the stack's app image (a one-off `compose run`, never a shell), with the single file mounted read-only.
The owner-role connection string travels in the child environment by name (`-e MIGRATION_DATABASE_URL`), never in argv,
and the CLI's own `--dsn` option is refused so a different database cannot be targeted. A policy is read from stdin when
the file argument is `-`. Output is the CLI's own (`create-key` prints the key once, to the caller only).
"""
import re
from collections.abc import Mapping, Sequence
from pathlib import Path

from scripts.poc_lib.context import load_context
from scripts.poc_lib.runner import CommandError, LocalRunner, Runner
from scripts.poc_lib.up import PocError, owner_dsn, validate_stack

SUBCOMMANDS = frozenset({"create-tenant", "create-kb", "create-principal", "create-key", "revoke-key", "list-keys",
                         "set-policy", "set-retention", "show-policy"})
CLI = Path("scripts/admin/identity.py")
TARGET = "/app/identity_admin.py"  # one read-only file in the image's working directory; nothing else is mounted


def _redact(text: str, environ: Mapping[str, str]) -> str:
    text = re.sub(r"(://[^:/@\s]+):[^@\s]*@", r"\1:***@", text)
    password = environ.get("POSTGRES_PASSWORD", "postgres")
    return text.replace(password, "***") if password else text


def run(root: Path, stack: str, args: Sequence[str], *, runner: Runner | None = None,
        environ: Mapping[str, str] | None = None, stdin: bytes | None = None) -> str:
    """Run one identity command for `stack` and return its stdout. Raises PocError on any refusal or failure."""
    validate_stack(stack)
    args = list(args)
    if not args or args[0] not in SUBCOMMANDS:
        raise PocError("unknown identity command; use one of: " + ", ".join(sorted(SUBCOMMANDS)))
    if any(a == "--dsn" or a.startswith("--dsn=") for a in args):
        raise PocError("--dsn is not accepted: the command always runs against this stack's own database")
    data = None
    if args[0] == "set-policy" and args[-1] == "-":
        if not stdin:
            raise PocError("set-policy with '-' needs the policy document on stdin")
        args[-1] = "/dev/stdin"
        data = stdin
    from scripts.poc_backup import pending  # imported here: pending depends on this package's up module

    context = load_context(root, stack, runner=runner or LocalRunner(), environ=environ)
    pending.refuse_if_pending(context.stack_dir, "admin")  # the database is being restored: there is nothing to administer
    cli = context.root / CLI
    if cli.is_symlink() or not cli.is_file():
        raise PocError("the identity admin CLI (scripts/admin/identity.py) was not found in this checkout")
    argv = context.argv("run", "--rm", "--no-deps", "-T", "-e", "MIGRATION_DATABASE_URL", "-v", f"{cli}:{TARGET}:ro",
                        "api", "python", TARGET, *args)
    env = {**context.env, "MIGRATION_DATABASE_URL": owner_dsn(context.environ)}
    try:
        return context.runner.run(argv, env=env, input=data).text
    except CommandError as exc:
        lines = _redact(exc.stderr.decode("utf-8", "replace"), context.environ).strip().splitlines()
        raise PocError(f"identity admin command failed ({exc.returncode}): {lines[-1] if lines else 'no message'}") from None
