---
submission: go-iouring-huykn
tree: 20c02b599c9575327209c0faf82203c8e075ee4b
verdict: pass
seccomp: unconfined
reviewed: 2026-11-15
---
# Security review: go-iouring-huykn

## Verdict
Safe to build and run. I found nothing malicious and no blockers. The server is a Go (cgo) io_uring HTTP/1.1 server on one locked OS thread, serving `HOST:PORT` directly (no nginx). Its io_uring binding is hand-written against the kernel ABI. It statically links a checksum-verified, unmodified SQLite 3.54.1 amalgamation, `#include`d by `sqlite_engine.c` together with a read-only B-tree cursor reader (`btree_reader.h`). At runtime it reads the four spec env vars plus three diagnostic `HKN_*` switches. It touches only its listening sockets, accepted client sockets and the SQLite file at SQLITE_PATH with its -wal sibling (the default `unix-excl` VFS keeps the WAL index in heap, so there is no -shm file). It makes no outbound connections, spawns no processes and reads no credentials. There are no third-party Go modules: `go.mod` has no `require` and there is no `go.sum`. The Go tarball sha256s in install.sh match go.dev's published checksums. The SQLite zip's sha256 matches build.sh, and its SHA3-256 matches the value sqlite.org publishes.

`seccomp: unconfined` is justified. The server has no non-io_uring code path. `main.go:52-55` returns the error if `newRing` fails, and `main.go:108-112` then exits with status 1. `newRing` (`server.go:189-206`) calls `io_uring_setup` through a raw syscall (`uring.go:128-131`). Under Docker's default seccomp profile, which blocks io_uring_setup, the server cannot start. The code's io_uring use is limited to these operations on its own listeners and ring-registered accepted sockets: Accept (into direct descriptors), Recv (multishot and single-shot, buffer select), Send (MSG_NOSIGNAL), Shutdown and Close (fixed), plus a sparse file table and one provided-buffer ring per io_uring. It uses no OpenAt, Read, Write, Connect, Splice or other file opcodes.

What "unconfined" exposes: the whole server container, including the entrypoint, runs without Docker's syscall filter. That widens the kernel attack surface, and io_uring has a history of local privilege-escalation CVEs. On Docker Desktop for Mac the exposed kernel is the LinuxKit VM's, not macOS. The compose file still sets `no-new-privileges`, Docker's default capability drop and resource limits, and the server runs as `ubuntu` via setpriv. That is acceptable for code that, as reviewed, does nothing hostile.

## Scope
- Read in full: all 41 tracked files under `submissions/go-iouring-huykn`:
  - Build and config: .gitignore, go.mod, install.sh, build.sh, start.sh and README.md.
  - Go sources: main.go, uring.go, server.go, app.go, db.go, http.go, jwt.go, scan.go and bytes.go.
  - C sources: bridge.h, store.h, store.c, read_plan.h, btree_reader.h, checkpoint.h, checkpoint.c, sqlite_engine.c and testdata/store_contract.c.
  - All 17 `*_test.go` files.
- The SQLite amalgamation is not tracked; build.sh downloads it. I verified it by hash rather than reading it line by line. I downloaded `sqlite-amalgamation-3540100.zip` into an isolated temp dir. Its sha256 equals build.sh's `SQ_SHA`, and its SHA3-256 equals the value in the product table on the sqlite.org download page. The zip holds only sqlite3.c, sqlite3.h, sqlite3ext.h and shell.c. build.sh keeps only sqlite3.c and sqlite3.h.
- I found no `go.work`, `vendor/` directory, `replace` directive, `.syso` file, `//go:cgo_*` pragma, `#cgo pkg-config`, `//go:linkname` or `//go:embed`, and no binaries or opaque blobs. `git status --ignored` on the folder is clean.
- Dependencies: the Go 1.27.3 standard library and toolchain, plus SQLite. I checked the Go stdlib and toolchain against OSV `/v1/query` (ecosystem Go, packages `stdlib` and `toolchain`).
- Downloads: I fetched `https://go.dev/dl/?mode=json&include=all` and compared the linux-amd64 and linux-arm64 sha256s with install.sh. I hashed the SQLite zip as described above.
- Harness context: docker/server-entrypoint.sh.
- Nothing from the submission was built, executed or imported.

## Findings
- **note** `install.sh:7-11`: native aarch64 support. install.sh maps `uname -m` to the Go `amd64` or `arm64` tarball, with a pinned sha256 for each, and exits on anything else. build.sh is architecture-neutral. Nothing in the code is x86-specific:
  - The io_uring syscall numbers 425/426/427 (`uring.go:17-19`) are the same on every Linux architecture.
  - The hard-coded `SO_REUSEPORT` value 0xf (`main.go:90`) is correct for arm64 and x86_64.
  - The unaligned 8-byte loads in `bytes.go:44-83` are valid on arm64, and each is bounds-guarded.
