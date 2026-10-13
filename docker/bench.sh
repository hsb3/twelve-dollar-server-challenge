#!/usr/bin/env bash
# Builds a submission into the server container, runs test/test.sh against it, then the k6 load test
# against a fresh restart. Results land in results/<submission>-<time>/. See docker/README.md.
#
#   bash docker/bench.sh <submission-folder> [VUS]
#
# Env: NGINX=1 (behind Nginx; default direct), DURATION, RAMP_UP, SERVER_CPUS, SERVER_MEMORY, SERVER_PLATFORM,
#      SERVER_CPUSET, SKIP_TEST=1, SKIP_LOAD=1.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export SUBMISSION="$(basename "${1:?usage: docker/bench.sh <submission-folder> [VUS]}")"
export VUS="${2:-${VUS:-100}}"
[ -d "$ROOT/submissions/$SUBMISSION" ] || { echo "no submissions/$SUBMISSION"; exit 1; }
OUT="$ROOT/results/$SUBMISSION-$(date +%Y%m%d-%H%M%S)"; mkdir -p "$OUT"
dc() { docker compose -f "$ROOT/docker/compose.yaml" "$@"; }

wait_healthy() {
  dc run --rm -T tools bash -c 'for _ in $(seq 60); do curl -sf http://server/health >/dev/null && exit 0; sleep 1; done; exit 1' \
    || { echo "no healthy /health after 60 s"; dc logs server | tail -30; exit 1; }
}
finish() { dc logs --no-color server > "$OUT/server.log" 2>&1 || true; dc down -t 5 >/dev/null 2>&1 || true; }
trap finish EXIT

[ -f "$ROOT/seed/feed.db" ] || { echo "== seed"; dc run --rm -T tools bash seed/make-seed.sh; }

echo "== build $SUBMISSION"
dc build tools server
dc up -d server && wait_healthy

if [ "${SKIP_TEST:-0}" != 1 ]; then
  echo "== test"
  dc run --rm -T tools bash test/test.sh http://server | tee "$OUT/test.txt"
  dc restart server && wait_healthy   # the tests write rows; load-test a fresh copy
fi

rc=0
if [ "${SKIP_LOAD:-0}" != 1 ]; then
  echo "== load: VUS=$VUS DURATION=${DURATION:-5m}"
  dc run --rm -T k6 2>&1 | tee "$OUT/k6.txt" || rc=$?
fi

id="$(dc ps -aq server)"
cg="$(dc exec -T server sh -c 'echo "memory.peak=$(cat /sys/fs/cgroup/memory.peak) cpu.max=$(cat /sys/fs/cgroup/cpu.max)"' 2>/dev/null || true)"
echo "== server: $cg oom_killed=$(docker inspect -f '{{.State.OOMKilled}}' "$id") running=$(docker inspect -f '{{.State.Running}}' "$id")" | tee "$OUT/server-stats.txt"
echo "== results in ${OUT#"$ROOT"/}, k6 exit $rc"
exit $rc
