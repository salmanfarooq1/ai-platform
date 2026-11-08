"""Required workflow jobs read explicit change-scope outputs; unknown paths run both."""
import os
import subprocess
from pathlib import Path

DOC_FILES = {"README.md", "CONTRIBUTING.md", "CHANGELOG.md", "SECURITY.md", "AGENTS.md", "CLAUDE.md", "CODEX.md"}


def scope(paths: list[str]) -> tuple[bool, bool]:
    backend = frontend = False
    for path in paths:
        if path == "docs/api/openapi.json":
            backend = frontend = True
        elif path.startswith("ui/"):
            backend = frontend = True
        elif path.startswith(("docs/", "planning/")) or path in DOC_FILES:
            continue
        else:
            backend = frontend = True
    return backend, frontend


if __name__ == "__main__":
    base = os.environ.get("CHANGE_BASE", "")
    if not base or set(base) == {"0"}:
        paths = subprocess.check_output(["git", "ls-files"], text=True).splitlines()
    else:
        paths = subprocess.check_output(["git", "diff", "--name-only", "--no-renames", base, "HEAD"], text=True).splitlines()
    backend, frontend = scope(paths)
    result = f"backend={str(backend).lower()}\nfrontend={str(frontend).lower()}\n"
    print(result, end="")
    with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
        output.write(result)