- **note** `db.go:4`, `build.sh:16`: cgo compiles with `-march=native`. The binary is tied to the build host's CPU, so build and run must be on the same machine. This is a portability issue, not a security one.
- **note** `build.sh:9-14`: build.sh skips the SQLite download if `sqlite/sqlite3.c` already exists, and that copy would not be hash-checked. `sqlite/` is gitignored, and the gate refuses a submission folder with ignored files, so in the bench a fresh, verified download always happens.
- **note** `install.sh:13`: Go 1.27.3 is not the latest patch release. Go 1.27.4 fixes:
  - one stdlib advisory, GO-2026-6859 in `net/http`. The server never imports `net/http`; it uses `net` only for `ParseIP`.
  - eleven toolchain advisories, GO-2026-6848 to 6858. These are cgo directive and linker-flag injection at build time, triggered by a malicious package's cgo directives, `//go:cgo_*` pragmas, `.syso` files or pkg-config.

  The only cgo directives in this submission are plain `-O3 -march=native -fno-plt -D...` CFLAGS, `-lm -lpthread` LDFLAGS and `nocallback` (`db.go:4-12`). It has none of the other inputs and no third-party packages, so none of these advisories is reachable. Bumping to 1.27.4 is still advisable.
- **note** `uring.go:376-381`: if the kernel returns EINVAL to `IORING_REGISTER_PBUF_RING`, the code retries once with `resv[0]=1`. This is a workaround for an inverted reserved-field check in some Ubuntu kernels (the comment cites Launchpad #2162843). On a correct kernel the retry is rejected too and the server exits. It is odd but benign, because it touches only the ring's own registration.
- **note** `uring.go:124-173,291-342`, `server.go:25-38,189-206`: the complete io_uring surface.
  - Setup uses CQSIZE, SUBMIT_ALL, SINGLE_ISSUER and DEFER_TASKRUN (Linux 6.1+), with 4096 SQ and 65536 CQ entries and MAP_POPULATE mmaps of the ring.
  - Registration covers `IORING_REGISTER_FILES2` (sparse) and one 1024 x 2 KiB provided-buffer ring per io_uring.
  - Opcodes are Accept (`IORING_FILE_INDEX_ALLOC`), Recv, Send, Shutdown (hard-linked) and Close.
  - Every target is one of the eight SO_REUSEPORT listener fds or a ring-registered accepted socket.
  - There are at most 16 rings, all on the one thread.
- **note**: complete syscall families, for the seccomp decision.
  - io_uring_setup, io_uring_enter and io_uring_register.
  - mmap and munmap, for the ring and for anonymous buffer memory.
  - getrlimit, and setrlimit(RLIMIT_NOFILE), which raises only the soft limit to the inherited hard limit (`main.go:63-73`).
  - socket, setsockopt (SO_REUSEADDR, SO_REUSEPORT, TCP_NODELAY), bind and listen on HOST:PORT. IPv4 only (`main.go:76-106`).
  - Go runtime basics: clone, futex, signals and sched.
  - One pthread for passive WAL checkpoints, on its own SQLite connection (`checkpoint.c`).
  - SQLite's unix-excl VFS on SQLITE_PATH and its -wal file: open, pread, pwrite, fdatasync, fcntl locks, unlink and stat. `PRAGMA mmap_size=0` (`store.c:99`).
  - The server does not spawn processes. `os/exec` appears only in tests. It makes no outbound connect and reads nothing in /proc, /etc, $HOME, ~/.ssh, ~/.aws or docker.sock.
- **note** `main.go:26-43`, `store.c:89,107,109`: runtime env vars are SQLITE_PATH, JWT_SECRET, HOST and PORT, with local defaults. There are also three diagnostic switches, all unset by the harness:
  - `HKN_VFS` passes a VFS name to `sqlite3_open_v2`. Only SQLite's built-in VFSes exist, and extension loading is compiled out.
  - `HKN_SQL_READS=1` forces the reference SQL reads.
  - `HKN_CHECKPOINT=inline` switches to SQLite's automatic checkpoints.

  `start.sh:3` sets `GOMAXPROCS=1 GODEBUG=asyncpreemptoff=1`, and `build.sh:6,15` sets PATH, `CGO_ENABLED`, `GOFLAGS=-trimpath` and `GOTOOLCHAIN=local`. `GOTOOLCHAIN=local` stops the go command from downloading a different toolchain.
- **note** `db.go:5`, `store.c:16-38`: SQLite is compiled with `SQLITE_OMIT_LOAD_EXTENSION`, so extension loading is unavailable. There is no `ATTACH` and no user-supplied SQL. All SQL is fixed, prepared at startup, and run with bound parameters.
- **note** `btree_reader.h`, `db.go:64-69,105`, `bytes.go:44-83`, `uring.go`: substantial unsafe and C code. The read plan reaches into SQLite internals (Table, Index, BtCursor, KeyInfo, UnpackedRecord) and decodes record headers by hand. Go then reads C arena spans through `unsafe.Slice`. I found no deliberate misuse, and the reads are guarded:
  - `bounded_varint` and `decode_prefix` check every varint and field width against the payload size.
  - Overflow payloads are copied into a fixed 64 KiB buffer only if they fit.
  - `arena_text` and `save_column` check each copy against the 64 KiB result arena.
  - Result rows are capped at 20, by the plan's loop and by the SQL `LIMIT 20` or primary-key lookup.
  - At startup the reader checks column names, index shape, collation, encoding and the schema cookie, and on any mismatch falls back to the reference SQL.

  Input is bounded: 16 KiB of headers, a 1 MiB body, 2 KiB receive buffers and a JSON nesting depth of 64. A memory-safety bug would be reachable from network input, but only on the isolated bench network.
- **note** `jwt.go:106-135`: the HS256 signature is verified in constant time (`hmac.Equal`) before the header or payload is parsed. `alg` must be HS256 and `exp` is required. The base64url decoding is strict. There is no `none` or key-confusion path.
- **note** `server.go:687-711`: there is no keep-alive or idle timeout, and the server holds connections until it reaches 16 rings of RLIMIT_NOFILE slots each. This is a resource concern, not a security one, on the isolated bench network.
- **note** `*_test.go`, `testdata/store_contract.c`: test-only code is not part of `go build`. It reads `../../schema.sql`, runs the `sqlite3` CLI and re-executes the test binary with fixture env vars, and the README's guard-page test uses mmap and mprotect. Go never compiles the `testdata/` directory.
- **note** `install.sh:5-6`: apt installs `build-essential curl ca-certificates unzip`. That is what the build needs (a C compiler for cgo, curl and unzip for SQLite), and nothing more.

No blockers. No concerns above note level.

## Dependencies
There are no third-party Go modules. `go.mod` declares only `module go-iouring-huykn` and `go 1.27.0`, has no `require`, and there is no `go.sum`. The imports are all standard library: bytes, crypto/hmac, crypto/sha256, encoding/base64, errors, fmt, hash, net (ParseIP only), os, runtime, runtime/debug, strconv, sync/atomic, syscall, time, unicode/utf8 and unsafe, plus `C`.

| name | version | source+checksum | registry check | OSV result |
|---|---|---|---|---|
| Go stdlib | 1.27.3 | go.dev tarball, sha256 match | official Go release, marked stable in go.dev's release list | GO-2026-6859 (`net/http`; not imported). Fixed in 1.27.4 |
| Go toolchain | 1.27.3 | same tarball | same | GO-2026-6848 to 6858 (cgo directive and linker-flag injection at build). Not triggered: the submission uses only plain CFLAGS and `-lm -lpthread`. Fixed in 1.27.4 |
| SQLite amalgamation | 3.54.1 | sqlite.org zip, sha256 and SHA3-256 match | official sqlite.org download | not queried in OSV (no OSV ecosystem for the amalgamation); latest release on sqlite.org |

No MAL-* advisories.

## Downloads at build time
| URL | official? | pinned? | checksum verified? |
|---|---|---|---|
| Ubuntu apt mirrors: `build-essential curl ca-certificates unzip` (install.sh:5-6) | yes (distro) | no (distro current) | apt signature verification |
| `https://go.dev/dl/go1.27.3.linux-$ARCH.tar.gz` (install.sh:13), ARCH amd64 or arm64 | yes | yes (1.27.3) | yes, the sha256 is checked by install.sh:14. Both amd64 `65efbc80...79b40` and arm64 `a06e9930...5f49` equal the values go.dev publishes |
| `https://www.sqlite.org/2026/sqlite-amalgamation-3540100.zip` (build.sh:11) | yes | yes (3.54.1) | yes, the sha256 `0a9c8e34352dad46006aa82836d5383bff9dc6bc9ce5a60553c05aa30e6ad1f9` is checked by build.sh:12 and matches my download. The SHA3-256 `92281c86...df28e30` equals the value on sqlite.org/download.html |
| Go modules | none | n/a | n/a (`GOTOOLCHAIN=local`; there are no module requirements, so nothing is fetched from the module proxy) |
