#!/usr/bin/env bash
# Starts the submission on a fresh copy of the seed database, behind Nginx (BEHIND_NGINX=1) or direct on :80.
set -euo pipefail
[ -f /seed/feed.db ] || { echo "no /seed/feed.db: run seed/make-seed.sh first"; exit 1; }
rm -rf /data && mkdir /data && cp /seed/feed.db /data/feed.db && chown -R ubuntu:ubuntu /data

export SQLITE_PATH=/data/feed.db JWT_SECRET="${JWT_SECRET:-twelve-dollar-challenge}"
if [ "${BEHIND_NGINX:-0}" = 1 ]; then
  export HOST=127.0.0.1 PORT=3000
  nginx
else
  export HOST=0.0.0.0 PORT=80   # Docker lets non-root bind low ports (ip_unprivileged_port_start=0)
fi
echo "server: $SUBMISSION nginx=${BEHIND_NGINX:-0} on $HOST:$PORT, $(nproc) cpu(s), cgroup cpu.max=$(cat /sys/fs/cgroup/cpu.max) memory.max=$(cat /sys/fs/cgroup/memory.max)"
exec runuser -u ubuntu -- bash "/srv/challenge/submissions/$SUBMISSION/start.sh"
