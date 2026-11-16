# Security reviews

`docker/bench.sh` builds and runs a submission only when `docker/reviews/<submission>.md` exists and:

- says `verdict: pass`
- has `tree:` equal to `git rev-parse HEAD:submissions/<submission>`, so a review covers exactly the code it read and any later change needs a new review
- the submission folder has no uncommitted, untracked or ignored files

The review also sets `seccomp:`. `builtin` keeps Docker's default syscall filter. `unconfined` is for
submissions that genuinely need io_uring, and `SERVER_SECCOMP` can't override it.

## What a review covers

The review is static: it never builds, installs or runs the code.

1. **Every tracked file, read in full.** Look for obfuscation, outbound network calls, file access
   outside the submission folder and `SQLITE_PATH`, unexpected environment variables, spawned processes,
   persistence, credential or Docker-socket access, and anything unrelated to serving the API.
2. **`install.sh` and `build.sh`.** For every download, check it comes from an official source, is
   pinned and has its checksum verified. Check for anything installed beyond what the app needs.
3. **Every dependency, transitive ones included where there's a lockfile.** Confirm it's the genuine
   package (not a typosquat), confirm it's pinned, and check it against [OSV](https://osv.dev). `MAL-*`
   advisories mean malware.
4. **No prebuilt binaries or opaque vendored blobs.**

Front matter, which the gate parses:

```
---
submission: <folder>
tree: <git tree sha>
verdict: pass | fail
seccomp: builtin | unconfined
reviewed: <date>
---
```

Then add sections for Verdict, Scope, Findings, Dependencies and Downloads at build time.

## The sandbox at run time

The review is one layer. During a run, the server also sits on an `internal` Docker network with no
internet, LAN or host access, and `bench.sh` checks that from inside the server before any load
starts. It also runs as a non-root user with `no-new-privileges`. Builds still have internet access,
because `install.sh` and `build.sh` download toolchains and dependencies. That is why the review
matters.
