---
submission: python-pypy-iouring-kiwamizamurai
tree: 36fb9fa6967fd8f17e47de34c150d5c760add276
verdict: pass
seccomp: unconfined
reviewed: 2026-11-15
---
# Security review: python-pypy-iouring-kiwamizamurai

## Verdict
Safe to build and run. Nothing malicious or blocker-level was found. The server is a single-threaded HTTP/1.1 server written in Python for PyPy 7.3.15. It drives io_uring rings by hand through a cffi module and serves `HOST:PORT` directly (no nginx). The cffi module, built by build.sh, contains an unmodified SQLite 3.54.1 amalgamation whose hash checks out, plus a few one-line syscall and atomic wrappers. HMAC-SHA256 comes from the system's `libcrypto.so.3`, loaded with `ffi.dlopen`. At runtime the server reads only the four spec env vars and touches only its listening sockets, accepted client sockets, eventfds, anonymous mmaps and the SQLite file at SQLITE_PATH (with its -wal sibling; `locking_mode=EXCLUSIVE` keeps the WAL index in heap, so there is no -shm file). It makes no outbound connections, spawns no processes and reads no credentials. The toolchain is Ubuntu 24.04's own `pypy3`/`pypy3-dev` packages, pinned to an exact version that is published for both amd64 and arm64. There are no PyPI or other third-party packages. The SQLite zip's sha256 matches build.sh, and its SHA3-256 matches the value sqlite.org publishes.

`seccomp: unconfined` is justified. The server has no non-io_uring code path. `server.py:1069` builds the first ring with `Ring(0)` at module load. If `io_uring_setup` fails, `Ring.__init__` raises `OSError` (`server.py:714`), nothing catches it, and the process exits. Docker's default seccomp profile blocks io_uring_setup, so under it the server cannot start. README.md says it needs "Linux 6.4+ with io_uring enabled". The io_uring use is limited to Accept (multishot, into direct descriptors), Recv (multishot, buffer select), Send (MSG_WAITALL|MSG_NOSIGNAL), AsyncCancel, Shutdown and Close on fixed slots, PollAdd on its own eventfds, and a multishot Timeout. Every target is one of its own eight listeners, an accepted socket in a ring's fixed-file table, or its own eventfd. There are no OpenAt, Read, Write, Connect, Splice or file opcodes.

What "unconfined" exposes: the whole server container, including the entrypoint, runs without Docker's syscall filter. That widens the kernel attack surface, and io_uring has a history of local privilege-escalation CVEs. On Docker Desktop for Mac the exposed kernel is the LinuxKit VM's, not macOS. The compose file still sets `no-new-privileges`, Docker's default capability drop and resource limits, and the server runs as `ubuntu` via setpriv. This is acceptable for code that, as reviewed, does nothing hostile.

## Scope
- Read in full: all 7 tracked files under `submissions/python-pypy-iouring-kiwamizamurai`: .gitignore, README.md, install.sh, build.sh, start.sh, build_sqlite.py, server.py.
- The SQLite amalgamation is not tracked; build.sh downloads it. I verified it by hash rather than reading it line by line. I downloaded `sqlite-amalgamation-3540100.zip` into an isolated temp dir and confirmed its sha256 equals build.sh's `SQLITE_SHA256`. Its SHA3-256 equals the value in the sqlite.org download page's product table (the same file and hash as in the rust-iouring-kensac review). The zip holds only sqlite3.c, sqlite3.h, sqlite3ext.h and shell.c. Only sqlite3.c is `#include`d.
- No requirements file, no pip/PyPI install, no git or path dependencies, and no binaries or opaque blobs. `git status --ignored` on the folder is clean.
- Dependencies: the apt packages in install.sh. I checked the pinned `pypy3` and `pypy3-dev` versions against Launchpad's published binaries for noble amd64 and arm64, and checked `pypy3` against OSV (ecosystems `Ubuntu:24.04:LTS` and `Debian`).
- Downloads: the sqlite.org download page and the amalgamation zip, as above.
- Harness context: docker/server-entrypoint.sh.
- Nothing from the submission was built, executed or imported.

