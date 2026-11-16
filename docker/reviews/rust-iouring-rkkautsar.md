---
submission: rust-iouring-rkkautsar
tree: c9fae57392fbccebb11910b4ed4e4fba6e0c0b25
verdict: pass
seccomp: unconfined
reviewed: 2026-11-15
---
# Security review: rust-iouring-rkkautsar

## Verdict
Safe to build and run. Nothing malicious or blocker-level was found. The server is a single-threaded io_uring HTTP/1.1 event loop plus one SQLite writer thread. It reads through a hand-written B-tree cursor layer (`btree.c`) that compiles a vendored SQLite 3.46.1 amalgamation. The vendored `sqlite/sqlite3.c` matches the SHA3-256 that sqlite.org publishes for 3.46.1. The vendored `sqlite3.h` is byte-identical to the official 3.46.1 amalgamation zip, and to the copy embedded in the hash-verified sqlite3.c apart from the standard amalgamation edits. At runtime the server reads only spec and tuning env vars. It touches only its listening sockets, accepted client sockets and the SQLite file at SQLITE_PATH (with its -wal/-shm siblings). It makes no outbound connections, spawns no processes and reads no credentials. All 26 third-party crates come from crates.io, their lockfile checksums match the registry, and OSV reports no advisories or malware for any of them. install.sh downloads the official Rust 1.94.0 tarball and checks it against a pinned sha256. Both pinned values (x86_64 and aarch64) match static.rust-lang.org's published `.sha256` files.

`seccomp: unconfined` is justified. start.sh runs the binary with no flags. `main.rs:47` calls `uring::run_pass`, which builds every ring with `RingState::new(&addr)?` (`uring.rs:1376`). An `IoUring::builder().build()` failure is returned (`uring.rs:503-511`) and propagates out of `main` as an error exit. There is no epoll or other fallback in the server. The `RECV_MODE` variants (`hybrid`, `poll`, `direct`) are all io_uring. The only epoll code is in `src/bin/loadgen.rs`, a separate load-generator binary that start.sh never runs. The server's io_uring use is limited to AcceptMulti (direct descriptors), RecvMulti and Recv (with and without buffer select), PollAdd (multishot), Send, Shutdown, Close (fixed) and AsyncCancel. Every target is its own listener or a ring-registered accepted socket. It uses no OpenAt, Read, Write, Connect, Splice or file opcodes.

What "unconfined" exposes: the whole server container, including nginx and the entrypoint, runs without Docker's syscall filter. That widens the kernel attack surface, and io_uring has a history of local privilege-escalation CVEs. On Docker Desktop for Mac the exposed kernel is the LinuxKit VM's, not macOS. The compose file still sets `no-new-privileges`, Docker's default capability drop and resource limits, and the server runs as `ubuntu` via setpriv. This is acceptable for code that, as reviewed, does nothing hostile.

## Scope
- Read in full: 18 of the 20 tracked files under `submissions/rust-iouring-rkkautsar`: install.sh, build.sh, start.sh, Cargo.toml, Cargo.lock, build.rs, btree.c, src/{main,db,uring,writer,stats}.rs, src/bin/loadgen.rs, tests/btree_extreme_ids.rs, tests/loadgen_liveness.rs, bench-240k.sh, README.md and .gitignore.
- Verified by hash instead of reading line by line: `sqlite/sqlite3.c` (257,679 lines, 9.1 MB) and `sqlite3.h` (13,425 lines). Together they are about 271k of the folder's 277k lines.
  - `sqlite/sqlite3.c`: SHA3-256 `186a1baa476b6d546de155160ca6d30ff7b7e6ee375f0bb6445e1a3d180a7dad` equals the "SHA3-256 for sqlite3.c" value on https://www.sqlite.org/releaselog/3_46_1.html. Its SQLITE_SOURCE_ID (`2024-08-13 09:16:08 c9c2ab54...69a1e33`) matches the release log too.
  - The file is also byte-identical (`cmp`) to sqlite3.c inside https://www.sqlite.org/2024/sqlite-amalgamation-3460100.zip, which I downloaded into an isolated temp dir (zip sha256 `77823cb110929c2bcb0f5d48e4833b5c59a8a6e40cdea3936b99e199dbbe5784`).
  - `sqlite3.h`: sqlite.org publishes no separate hash for it. It is byte-identical (`cmp`) to sqlite3.h in the same official zip. It also matches the sqlite3.h embedded in the hash-verified sqlite3.c (lines 314-13739), apart from the 13 standard amalgamation rewrites (`#ifdef __cplusplus` to `#if 0`, `SQLITE_EXTERN` removed from three declarations, one trailing blank line). So it is anchored to the official hash.
