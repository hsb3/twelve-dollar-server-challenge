---
submission: python-fastapi-cknutson12
tree: 86770faa48e4512cd540592ee09c740188e9c61f
verdict: pass
seccomp: builtin
reviewed: 2026-10-13
---
# Security review: python-fastapi-cknutson12

## Verdict
Safe to build and run. The submission is a straightforward FastAPI + uvicorn app over the stdlib
`sqlite3` module. It has no obfuscation, no eval/exec or dynamic imports, no outbound network
calls, no process spawning, no persistence, no filesystem access beyond `SQLITE_PATH`, and it reads
only the four sanctioned env vars. install.sh installs only Ubuntu's `python3` and `python3-venv`
from apt. build.sh installs 17 exact-pinned, wheels-only packages from PyPI. All are genuine,
long-established projects with no OSV advisories, malware ones included. Remaining concerns are
supply-chain hygiene only: there are no hashes in requirements.txt, and apt versions are not pinned.

## Scope
- Files read in full (all 8 tracked files in the tree): `.gitignore`, `README.md`, `app.py` (215
  lines), `server.py` (20), `install.sh`, `build.sh`, `start.sh`, `requirements.txt`. `file`
  reports all as text. No binaries, archives or blobs.
- Checked every non-ASCII byte in the tree. The only ones are on `app.py:124`, inside a string
  literal: 19 Unicode whitespace code points (U+00A0, U+1680, U+2000-U+200A, U+2028, U+2029,
  U+202F, U+205F, U+3000, U+FEFF). They match JavaScript's `trim()` set. There are no bidi
  override or isolate characters (U+202A-U+202E, U+2066-U+2069) and no other control characters.
- Dependencies: the PyPI JSON API (`/pypi/<name>/<version>/json` and `/pypi/<name>/json`) for all
  17 pins. Checked the release exists and is not yanked, project age, maintainers, source repo,
  wheel availability for cp312 manylinux x86_64/aarch64, and `requires_dist`.
- OSV: `POST https://api.osv.dev/v1/querybatch` for all 17 name+version pairs, plus a per-package
  `/v1/query` without a version to catch any `MAL-*` advisory on any release.

## Findings
- note, app.py:7-19 / server.py:2-4: imports are stdlib (`base64`, `gc`, `hashlib`, `hmac`, `os`,
  `re`, `sqlite3`, `time`) plus `orjson`, `fastapi`, `starlette`, `uvicorn`. `base64` is used only
  for JWT base64url decoding (app.py:82-85, 99). There are no encoded payloads.
- note, app.py:21-22, server.py:9-10: env reads are limited to `SQLITE_PATH`, `JWT_SECRET`, `HOST`
  and `PORT`. The HOST/PORT defaults are 127.0.0.1:3000.
- note, app.py:30: the only file opened is `sqlite3.connect(SQLITE_PATH)` (plus SQLite's own WAL
  and shm sidecar files). Pragmas are WAL, synchronous=NORMAL, mmap 1 GiB and cache 64 MiB.
  `mmap_size` and `cache_size` are memory tuning, not a security issue.
- note, server.py:7-20: the only socket is uvicorn's listener, with `backlog=4096`. Nothing dials out.
- note, app.py:88-119: JWT verification is hand-rolled but sound. It accepts HS256 only, compares
  signatures in constant time with `hmac.compare_digest`, and checks exp and nbf. SQL is fully
  parameterised.
- note, app.py:148: `/health` returns `str(exc)` on a DB failure. That is a minor info leak (an
  SQLite error message) and is harmless here.
- note, app.py:213-215: `gc.freeze()` and a raised GC threshold. Performance tuning only.
- concern, requirements.txt: every package is pinned with `==` (transitive set included) and
  build.sh uses `--only-binary=:all:`, so no sdist `setup.py` runs at build time. But there are no
  `--hash=` entries, so integrity relies on PyPI's TLS and immutability, not on a hash lock.
  Acceptable for an official registry.
- concern, install.sh:5-6: `apt-get install python3 python3-venv` takes whatever versions are
  current in Ubuntu 24.04. They are official packages and apt verifies its signatures, but the
  versions are not pinned. This is normal for the challenge.
- note, requirements.txt:14: `opentelemetry-api` looks out of place, but it is a declared runtime
  dependency of fastapi 0.142.2 (`opentelemetry-api>=1.44.0`). It is genuine (OpenTelemetry
  Authors, CNCF) and the app never imports it.
- note, pin closure: every non-extra `requires_dist` of every pin is satisfied inside the file, so
  pip resolves nothing unpinned. `exceptiongroup` is excluded by its python<3.11 marker.
- Seccomp: nothing needs syscalls outside Docker's default profile. uvloop uses libuv's
  epoll-based loop, not io_uring, and there is no ptrace, perf or raw sockets. The value is
  `builtin`.
- Blockers: none. Prebuilt binaries in the tree: none (compiled code arrives only as official
  PyPI wheels at build time, which the rules allow).

## Dependencies
| name | version | pinned | registry check | OSV result |
|---|---|---|---|---|
| fastapi | 0.142.2 | == | genuine (tiangolo, since 2018), py3 wheel, not yanked | none |
| uvicorn | 0.54.0 | == | genuine (Kludex/encode, since 2017), py3 wheel | none |
| uvloop | 0.23.0 | == | genuine (MagicStack/Selivanov, since 2016), cp312 manylinux wheels | none |
| httptools | 0.8.0 | == | genuine (MagicStack, since 2015), cp312 manylinux wheels | none |
| orjson | 3.12.0 | == | genuine (ijl, since 2018), cp312 manylinux wheels | none |
| annotated-doc | 0.0.5 | == | genuine (fastapi org, since 2023), py3 wheel | none |
| annotated-types | 0.8.0 | == | genuine (pydantic maintainers, since 2022), py3 wheel | none |
| anyio | 4.15.1 | == | genuine (agronholm, since 2018), py3 wheel | none |
| click | 8.5.0 | == | genuine (pallets, since 2014), py3 wheel | none |
| h11 | 0.16.0 | == | genuine (python-hyper, since 2016), py3 wheel | none |
| idna | 3.20 | == | genuine (kjd, since 2013), py3 wheel | none |
| opentelemetry-api | 1.45.0 | == | genuine (OpenTelemetry/CNCF, since 2019), py3 wheel | none |
| pydantic | 2.13.5 | == | genuine (pydantic, since 2017), py3 wheel | none |
| pydantic_core | 2.46.5 | == | genuine (pydantic, since 2022), cp312 manylinux wheels | none |
| starlette | 1.7.0 | == | genuine (Kludex/encode, since 2018), py3 wheel | none |
| typing-inspection | 0.4.4 | == | genuine (pydantic, since 2025), py3 wheel | none |
| typing_extensions | 4.16.0 | == | genuine (python/typing, since 2017), py3 wheel | none |

There are no typosquats. Every name matches its canonical project and its source repo. Installs are
wheels-only (`--only-binary=:all:`) but not hash-pinned.

## Downloads at build time
| URL | official? | pinned? | checksum verified? |
|---|---|---|---|
| Ubuntu 24.04 apt mirrors (`apt-get update`; `python3`, `python3-venv` + deps) | yes | no (distro-current) | yes (apt GPG-signed Release + package hashes) |
| https://pypi.org/simple + files.pythonhosted.org (17 wheels via `pip -r requirements.txt`) | yes | yes (`==`, full closure) | no `--hash`; TLS only |

There is no curl, wget or `curl | sh`, and no other URLs anywhere in the submission.
