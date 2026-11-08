"""Each exported requirement must carry at least one SHA-256 hash."""
import re
import sys
from pathlib import Path


def check(path: Path) -> None:
    requirements = path.read_text().replace("\\\n", " ")
    lines = [line for line in requirements.splitlines() if line.strip() and not line.startswith("#")]
    if not lines or any("==" not in line or not re.search(r"--hash=sha256:[a-f0-9]{64}", line) for line in lines):
        raise ValueError(f"unhashed or unpinned requirement: {path}")
    print(f"{path.name}: {len(lines)} hash-locked requirements")


if __name__ == "__main__":
    for name in sys.argv[1:]:
        check(Path(name))
