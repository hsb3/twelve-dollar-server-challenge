---
submission: mojo-iouring-oh-meh
tree: 0f89eb7f101de47bccfd7efead8d0bda1ee0dd78
verdict: pass
seccomp: unconfined
reviewed: 2026-11-15
---
# Security review: mojo-iouring-oh-meh

## Verdict
Safe to build and run. Nothing malicious or blocker-level was found. The server is a single-threaded Mojo io_uring HTTP/1.1 server. A C shim (`src/shim.c`) wraps liburing's inline helpers and compiles in the unmodified SQLite amalgamation to expose B-tree cursor calls. At runtime it reads the four spec env vars plus two test-only knobs. It touches only its listening socket, accepted sockets, the SQLite file at SQLITE_PATH (with its -wal sibling; `unix-excl` keeps the WAL index in heap), `/proc/meminfo` and `/proc/self/{maps,exe}`. It makes no outbound connections, spawns no processes and reads no credentials. The SQLite zip matches build.sh's sha256 and sqlite.org's published SHA3-256, and its sqlite3.c matches the SHA3-256 in the 3.54.1 release log. The liburing tarball matches build.sh's sha256 and is byte-identical to the signed-off `liburing-2.15` git tag. All ten PyPI packages in the Mojo toolchain's dependency tree are genuine, and OSV lists no advisories or malware for any of them.

`seccomp: unconfined` is justified. start.sh runs the binary with no flags. `Server.__init__` (`src/server.mojo:197-198,239-240`) raises if `sh_init` or `sh_ring_open(0)` fails, and `sh_ring_open` (`src/shim.c:94-151`) returns the error from `io_uring_queue_init_params` directly. There is no epoll or other non-io_uring path: `epoll_wait` (`shim.c:213-225`) only multiplexes the rings' eventfds. Under Docker's default seccomp profile, which blocks `io_uring_setup`, the server exits at startup. The io_uring use is limited to provide-buffers, direct accept, multishot recv, send, shutdown and direct close on its own listener and accepted sockets. It uses no file, OpenAt, Read, Write, Connect or Splice opcodes.

What "unconfined" exposes: the whole server container runs without Docker's syscall filter. That widens the kernel attack surface, and io_uring has a history of local privilege-escalation CVEs. On Docker Desktop for Mac the exposed kernel is the LinuxKit VM's, not macOS. The compose file still sets `no-new-privileges`, Docker's default capability drop and resource limits. This is acceptable for code that, as reviewed, does nothing hostile.

## Scope
- Read in full: all 17 tracked files under `submissions/mojo-iouring-oh-meh`: .gitignore, install.sh, build.sh, start.sh, README.md, src/shim.c, src/{server,db,uring,http,jwt,sha256,jsonscan,record,resp,bytes,selftest}.mojo.
- No vendored code, lockfile, binaries or blobs are tracked. `.gitignore` covers `bin/` and `third_party/`, and the submission folder has no untracked or ignored files.
- SQLite amalgamation (`sqlite3.c`, 9.6 MB) was verified by hash, not read line by line. I downloaded `sqlite-amalgamation-3540100.zip` into an isolated temp dir. Its sha256 `0a9c8e34...e6ad1f9` matches build.sh:16, and its SHA3-256 `92281c86...df28e30` matches sqlite.org/download.html. The extracted sqlite3.c SHA3-256 `e2b869d3...b558ee81` equals the value in sqlite.org/releaselog/3_54_1.html, and `SQLITE_VERSION` is "3.54.1".
- liburing 2.15 was verified by hash and by tree diff, not read line by line. The tarball sha256 `8d052f26...b636120a` matches build.sh:20. Its extracted tree is identical (`diff -r`) to a clone of tag `liburing-2.15` (annotated tag by Jens Axboe, `axboe/liburing`). It contains no non-text files.
- Mojo toolchain: PyPI JSON API metadata for every package in the tree (author, upload date, wheel platforms, requires_dist), plus OSV `/v1/querybatch` (ecosystem PyPI), both with exact versions and with name only to catch MAL-* entries. The wheels were not downloaded or unpacked.
- Harness context: docker/compose.yaml, docs/security-reviews.md.
- Nothing from the submission was built, executed or imported.