- No `.cargo/config*`, no `[patch]`/`[replace]`, no git or path dependencies, and no `cc` crate (build.rs calls the system `cc` and `ar` directly). There are no binaries or opaque blobs. Every tracked file is source text.
- Dependencies: all 27 Cargo.lock entries (26 from crates.io plus the local package). Checked against the crates.io API (version checksum, yanked flag, crate age, downloads, owners, repository) and OSV `/v1/querybatch` (ecosystem crates.io). Vendored SQLite 3.46.1 was checked against OSV and the upstream CVE list (see Findings).
- Downloads: fetched `https://static.rust-lang.org/dist/rust-1.94.0-{x86_64,aarch64}-unknown-linux-gnu.tar.xz.sha256` and compared them with install.sh.
- Harness context: docker/compose.yaml, docker/server.Dockerfile, docker/server-entrypoint.sh.
- Nothing from the submission was built, executed or imported.

## Findings
- **low** `sqlite/sqlite3.c`: SQLite 3.46.1 (August 2024) is outdated and has known upstream CVEs fixed in later releases. They include CVE-2025-6965 (aggregate-term memory corruption, fixed in 3.50.2), CVE-2025-3277 and CVE-2025-29087 (`concat_ws()` overflow, fixed in 3.49.1), and the CVE-2026-1193xx batch fixed in 3.54.0 (CTE/expression-depth stack exhaustion, a page-cache info leak, and FTS/R-Tree/session bugs). Every one needs attacker-controlled SQL or an attacker-supplied database file. Here all SQL is fixed string constants in `db.rs`/`writer.rs`. Request data reaches SQLite only as bound parameters: an i64 post id, or a JSON array that serde_json serializes and `json_each(?1)` consumes. The database is the bench's own seed copy. FTS3/FTS5, R-Tree and session are not enabled (build.rs defines none of them), and extension loading is compiled out (`-DSQLITE_OMIT_LOAD_EXTENSION`). Not reachable from the network as built. Worth upgrading, but not a blocker.
- **note**: complete syscall families, for the seccomp decision.
  - io_uring_setup, io_uring_enter and io_uring_register (sparse file table of 65,000 slots per ring and a provided-buffer ring, `uring.rs:241-281,513`).
  - socket, setsockopt (SO_REUSEADDR, SO_REUSEPORT written as the literal `15` at `uring.rs:428`, TCP_NODELAY), bind and listen (`uring.rs:395-470`).
  - poll on the ring fds with a 1 ms timeout (`uring.rs:1450`), and getrusage only when `DIAG` is set.
  - One writer thread (clone, futex via std mpsc).
  - SQLite's unix VFS on SQLITE_PATH and its -wal/-shm files: open, pread, pwrite, fsync/fdatasync, fcntl locks, unlink and stat, plus mmap only if `READ_MMAP_MB` > 0.
  - No process spawning in the server (`std::process::Command` appears only in build.rs and the loadgen test). No outbound connect in the server. No reads of /proc, /etc, $HOME, ~/.ssh, ~/.aws or docker.sock.
