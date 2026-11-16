# Notes for load-testing other servers

Lessons from building this stack that apply to any server, not only this challenge's HTTP API. The
stack itself is described in [`README.md`](README.md).

## Checklist for a new kind of server

1. **Pin the box you are simulating.** Write down its CPUs, memory, swap and open-files limit, then
   set the same in compose: `cpus`, `cpuset` (so `nproc` reports the same count), `mem_limit` equal
   to `memswap_limit` (no swap) and `ulimits.nofile`. Check the limits from inside the container at
   start, because some tools reset them (see Gotchas).
2. **Decide what one user is.** A closed model (k6 `ramping-vus`, a fixed number of users, each
   waiting for its reply) measures how many users the server holds. An open model (k6
   `constant-arrival-rate`, requests arrive at a fixed rate) shows overload as rising latency and
   dropped requests. Most real traffic is closer to open. Pick the one that matches the question.
3. **Write a correctness check first.** Run it before every load run, then restart on fresh data. A
   fast server that returns wrong answers is the most common false win.
4. **Size the load generator before the server.** Estimate its memory and connections at the peak
   (numbers below). If the generator runs out first, you measure the generator.
5. **Capture raw data and the exact re-run command.** Every run here saves raw k6 samples, per-second
   Docker stats and a `meta.json` with the command that reproduces it. The importer refuses a run
   with less than 90% of its seconds covered.
6. **Sandbox untrusted code.** Put the server on an `internal` Docker network, run it as non-root
   with `no-new-privileges`, keep Docker's default seccomp filter, and check from inside that it has
   no outbound route before load starts. Builds still need the internet, so build first and run on
   the sandboxed network.

## Load generator sizing (k6, measured here)

- **Memory per VU.** `ramping-vus` creates every VU up front at about 0.13 MB each, then grows with
  activity: 4.8 GB at 10k active VUs, 8.1 GB at 25k, peaking at 8.6 GB. It also grows at a constant
  VU count (about 12-20 MB/s). Budget about 0.35 MB per VU for a 5-minute hold.
- **Connections.** Each VU keeps its own connection. Linux's default ephemeral port range allows
  about 28k connections to one server address. Setting `net.ipv4.ip_local_port_range` to
  `1024 65535` in the k6 container raises that to about 64k. Beyond that, give the server several
  addresses or run several generator containers.
- **Untested levers.** `GOMEMLIMIT` in k6's environment should cap its Go heap. Turning off
  thresholds and the end-of-test summary may save 20-30%.
- **When k6 is too heavy.** For more than about 50k concurrent users on one machine, use an
  event-driven generator where a user costs a few KB: Gatling, `wrk2`, `oha` or `vegeta`
  (rate-based). Results then aren't like-for-like with a k6 baseline, so re-baseline.

## Other protocols

k6 covers more than HTTP, so the same stack works with a different script:

| Server type | k6 module | What changes |
|---|---|---|
| WebSocket, chat, push | `k6/websockets` | Connections are long-lived, so measure concurrent connections and message latency, not requests/s |
| gRPC | `k6/net/grpc` | The script needs the `.proto` files. Health check through gRPC health or a side HTTP port |
| HTTP/2 or TLS | built in | Add certificates to the server image. TLS handshakes cost CPU, so test with and without keep-alive |
| Databases, queues | none | Use the native tool (`pgbench`, `redis-benchmark`, `memtier`) in place of k6. Keep the same limits and capture |

To add any of these here: a scenario in `bench/scenarios/`, any new env vars in the `k6` service in
`compose.yaml` and the list in `bench.sh`, and a health check in `bench.sh`'s `wait_healthy` if it
isn't `GET /health`.

## Fidelity: what a single laptop gets wrong

- **Shared host.** The generator and server compete for CPU and memory. Give Docker enough CPUs that
  the generator never touches the server's core, and pin the server with `cpuset`.
- **Faster cores.** An Apple Silicon core is much faster than a cloud vCPU. Compare results only with
  runs on the same machine.
- **Architecture.** arm64 images differ from x86_64 production. `--platform linux/amd64` runs under
  emulation, so those numbers aren't comparable with native runs.
- **No OS overhead.** On a real box the OS shares the memory. Lower the memory limit to make up for
  it.
- **Memory readings.** Docker's memory figure includes page cache. Report memory excluding cache.
- **Build flags.** `target-cpu=native` and similar optimise for the build machine.

## Gotchas

- Stale networks from other projects can exhaust Docker's default address pools. Pin subnets.
- `runuser` and `su` reset the open-files limit to 1024 through PAM. Use `setpriv`, and refuse to
  start below the limit you set.
- An `internal` network can't publish ports, so dashboards need their own network.
- Some programs read environment variables you might reuse (Nginx reads `NGINX`). Prefix your own.
- Docker's default seccomp filter blocks io_uring. Allow `unconfined` only for code you have
  reviewed.
