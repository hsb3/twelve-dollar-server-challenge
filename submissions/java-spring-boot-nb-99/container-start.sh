#!/usr/bin/env bash
# Docker entrypoint. Nginx and the app share this container and its limits, as on
# the challenge VPS. Nginx uses the challenge's site config, and the app runs unprivileged.
set -euo pipefail
nginx -g 'daemon off;' &
nginx_pid=$!
setpriv --reuid=10001 --regid=10001 --clear-groups bash /app/start.sh &
app_pid=$!
trap 'kill -TERM "$nginx_pid" "$app_pid" 2>/dev/null || true' TERM INT
status=0
wait -n || status=$?
kill -TERM "$nginx_pid" "$app_pid" 2>/dev/null || true
wait || true
exit "$status"