- **note** `src/main.rs:36-44`, `src/db.rs:152,296,301`, `src/uring.rs:69,474,1386`, `src/stats.rs:63`, `src/writer.rs:89`, `btree.c:222,310,624`: env vars beyond the spec. The server reads SQLITE_PATH, JWT_SECRET, HOST and PORT, plus tuning and debug knobs: SHARDS (clamped to 1-16), RECV_MODE, WAL_AUTOCHECKPOINT, READ_CACHE_MB, READ_MMAP_MB, WRITE_COALESCE_US, STATS, DIAG, PASS_STATS and FEED_PARTS. Each is parsed as a number or a fixed enum, or only tested for presence, and the debug ones print counters to stderr. None is set by the harness. They are benign.
- **note** `btree.c`, `src/db.rs`, `src/uring.rs`: heavy `unsafe` and raw C. btree.c reaches into SQLite internals (BtCursor, KeyInfo, UnpackedRecord, `sqlite3VdbeSerialTypeLen`) to decode records directly. The record parsers bounds-check header and field lengths against the payload size (`btree.c:192-199,417-437`), and JSON output is capacity-checked (`btree.c:52`). uring.rs writes the kernel-shared buffer ring by hand, with entry layout `{u64 addr, u32 len, u16 bid, u16 resv}` and the tail at offset 14 (`uring.rs:223-300`), and checks `bid` and `res` before indexing buffers (`uring.rs:969-973,1061-1065`). `db.rs:658-661` transmutes `Stmt` to `'static`. That is sound only because `cache` is dropped before `db` in `writer.rs:80-87` (reverse declaration order). Input is bounded: 1 MiB body (`main.rs:221`) and 1 MiB per-connection input (`uring.rs:971,1063,1118`). I found no deliberate misuse. A memory-safety bug would be reachable from network input, but only on the isolated bench network.
- **note** `build.rs:12-35`: build-time code execution is limited to the system `cc` compiling btree.c (which `#include`s the verified sqlite3.c) and `ar` archiving it. It uses no network, runs no generated binary and writes only to OUT_DIR. It runs as the unprivileged build user.
- **note** `build.rs:17`, `build.sh:5`: `-march=native` and `-C target-cpu=native` tie the binary to the build host's CPU, so build and run must be on the same machine. This is a portability issue, not a security one. On aarch64 both flags are valid (GCC accepts `-march=native` on aarch64), and the SSE2 fast path in `btree.c:13-15,87-98` is behind `#if defined(__SSE2__)`, so ARM builds use the portable word-at-a-time scan.
- **note** `uring.rs:513`, `uring.rs:31`: (inference, not verified by running) the kernel rejects `register_files_sparse(65000)` with EMFILE if RLIMIT_NOFILE is below 65,000, and the server does not raise the limit itself. Docker's default container nofile limit is far higher, so this matters only if the harness lowers it. This is availability, not security.
- **note** `src/bin/loadgen.rs`, `tests/loadgen_liveness.rs`: the author's epoll load generator. `cargo build --release` compiles it (as `target/release/loadgen`), but install, build and start never run it. It connects only to a host and port given on its command line, reads a tokens file named on its command line, and writes a histogram to `LG_HISTOGRAM_PATH` if that is set. The test spawns it against a local listener on 127.0.0.1. Benign.
- **note** `bench-240k.sh`: the author's local capacity harness, not run by install, build or start. It runs `--privileged` containers with `--pid host --network host` and `--cgroupns host`. It creates cgroups under /sys/fs/cgroup, creates veth pairs with `nsenter`, and needs a local `lgipimg:latest` image that isn't in the repo. Nothing hostile, but **do not run it**: it needs host-level privileges and an unknown image.
- **note** `install.sh:3-4`: installs `build-essential curl ca-certificates xz-utils` from apt. That is the minimum for a C compiler, the download and the `.tar.xz` extraction.
- **note** `install.sh:16`: runs the tarball's own `install.sh` as root with `--prefix=/usr/local`, installing rustc, cargo and rust-std into /usr/local. This is the official installer, run only after the sha256 check, and standard practice.
- **note** `build.sh:5`: `cargo build --release --locked`, so the lockfile is enforced. `Cargo.toml` uses caret ranges, but `--locked` pins the exact versions below.

No blockers. One low-severity item (outdated vendored SQLite, not reachable as built). No other concerns above note level.

## Dependencies
All entries: source `registry+https://github.com/rust-lang/crates.io-index` with a Cargo.lock checksum that matches the crates.io API for that exact version. None are yanked. OSV querybatch returned no vulns for any of them, and no MAL-* ids.

