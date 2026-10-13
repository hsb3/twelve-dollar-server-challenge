# Isolated Docker benchmark stack

Runs a submission and the load test on one machine with Docker only: no droplet, no separate k6 box,
and nothing installed on the host.

| Container | What it is |
|---|---|
| `server` | Ubuntu 24.04 with the submission's `install.sh` run as root and `build.sh` as user `ubuntu`, plus Nginx with [`bench/nginx.conf`](../bench/nginx.conf). Limited to **1 CPU, 2 GB, no swap** by default, `nofile` 65535. Each start copies `seed/feed.db` fresh |
| `k6` | `grafana/k6`, the tool the OP scores with, running [`bench/load.js`](../bench/load.js) unchanged |
| `tools` | node, sqlite3, curl, jq, openssl: builds the seed and runs [`test/test.sh`](../test/test.sh) |

## Run

```bash
bash docker/bench.sh python-fastapi-cknutson12 1000             # direct on :80
NGINX=1 bash docker/bench.sh ruby-rails-gambitboy 1000          # behind Nginx, app on 127.0.0.1:3000
DURATION=60s RAMP_UP=15s bash docker/bench.sh <submission> 200  # quick smoke run
```

The first run builds `seed/feed.db` (about a minute). Each run: build the image, start the server, run
the 42-check test suite, restart on a fresh database, then run k6. The script exits with k6's status
(non-zero when a threshold fails). `results/<submission>-<time>/` gets `test.txt`, `k6.txt`,
`server.log` and `server-stats.txt` (peak memory, and whether the server was OOM-killed).

| Env | Default | |
|---|---|---|
| `NGINX` | `0` | `1` runs the submission behind Nginx. Use whatever its README says |
| `VUS`, `DURATION`, `RAMP_UP` | `100`, `5m`, `60s` | Passed to `load.js`. `VUS` can also go as the second argument |
| `SERVER_CPUS` | `1` | CPU quota (fractions allowed) |
| `SERVER_CPUSET` | `1` | Cores the server may use. It sets what `nproc` reports, so keep it at `SERVER_CPUS` cores |
| `SERVER_MEMORY` | `2g` | Memory limit. Swap is set to the same value, so no swap |
| `SERVER_PLATFORM` | native | `linux/amd64` builds and runs the server for x86_64. k6 stays native |
| `SKIP_TEST`, `SKIP_LOAD` | `0` | `1` skips that stage |
| `BENCH_SUBNET` | `10.212.12.0/24` | Docker network subnet, if that one clashes with something on your machine |

## How it differs from the OP's setup

- **k6 shares the host with the server.** Give Docker enough CPUs that k6 never has to compete with the
  server's core. On Docker Desktop, set at least 4 CPUs.
- **No OS overhead.** On the droplet, the OS shares the 2 GB with the server. Here the server gets all of
  it. Lower `SERVER_MEMORY` (for example, `1800m`) to make up for that.
- **CPU architecture.** The droplet is x86_64. On Apple Silicon the image builds for arm64, so an
  `install.sh` that downloads `amd64` or `x86_64` tarballs fails. Run those submissions with
  `SERVER_PLATFORM=linux/amd64`. They then run under emulation, so their numbers can't be compared
  with native runs.
- **One run, not the scoring search.** The OP warms up, doubles the VUs until a run fails, narrows the
  range to 250 users, then confirms with a 5-minute hold. Call `bench.sh` with different `VUS` to do the
  same.
