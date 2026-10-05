#!/usr/bin/env bash
# Lighthouse performance for the landing page (Sprint 005 A8, Sprint 005b A6).
# Targets: desktop 90 or more, mobile 75 or more.
#
#   scripts/verify/lighthouse.sh [output.json] [desktop|mobile]
#
# It builds the UI, serves it with `vite preview`, runs Lighthouse against `/` with the desktop preset (or the mobile
# form factor with simulated throttling), and prints the score. It needs a Chromium: it uses $CHROME_PATH, else a Playwright Chromium under $PLAYWRIGHT_BROWSERS_PATH, ~/.cache/ms-playwright or /opt/pw-browsers.
# The landing page needs no API, so no backend is started.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
FORM="${2:-desktop}"
OUT="${1:-$ROOT/planning/sprints/005b-polish/evidence/lighthouse-$FORM.json}"
case "$OUT" in /*) ;; *) OUT="$PWD/$OUT" ;; esac
PORT="${LIGHTHOUSE_PORT:-4175}"
if [ "$FORM" = "mobile" ]; then MIN_SCORE="${LIGHTHOUSE_MIN_SCORE:-0.75}"; else MIN_SCORE="${LIGHTHOUSE_MIN_SCORE:-0.90}"; fi

if [ -z "${CHROME_PATH:-}" ]; then
  for BASE in "${PLAYWRIGHT_BROWSERS_PATH:-}" "$HOME/.cache/ms-playwright" /opt/pw-browsers; do
    [ -n "$BASE" ] && [ -d "$BASE" ] || continue
    CHROME_PATH="$(find "$BASE" -type f -name chrome -path '*chrome-linux*' 2>/dev/null | sort | tail -n 1 || true)"
    [ -n "$CHROME_PATH" ] && break
  done
fi
if [ -z "${CHROME_PATH:-}" ] || [ ! -x "$CHROME_PATH" ]; then
  echo "No Chromium found. Set CHROME_PATH to a Chrome or Chromium binary." >&2
  exit 2
fi
export CHROME_PATH

cd "$ROOT/ui"
npm run build >/dev/null 2>&1
./node_modules/.bin/vite preview --host 127.0.0.1 --port "$PORT" --strictPort >/dev/null 2>&1 &
SERVER=$!
trap 'kill $SERVER 2>/dev/null || true' EXIT
for _ in $(seq 1 30); do
  curl -fsS "http://127.0.0.1:$PORT/" >/dev/null 2>&1 && break
  sleep 1
done

if [ "$FORM" = "mobile" ]; then PRESET="--form-factor=mobile"; else PRESET="--preset=desktop"; fi
mkdir -p "$(dirname "$OUT")"
npx --yes lighthouse@12 "http://127.0.0.1:$PORT/" \
  $PRESET --only-categories=performance \
  --output=json --output-path="$OUT" --quiet \
  --chrome-flags="--headless=new --no-sandbox --use-angle=swiftshader --enable-unsafe-swiftshader"

python3 - "$OUT" "$MIN_SCORE" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
score = d["categories"]["performance"]["score"]
print(f"lighthouse {d['configSettings']['formFactor']} performance: {round(score * 100)} (lighthouse {d['lighthouseVersion']})")
for k in ("first-contentful-paint", "largest-contentful-paint", "total-blocking-time", "cumulative-layout-shift", "speed-index", "interactive"):
    print(f"  {k}: {d['audits'][k]['displayValue']}")
sys.exit(0 if score >= float(sys.argv[2]) else 1)
PY