| name | version | source+checksum | registry check | OSV result |
|---|---|---|---|---|
| base64 | 0.22.1 | crates.io, match | 2015, 2.0B dl, marshallpierce | none |
| bitflags | 2.13.2 | crates.io, match | 2015, 2.3B dl, KodrAus/rust-lang-owner | none |
| block-buffer | 0.10.4 | crates.io, match | 2017, RustCrypto | none |
| cfg-if | 1.0.5 | crates.io, match | 2015, rust-lang-owner | none |
| cpufeatures | 0.2.17 | crates.io, match | 2021, RustCrypto | none |
| crypto-common | 0.1.7 | crates.io, match | 2021, RustCrypto | none |
| digest | 0.10.7 | crates.io, match | 2016, RustCrypto | none |
| generic-array | 0.14.7 | crates.io, match | 2015, fizyk20/novacrazy | none |
| hmac | 0.12.1 | crates.io, match | 2016, RustCrypto | none |
| io-uring | 0.7.15 | crates.io, match | 2019, 71M dl, tokio-rs uring-core | none |
| itoa | 1.0.18 | crates.io, match | 2016, dtolnay | none |
| libc | 0.2.191 | crates.io, match | 2015, rust-lang-owner | none |
| memchr | 2.8.3 | crates.io, match | 2015, BurntSushi | none |
| proc-macro2 | 1.0.107 | crates.io, match | 2017, dtolnay | none |
| quote | 1.0.47 | crates.io, match | 2016, dtolnay | none |
| serde | 1.0.229 | crates.io, match | 2014, dtolnay/serde-rs | none |
| serde_core | 1.0.229 | crates.io, match | 2025-09, dtolnay/serde-rs (official serde split), 866M dl | none |
| serde_derive | 1.0.229 | crates.io, match | 2016, dtolnay/serde-rs | none |
| serde_json | 1.0.154 | crates.io, match | 2015, dtolnay/serde-rs | none |
| sha2 | 0.10.9 | crates.io, match | 2016, RustCrypto | none |
| subtle | 2.6.1 | crates.io, match | 2017, dalek-cryptography | none |
| syn | 3.0.9 | crates.io, match | 2016, dtolnay, 3.1B dl | none |
| typenum | 1.20.1 | crates.io, match | 2015, paholg | none |
| unicode-ident | 1.0.27 | crates.io, match | 2021, dtolnay | none |
| version_check | 0.9.5 | crates.io, match | 2017, SergioBenitez | none |
| zmij | 1.0.23 | crates.io, match | 2025-12, dtolnay, github.com/dtolnay/zmij (serde_json float formatter), 696M dl | none |

The two recently created crates (serde_core, zmij) are owned by dtolnay and serde-rs. They are an official split of serde and a new serde_json dependency, with hundreds of millions of downloads, so they are not typosquats.

Vendored C: SQLite 3.46.1 amalgamation (`sqlite/sqlite3.c`, `sqlite3.h`), verified against sqlite.org's published SHA3-256 as described in Scope. Its outdated-version CVEs are covered in Findings.

## Downloads at build time
| URL | official? | pinned? | checksum verified? |
|---|---|---|---|
| Ubuntu apt mirrors: `build-essential curl ca-certificates xz-utils` (install.sh:3-4) | yes (distro) | no (distro current) | apt signature verification |
| `https://static.rust-lang.org/dist/rust-1.94.0-x86_64-unknown-linux-gnu.tar.xz` (install.sh:7,13) | yes | yes (1.94.0) | yes: `sha256sum -c` against `e8fa4185...0b15a`, which equals static.rust-lang.org's published `.sha256` |
| `https://static.rust-lang.org/dist/rust-1.94.0-aarch64-unknown-linux-gnu.tar.xz` (install.sh:8,13) | yes | yes (1.94.0) | yes: `sha256sum -c` against `c6fd6d1c...6b3c1a`, which equals static.rust-lang.org's published `.sha256` |
| crates.io (26 crates via `cargo build --locked`) | yes | yes (lockfile) | yes (Cargo.lock checksums, verified against the registry) |

SQLite is vendored, not downloaded. Any other architecture exits with "unsupported architecture" (install.sh:9).
