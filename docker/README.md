# Isolated Docker benchmark stack

Runs a submission, the load test and a results dashboard on one machine with Docker only: no droplet,
no separate k6 box, and nothing installed on the host.

| Container | What it is |
|---|---|
| `server` | Ubuntu 24.04 with the submission's `install.sh` run as root and `build.sh` as user `ubuntu`, plus Nginx with [`bench/nginx.conf`](../bench/nginx.conf). Limited to **1 CPU, 2 GB, no swap** by default, with 65535 open files (checked at start). Each start copies `seed/feed.db` fresh |
| `k6` | `grafana/k6`, the tool the OP scores with, running [`bench/load.js`](../bench/load.js) or a scenario |
| `stats` | Samples the server container's CPU and memory from the Docker API about once a second during the load |
| `grafana` | Dashboard over every recorded run (`results/runs.db`) |
| `tools` | node, sqlite3, curl, jq, openssl: builds the seed, runs [`test/test.sh`](../test/test.sh), ingests results |

## Safety: reviews and sandbox

A submission runs only after a passing security review of its exact committed code. Each run also
checks, before any load, that the server is sandboxed: it sits on an internal Docker network with no
internet, LAN or host access, and runs as a non-root user with `no-new-privileges`. Builds still
download from the internet. See [`reviews/README.md`](reviews/README.md).

## Run a benchmark

```bash
bash docker/bench.sh python-fastapi-cknutson12 1000                  # the OP's load.js, direct on :80
NGINX=1 bash docker/bench.sh ruby-rails-gambitboy 1000               # behind Nginx, app on 127.0.0.1:3000
SCENARIO=stairs START=1000 STEP=1000 bash docker/bench.sh <submission>
```

The first run builds `seed/feed.db` (about a minute). Each run: build the image, start the server, run
the 42-check test suite, restart on a fresh database, then run k6 while sampling the server. The script
exits with k6's status (non-zero when a threshold fails).

| Env | Default | |
|---|---|---|
| `SCENARIO` | `load` | `load` is the OP's `bench/load.js`, anything else is `bench/scenarios/<name>.js` |
| `NGINX` | `0` | `1` runs the submission behind Nginx. Use whatever its README says |
| `VUS`, `DURATION`, `RAMP_UP` | `100`, `5m`, `60s` | For `load.js` (and `rate.js`). `VUS` can also go as the second argument |
| `SERVER_CPUS` | `1` | CPU quota (fractions allowed) |
| `SERVER_CPUSET` | `1` | Cores the server may use. It sets what `nproc` reports, so keep it at `SERVER_CPUS` cores |
| `SERVER_MEMORY` | `2g` | Memory limit. Swap is set to the same value, so no swap |
| `SERVER_PLATFORM` | native | `linux/amd64` builds and runs the server for x86_64. k6 stays native |
| `SERVER_SECCOMP` | from the review | Taken from the submission's security review. `unconfined` (needed for io_uring) only when the review approves it |
| `SKIP_TEST` | `0` | `1` skips the test suite |
| `BENCH_SUBNET`, `VIZ_SUBNET`, `GRAFANA_PORT` | `10.212.12.0/24`, `10.212.13.0/24`, `3000` | Change them if they clash with something on your machine |

## Load scenarios

Each scenario is a k6 script. k6's executors already cover these models, so nothing here is custom
load-generation code. The VU-based ones reuse `load.js`'s user unchanged.

| `SCENARIO` | Model | Knobs |
|---|---|---|
| `load` | The OP's scored test: ramp to `VUS`, hold `DURATION` | `VUS`, `DURATION`, `RAMP_UP` |
| `stairs` | Steps up VUs and holds each step. The p95 knee approximates the score in one run | `START`, `STEP`, `STEPS`, `HOLD`, `RAMP` |
| `spike` | Baseline, jump to a peak in seconds, back to baseline. Shows recovery | `BASE`, `PEAK`, `HOLD`, `JUMP` |
| `rate` | Open model: a fixed arrival rate whether or not the server keeps up, so overload shows as latency and dropped iterations. One request per iteration, picked by `MIX` | `RATE`, `MIX` (e.g. `feed:20,post:20,like:50,create:10` for write-heavy), `MAX_VUS`, `DURATION`, `RAMP_UP` |

For a soak test, use `load` with a long `DURATION`. To add a scenario, drop a k6 script in
`bench/scenarios/`. If it takes new env vars, add them to the `k6` service in `compose.yaml` and to the
list in `bench.sh`.

## Results, replay and overlay

Each run saves `results/<run-id>/` (gitignored):

| File | |
|---|---|
| `meta.json` | Submission, scenario, limits, git SHA, image ID and `command`, the exact line that re-runs it |
| `k6.csv.gz` | Every k6 metric sample, raw |
| `server-stats.jsonl` | Raw Docker stats for the server, one JSON object per second |
| `k6.txt`, `test.txt`, `server.log`, `server-stats.txt` | k6 summary, test output, server log, peak memory and OOM flag |

`docker/ingest.mjs` folds each run into `results/runs.db`. It stores one row per run and one row per
second of the run: VUs, requests/s, p50/p95/p99/max latency, failure %, dropped iterations, server CPU
and memory. `bench.sh` runs it automatically. To rebuild the database from the raw files, run
`docker compose -f docker/compose.yaml run --rm tools node --no-warnings docker/ingest.mjs results/*/`.

To open the dashboard:

```bash
docker compose -f docker/compose.yaml up -d grafana    # http://localhost:3000 (admin/admin to edit)
```

- **Overlay:** pick several runs in **Runs**. Every run's x-axis starts at `00:00`, the moment it sent
  its first request, so runs from different days line up.
- **Replay:** drag across any panel to zoom all of them to that stretch. The crosshair is shared, so
  hovering at `00:02:30` shows VUs, latency, errors, CPU and memory for every selected run at that
  moment. The arrows next to the time picker step through the run.
- **Thresholds:** the dashed lines are the score limits: p95 500 ms, p99 1 s and 1% failures.
- **Time range:** the time picker shows 1970-01-01 because elapsed time is stored as time since 1970.
  Use absolute ranges or zoom rather than "Last 5 minutes".

To re-run a recorded configuration, run its `command` (from the table, or `jq -r .command meta.json`).

## How it differs from the OP's setup

- **k6 shares the host with the server.** Give Docker enough CPUs that k6 never has to compete with the
  server's core. On Docker Desktop, set at least 4 CPUs.
- **No OS overhead.** On the droplet, the OS shares the 2 GB with the server. Here the server gets all of
  it. Lower `SERVER_MEMORY` (for example, `1800m`) to make up for that.
- **CPU architecture.** The droplet is x86_64. On Apple Silicon the image builds for arm64, so an
  `install.sh` that downloads `amd64` or `x86_64` tarballs fails. Run those submissions with
  `SERVER_PLATFORM=linux/amd64`. They then run under emulation, so their numbers can't be compared
  with native runs.
- **No scoring search.** The OP warms up, doubles the VUs until a run fails, narrows the range to 250
  users, then confirms with a 5-minute hold. `stairs` gets close in one run. For the real procedure,
  call `bench.sh` with different `VUS`.
