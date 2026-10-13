#!/usr/bin/env bash
# Run the challenge suite or benchmark against the app on this host.
#   scripts/direct.sh test
#   scripts/direct.sh benchmark [benchmark.py options]
# Uses installed Java 25, Nginx, and k6 v2 when present. Missing tools are
# downloaded or built in a temporary directory that is deleted afterwards.
set -euo pipefail
action=${1:?usage: direct.sh test|benchmark [benchmark.py options]}
shift
here=$(cd "$(dirname "$0")/.." && pwd)
root=$(cd "$here/../.." && pwd)
work=$(mktemp -d "${TMPDIR:-/tmp}/twelve-dollar-java.XXXXXX")
pids=()
child=
# shellcheck source-path=SCRIPTDIR source=lib.sh
. "$here/scripts/lib.sh"

cleanup() {
  local status=$?
  trap - EXIT
  for pid in ${pids[@]+"${pids[@]}"}; do kill "$pid" 2>/dev/null || true; done
  for pid in ${pids[@]+"${pids[@]}"}; do wait "$pid" 2>/dev/null || true; done
  rm -rf "$work"
  exit "$status"
}
trap cleanup EXIT
# Bash runs traps only after a foreground command exits, so the benchmark runs in
# the background. Ctrl-C already reaches it; SIGTERM sent to make must be forwarded.
stop() {
  if [ -n "$child" ]; then
    [ "$1" = INT ] || kill -TERM "$child" 2>/dev/null || true
    wait "$child" 2>/dev/null || true
  fi
  exit "$2"
}
trap 'stop INT 130' INT
trap 'stop TERM 143' TERM

ensure_java() {
  JAVA=${JAVA:-java}
  local major
  major=$("$JAVA" -version 2>&1 | awk -F'"' '/version/ { split($2, v, "."); print v[1]; exit }') || true
  if [ "${major:-0}" -ge 25 ] 2>/dev/null; then return; fi
  local name sha
  case "$platform" in
    Darwin/arm64) name=aarch64_mac sha=964ffce1ff9f24e8d29df4e4201b5b96499026dc8387cf35bb39fe969ffea2bb ;;
    Darwin/x86_64) name=x64_mac sha=720829aa4e4bddf3e95171cc059a52f7b9c56f443313dfef05114701bf60da06 ;;
    Linux/x86_64) name=x64_linux sha=8daf77d1aacffe38c9889689bc224a13557de77559d9a5bb91991e6a298baa0d ;;
    Linux/aarch64 | Linux/arm64) name=aarch64_linux sha=5c83b7d2121ed482fd06831a1eba1633dbab818aba6addddf48e075b97e6e9b8 ;;
    *) echo "No Java 25 download for $platform" >&2; exit 1 ;;
  esac
  echo "Java 25 not found; downloading Temurin 25.0.1 to $work"
  fetch "https://github.com/adoptium/temurin25-binaries/releases/download/jdk-25.0.1%2B8/OpenJDK25U-jdk_${name}_hotspot_25.0.1_8.tar.gz" "$sha" "$work/jdk.tar.gz"
  mkdir "$work/jdk"
  tar -xzf "$work/jdk.tar.gz" -C "$work/jdk" --strip-components=1
  JAVA=$work/jdk/bin/java
  [ -x "$JAVA" ] || JAVA=$work/jdk/Contents/Home/bin/java
}

ensure_nginx() {
  NGINX=${NGINX:-$(command -v nginx || true)}
  [ -n "$NGINX" ] || [ ! -x /usr/sbin/nginx ] || NGINX=/usr/sbin/nginx
  if [ -n "$NGINX" ]; then return; fi
  need cc
  need make
  echo "Nginx not found; building Nginx 1.28.0 in $work (about a minute)"
  fetch https://nginx.org/download/nginx-1.28.0.tar.gz c6b5c6b086c0df9d3ca3ff5e084c1d0ef909e6038279c71c1c3e985f576ff76a "$work/nginx.tar.gz"
  fetch https://zlib.net/fossils/zlib-1.3.1.tar.gz 9a93b2b7dfdac77ceba5a558a580e74667dd6fede4585b91eefb60f03b72df23 "$work/zlib.tar.gz"
  tar -xzf "$work/nginx.tar.gz" -C "$work"
  tar -xzf "$work/zlib.tar.gz" -C "$work"
  if ! (cd "$work/nginx-1.28.0" &&
    ./configure --without-http_rewrite_module --without-pcre --with-zlib=../zlib-1.3.1 &&
    make -j4) >"$work/nginx-build.log" 2>&1; then
    tail -n 30 "$work/nginx-build.log" >&2
    exit 1
  fi
  NGINX=$work/nginx-1.28.0/objs/nginx
}

[ -f "$here/target/server.jar" ] || { echo "target/server.jar is missing; run make build" >&2; exit 1; }
need curl
need python3
ensure_java

if [ ! -f "$root/seed/feed.db" ] || [ ! -f "$root/seed/tokens.json" ]; then
  need node
  need sqlite3
  bash "$root/seed/make-seed.sh"
fi
cp "$root/seed/feed.db" "$work/feed.db"

app_port=$(free_port)
SQLITE_PATH=$work/feed.db JWT_SECRET=twelve-dollar-challenge HOST=127.0.0.1 PORT=$app_port \
  "$JAVA" -Xmx512m -jar "$here/target/server.jar" >"$work/app.log" 2>&1 &
app_pid=$!
pids+=("$app_pid")
if ! wait_healthy "http://127.0.0.1:$app_port" "$app_pid"; then
  echo "The app did not become healthy. Last log lines:" >&2
  tail -n 40 "$work/app.log" >&2
  exit 1
fi

case "$action" in
  test)
    need jq
    need openssl
    NO_PROXY='*' no_proxy='*' bash "$root/test/test.sh" "http://127.0.0.1:$app_port"
    ;;
  benchmark)
    ensure_nginx
    ensure_k6
    raise_file_limit
    port=$(free_port)
    mkdir "$work/nginx"
    # The challenge's site config inside the main settings described in its header.
    {
      echo "worker_processes 1; worker_rlimit_nofile $files; pid $work/nginx/nginx.pid;"
      echo "events { worker_connections 16384; }"
      echo "http {"
      for kind in client_body proxy fastcgi uwsgi scgi; do
        echo "${kind}_temp_path $work/nginx/$kind;"
      done
      sed -e "s/127.0.0.1:3000;/127.0.0.1:$app_port;/" \
        -e "s/listen 80 default_server;/listen 127.0.0.1:$port default_server;/" \
        -e "s#/var/log/nginx/#$work/nginx/#" "$root/bench/nginx.conf"
      echo "}"
    } >"$work/nginx/nginx.conf"
    "$NGINX" -p "$work/nginx/" -c "$work/nginx/nginx.conf" -e "$work/nginx/error.log" \
      -g "daemon off;" &
    nginx_pid=$!
    pids+=("$nginx_pid")
    if ! wait_healthy "http://127.0.0.1:$port" "$nginx_pid"; then
      echo "Nginx did not proxy a healthy app. Error log:" >&2
      tail -n 40 "$work/nginx/error.log" >&2 || true
      exit 1
    fi
    python3 "$here/benchmark.py" --mode direct --url "http://127.0.0.1:$port" \
      --k6 local --k6-bin "$K6_BIN" --tokens "$root/seed/tokens.json" --app-pid "$app_pid" "$@" &
    child=$!
    wait "$child"
    ;;
  *)
    echo "Unknown action: $action" >&2
    exit 2
    ;;
esac
