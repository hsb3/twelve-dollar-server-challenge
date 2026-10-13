# Handoff: isolated Docker benchmark stack

The state of this fork's benchmarking work. It's enough to pick up cold.

## Where things stand

- **`main`** has the upstream repo plus every submission from the 36 open, unmerged upstream PRs. Each
  is copied verbatim from its PR's head commit and checked against it (hsb3#1, merged).
- **`docker-bench`** (hsb3#2, open, not merged) holds the isolated benchmark stack in `docker/`. See
  [`docker/README.md`](docker/README.md). In short:
  - **Server container.** Ubuntu 24.04, limited to 1 CPU, 2 GB, no swap and 65535 open files, with
    optional Nginx.
  - **Load.** The `grafana/k6` container runs the upstream `bench/load.js` unchanged, or the extra
    scenarios in `bench/scenarios/`: `stairs`, `spike` and `rate`.
  - **Capture.** Each run saves its raw k6 samples, per-second Docker stats and `meta.json`, which holds
    the exact re-run command. `docker/ingest.mjs` folds them into `results/runs.db`, and a provisioned
    Grafana dashboard overlays runs on an elapsed-time axis.
  - **Safety.** `bench.sh` runs a submission only when `docker/reviews/<name>.md` says `verdict: pass`
    for its exact committed tree. At run time the server sits on an `internal` Docker network, with no
    internet, LAN or host access, and runs as a non-root user with `no-new-privileges`. `bench.sh`
    checks from inside the server that it has no outbound route before any load starts.
  - **Syscall filter.** The `seccomp` value comes from the review. `unconfined` is only for io_uring
    submissions.

## Reviewed submissions

All three passed static review (see `docker/reviews/`):

| Submission | Mode | seccomp |
|---|---|---|
| python-fastapi-cknutson12 | direct | builtin |
| ruby-rails-gambitboy | Nginx | builtin |
| rust-epoll-scooter1337 | direct (io_uring) | unconfined |

The other 33 submissions are unreviewed, and `bench.sh` refuses them.

## Results so far

These are from an Apple Silicon Mac running Docker Desktop: the server is arm64, the Docker VM has 16
CPUs and 11.7 GB, and k6 runs on the same machine. One core here is much faster than a $12 droplet's
vCPU, so these numbers are **not comparable to the upstream scores**. `results/` is gitignored, so this
table is the durable record.

`load.js` at 10,000 VUs (60 s ramp, 5 min hold), sandboxed, after the 42-check suite passed:

| Submission | p95 | p99 | Failed | Peak server CPU (% of one core) | Peak server memory (excluding page cache) |
|---|---|---|---|---|---|
| python-fastapi-cknutson12 | 0.54 ms | 1.14 ms | 0% | 22% | 221 MB |
| ruby-rails-gambitboy | 1.30 ms | 2.45 ms | 0% | 45% | 236 MB |
| rust-epoll-scooter1337 | 0.48 ms | 0.87 ms | 0% | 10% | 62 MB |

Earlier `stairs` runs (1k to 4k VUs) also had 0% failures. No run so far has come near any server's
limit. Each 10k run was about 374k requests, roughly 1k req/s at the hold.

## Follow-ups

1. **Run Rust at 50k VUs.** The upstream author reports Rust above 60k. k6 used about 3.2 GB at 10k
   VUs (about 0.33 MB per VU, a single `docker stats` reading near the end of the run, not a tracked
   peak). So 50k needs about 16 GB for k6 plus 2 GB for the server, more than the Docker VM's 11.7 GB.
   The k6 container already has its ephemeral port range widened to `1024 65535`, so it can hold
   about 64k connections to one server address. That has only been tested at 10k. Options:
   - **A (recommended):** raise Docker Desktop memory to 24 GB (about 60k VUs) or 32 GB (about 80k).
     There's no code change, and runs stay comparable with upstream's tool and script.
   - **B:** trim k6 memory by turning off thresholds and the end-of-test summary and slimming the
     script. Expect 20-30% less, not 3x.
   - **C:** port `load.js` to an event-driven generator such as Gatling, where a user is a small session
     of a few KB, not a JS runtime. That's about 60 lines plus a results importer and a check that it
     behaves like `load.js`. Results would no longer be like-for-like with upstream.
   - **D:** combine `rate.js` at the equivalent request rate (about 5.1k req/s for 50k users) with a
     holder for 50k idle keep-alive connections. Cheap, but only an approximation.

   Before choosing C, measure k6's real per-VU floor with a sleep-only script, after the current runs.
2. **Upstream's scoring search** (warm-up, doubling, narrowing to 250, a 5-minute confirm hold) isn't
   automated. `stairs` approximates it in one run.
3. **The `spike` scenario has never been run.**
4. **Fidelity gaps** (detailed in `docker/README.md`):
   - k6 shares the host with the server.
   - There's no OS memory overhead inside the 2 GB.
   - arm64 differs from the droplet's x86_64. `SERVER_PLATFORM=linux/amd64` exists but is emulated.
   - `rust-epoll-scooter1337` builds with `target-cpu=native`.
5. **Review backlog.** Each new submission needs a review file before it can run. The process is in
   `docker/reviews/README.md`.
6. **Merge hsb3#2** once the stack is accepted.

## Running it

```bash
docker compose -f docker/compose.yaml up -d grafana        # dashboard on http://localhost:3000
bash docker/bench.sh python-fastapi-cknutson12 10000       # direct
NGINX=1 bash docker/bench.sh ruby-rails-gambitboy 10000    # behind Nginx
```

## Gotchas

- Docker's default address pools can be exhausted by stale networks from other projects. The stack
  pins its own subnets (`BENCH_SUBNET`, `VIZ_SUBNET`) to avoid that.
- Nginx reads an environment variable named `NGINX`, so the container uses `BEHIND_NGINX` internally.
- `runuser` and `su` reset the open-files limit to 1024 through PAM, and so did compose's
  `nofile: 65535` shorthand on this Docker version. The entrypoint uses `setpriv` and refuses to start
  below 65535.
- The bench network is `internal`, so nothing on it can publish ports. That's why Grafana has its own
  network.
