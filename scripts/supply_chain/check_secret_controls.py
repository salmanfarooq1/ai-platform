"""Prove metadata exceptions do not suppress credentials in the same files."""
import json
import re
import secrets
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    scanner = sys.argv[1] if len(sys.argv) > 1 else "gitleaks"
    config = ROOT / ".gitleaks.toml"
    artifact = json.loads((ROOT / "scripts/supply_chain/numpy-2.4.2-cp311-linux-x86_64.json").read_text())
    checksum = artifact["members"]["numpy/_array_api_info.py"]
    scope = ROOT / "planning/sprints/011-baseline-and-stack/evidence/rework-source-scope.txt"
    openapi = re.search(r"(?i)OpenAPI(?:\.json)? SHA-?256:\s*([0-9a-f]{64})", scope.read_text())
    if openapi is None:
        raise RuntimeError("reviewed OpenAPI checksum is missing")
    # Construct public metadata in parts so the guard's own source is not a false positive.
    variable_name = "S3_LIVE_SECRET_KEY"
    bucket_name = "S3_LIVE_BUCKET"
    key_label = "key created"
    public_prefix = "prefix=abcd1234"
    prose_label = "token for English prose"
    chunk_setting = "chunk_size=1200"
    fixtures = {
        "scripts/supply_chain/numpy-2.4.2-cp311-linux-x86_64.json":
            f'"numpy/_array_api_info.py": "{checksum}"',
        "planning/sprints/011-baseline-and-stack/evidence/finish-integration-final.xml":
            f"{variable_name}, {bucket_name} ",
        "planning/sprints/011-baseline-and-stack/evidence/gitleaks-triage.txt":
            f"{key_label}: {public_prefix} \n{prose_label}, {chunk_setting}",
        "planning/sprints/011-baseline-and-stack/evidence/rework-source-scope.txt":
            f"OpenAPI SHA-256: {openapi[1]}",
    }
    with tempfile.TemporaryDirectory(prefix="secret-control-") as directory:
        work = Path(directory)
        files = work / "files"

        def write(values: dict[str, str]) -> None:
            for name, value in values.items():
                target = files / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(value + "\n")

        def scan(expected: int, label: str) -> list[dict]:
            report = work / "report.json"
            result = subprocess.run(
                [scanner, "dir", "--config", str(config), "--redact=100", "--no-banner",
                 "--report-format", "json", "--report-path", str(report), str(files)],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode != expected:
                # Never include scanner output or synthetic credential values in evidence.
                raise RuntimeError(f"{label}: expected exit {expected}, got {result.returncode}")
            rows = json.loads(report.read_text())
            print(f"PASS {label}: exit={result.returncode}, findings={len(rows)}")
            return rows

        write(fixtures)
        if scan(0, "reviewed metadata is accepted"):
            raise RuntimeError("reviewed metadata unexpectedly reported a finding")

        def synthetic(size: int) -> str:
            return "".join("".join(secrets.SystemRandom().sample("0123456789abcdef", 16))
                           for _ in range(size // 16))

        seeded = {name: value + f' api_key = "{synthetic(48)}"'
                  for name, value in fixtures.items()}
        write(seeded)
        rows = scan(1, "credential on the same metadata line is rejected")
        observed = {Path(row["File"]).relative_to(files).as_posix() for row in rows}
        if observed != set(fixtures):
            raise RuntimeError("a metadata exception suppressed its adjacent credential")
        write(fixtures)
        target = files / next(iter(fixtures))
        target.write_text(f'"numpy/_array_api_info.py": "{synthetic(64)}"\n')
        scan(1, "an unreviewed checksum value remains scanned")
        write(fixtures)
        (files / "unrelated.json").write_text(next(iter(fixtures.values())) + "\n")
        scan(1, "a reviewed value outside its approved path remains scanned")
        (files / "unrelated.json").unlink()
        marker = "gh" + "p_" + synthetic(48)[:36]
        (files / "other.txt").write_text(marker + "\n")
        if not any(row["RuleID"] == "github-pat" for row in scan(1, "other default rules remain enabled")):
            raise RuntimeError("default GitHub credential rule is not active")
    print("PASS secret control regression: default rules retained; metadata exceptions are scoped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
