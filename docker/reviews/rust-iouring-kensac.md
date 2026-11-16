---
submission: rust-iouring-kensac
tree: 94966f6cc58c436ee382107b937f3bfe02548966
verdict: pass
seccomp: unconfined
reviewed: 2026-11-15
---
# Security review: rust-iouring-kensac

## Verdict
Safe to build and run. Nothing malicious or blocker-level was found. The server is a single-threaded io_uring HTTP/1.1 server that serves `HOST:PORT` directly (no nginx). It statically links a checksum-verified SQLite 3.54.1 amalgamation, unmodified and `#include`d by a C shim that reads SQLite's B-tree cursors directly. At runtime it reads only the four spec env vars and touches only its listening sockets, accepted client sockets and the SQLite file at SQLITE_PATH (with its -wal sibling; the `unix-excl` VFS keeps the WAL index in heap, so there is no -shm file). It makes no outbound connections, spawns no processes and reads no credentials. All 15 third-party crates come from crates.io, their lockfile checksums match the registry, and OSV reports no advisories or malware for any of them. The Rust tarball sha256s in install.sh match the `.sha256` files static.rust-lang.org publishes, and the SQLite zip's sha256 matches build.sh while its SHA3-256 matches the value sqlite.org publishes.

`seccomp: unconfined` is justified. The server has no non-io_uring code path. `main.rs:977-980` builds the first ring with `Ring::new(slots)` and calls `std::process::exit(1)` if that fails, so under Docker's default seccomp profile (which blocks io_uring_setup) it cannot start. README.md says so explicitly ("There is no epoll fallback"). The code's io_uring use is limited to Accept (into direct descriptors), RecvMulti and Recv (buffer select), Send (MSG_NOSIGNAL), Shutdown and Close (fixed) on its own listeners and accepted sockets, plus a sparse file table and a provided-buffer ring. It uses no OpenAt, Read, Write, Connect, Splice or file opcodes.

What "unconfined" exposes: the whole server container, including the entrypoint, runs without Docker's syscall filter. That widens the kernel attack surface, and io_uring has a history of local privilege-escalation CVEs. On Docker Desktop for Mac the exposed kernel is the LinuxKit VM's, not macOS. The compose file still sets `no-new-privileges`, Docker's default capability drop and resource limits, and the server runs as `ubuntu` via setpriv. This is acceptable for code that, as reviewed, does nothing hostile.

## Scope
- Read in full: all 15 tracked files under `submissions/rust-iouring-kensac`: .gitignore, install.sh, build.sh, start.sh, Cargo.toml, Cargo.lock, build.rs, csrc/shim.c, src/{main,app,db,http,json,jwt}.rs, README.md.
- The SQLite amalgamation is not tracked; build.sh downloads it. I verified it by hash rather than reading it line by line: downloaded `sqlite-amalgamation-3540100.zip` into an isolated temp dir, confirmed its sha256 equals build.sh's `SQ_SHA` and its SHA3-256 equals the value in the sqlite.org download page's product table. The zip holds only sqlite3.c, sqlite3.h, sqlite3ext.h and shell.c (shell.c is not used).
- No `.cargo/config*`, no `[patch]`/`[replace]`, no git or path dependencies, and no binaries or opaque blobs. `git status --ignored` on the folder is clean.
- Dependencies: all 16 Cargo.lock entries (15 from crates.io plus the local package). Checked against the crates.io API (version checksum, yanked flag, crate age, downloads, repository) and OSV `/v1/querybatch` (ecosystem crates.io).
- Downloads: fetched `rust-1.94.0-{x86_64,aarch64}-unknown-linux-gnu.tar.xz.sha256` from static.rust-lang.org and compared them to install.sh. Fetched the sqlite.org download page and hashed the amalgamation zip as above.
- Harness context: docker/server-entrypoint.sh.
- Nothing from the submission was built, executed or imported.

