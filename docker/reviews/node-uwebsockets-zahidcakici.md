---
submission: node-uwebsockets-zahidcakici
tree: 9fe497a3367839d8ca40a6305ee81974467988b4
verdict: pass
seccomp: builtin
reviewed: 2026-11-15
---
# Security review: node-uwebsockets-zahidcakici

## Verdict
Safe to build and run. Nothing malicious or blocker-level was found. The server is a single-threaded Node.js 24.21.0 process. It uses uWebSockets.js for HTTP and better-sqlite3 for SQLite, and serves `HOST:PORT` directly (no nginx). Both native addons are compiled from source at build time. uWebSockets.js, uWebSockets and uSockets are fetched by exact git commit, and each commit is verified after checkout. The better-sqlite3 npm package ships prebuilt `.node` files; build.sh deletes them and compiles the addon and its bundled SQLite 3.53.4 amalgamation with node-gyp. The uWebSockets.js prebuilt release binaries are never downloaded. At runtime the server reads only the four spec env vars, `/proc/self/limits`, and the SQLite file at SQLITE_PATH (plus its -wal file). It makes no outbound connections, spawns no processes and reads no credentials. Both npm packages (better-sqlite3 and its one transitive dependency, node-addon-api) are genuine, their lockfile integrity matches the registry, and OSV reports nothing for either. The Node tarball sha256s in install.sh match nodejs.org's SHASUMS256.txt.