## Findings
- **note**: native aarch64 support. PyPy comes from Ubuntu's archive (`pypy3=7.3.15+dfsg-1build3`), which Launchpad lists as Published in noble/release for both amd64 and arm64. Nothing is downloaded per architecture. Syscall numbers are not hard-coded: `build_sqlite.py:86-97` uses `__NR_io_uring_setup/enter/register` from `<sys/syscall.h>`, and `IORING_*` register constants and struct layouts come from `<linux/io_uring.h>` (linux-libc-dev), so the C compiler fills them in for the target. The constants hard-coded in `server.py:631-653` are io_uring opcodes and flags, MSG_* flags and errno values (ENOBUFS 105, ECANCELED 125). All of these are the same on x86_64 and aarch64. The hand-packed 64-byte SQEs and 16-byte CQEs assume a little-endian 64-bit target, which aarch64 Linux is. No SIMD or x86 intrinsics.
- **note** `build.sh:8-12`: the SQLite download is skipped if `vendor/<dir>/sqlite3.c` already exists, and that copy would not be hash-checked. `vendor/` is gitignored, and the gate refuses a submission folder with ignored files, so in the bench a fresh, verified download always happens.
- **note** `server.py:411-426`: `cffi.FFI().dlopen("libcrypto.so.3")` loads the system OpenSSL (from the apt-installed `libssl3t64`) and calls only `EVP_sha256` and the one-shot `HMAC`. That is a dynamic library load from the distro's own package, not a vendored binary.
- **note** `server.py:750-752`: if `IORING_REGISTER_PBUF_RING` fails, the server retries once with `resv[0]=1`. This works around an inverted reserved-field check in some Ubuntu kernels (README cites Launchpad #2162843; the same workaround appears in c-iouring-pavlyhalim and rust-iouring-kensac). On a correct kernel the retry is rejected too and the server exits. It touches only the ring's own registration.
- **note**: complete syscall families, for the seccomp decision.
  - io_uring_setup, io_uring_enter and io_uring_register (files sparse, PBUF_RING, EVENTFD).
  - mmap of the ring and SQE regions (`MAP_SHARED|MAP_POPULATE` on the ring fd) and anonymous mmaps for provided buffers and the 1 MiB send arena segments (`build_sqlite.py:98-99`).
  - eventfd, one per extra ring, registered as that ring's completion notifier and polled from ring 0 (`server.py:1082-1087`).
  - getrlimit, and setrlimit(RLIMIT_NOFILE) raising only the soft limit to the inherited hard limit (`server.py:618-621`, `start.sh:4`).
  - socket, setsockopt (SO_REUSEADDR, SO_REUSEPORT, TCP_NODELAY), bind and listen on HOST:PORT, IPv4 only, eight listeners (`server.py:1059-1067`).
  - SQLite on SQLITE_PATH and its -wal file: open, pread, pwrite, fdatasync, fcntl locks, unlink, stat, and mmap (`PRAGMA mmap_size=1073741824`, `server.py:88`). The database is opened `SQLITE_OPEN_READWRITE` without CREATE.
  - PyPy's own runtime: loading its stdlib and `_sq` module, dlopen of libcrypto, and its JIT's executable mappings.
  - No process spawning (no `subprocess`, `os.system` or `os.exec*`). No outbound connect. No reads of /proc, /etc, $HOME, ~/.ssh, ~/.aws or docker.sock.
- **note** `server.py:19,77,613-614`: runtime env vars are exactly JWT_SECRET (required), SQLITE_PATH, HOST and PORT. `build_sqlite.py:7` reads `SQLITE_DIR`, which build.sh sets.
- **note** `build_sqlite.py:72-74`: SQLite is compiled with `SQLITE_OMIT_LOAD_EXTENSION`, so extension loading is unavailable. There is no `ATTACH` and no user-supplied SQL. All SQL is fixed and prepared at startup with bound parameters. The one string-built query, `rootpage()` (`server.py:101-106`), is called only with four hard-coded table and index names.
- **note** `server.py:144-363`: the read path walks SQLite's B-tree cursors through cffi and decodes record headers by hand with raw `unsigned char *` indexing, which is not bounds-checked. The record bytes come from the server's own database, not the network. Overflowing payloads are refused (`record()` requires the local payload to equal the full size), and any unexpected serial type falls back to the SQL statements. A corrupt database could cause out-of-bounds reads; network input cannot. Request input is bounded: 16 KiB of headers, 1 MiB body (Content-Length or chunked), and pending data per connection is capped at headers plus body.
- **note** `server.py:435-468`: the HS256 signature is checked with `hmac.compare_digest` before the payload is decoded. A header other than the canonical HS256 one is parsed only to confirm `alg == "HS256"`. `exp` is required and `nbf` is honoured. There is no `none` or key-confusion path. Segments are restricted to the base64url alphabet before `binascii.a2b_base64`, and the MAC covers the raw segment bytes, so the base64-decoding leniency CVEs listed below can't forge a token.
- **note** `server.py:1087`: functional, not security. The eventfd poll passes `IORING_POLL_ADD_MULTI` in the ioprio field, but the kernel reads it from `sqe->len`, so the poll is single-shot. After its first wakeup, completions on rings 1-7 are noticed only when ring 0 wakes for its own traffic or its once-a-second timer. Extra rings start only above roughly `TABLE/2` connections on ring 0, so this matters only at very high connection counts.

No blockers. No concerns above note level.

## Dependencies
No language-level dependencies. `cffi` is the copy bundled with PyPy (part of the `pypy3` package), not a PyPI install. The C dependencies are SQLite (vendored by download, hash-verified) and the system libcrypto.

| name | version | source | registry check | OSV result |
|---|---|---|---|---|
| pypy3 | 7.3.15+dfsg-1build3 (pinned) | Ubuntu noble main archive | Launchpad: Published, noble release, amd64 and arm64 | 20 `UBUNTU-CVE-*` entries, no MAL-* |
| pypy3-dev | 7.3.15+dfsg-1build3 (pinned) | Ubuntu noble archive (same source package) | Launchpad: Published, noble release, arm64 | covered by the pypy3 source entry |
| build-essential, curl, unzip, ca-certificates, libssl3t64, linux-libc-dev | distro current | Ubuntu noble archive | standard Ubuntu packages | not pinned; apt signature-verified |
| SQLite amalgamation | 3.54.1 | sqlite.org | see Downloads | n/a (not an OSV ecosystem package) |

The pypy3 OSV entries are CPython stdlib issues that PyPy inherits: urllib.parse, xml.dom.minidom, the base64 module, os.path.expandvars, html.parser, tarfile, email, http.client, unicodedata, pyexpat/ElementTree, webbrowser, http.cookies and the lzma/bz2/gzip decompressors. The server imports only binascii, gc, hmac, json, os, resource, socket, sys, time and cffi. Of these advisories, only the two base64-leniency ones (CVE-2025-12781, CVE-2026-3446) are near a code path it uses. The server calls `binascii.a2b_base64` directly, on input already restricted to the base64url alphabet, and only after the signature over the raw bytes has been verified, so neither applies. None is reachable from the API.

## Downloads at build time
| URL | official? | pinned? | checksum verified? |
|---|---|---|---|
| Ubuntu apt mirrors: `pypy3 pypy3-dev` (install.sh:6) | yes (distro) | yes (`=7.3.15+dfsg-1build3`) | apt signature verification |
| Ubuntu apt mirrors: `build-essential curl unzip ca-certificates libssl3t64 linux-libc-dev` (install.sh:6) | yes (distro) | no (distro current) | apt signature verification |
| `https://sqlite.org/2026/sqlite-amalgamation-3540100.zip` (build.sh:9) | yes | yes (3.54.1) | yes: sha256 `0a9c8e34352dad46006aa82836d5383bff9dc6bc9ce5a60553c05aa30e6ad1f9` checked by build.sh:10 and matches my download; SHA3-256 `92281c86...df28e30` equals the value on sqlite.org/download.html |