## Findings
- **note** `install.sh:8-19`: native aarch64 support. install.sh picks the Rust standalone tarball by `uname -m`, with pinned sha256s for both `x86_64` and `aarch64`, and exits on anything else. build.sh is architecture-neutral. `src/json.rs:454-468,531-558` uses SSE2/AVX2 only under `#[cfg(target_arch = "x86_64")]`; other targets take the portable 8-byte path. Nothing else is x86-specific.
- **note** `build.rs:9`, `build.sh:15`: `-march=native` (via `flag_if_supported`) and `-C target-cpu=native`. The binary is tied to the build host's CPU, so build and run must be on the same machine. Portability, not security.
- **note** `build.sh:10-14`: the SQLite download is skipped if `vendor/sqlite3.c` already exists, and that copy would not be hash-checked. `vendor/` is gitignored, and the gate refuses a submission folder with ignored files, so in the bench a fresh, verified download always happens.
- **note** `src/main.rs:67-93`: `register_buf_ring` calls `io_uring_register(IORING_REGISTER_PBUF_RING)` directly. If the kernel returns EINVAL, it retries once with `resv[0]=1`, a workaround for an inverted reserved-field check in some Ubuntu kernels (README cites Launchpad #2162843). On a correct kernel that retry is rejected too and the server exits. Odd but benign: it touches only the ring's own registration.
- **note** `src/main.rs:212-219,913-946`: complete io_uring surface. Setup with SINGLE_ISSUER, DEFER_TASKRUN and SUBMIT_ALL (Linux 6.1+), CQ size 65536, `register_files_sparse`, and one provided-buffer ring per io_uring. Opcodes: Accept (auto-target direct slot), RecvMulti, Recv (BUFFER_SELECT, MSG_DONTWAIT), Send, Shutdown (hard-linked) and Close on fixed slots. Every target is one of the eight listener fds or a ring-registered accepted socket. Up to 16 rings, all on the one thread.
- **note**: complete syscall families, for the seccomp decision.
  - io_uring_setup, io_uring_enter and io_uring_register.
  - Anonymous mmap for the buffer ring (`main.rs:98-100`).
  - getrlimit, and setrlimit(RLIMIT_NOFILE) raising only the soft limit up to the inherited hard limit (`main.rs:949-958`).
  - socket, setsockopt (SO_REUSEADDR, SO_REUSEPORT, TCP_NODELAY), bind and listen on HOST:PORT, IPv4 only (`main.rs:913-946`), and signal(SIGPIPE, SIG_IGN).
  - One pthread for WAL checkpoints, which lowers its own priority with setpriority/gettid (`csrc/shim.c:119-150`), plus futex.
  - SQLite's unix-excl VFS on SQLITE_PATH and its -wal file: open, pread, pwrite, fdatasync, fcntl locks, unlink and stat. `PRAGMA mmap_size = 0` (`shim.c:165`).
  - No process spawning (`std::process` appears only as `exit`). No outbound connect. No reads of /proc, /etc, $HOME, ~/.ssh, ~/.aws or docker.sock.
- **note** `src/main.rs:961-965`: runtime env vars are exactly SQLITE_PATH, JWT_SECRET, HOST and PORT, with local defaults. `build.sh:6` reads `$HOME` only to extend PATH.
- **note** `build.rs:12-37`: SQLite is compiled with `SQLITE_OMIT_LOAD_EXTENSION`, so extension loading is unavailable. No `ATTACH` or user-supplied SQL; all SQL is fixed, prepared at startup, with bound parameters (`shim.c:198-208`).
- **note** `csrc/shim.c`, `src/db.rs`, `src/main.rs`, `src/json.rs:360-529`: substantial `unsafe`. The shim reaches into SQLite internals (BtCursor, MemPage, `findCell`) and decodes record cells by hand. Rust decodes record bytes via raw pointers, and the JSON writer stores into reserved capacity with a single end-of-write bound `assert!`. I found no deliberate misuse. Cell decoding in `td_count_likes` checks lengths against `aDataEnd`, Rust record decoding uses bounds-checked `get`, and startup refuses any schema whose column order differs from what the decoders expect (`shim.c:173-185`). Input is bounded: 16 KiB of headers, 1 MiB body, 2 KiB receive buffers. A memory-safety bug would be reachable from network input, but only on the isolated bench network.
- **note** `src/jwt.rs:94-121`: HS256 signature is verified, in constant time, before the header or payload is parsed. `alg` must be HS256 and `exp` is required. No `none` or key-confusion path.
- **note** `install.sh:19`: the Rust tarball's own `install.sh` runs as root to install into `/usr/local`. It is part of the sha256-verified official tarball, so this is the standard install path for the standalone distribution.
- **note** `build.sh:16`: `cargo build --release --locked`, so the lockfile is enforced. `Cargo.toml` also pins every direct dependency with `=`.
- **note** `Cargo.toml:13-14`: the `stats` feature (stderr counters only) is off in the submitted build.

No blockers. No concerns above note level.

## Dependencies
All entries: source `registry+https://github.com/rust-lang/crates.io-index` with a Cargo.lock checksum that matches the crates.io API for that exact version. None are yanked. OSV querybatch returned no vulns for any of them, and no MAL-* ids.

| name | version | source+checksum | registry check | OSV result |
|---|---|---|---|---|
| bitflags | 2.13.2 | crates.io, match | 2015, 2.3B dl, bitflags/bitflags | none |
| block-buffer | 0.10.4 | crates.io, match | 2017, 1.4B dl, RustCrypto/utils | none |
| cc (build) | 1.2.56 | crates.io, match | 2014, 1.5B dl, rust-lang/cc-rs | none |
| cfg-if | 1.0.5 | crates.io, match | 2015, 1.8B dl, rust-lang/cfg-if | none |
| cpufeatures | 0.2.17 | crates.io, match | 2021, 1.3B dl, RustCrypto/utils | none |
| crypto-common | 0.1.7 | crates.io, match | 2021, 1.2B dl, RustCrypto/traits | none |
| digest | 0.10.7 | crates.io, match | 2016, 1.4B dl, RustCrypto/traits | none |
| find-msvc-tools (build) | 0.1.15 | crates.io, match | 2025-08, 698M dl, rust-lang/cc-rs (split out of cc) | none |
| generic-array | 0.14.7 | crates.io, match | 2015, 1.1B dl, fizyk20/generic-array | none |
| io-uring | 0.7.15 | crates.io, match | 2019, 71M dl, tokio-rs/io-uring | none |
| libc | 0.2.183 | crates.io, match | 2015, 2.0B dl, rust-lang/libc | none |
| memchr | 2.8.0 | crates.io, match | 2015, 1.8B dl, BurntSushi/memchr | none |
| sha2 | 0.10.9 | crates.io, match | 2016, 1.2B dl, RustCrypto/hashes | none |
| shlex (build) | 1.3.0 | crates.io, match | 2015, 1.1B dl, comex/rust-shlex | none |
| typenum | 1.20.1 | crates.io, match | 2015, 1.1B dl, paholg/typenum | none |
| version_check | 0.9.5 | crates.io, match | 2017, 1.2B dl, SergioBenitez/version_check | none |

The one recently created crate, find-msvc-tools, lives in the official cc-rs repository and is a dependency of cc, with hundreds of millions of downloads, so it is not a typosquat.

## Downloads at build time
| URL | official? | pinned? | checksum verified? |
|---|---|---|---|
| Ubuntu apt mirrors: `build-essential curl ca-certificates unzip xz-utils` (install.sh:6-7) | yes (distro) | no (distro current) | apt signature verification |
| `https://static.rust-lang.org/dist/rust-1.94.0-$ARCH-unknown-linux-gnu.tar.xz` (install.sh:16), ARCH x86_64 or aarch64 | yes | yes (1.94.0) | yes: sha256 checked by install.sh:17; x86_64 `e8fa4185...b03b15a` and aarch64 `c6fd6d1c...56b3c1a` both equal the `.sha256` files static.rust-lang.org publishes |
| `https://www.sqlite.org/2026/sqlite-amalgamation-3540100.zip` (build.sh:11) | yes | yes (3.54.1) | yes: sha256 `0a9c8e34352dad46006aa82836d5383bff9dc6bc9ce5a60553c05aa30e6ad1f9` checked by build.sh:12 and matches my download; SHA3-256 `92281c86...df28e30` equals the value on sqlite.org/download.html |
| crates.io (15 crates via `cargo build --locked`) | yes | yes (exact `=` versions + lockfile) | yes (Cargo.lock checksums, verified against the registry) |
