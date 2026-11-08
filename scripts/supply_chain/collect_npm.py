"""Collect licence metadata for every independently inventoried production identity."""
import json
import subprocess
import sys

from licence_metadata import ROOT, npm_inventory

COLLECTOR = ["npm", "exec", "--yes", "--package=license-checker-rseidelsohn@5.0.1", "--",
             "license-checker-rseidelsohn"]


def collect() -> dict:
    ui = ROOT / "ui"
    required = npm_inventory()
    root = json.loads((ui / "package.json").read_text())
    private = f"{root['name']}@{root['version']}"
    result = subprocess.run(COLLECTOR + ["--production", "--excludePackages", private, "--json"],
                            cwd=ui, check=True, capture_output=True, text=True)
    metadata = json.loads(result.stdout)
    if set(metadata) - required:
        raise ValueError(f"unexpected npm collector identities: {sorted(set(metadata) - required)}")
    lock = json.loads((ui / "package-lock.json").read_text())["packages"]
    # The collector's production traversal can omit installed optional peers. Ask
    # the same pinned tool about each missing installed artifact; never waive it.
    for identity in sorted(required - set(metadata)):
        name, version = identity.rsplit("@", 1)
        location = next(path for path, entry in lock.items()
                        if path.rsplit("node_modules/", 1)[-1] == name and entry.get("version") == version)
        result = subprocess.run(COLLECTOR + ["--start", str(ui / location), "--json"],
                                cwd=ui, check=True, capture_output=True, text=True)
        artifact = json.loads(result.stdout)
        if identity not in artifact:
            raise ValueError(f"collector omitted installed artifact: {identity}")
        metadata[identity] = artifact[identity]
        print(f"Collected installed optional artifact: {identity}", file=sys.stderr)
    if set(metadata) != required:
        raise ValueError("incomplete npm licence inventory")
    return metadata


if __name__ == "__main__":
    try:
        print(json.dumps(collect(), indent=2))
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        print(f"npm collection failed: {exc}", file=sys.stderr)
        sys.exit(1)