## Findings
- **concern** `src/jsonscan.mojo:361-366`, `src/resp.mojo:13,83-107`, `src/bytes.mojo:154-185`, `src/db.mojo:424-481`: a heap overflow reachable from authenticated input. The 500-character limit counts only bytes that are not UTF-8 continuation bytes (`& 0xC0 != 0x80`). The JSON scanner accepts any raw byte ≥ 0x20, so a body of about 16 KB of bare `0x80` bytes counts as 0 characters, passes validation, and is stored as-is. `GET /feed` reserves `FEED_MAX` (96 KB) in a 1 MiB response arena, and `Out` writes with no bounds check. Twenty such posts make a feed of about 330 KB. When the current arena is past about 700 KB used, the write runs off the end of the `balloc`ed arena and corrupts the heap. Only a client holding a valid JWT can trigger this, and it needs deliberately invalid UTF-8. The benchmark's load does neither, and the server runs on the isolated bench network. So this is not a blocker for running it, but it is a real memory-safety bug and a spec deviation (over-length bodies accepted). `GET /posts/:id` (32 KB reservation) and the create response (64 KB) stay within their bounds even with such bodies.
- **note** `install.sh:11-13`: the Mojo toolchain is a prebuilt, closed-source compiler and runtime from Modular, installed from PyPI (`mojo==1.2.0`). This is the same trust category as a Rust or Go release tarball. The top-level version is pinned, but there is no `--require-hashes`, so pip relies on PyPI's TLS and per-file hashes from the index. `mojo` pins `mojo-compiler`, `mojo-compiler-mojo-libs` and `mojo-lldb-libs` exactly (1.2.0) and `mblack` exactly (26.7.0). mblack's own dependencies (click, mypy-extensions, pathspec, platformdirs) and the `pip install --upgrade pip` step are unpinned and resolve to the latest versions at build time. The compiled server links the Mojo runtime libraries from that wheel, and README:182 notes that the runtime starts a few idle worker threads.
- **note** `install.sh:13`, aarch64: PyPI publishes `manylinux_2_34_aarch64` wheels for `mojo`, `mojo-compiler` and `mojo-lldb-libs` 1.2.0, alongside x86_64 and macOS arm64. Ubuntu 24.04 has glibc 2.39, so pip selects the native aarch64 wheel. build.sh is architecture-neutral (GCC, liburing, SQLite), and README:162-165 says the server was developed on an arm64 VM.
- **note** `build.sh:41`: `-O3 -march=native`. The shim is tied to the build host's CPU, so build and run must be on the same machine. This is a portability issue, not a security one.
- **note** `build.sh:33`: build-time code execution of upstream code. It runs liburing's `./configure` (a shell script that compiles feature probes) and `make -C src liburing.a`, as the build user. The tree is identical to the upstream tag.
- **note** `src/shim.c:339,412-424,437-508`: the shim `#include`s the whole amalgamation so it can call SQLite's file-private B-tree functions (`sqlite3BtreeTableMoveto`, `IndexMoveto`, `PayloadFetch`) and read `Pager`/`Wal` internals directly. SQLite itself is unmodified. Compile flags include `SQLITE_OMIT_LOAD_EXTENSION`, so no extension loading. Record decoding (`src/record.mojo`) trusts the on-disk format, and its input is the SQLite file the harness supplies.
- **note** `src/shim.c:94-151,185-201,265-308,213-248`: complete io_uring surface. Setup uses SINGLE_ISSUER, DEFER_TASKRUN, TASKRUN_FLAG, CQSIZE, SUBMIT_ALL and CLAMP. Registration is `register_files_sparse` and `register_eventfd`. Opcodes: PROVIDE_BUFFERS, ACCEPT (direct, `IORING_FILE_INDEX_ALLOC`), RECV (multishot, buffer select, fixed file), SEND (MSG_NOSIGNAL, fixed file), SHUTDOWN hard-linked to CLOSE (direct). Every target fd is the listener or a ring-registered accepted socket.
- **note**: complete syscall families, for the seccomp decision.
  - io_uring_setup, io_uring_enter and io_uring_register (up to 16 rings).
  - epoll_create1, epoll_ctl and epoll_wait, plus eventfd and read on the rings' eventfds.
  - socket, setsockopt(SO_REUSEADDR), bind and listen (`shim.c:185-201`).
  - getrlimit, and setrlimit(RLIMIT_NOFILE) raising the soft limit to the inherited hard limit (`shim.c:53-60`).
  - mlock of the process's own read-only file-backed mappings, bounded by RLIMIT_MEMLOCK (`shim.c:573-596`), reading `/proc/self/maps` and `readlink(/proc/self/exe)`.
  - fopen of `/proc/meminfo` (`shim.c:326-335`).
  - setpriority(nice 19) on the checkpoint thread only, which needs no privilege (`shim.c:527`).
  - One pthread_create for the checkpointer, nanosleep/usleep and clock_gettime.
  - SQLite's unix VFS on SQLITE_PATH: open, pread, pwrite, fsync, unlink and stat. Plus `open(O_RDONLY)` and `posix_fadvise(DONTNEED)` on the same path (`shim.c:381-386`).
  - No exec, fork or system. No outbound connect. No reads of /etc, $HOME, ~/.ssh or docker.sock.
