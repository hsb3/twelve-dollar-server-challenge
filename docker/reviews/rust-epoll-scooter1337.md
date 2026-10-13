---
submission: rust-epoll-scooter1337
tree: 1743624dee309649d8bb44b0532f73163a1e62c8
verdict: pass
seccomp: unconfined
reviewed: 2026-10-13
---
# Security review: rust-epoll-scooter1337

## Verdict
Safe to build and run. Nothing malicious or blocker-level was found. The server is a raw io_uring HTTP/1.1 server over a statically linked, checksum-verified SQLite amalgamation. At runtime it reads only the four spec env vars and touches only its listening socket, accepted client sockets and the SQLite file at SQLITE_PATH (with its -wal/-shm siblings). It makes no outbound connections, spawns no processes and reads no credentials. All 30 third-party crates come from crates.io, their lockfile checksums match the registry, and OSV reports no advisories or malware for any of them. The SQLite tarball's sha256 matches build.sh, and the sqlite3.c inside it matches the SHA3-256 that sqlite.org publishes for 3.53.4.

`seccomp: unconfined` is justified. start.sh runs the binary with no flags, and the default path (`main.rs:481-485`) calls `uring::run(...).expect(...)`, so the server panics at startup if io_uring is unavailable. There is no automatic fallback; the `--epoll` path only runs when someone passes that flag by hand. The code's io_uring use is limited to accept, receive, send, shutdown, close and cancel on its own listener and accepted sockets, plus provided receive buffers. It uses no OpenAt, Read, Write, Connect, Splice or file opcodes.

What "unconfined" exposes: the whole server container, including nginx and the entrypoint, runs without Docker's syscall filter. That widens the kernel attack surface, and io_uring has a history of local privilege-escalation CVEs. On Docker Desktop for Mac the exposed kernel is the LinuxKit VM's, not macOS. The compose file still sets `no-new-privileges`, Docker's default capability drop and resource limits, and the server runs as `ubuntu` via setpriv. This is acceptable for code that, as reviewed, does nothing hostile.

