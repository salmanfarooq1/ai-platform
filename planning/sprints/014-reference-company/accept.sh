#!/usr/bin/env bash
# Sprint 014 acceptance: every check, in order, alone on this host (live tiers clear the shared Valkey).
# Usage: planning/sprints/014-reference-company/accept.sh   (from the worktree root; writes evidence/checks.txt)
set -uo pipefail
cd "$(dirname "$0")/../../.."
WT=$(pwd)
source /home/ubuntu/ai-platform/scratch/env012.sh >/dev/null 2>&1
P=${POETRY:-poetry}
EV=planning/sprints/014-reference-company/evidence
mkdir -p "$EV"
OUT=$EV/checks.txt
: > "$OUT"
fails=0
run() {
  local label=$1; shift
  local log=$EV/accept-$label.log
  local start=$SECONDS
  "$@" > "$log" 2>&1
  local rc=$?
  local summary
  summary=$(grep -E "passed|failed|error|kept|broken|Success|All checks|exit" "$log" | tail -1)
  printf '%-14s %s  rc=%s  %ss  %s\n' "$label" "$([ $rc -eq 0 ] && echo PASS || echo FAIL)" "$rc" "$((SECONDS-start))" "$summary" | tee -a "$OUT"
  [ $rc -eq 0 ] || fails=$((fails+1))
}
echo "sprint 014 acceptance $(date -Iseconds) $(git rev-parse --short HEAD) (+ working tree)" | tee -a "$OUT"
run ruff        $P run ruff check api core gateway evidence ports adapters workers sandbox_agent tests scripts/e2e scripts/docs scripts/supply_chain scripts/showcase scripts/ci
run mypy        $P run mypy
run contracts   $P run lint-imports
run unit        $P run pytest -m unit -q -p no:cacheprovider
run refco       $P run pytest -q -p no:cacheprovider tests/integration/refco
run ui-types    bash -c "cd ui && npx tsc --noEmit -p ."
run playwright  /home/ubuntu/ai-platform/scratch/pw/run.sh "$WT" --project=showcase-m0
run live-m0     $P run python planning/sprints/014-reference-company/accept_live_m0.py
echo "failures: $fails" | tee -a "$OUT"
exit $fails
