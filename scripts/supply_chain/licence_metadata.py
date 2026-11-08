"""Validate tool metadata and fixtures against the same OSI list and reviewed exceptions."""
import argparse
import json
import sys
import tomllib
from pathlib import Path

from license_expression import AND, OR, LicenseSymbol, LicenseWithExceptionSymbol, get_spdx_licensing
from packaging.markers import default_environment
from packaging.utils import canonicalize_name

if __package__:
    from .artifact_licences import numpy_correction
else:
    from artifact_licences import numpy_correction

ROOT = Path(__file__).resolve().parents[2]
CHAIN = ROOT / "scripts/supply_chain"
LICENSING = get_spdx_licensing()
REVIEWED_COMBINATIONS = {"GPL-3.0-or-later WITH GCC-exception-3.1"}


def _name_key(name: str) -> str:
    """npm identities are exact; only Python distribution names use PEP 503 normalization."""
    return name if name.startswith("npm:") else canonicalize_name(name)


def main_packages() -> list[str]:
    lock = tomllib.loads((ROOT / "poetry.lock").read_text())
    environment = default_environment()
    names = []
    from packaging.markers import Marker

    for package in lock["package"]:
        if "main" not in package["groups"]:
            continue
        marker = package.get("markers", "")
        if isinstance(marker, dict):
            marker = marker.get("main", "")
        if not marker or Marker(marker).evaluate(environment):
            names.append(package["name"])
    return names


def exceptions() -> dict[tuple[str, str], str]:
    result = {}
    for line in (CHAIN / "licence-exceptions.txt").read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        name, version, expression, source, reason = line.split("|", 4)
        if not source.startswith("https://") or not reason.strip():
            raise ValueError("exception needs a primary source and reason")
        result[(_name_key(name), version)] = expression
    return result


def permitted(expression: str, allowed: set[str]) -> bool:
    try:
        tree = LICENSING.parse(expression, validate=True, strict=True)
    except Exception:
        return False

    def evaluate(node):
        if isinstance(node, LicenseWithExceptionSymbol):
            # Only the exact, separately reviewed SPDX combination grants an extra permission.
            return str(node) in REVIEWED_COMBINATIONS
        if isinstance(node, LicenseSymbol):
            return str(node) in allowed
        if isinstance(node, AND):
            return all(evaluate(child) for child in node.args)
        if isinstance(node, OR):
            return any(evaluate(child) for child in node.args)
        return False

    return tree is not None and evaluate(tree)


def validate(rows: list[dict], required: list[str] | None = None) -> list[str]:
    allowed = {x.strip() for x in (CHAIN / "osi-licences.txt").read_text().splitlines() if x.strip() and not x.startswith("#")}
    reviewed = exceptions()
    seen = set()
    raw_allowed = []
    problems = []
    for row in rows:
        name = row.get("name", row.get("Name", ""))
        version = row.get("version", row.get("Version", ""))
        raw = row.get("license", row.get("License", "UNKNOWN"))
        key = _name_key(name)
        seen.add(key)
        reviewed_expression = reviewed.get((key, version))
        expression = reviewed_expression if reviewed_expression is not None else raw
        if key == "numpy":
            expression = numpy_correction(version)
        # Owner decision D2: PSF-2.0 passes only through an exact name and version line in licence-exceptions.txt.
        owner_reviewed_psf = reviewed_expression == "PSF-2.0"
        if not permitted(expression, allowed) and not owner_reviewed_psf:
            # Raw metadata may contain entire licence text. Keep logs concise.
            problems.append(f"{name}=={version}: licence not approved: {raw.splitlines()[0]}")
        elif expression == raw:
            raw_allowed.append(raw)
    if required:
        problems.extend(f"missing installed main package: {name}" for name in required if _name_key(name) not in seen)
    if problems:
        raise ValueError("\n".join(problems))
    print(f"licence gate ok: {len(rows)} packages", file=sys.stderr)
    return raw_allowed