## Scope
- Read in full: all 41 tracked files under `submissions/rust-epoll-scooter1337`: install.sh, build.sh, start.sh, Cargo.toml, Cargo.lock, build.rs, src/{main,net,uring,db}.rs, tests/check.py, tests/feed_ranges.py, tests/support/{allocations,snapshots}.rs, bench/train_sqlite.c, bench/{Dockerfile,build_wrk.sh,launch.sh,prepare_environment.py,compare_all.py,compare_revisions.py}, bench/*.lua, bench/manifest.json, README.md, .gitignore, LICENSE. Skimmed for instructions, URLs and privileged steps: IO_URING.md, BENCHMARKS.md, bench/README.md, bench/PROFILING.md.
- The eight `bench/*.json.gz` files were decompressed only to confirm each is valid JSON. They were not executed.
- No `.cargo/config*`, no `[patch]`/`[replace]`, no git or path dependencies, and no executable or binary blobs other than the gz JSON.
- Dependencies: all 31 Cargo.lock entries (30 from crates.io plus the local package). Checked against the crates.io API (version checksum, yanked flag, crate age, downloads, owners, repository) and OSV `/v1/querybatch` (ecosystem crates.io).
- Downloads: fetched the sqlite.org download page and the 3.53.4 release log, and downloaded the tarball into an isolated temp dir to hash it (sha256 of the tarball, SHA3-256 of the extracted sqlite3.c). Confirmed `https://static.rust-lang.org/dist/channel-rust-1.94.0.toml` exists and `sh.rustup.rs` serves the official rustup-init script.
- Harness context: docker/compose.yaml, docker/server.Dockerfile, docker/server-entrypoint.sh, SPEC.md, README.md.
- Nothing from the submission was built, executed or imported.

## Findings
- **note** `build.rs:24-35`: build-time code execution. On GCC hosts (Ubuntu's build-essential is GCC), build.rs compiles `bench/train_sqlite.c` against SQLite and runs it as a PGO trainer before recompiling SQLite. The trainer (`bench/train_sqlite.c:23-55`) builds a synthetic DB at `$OUT_DIR/training.db`, runs about 100k representative queries, then unlinks the file. It uses no network, no env vars and no paths outside OUT_DIR. Benign, but it is real build-time execution of submitter code (it runs as the unprivileged build user).
- **note** `build.rs:5-7`, `build.sh:18`: `-march=native` / `-C target-cpu=native`. The binary is tied to the build host's CPU, so build and run must be on the same machine. This is a portability issue, not a security one. `build.rs:5` reads cargo's `HOST`/`TARGET` triples, not the server's `HOST` env var.
- **note** `src/uring.rs:215-221,265,300,309,317,326,448,457`: complete io_uring surface. Setup with COOP_TASKRUN, SINGLE_ISSUER and DEFER_TASKRUN, then `register_files_sparse` and `register_buf_ring`, falling back to `ProvideBuffers`. Opcodes used: AcceptMulti (direct descriptors), RecvMulti (buffer select), Send (MSG_NOSIGNAL), Shutdown, Close (fixed), AsyncCancel. Every target fd is the listener or a ring-registered accepted socket.
- **note**: complete syscall families, for the seccomp decision.
  - io_uring_setup, io_uring_enter and io_uring_register.
  - Anonymous mmap/munmap (`uring.rs:153-178`).
  - getrlimit, and setrlimit(RLIMIT_NOFILE) raising only the soft limit up to the inherited hard limit (`uring.rs:832-851`).
  - socket, bind, listen and setsockopt(TCP_NODELAY), plus thread clone (up to 8 workers) and futex.
  - The flag-only epoll path (`net.rs`): epoll_create1, epoll_ctl, epoll_wait, accept4, recv, send and close.
  - SQLite's unix VFS on SQLITE_PATH and its -wal/-shm files: open, pread, pwrite, fdatasync, fcntl locks, mmap (`PRAGMA mmap_size=1 GiB`, `db.rs:176`), unlink and stat.
  - No process spawning (`std::process` appears only in `build.rs` and `std::process::exit` at `uring.rs:742`). No outbound connect. No reads of /proc, /etc, $HOME, ~/.ssh, ~/.aws or docker.sock.
- **note** `src/main.rs:472-475`: runtime env vars are exactly SQLITE_PATH, JWT_SECRET, HOST and PORT. `tests/support/allocations.rs:45` reads CHECK_TOKEN, but only in an `#[ignore]` test and never in the release binary.
- **note** `src/uring.rs`, `src/db.rs`, `src/main.rs:18-45`: heavy `unsafe` (manual allocator-backed buffers, kernel-shared buffer rings, raw SQLite FFI, SIMD loads). I found no deliberate misuse. Input is bounded: request 64 KiB of headers, 1 MiB body, 1.1 MiB per-connection input, `Buffer::reserve` asserts ≤ 4 MiB. A memory-safety bug would be reachable from network input, but only on the isolated bench network.
- **note** `install.sh:7-8`: rustup is installed via `curl https://sh.rustup.rs` then `sh`. The source is official and HTTPS, but the script is neither pinned nor checksum-verified. The toolchain is pinned (`1.94.0`), and rustup verifies component hashes from the channel manifest. Standard practice.
- **note** `install.sh:10-13`: writes `/usr/local/bin/cargo` and `/usr/local/bin/rustc` as 3-line shims. Each sets `RUSTUP_HOME=/opt/twelve-rust/rustup` and execs `/opt/twelve-rust/cargo/bin/<tool> "$@"`. Benign, though they shadow any other cargo/rustc in the image.
- **note** `bench/*.json.gz`: about 12 MB of benchmark result data; `official-k6-capacity-results.json.gz` inflates to about 829 MB. All are valid JSON, and no build, start or test path references them. They are inert, but avoid decompressing them casually.
- **note** `bench/prepare_environment.py`, `bench/compare_*.py`, `bench/launch.sh`, `bench/build_wrk.sh`, `bench/Dockerfile`: the author's own comparison harness, not run by install/build/start. prepare_environment.py clones the upstream repo, runs other PRs' install/build scripts and uses `docker run --network host`, and the bench Dockerfile pipes rustup to sh. **Do not run anything under `bench/`.** Its pinned downloads (wrk 4.2.0, bun 1.4.2) are sha256-checked.
- **note** `build.sh:19`: `cargo build --release --locked`, so the lockfile is enforced.

No blockers. No concerns above note level.

## Dependencies
All entries: source `registry+https://github.com/rust-lang/crates.io-index` with a Cargo.lock checksum that matches the crates.io API for that exact version. None are yanked. OSV querybatch returned no vulns for any of them, and no MAL-* ids.

| name | version | source+checksum | registry check | OSV result |
|---|---|---|---|---|
| base64 | 0.22.1 | crates.io, match | 2015, 1.7B dl, marshallpierce | none |
| bitflags | 2.13.2 | crates.io, match | 2015, 2.0B dl, KodrAus/rust-lang-owner | none |
| block-buffer | 0.10.4 | crates.io, match | 2017, RustCrypto | none |
| cc (build) | 1.2.56 | crates.io, match | 2014, rust-lang-owner | none |
| cfg-if | 1.0.5 | crates.io, match | 2015, rust-lang-owner | none |
| cpufeatures | 0.2.17 | crates.io, match | 2021, RustCrypto | none |
| crypto-common | 0.1.7 | crates.io, match | 2021, RustCrypto | none |
| digest | 0.10.7 | crates.io, match | 2016, RustCrypto | none |
| find-msvc-tools (build) | 0.1.14 | crates.io, match | 2025-08, rust-lang-owner, cc-rs repo (split out of cc), 545M dl | none |
| generic-array | 0.14.7 | crates.io, match | 2015, fizyk20/novacrazy | none |
| hmac | 0.12.1 | crates.io, match | 2016, RustCrypto | none |
| httparse | 1.10.1 | crates.io, match | 2015, seanmonstar | none |
| io-uring | 0.7.15 | crates.io, match | 2019, 62M dl, tokio-rs uring-core | none |
| itoa | 1.0.18 | crates.io, match | 2016, dtolnay | none |
| libc | 0.2.183 | crates.io, match | 2015, rust-lang-owner | none |
| memchr | 2.8.0 | crates.io, match | 2015, BurntSushi | none |
| proc-macro2 | 1.0.107 | crates.io, match | 2017, dtolnay | none |
| quote | 1.0.47 | crates.io, match | 2016, dtolnay | none |
| serde | 1.0.228 | crates.io, match | 2014, dtolnay/serde-rs | none |
| serde_core | 1.0.228 | crates.io, match | 2025-09, dtolnay/serde-rs (official serde split), 686M dl | none |
| serde_derive | 1.0.228 | crates.io, match | 2016, dtolnay/serde-rs | none |
| serde_json | 1.0.149 | crates.io, match | 2015, dtolnay/serde-rs | none |
| sha2 | 0.10.9 | crates.io, match | 2016, RustCrypto | none |
| shlex (build) | 1.3.0 | crates.io, match | 2015, comex/fenhl | none |
| subtle | 2.6.1 | crates.io, match | 2017, dalek-cryptography | none |
| syn | 2.0.119 | crates.io, match | 2016, dtolnay | none |
| typenum | 1.20.1 | crates.io, match | 2015, paholg | none |
| unicode-ident | 1.0.26 | crates.io, match | 2021, dtolnay | none |
| version_check | 0.9.5 | crates.io, match | 2017, SergioBenitez | none |
| zmij | 1.0.23 | crates.io, match | 2025-12, dtolnay, github.com/dtolnay/zmij (serde_json float formatter), 531M dl | none |

The three recently created crates (find-msvc-tools, serde_core, zmij) are owned by rust-lang-owner or dtolnay. They are official splits or new dependencies of cc and serde, with hundreds of millions of downloads, so they are not typosquats.

## Downloads at build time
| URL | official? | pinned? | checksum verified? |
|---|---|---|---|
| Ubuntu apt mirrors: `build-essential curl ca-certificates` (install.sh:3-4) | yes (distro) | no (distro current) | apt signature verification |
| `https://sh.rustup.rs` (install.sh:7) | yes (rustup) | script no; toolchain `1.94.0` yes | script no; rustup checks toolchain component sha256 from the channel manifest |
| `https://static.rust-lang.org/...` (fetched by rustup, toolchain 1.94.0) | yes | yes | yes (by rustup) |
| `https://www.sqlite.org/2026/sqlite-autoconf-3530400.tar.gz` (build.sh:13) | yes | yes (3.53.4) | yes: sha256 `0e9483900e92cd5de8fd48d16bf9200145a61f7fd5be542a5ac81d8a9516eb9c` matches my download; extracted sqlite3.c SHA3-256 `67f423e9...043a16` equals the value in sqlite.org/releaselog/3_53_4.html |
| crates.io (30 crates via `cargo build --locked`) | yes | yes (exact `=` versions + lockfile) | yes (Cargo.lock checksums, verified against the registry) |
