#!/usr/bin/env bash
# Prepared tools only; never installs. Run alone: live tiers share local Valkey.
# --baseline captures existing checks before code; it never accepts Sprint 015.
set -uo pipefail
set +x
cd "$(dirname "$0")/../../.." || exit 2
P=${POETRY:-poetry}
export POETRY="$P"
PACK=planning/sprints/015-local-poc-lifecycle
EV=$PACK/evidence
baseline=0
case "${1:-}" in
  '') ;;
  --baseline) baseline=1; EV=$EV/baseline ;;
  *) echo 'usage: accept.sh [--baseline]' >&2; exit 2 ;;
esac
mkdir -p "$EV"
EV=$(cd "$EV" && pwd)
OUT=$EV/checks.txt
: > "$OUT"
fails=0
run() {
  local label=$1; shift
  local log=$EV/accept-$label.log rc
  "$@" > "$log" 2>&1
  rc=$?
  printf '%-16s rc=%s\n' "$label" "$rc" | tee -a "$OUT"
  if [ "$rc" -ne 0 ]; then fails=$((fails+1)); fi
}
no_skips() {
  "$P" run python - "$@" <<'PY'
import sys
import xml.etree.ElementTree as ET
failed = False
for path in sys.argv[1:]:
    cases = list(ET.parse(path).getroot().iter('testcase'))
    skipped = sum(case.find('skipped') is not None for case in cases)
    bad = sum(case.find('failure') is not None or case.find('error') is not None for case in cases)
    print(f'{path}: tests={len(cases)} skipped={skipped} failed={bad}')
    failed |= not cases or skipped > 0 or bad > 0
raise SystemExit(int(failed))
PY
}
required_drill() {
  # The drill owns and fully tears down its fixture stack.
  local showcase_python
  showcase_python=$("$P" run python -c "import sys; print(sys.executable)") || return 1
  SHOWCASE_PYTHON="$showcase_python" bash scripts/showcase/m0.sh "${POC_STACK:-m0drill}"
}
printf 'Sprint 015 mode=%s source=%s (includes working tree)\n' "$baseline" "$(git rev-parse --short HEAD)" | tee -a "$OUT"
run ruff "$P" run ruff check api core gateway evidence ports adapters workers sandbox_agent tests scripts/e2e scripts/docs scripts/supply_chain scripts/showcase scripts/ci scripts/verify $(ls -d scripts/release scripts/poc_lib scripts/poc_backup 2>/dev/null)
run mypy "$P" run mypy
run imports "$P" run lint-imports
run ddl bash scripts/check_no_ddl.sh
run docs "$P" run python scripts/docs/generate.py --check
run eval "$P" run python scripts/eval/run_gate.py
run pins "$P" run python scripts/supply_chain/check_pins.py
run licences bash scripts/supply_chain/licence_gate.sh
run image-scan bash scripts/supply_chain/image_scan.sh
run unit "$P" run pytest -m unit -q -p no:cacheprovider --junitxml="$EV/unit.xml"
run all "$P" run pytest -m "unit or integration or e2e" -q -p no:cacheprovider --junitxml="$EV/all.xml"
run skip-guard "$P" run python scripts/check_skips.py "$EV/all.xml"
run unit-no-skips no_skips "$EV/unit.xml"
if [ "$baseline" -eq 0 ]; then
  run new-live "$P" run pytest -q -p no:cacheprovider tests/integration/poc tests/integration/refco tests/integration/test_llm_governance.py --junitxml="$EV/new-live.xml"
  run new-no-skips no_skips "$EV/new-live.xml"
fi
run ui-tokens npm --prefix ui run tokens:check
run ui-lint npm --prefix ui run lint
run ui-types npm --prefix ui run typecheck
run ui-unit npm --prefix ui test -- --run
run ui-build npm --prefix ui run build
run ui-chunks npm --prefix ui run chunk-report
run ui-copy npm --prefix ui run copy-check
run playwright npm --prefix ui run test:e2e -- --project=showcase-m0
if [ "$baseline" -eq 0 ]; then
  run live-m0 required_drill
  run drill-output "$P" run python - "$EV/accept-live-m0.log" <<'PYDRILL'
import sys
from pathlib import Path
lines = Path(sys.argv[1]).read_text().splitlines()
markers = ('PASS backup', 'PASS checked down', 'PASS restored counts and heads',
           'PASS saved receipts offline', 'PASS new governed call', 'PASS restore drill')
missing = [marker for marker in markers if not any(line.startswith(marker) for line in lines)]
skipped = any(line.startswith('SKIP') for line in lines)
print(f'required markers missing={len(missing)} skipped={skipped}')
raise SystemExit(int(bool(missing) or skipped))
PYDRILL
fi
printf 'failures: %s\n' "$fails" | tee -a "$OUT"
exit "$fails"
