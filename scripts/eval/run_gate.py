#!/usr/bin/env python3
"""The eval regression gate (Sprint 008): run the fixed suite with the fake LLM and compare it to the stored baseline.

    poetry run python scripts/eval/run_gate.py                      # CI: exits 1 on a regression
    poetry run python scripts/eval/run_gate.py --record             # also writes the run to `eval_runs` (owner role)
    poetry run python scripts/eval/run_gate.py --update-baseline    # a deliberate, reviewed change of the baseline file

A metric fails the gate when its score is lower than `baseline - tolerance`. A higher score passes and is reported, so
the baseline can be raised on purpose. The suite uses only fakes (see `suite.py`): no network, no key, no cost. The run
with real providers is `run_real.py`, a manual script that CI never runs.

Exit status: 0 passed, 1 a metric regressed, 2 a usage or input error.
"""
import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))  # the repository root, when run as a script

BASELINE = Path(__file__).resolve().parent / "baseline.json"
EPSILON = 1e-9


@dataclass(frozen=True)
class Regression:
    metric: str
    baseline: float
    score: float | None
    tolerance: float

    def __str__(self) -> str:
        got = "missing" if self.score is None else f"{self.score:.4f}"
        return f"{self.metric}: {got} is below the baseline {self.baseline:.4f} minus the tolerance {self.tolerance:.4f}"


def compare(scores: dict[str, float], baseline: dict[str, float], tolerance: float) -> list[Regression]:
    """The metrics that dropped below `baseline - tolerance`. A metric the baseline names and the run lacks fails."""
    out = []
    for metric, expected in baseline.items():
        got = scores.get(metric)
        if got is None or got < expected - tolerance - EPSILON:
            out.append(Regression(metric, expected, got, tolerance))
    return out


def load_baseline(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data.get("scores"), dict) or not data["scores"] or not isinstance(data.get("tolerance"), (int, float)):
        raise ValueError("a baseline needs `scores` and a numeric `tolerance`")
    return data


def record_run(suite: str, scores: dict[str, float], baseline: dict[str, float], passed: bool, dsn: str | None) -> None:
    """Write one row to `eval_runs`. Needs the owner role: the app role can only read the table."""
    import psycopg2

    from core.settings import get_settings

    conn = psycopg2.connect(dsn or get_settings().migration_dsn)
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO eval_runs (suite, scores, baseline, passed) VALUES (%s, %s::jsonb, %s::jsonb, %s)",
                (suite, json.dumps(scores), json.dumps(baseline), passed),
            )
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--baseline", type=Path, default=BASELINE)
    parser.add_argument("--record", action="store_true", help="write the run to eval_runs (owner role)")
    parser.add_argument("--dsn", help="owner database URL for --record (default: MIGRATION_DATABASE_URL)")
    parser.add_argument("--update-baseline", action="store_true", help="write the scores of this run as the new baseline")
    args = parser.parse_args(argv)
    try:
        baseline = load_baseline(args.baseline)
        from scripts.eval.suite import SUITE, run_fake  # imported late: it pulls in the platform and DeepEval

        scores = asyncio.run(run_fake())
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    regressions = compare(scores, baseline["scores"], float(baseline["tolerance"]))
    print(f"eval gate, suite {SUITE}, tolerance {baseline['tolerance']}")
    for metric, expected in baseline["scores"].items():
        got = scores.get(metric)
        note = "" if got is None or got <= expected + EPSILON else "  (higher than the baseline)"
        print(f"  {metric}: {got} (baseline {expected}){note}")
    if args.update_baseline:
        baseline["scores"], baseline["suite"] = scores, SUITE
        args.baseline.write_text(json.dumps(baseline, indent=2) + "\n", encoding="utf-8")
        print(f"baseline written to {args.baseline}")
        return 0
    passed = not regressions
    if args.record:
        record_run(SUITE, scores, baseline["scores"], passed, args.dsn)
        print("run recorded in eval_runs")
    for regression in regressions:
        print(f"REGRESSION {regression}")
    print("PASSED" if passed else "FAILED")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
