"""Check that every relative link and every backticked repo path in the product docs resolves.

    poetry run python scripts/docs/check_links.py

Files checked: README.md, CONTRIBUTING.md, SECURITY.md, CHANGELOG.md and every Markdown file under docs/.
- A Markdown link `[text](target)` must point to a file or folder that exists, relative to the file that holds it.
  URLs (`http`, `https`, `mailto`) and in-page anchors are allowed and not followed.
- An inline code span that looks like a repo path must exist, relative to the repository root or to the file that holds
  it. A span is a repo path when it is made of letters, digits, `_`, `.`, `-` and `/`, and either its first folder is a
  top-level entry of the repository (`core/settings.py`), or it is a bare file name with a known extension
  (`tokens.json`), which must then exist somewhere in the repository. Model names such as `gemini/gemini-embedding-001`,
  placeholders, globs, a leading slash (an API route or a container path) and any other span are not paths and are
  skipped.
- Generated blocks (`<!-- BEGIN GENERATED: ... -->`) hold values taken from the code, so they are skipped.
- Code spans in `docs/adr/` are not checked as paths: an ADR records the code as it was when it was decided.
"""
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
TOP_LEVEL = ("README.md", "CONTRIBUTING.md", "SECURITY.md", "CHANGELOG.md")
EXTENSIONS = (
    ".py", ".md", ".json", ".yml", ".yaml", ".sh", ".toml", ".sql", ".ts", ".tsx", ".mjs", ".css", ".txt", ".ini", ".lock",
)
NOT_PATHS = ("application/", "text/")

_GENERATED = re.compile(r"<!-- BEGIN GENERATED: (?P<name>[\w-]+) -->.*?<!-- END GENERATED: (?P=name) -->", re.S)
_FENCE = re.compile(r"^(```|~~~).*?^\1[ \t]*$", re.S | re.M)
_LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
_CODE = re.compile(r"`([^`\n]+)`")
_PATHLIKE = re.compile(r"^[\w.\-/]+$")


def _ignored_paths(root: Path) -> set[Path]:
    """Ask git once per check. Outside a checkout, ignore nothing."""
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "ls-files", "--others", "--ignored", "--exclude-standard", "--directory", "-z"],
            capture_output=True, check=False,
        )
    except FileNotFoundError:
        return set()
    if result.returncode:
        return set()
    return {root / os.fsdecode(name).rstrip("/") for name in result.stdout.split(b"\0") if name}


def _walk(root: Path, ignored: set[Path]):
    skip = {"node_modules", ".git", ".venv", "__pycache__", "dist"}
    for base, dirs, files in os.walk(root):
        parent = Path(base)
        dirs[:] = [d for d in dirs if d not in skip and parent / d not in ignored]
        for name in dirs + files:
            path = parent / name
            if path not in ignored:
                yield path


def doc_files(root: Path = ROOT, ignored: set[Path] | None = None) -> list[Path]:
    ignored = _ignored_paths(root) if ignored is None else ignored
    files = [root / name for name in TOP_LEVEL if (root / name).exists() and root / name not in ignored]
    files += sorted(p for p in _walk(root, ignored) if p.suffix == ".md" and p.is_relative_to(root / "docs"))
    return files


def _strip(text: str) -> str:
    """The text without generated blocks and fenced code (a fence is a command or a sample, not a reference)."""
    return _FENCE.sub("", _GENERATED.sub("", text))


def _is_url(target: str) -> bool:
    return target.startswith(("http://", "https://", "mailto:"))


def _looks_like_path(span: str, root: Path) -> bool:
    if span.startswith(("/", "~")) or span.startswith(NOT_PATHS) or not _PATHLIKE.match(span):
        return False
    if "/" in span:
        return (root / span.split("/", 1)[0]).exists()
    return span.endswith(EXTENSIONS)


def _known_names(root: Path, ignored: set[Path] | None = None) -> set[str]:
    return {p.name for p in _walk(root, _ignored_paths(root) if ignored is None else ignored)}


def check_file(path: Path, root: Path = ROOT, names: set[str] | None = None) -> list[str]:
    """Problems found in one file, as `file: what` lines."""
    text = _strip(path.read_text())
    rel = path.relative_to(root)
    problems: list[str] = []
    names = _known_names(root) if names is None else names
    for target in _LINK.findall(text):
        if _is_url(target) or target.startswith("#"):
            continue
        base = target.split("#", 1)[0]
        if base and not (path.parent / base).exists():
            problems.append(f"{rel}: broken link ({target})")
    # An ADR is a dated record: its Context names the code as it was when the decision was made, so its paths are
    # history and are not checked. Its links still are.
    spans = [] if rel.parts[:2] == ("docs", "adr") else _CODE.findall(text)
    for span in spans:
        if not _looks_like_path(span, root):
            continue
        clean = span.rstrip("/")
        found = (root / clean).exists() or (path.parent / clean).exists() or ("/" not in clean and clean in names)
        if not found:
            problems.append(f"{rel}: path does not exist (`{span}`)")
    return problems


def check(root: Path = ROOT, ignored: set[Path] | None = None) -> list[str]:
    problems: list[str] = []
    ignored = _ignored_paths(root) if ignored is None else ignored
    names = _known_names(root, ignored)
    for path in doc_files(root, ignored):
        problems += check_file(path, root, names)
    return problems


def main() -> int:
    ignored = _ignored_paths(ROOT)
    problems = check(ROOT, ignored)
    for line in problems:
        print(line)
    print(f"{len(doc_files(ROOT, ignored))} files checked, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