`seccomp: builtin` is correct. uSockets is built with `-DLIBUS_USE_LIBUV` (Node's own libuv loop, epoll on Linux). Only `src/us/*.c` and `src/us/eventing/*.c` are compiled, and uSockets' `io_uring/` directory is not. Nothing in the submission uses io_uring.

## Scope
- Read in full: all 8 tracked files under `submissions/node-uwebsockets-zahidcakici`: .gitignore, install.sh, build.sh, start.sh, package.json, package-lock.json, server.js, README.md.
- Build-time sources, inspected read-only at the pinned commits (codeload tarballs and the GitHub API, in an isolated temp dir, not built):
  - uWebSockets.js `127ac802`: `src/` file list and `addon.cpp` includes, plus the lines build.sh's sed edits. This commit equals `source_commit` in the official v20.71.0 release tag (`9ec36de7`, `binaries` branch).
  - uWebSockets `1d80f7a5` and uSockets `86097c49`: both equal the submodule pointers recorded at the parent commit.
  - All three commits are ancestors of their upstream default branches (GitHub compare: behind_by 0).
  - I grepped all three source trees for process spawning, dlopen, getenv, file opens and URLs. The only hit is upstream's `getenv("UWS_HTTP_MAX_HEADERS_SIZE")` (`HttpParser.h:51`), which is benign.
- better-sqlite3 13.0.3 and node-addon-api 8.9.2: downloaded both registry tarballs, recomputed their sha512 against the lockfile, and listed every file. I read the build-time JS and gyp that node-gyp executes: `binding.gyp`, `deps/{common,defines,sqlite3}.gypi/gyp`, `deps/copy.js`, `lib/binding.js`, `deps/patches/1208.patch` and node-addon-api's `index.js`. The bundled `sqlite3.c` reports SQLITE_VERSION 3.53.4 with source id `bf7c7f3003…`, which matches the 3.53.4 check-in in sqlite.org's release chronology. I did not diff the amalgamation line by line.
- Downloads: fetched nodejs.org/dist/v24.21.0/SHASUMS256.txt and compared it to install.sh. Hashed `v8-fast-api-calls.h` from the v24.21.0 tag and compared it to build.sh.
- Harness context: docker/server-entrypoint.sh.
- `git status --ignored` on the folder is clean. No binaries or opaque blobs are tracked.
- Nothing from the submission was built, executed or imported.

## Findings
- **note** `install.sh:12-16`: native aarch64 support. install.sh picks the Node tarball by `uname -m`, with pinned sha256s for `x86_64` (x64) and `aarch64` (arm64), and exits on anything else. build.sh is architecture-neutral: `-O3 -flto`, no `-march=native`, no x86 intrinsics in server.js. The uSockets and better-sqlite3 C sources are portable.
- **note** `build.sh:19-24,28-33`: the git fetches are shallow fetches of an exact commit SHA, followed by a `rev-parse HEAD` equality check. The fetch is skipped if `build/uws.<sha>.ok` already exists. `build/` is gitignored and the gate refuses a submission folder with ignored files, so in the bench a fresh fetch always happens.
- **note** `build.sh:37-38`: `v8-fast-api-calls.h` comes from raw.githubusercontent.com at the `v24.21.0` tag, a mutable ref. Its sha256 is checked, so it is effectively pinned. The hash matches the file as served today.
- **note** `build.sh:46-56`: build.sh makes three source edits, and each is checked by grep afterwards:
  - Both HTTP timeout constants go from 10 s to 75 s.
  - The HTTP/3 include, export and template lines are deleted from `addon.cpp`.
  - A forward-declaration stub stands in for the H3 types.

  These edits disable code rather than add it. They need TLS and QUIC to be off (`-DLIBUS_NO_SSL`), so BoringSSL and lsquic are not fetched.
- **note** `build.sh:58`: `-DUWS_WITH_PROXY` enables PROXY-protocol parsing, so a client could claim another source address. The server never reads the remote address, so this has no security effect here.
- **note** `build.sh:68-73`: `npm ci --ignore-scripts` means no package lifecycle scripts run. The prebuilt `prebuilds/*.node` (8 platform ELF/Mach-O/PE files shipped in the npm tarball) are deleted before the build. The addon is then built with `--force_build=1` and `--nodedir` (the verified Node install, so no header download). server.js loads it via an explicit `nativeBinding` path into `bin/`, so the prebuild lookup in `lib/binding.js` is never used. During the build, node-gyp runs better-sqlite3's `node lib/binding.js`, `deps/copy.js` and `node -p require('node-addon-api').include`. I read all three, and they only test for or copy files inside the package.
- **note** `build.sh:74`: build.sh loads both built addons once with `:memory:` as a smoke test. This is part of the normal build, not a network call.
- **note** `server.js:15`: runtime env vars are exactly SQLITE_PATH, JWT_SECRET, HOST and PORT, with local defaults for HOST and PORT. `server.js:79` reads `/proc/self/limits` to size a keep-alive budget. Nothing else is read from disk except the SQLite database.
- **note** `server.js:37-60`: all SQL is fixed, prepared at startup, with bound parameters. There is no `loadExtension`, `ATTACH` or user-supplied SQL. `locking_mode = EXCLUSIVE`, so there is no -shm file.
- **note** `server.js:109-136`: the HS256 signature is verified with `timingSafeEqual` (length checked first) before the payload is parsed. `alg` must be HS256, so there is no `none` or key-confusion path. `exp` and `nbf` are enforced only when present: a validly signed token without `exp` is accepted. Whether that is acceptable is a spec question, not a security one, since only the bench holds the secret.
- **note** `server.js:217`: `/health` returns the SQLite error message in its 503 body. This is a minor information leak, limited to the isolated bench network.
- **note** `server.js:245-282`: request bodies are capped at 64 KiB (413 above that), and post bodies at 500 code points. uWebSockets caps headers at 4 KiB by default.
- **note** `install.sh:9-10`: install.sh installs `build-essential python3 git curl ca-certificates xz-utils` from Ubuntu apt. All are needed: python3 for node-gyp, git for the fetches. Node is extracted with `--no-same-owner` into `/opt/node-v24.21.0`.
- **note** `start.sh:5`: start.sh runs `node --max-semi-space-size=64 server.js` with the pinned Node binary. No other flags are passed.

No blockers. No concerns above note level.

## Dependencies
Both lockfile entries resolve to registry.npmjs.org, and their `integrity` sha512 equals both the registry metadata and my hash of the downloaded tarball. Both versions were published by GitHub Actions trusted publishing (OIDC) from their official repositories. OSV `/v1/querybatch` (ecosystem npm) returned no vulns for either, and no MAL-* ids. I also queried OSV for `uWebSockets.js` 20.71.0, which is built from git, not npm: no results.

| name | version | source+integrity | registry check | OSV result |
|---|---|---|---|---|
| better-sqlite3 | 13.0.3 (exact in package.json) | npm, match | 2016, 16.9M dl/week, WiseLibs/better-sqlite3 | none |
| node-addon-api (transitive) | 8.9.2 | npm, match | 2017, 134M dl/week, nodejs/node-addon-api | none |

Native sources fetched from GitHub (not npm):

| repo | commit | provenance |
|---|---|---|
| uNetworking/uWebSockets.js | 127ac8029b04e8272da068055bc04c1cd0d7bd38 | `source_commit` of the v20.71.0 release; on the default branch |
| uNetworking/uWebSockets | 1d80f7a53816ef2433e89793b285b827f3efb2b2 | submodule pointer at the above; on the default branch |
| uNetworking/uSockets | 86097c490263ab662d62e8e7b541390bdec7d149 | submodule pointer at uWebSockets `1d80f7a`; on the default branch |

## Downloads at build time
| URL | official? | pinned? | checksum verified? |
|---|---|---|---|
| Ubuntu apt mirrors: `build-essential python3 git curl ca-certificates xz-utils` (install.sh:9-10) | yes (distro) | no (distro current) | apt signature verification |
| `https://nodejs.org/dist/v24.21.0/node-v24.21.0-linux-$arch.tar.xz` (install.sh:19), arch x64 or arm64 | yes | yes (v24.21.0) | yes: sha256 checked by install.sh:20. x64 `fd8e59d5…cb2d6` and arm64 `6ad1325e…89ad2` both equal nodejs.org's SHASUMS256.txt |
| `https://github.com/uNetworking/uWebSockets.js.git` @ `127ac802…` (build.sh:29) | yes | yes (exact commit) | yes: `rev-parse HEAD` must equal the pinned SHA |
| `https://github.com/uNetworking/uWebSockets.git` @ `1d80f7a5…` (build.sh:30) | yes | yes (exact commit) | yes: as above |
| `https://github.com/uNetworking/uSockets.git` @ `86097c49…` (build.sh:31) | yes | yes (exact commit) | yes: as above |
| `https://raw.githubusercontent.com/nodejs/node/v24.21.0/deps/v8/include/v8-fast-api-calls.h` (build.sh:37) | yes | tag ref, pinned by hash | yes: sha256 `c6c8b22e…0b842` checked by build.sh:38, and it matches my download |
| registry.npmjs.org (2 packages via `npm ci --ignore-scripts`, build.sh:68) | yes | yes (exact version + lockfile) | yes (lockfile sha512 integrity, verified against the registry) |
