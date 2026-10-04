"""Identity admin CLI. Runs as the owner role (MIGRATION_DATABASE_URL, or --dsn).

    poetry run python scripts/admin/identity.py create-tenant acme --name "Acme Ltd"
    poetry run python scripts/admin/identity.py create-kb acme legal --description "Data protection law"
    poetry run python scripts/admin/identity.py create-principal acme service ingest-bot
    poetry run python scripts/admin/identity.py create-key <principal-id> --scopes query kb:read
    poetry run python scripts/admin/identity.py revoke-key <prefix>
    poetry run python scripts/admin/identity.py list-keys [--tenant acme]
    poetry run python scripts/admin/identity.py set-policy acme policy.json [--by alice]
    poetry run python scripts/admin/identity.py show-policy acme

`create-key` prints the full key once. Only its SHA-256 hash is stored, so a lost key cannot be
recovered, only replaced. Never paste a key into a ticket, a log or the repo.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.identity.admin import (  # noqa: E402 - needs the sys.path line above
    AdminError,
    admin_connection,
    create_kb,
    create_key,
    create_principal,
    create_tenant,
    list_keys,
    revoke_key,
)
from core.identity.models import ALL_SCOPES, PRINCIPAL_KINDS  # noqa: E402
from core.settings import get_settings  # noqa: E402
from gateway.admin import set_policy, show_policy  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Identity admin for the platform")
    parser.add_argument("--dsn", help="owner-role database URL (default: MIGRATION_DATABASE_URL / settings)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("create-tenant", help="create a tenant (and its `default` knowledge base)")
    p.add_argument("slug")
    p.add_argument("--name")
    p.add_argument("--no-default-kb", action="store_true")

    p = sub.add_parser("create-kb", help="create a knowledge base for a tenant")
    p.add_argument("tenant")
    p.add_argument("slug")
    p.add_argument("--description", default="")

    p = sub.add_parser("create-principal", help="create a user, service or agent principal")
    p.add_argument("tenant")
    p.add_argument("kind", choices=PRINCIPAL_KINDS)
    p.add_argument("name")

    p = sub.add_parser("create-key", help="create an API key (the secret is printed once)")
    p.add_argument("principal_id")
    p.add_argument("--scopes", nargs="+", required=True, choices=sorted(ALL_SCOPES))

    p = sub.add_parser("revoke-key", help="revoke a key by its prefix")
    p.add_argument("prefix")

    p = sub.add_parser("list-keys", help="list key metadata (never secrets or hashes)")
    p.add_argument("--tenant")

    p = sub.add_parser("set-policy", help="publish a new policy version for a tenant from a JSON file")
    p.add_argument("tenant")
    p.add_argument("file", type=Path)
    p.add_argument("--by", default="admin-cli", help="who is publishing it (recorded as created_by)")

    p = sub.add_parser("show-policy", help="print a tenant's active policy")
    p.add_argument("tenant")
    return parser


def run(args: argparse.Namespace) -> int:
    dsn = args.dsn or get_settings().migration_dsn
    with admin_connection(dsn) as conn:
        if args.command == "create-tenant":
            tenant_id = create_tenant(conn, args.slug, args.name, default_kb=not args.no_default_kb)
            print(f"tenant {args.slug} created: id={tenant_id}")
        elif args.command == "create-kb":
            create_kb(conn, args.tenant, args.slug, args.description)
            print(f"knowledge base {args.slug} created for tenant {args.tenant}")
        elif args.command == "create-principal":
            principal_id = create_principal(conn, args.tenant, args.kind, args.name)
            print(f"principal {args.name} created: id={principal_id}")
        elif args.command == "create-key":
            key = create_key(conn, args.principal_id, args.scopes)
            print(f"key created: prefix={key.prefix} scopes={','.join(sorted(args.scopes))}")
            print(f"KEY (shown once, store it now): {key.token}")
        elif args.command == "revoke-key":
            if not revoke_key(conn, args.prefix):
                print(f"no active key with prefix {args.prefix}", file=sys.stderr)
                return 1
            print(f"key {args.prefix} revoked")
        elif args.command == "list-keys":
            for row in list_keys(conn, args.tenant):
                state = "revoked" if row["revoked_at"] else "active"
                print(f"{row['prefix']}  {row['tenant']}/{row['principal']} ({row['kind']})  "
                      f"scopes={','.join(row['scopes'])}  {state}  last_used={row['last_used_at']}")
        elif args.command == "set-policy":
            try:
                document = json.loads(args.file.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise AdminError(f"cannot read policy file: {exc}") from exc
            version = set_policy(conn, args.tenant, document, args.by)
            print(f"policy version {version} is now active for tenant {args.tenant}")
        elif args.command == "show-policy":
            policy = show_policy(conn, args.tenant)
            if policy is None:
                print(f"tenant {args.tenant} has no active policy (platform default applies)")
            else:
                print(f"version {policy['version']} by {policy['created_by']} at {policy['created_at']}")
                print(json.dumps(policy["document"], indent=2, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return run(args)
    except AdminError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
