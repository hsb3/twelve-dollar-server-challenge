#!/usr/bin/env bash
# Builds a submission into the server container, runs test/test.sh against it, then a k6 scenario against
# a fresh restart while sampling the server's CPU and memory. Each run lands in results/<run-id>/ and is
# ingested into results/runs.db for Grafana. See docker/README.md.
#
#   bash docker/bench.sh <submission-folder> [VUS]
#
# Env: SCENARIO (load = bench/load.js, or a name from bench/scenarios/), NGINX=1, DURATION, RAMP_UP,
#      SERVER_CPUS, SERVER_MEMORY, SERVER_CPUSET, SERVER_PLATFORM, SERVER_SECCOMP, SKIP_TEST=1, plus each scenario's own env.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export SUBMISSION="$(basename "${1:?usage: docker/bench.sh <submission-folder> [VUS]}")"
export VUS="${2:-${VUS:-100}}"
SCENARIO="${SCENARIO:-load}"
[ -d "$ROOT/submissions/$SUBMISSION" ] || { echo "no submissions/$SUBMISSION"; exit 1; }
if [ "$SCENARIO" = load ]; then SCRIPT=load.js; else SCRIPT="scenarios/$SCENARIO.js"; fi
[ -f "$ROOT/bench/$SCRIPT" ] || { echo "no bench/$SCRIPT"; exit 1; }
RUN="$(date -u +%Y%m%d-%H%M%S)_${SUBMISSION}_${SCENARIO}"
OUT="$ROOT/results/$RUN"; mkdir -p "$OUT"
dc() { docker compose -f "$ROOT/docker/compose.yaml" "$@"; }

wait_healthy() {
  dc run --rm -T tools bash -c 'for _ in $(seq 60); do curl -sf http://server/health >/dev/null && exit 0; sleep 1; done; exit 1' \
    || { echo "no healthy /health after 60 s"; dc logs server | tail -30; exit 1; }
}
STATS=""
finish() {
  dc logs --no-color server > "$OUT/server.log" 2>&1 || true
  dc rm -sfv server >/dev/null 2>&1 || true   # also ends the stats stream; leaves Grafana up
  [ -z "$STATS" ] || docker wait "$STATS" >/dev/null 2>&1 || true
}
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

id="$(dc ps -q server)"
STATS="$(dc run -d --rm stats sh -c "exec curl -sN --unix-socket /var/run/docker.sock http://localhost/containers/$id/stats > /repo/results/$RUN/server-stats.jsonl")"

# Everything needed to re-run this exact run: the env that shaped it plus the command.
envs=""
for v in SCENARIO NGINX DURATION RAMP_UP SERVER_CPUS SERVER_MEMORY SERVER_CPUSET SERVER_PLATFORM SERVER_SECCOMP \
         START STEP STEPS HOLD RAMP BASE PEAK JUMP RATE MIX MAX_VUS; do
  [ -n "${!v:-}" ] && envs="$envs$v=${!v} "
done
cat > "$OUT/meta.json" <<EOF
{"run_id":"$RUN","started_at":"$(date -u +%Y-%m-%dT%H:%M:%SZ)","submission":"$SUBMISSION","scenario":"$SCENARIO",
 "vus":$VUS,"nginx":${NGINX:-0},"cpus":"${SERVER_CPUS:-1}","memory":"${SERVER_MEMORY:-2g}","platform":"${SERVER_PLATFORM:-native}",
 "env":"${envs% }","command":"${envs}bash docker/bench.sh $SUBMISSION $VUS",
 "git_sha":"$(git -C "$ROOT" rev-parse --short HEAD)","image_id":"$(docker inspect -f '{{.Image}}' "$id")"}
EOF

echo "== load: $SCRIPT VUS=$VUS ${envs}"
rc=0
dc run --rm -T k6 run --quiet --out "csv=/results/$RUN/k6.csv.gz" "/bench/$SCRIPT" 2>&1 | tee "$OUT/k6.txt" || rc=$?

cg="$(dc exec -T server sh -c 'echo "memory.peak=$(cat /sys/fs/cgroup/memory.peak) cpu.max=$(cat /sys/fs/cgroup/cpu.max)"' 2>/dev/null || true)"
echo "== server: $cg oom_killed=$(docker inspect -f '{{.State.OOMKilled}}' "$id") running=$(docker inspect -f '{{.State.Running}}' "$id")" | tee "$OUT/server-stats.txt"
echo "$rc" > "$OUT/k6-exit"
trap - EXIT; finish

echo "== ingest"
dc run --rm -T tools node --no-warnings docker/ingest.mjs "results/$RUN"
echo "== results in results/$RUN, k6 exit $rc"
exit $rc
