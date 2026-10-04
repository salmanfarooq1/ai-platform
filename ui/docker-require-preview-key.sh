#!/bin/sh
# Runs before nginx starts (the nginx image runs every /docker-entrypoint.d/*.sh).
# Refuse to start without the preview key: an empty key would send "Bearer " and every call would be 401.
# The value is never printed.
if [ -z "${PREVIEW_API_KEY:-}" ]; then
    echo "PREVIEW_API_KEY is not set. Set it as a secret on the UI service (see docs/render-deployment.md)." >&2
    exit 1
fi