def npm_inventory() -> set[str]:
    """Reconcile collector identities against lock locations and installed manifests.

    npm lock v3 marks development-only packages. Optional packages absent from the
    installed platform are excluded; every installed production optional is required.
    The private first-party root is explicitly outside the third-party inventory.
    """
    ui = ROOT / "ui"
    manifest = json.loads((ui / "package.json").read_text())
    lock = json.loads((ui / "package-lock.json").read_text())
    if manifest.get("private") is not True or lock.get("lockfileVersion") != 3:
        raise ValueError("npm inventory requires a private root and lockfile version 3")
    packages = lock["packages"]
    if any(packages[""].get(key) != manifest.get(key) for key in ("name", "version", "dependencies")):
        raise ValueError("npm root manifest differs from lock")
    for name in manifest.get("dependencies", {}):
        if f"node_modules/{name}" not in packages:
            raise ValueError(f"missing direct production dependency in lock: {name}")
    identities = set()
    absent_optional = 0
    for location, entry in packages.items():
        if not location or entry.get("dev") is True:
            continue
        if not location.startswith("node_modules/") or ".." in Path(location).parts or entry.get("link"):
            raise ValueError(f"unsupported npm production lock location: {location}")
        path = ui / location / "package.json"
        if not path.exists() and entry.get("optional") is True:
            absent_optional += 1
            continue
        installed = json.loads(path.read_text())
        name = location.rsplit("node_modules/", 1)[1]
        if installed.get("version") != entry.get("version") or installed.get("name") != name:
            raise ValueError(f"installed npm identity differs from lock: {location}")
        identities.add(f"{name}@{installed['version']}")
    if not identities:
        raise ValueError("empty installed npm production inventory")
    print(f"npm inventory: {len(identities)} identities; {absent_optional} absent optional packages; "
          f"private root {manifest['name']}@{manifest['version']} excluded", file=sys.stderr)
    return identities


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--names", action="store_true")
    parser.add_argument("--metadata", type=Path)
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--ignored", action="store_true")
    parser.add_argument("--npm-metadata", type=Path)
    parser.add_argument("--npm-ignored", type=Path)
    args = parser.parse_args()
    if args.names:
        print(" ".join(main_packages()))
        return 0
    if args.ignored:
        # Recheck the installed artifact before excluding its overly broad raw metadata.
        numpy_correction("2.4.2")
        print(" ".join([name for name, _ in exceptions() if not name.startswith("npm:")] + ["numpy"]))
        return 0
    if args.npm_metadata or args.npm_ignored:
        try:
            packages = json.loads((args.npm_metadata or args.npm_ignored).read_text())
            if not isinstance(packages, dict):
                raise ValueError("npm metadata must be an identity mapping")
            required = npm_inventory()
            supplied = set(packages)
            if supplied != required:
                raise ValueError(f"npm inventory mismatch: missing={sorted(required - supplied)}; "
                                 f"unexpected={sorted(supplied - required)}")
            rows = []
            ignored = []
            reviewed = exceptions()
            for package, metadata in packages.items():
                name, version = package.rsplit("@", 1)
                key = "npm:" + name
                raw = metadata.get("licenses", "UNKNOWN")
                if isinstance(raw, list):
                    raw = " OR ".join(raw)
                rows.append({"name": key, "version": version, "license": raw})
                if (_name_key(key), version) in reviewed:
                    ignored.append(package)
            # Both CLI modes validate before emitting any exclusion.
            validate(rows)
            if args.npm_ignored:
                print(";".join(ignored))
            return 0
        except (OSError, ValueError, KeyError, TypeError) as exc:
            print(exc, file=sys.stderr)
            return 1
    path = args.metadata or (args.fixture / "packages.json")
    try:
        rows = json.loads(path.read_text())
        values = validate(rows, main_packages() if args.metadata else None)
        print(";".join(sorted(set(values))))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