- **note** `src/server.mojo:825-830`, `src/server.mojo:187`, `src/db.mojo:224`: runtime env vars are SQLITE_PATH, JWT_SECRET, HOST and PORT. Two more are test-only and integer-parsed: `MOJO_TABLE_OVERRIDE` (fd table size) and `MOJO_WAL_HOLD_OVERRIDE` (WAL hold threshold). The harness sets neither. start.sh's comment mentions only the first. `JWT_SECRET` falls back to the public default `twelve-dollar-challenge` if unset. That does not matter under the harness, which sets it.
- **note** `src/jwt.mojo:74-131`: HS256 with a constant-time compare, signature checked before header and payload, `alg` required to be `HS256`, `exp` required. Buffers are sized to MAX_TOKEN (4096) and the token length is checked against it first.
- **note** `src/selftest.mojo`: a standalone unit-check program for the leaf modules. It is not built by build.sh and not run by start.sh.

No blockers. One concern (the feed-arena overflow above), the rest notes.

## Dependencies
No lockfile. The only package-manager dependency is the Mojo toolchain from PyPI. These are the packages pip resolves for `mojo==1.2.0` on Python 3.12 (`tomli` is skipped because it is only for Python < 3.11). Versions for unpinned entries are the current PyPI latest on the review date. OSV querybatch returned no vulns for any of them and no MAL-* ids, by exact version or by name alone.

| name | version | pinned? | registry check | OSV result |
|---|---|---|---|---|
| mojo | 1.2.0 | yes (install.sh) | Modular Inc, hello@modular.com, source github.com/modular/modular; uploaded 2026-10-22; wheels for linux x86_64, linux aarch64, macOS arm64 | none |
| mojo-compiler | 1.2.0 | yes (`==` in mojo) | Modular Inc; 2026-10-22; linux x86_64/aarch64, macOS arm64 | none |
| mojo-compiler-mojo-libs | 1.2.0 | yes (`==` in mojo-compiler) | Modular Inc; 2026-10-22; pure wheel | none |
| mojo-lldb-libs | 1.2.0 | yes (`==` in mojo) | Modular Inc; 2026-10-22; linux x86_64/aarch64, macOS arm64 | none |
| mblack | 26.7.0 | yes (`==` in mojo) | Modular Inc (the Mojo formatter); 2026-10-22; pure wheel | none |
| click | 8.5.1 (latest) | no (`>=8.0.0`) | pallets/click | none |
| mypy-extensions | 1.2.0 (latest) | no (`>=0.4.3`) | python/mypy_extensions | none |
| pathspec | 1.1.1 (latest) | no (`>=1.1.0`) | cpburnz/python-pathspec | none |
| platformdirs | 4.14.5 (latest) | no (`>=2`) | tox-dev/platformdirs | none |
| pip | 26.3 (latest) | no (`--upgrade`) | pypa/pip | none |

C dependencies (vendored at build time, not package-managed):
- SQLite 3.54.1. OSV has no upstream-ecosystem entry for it. Distro and GIT-range records matching 3.54.1 concern the Session extension (CVE-2026-50812/50813), which is not compiled in, and the `sqlite3` CLI's `.recover` (CVE-2026-119586), which is not built. CVE-2026-119371 (CTE depth) is fixed in 3.54.0, and the server runs only its own fixed SQL in any case.
- liburing 2.15: no OSV entries.

## Downloads at build time
| URL | official? | pinned? | checksum verified? |
|---|---|---|---|
| Ubuntu apt mirrors: `build-essential curl unzip ca-certificates python3 python3-venv` (install.sh:7-8) | yes (distro) | no (distro current) | apt signature verification |
| PyPI: `pip install --upgrade pip` (install.sh:12) | yes | no | PyPI index hashes only |
| PyPI: `mojo==1.2.0` and its tree (install.sh:13) | yes (Modular's own PyPI project) | top level and Modular packages yes; mblack's deps no | PyPI index hashes only (no `--require-hashes`) |
| `https://sqlite.org/2026/sqlite-amalgamation-3540100.zip` (build.sh:15,23-24) | yes | yes (3.54.1) | yes: sha256 `0a9c8e34352dad46006aa82836d5383bff9dc6bc9ce5a60553c05aa30e6ad1f9` matches my download; zip SHA3-256 matches sqlite.org/download.html; sqlite3.c SHA3-256 matches the 3.54.1 release log |
| `https://github.com/axboe/liburing/archive/refs/tags/liburing-2.15.tar.gz` (build.sh:19,28-29) | yes (upstream repo, Jens Axboe) | yes (tag 2.15) | yes: sha256 `8d052f2622dcb3678cbaee5ff582a87572672a6c0a56533cdda5b65cb636120a` matches my download; contents identical to the git tag |
