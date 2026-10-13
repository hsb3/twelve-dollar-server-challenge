---
submission: ruby-rails-gambitboy
tree: d4c78caa9477e5ea716fb82f87fa271c18711083
verdict: pass
seccomp: builtin
reviewed: 2026-10-13
---
# Security review: ruby-rails-gambitboy

## Verdict
Safe to build and run in the Docker harness. The submission is a stock `rails new` app (Rails 8.1.4) with a small amount of hand-written API code (5 controllers, 3 models, 2 concerns) that does only what SPEC.md asks: SQLite reads/writes through Active Record and HS256 JWT verification via the `jwt` gem. The app code has no process spawning, outbound network, dynamic eval, deserialization of untrusted data, obfuscated blobs or file access outside the app dir and `SQLITE_PATH`. The Gemfile uses only rubygems.org (no `git:`/`path:` sources). Gemfile.lock pins all 134 specs and has a `CHECKSUMS` section, and every checksum matches rubygems.org. OSV reports no vulnerabilities or malware for any locked gem. The one moderate concern is that install.sh downloads the official Ruby tarball without verifying its checksum. The tarball served today matches the official sha256.

## Scope
- All 110 tracked files in `git ls-files submissions/ruby-rails-gambitboy`; the working tree is clean against the index, so the files read are the reviewed tree.
- Read in full: install.sh, build.sh, start.sh, Gemfile, Gemfile.lock, .ruby-version, Dockerfile, .dockerignore, all of `app/` (controllers, concerns, models, helpers, jobs, mailers, views, JS, CSS), `config/` (application, boot, environment, puma, routes, database, cable, storage, importmap, ci, deploy, bundler-audit, locales, all 3 environments, all 4 initializers), all `bin/*`, `.kamal/secrets` and all 9 `.kamal/hooks/*.sample`, `.github/*`, `.rubocop.yml`, `.gitignore`, CLAUDE.md, README.md, `script/bench`, `test/test_helper.rb`, `db/seeds.rb`, config.ru, Rakefile, `public/icon.svg`, `public/robots.txt`.
- `public/4xx/5xx.html`: grepped for `<script>`, `<link>`, `<img>` and URLs. None found apart from the SVG xmlns, so these are the stock Rails 8 error pages. `public/icon.png`: a valid 512x512 PNG with no bytes after IEND. `config/credentials.yml.enc`: a stock encrypted-credentials blob (see N4).
- Tree-wide greps: eval/instance_eval/class_eval, Marshal, backticks/%x, system/spawn/exec/Open3/IO.popen, Socket/Net::HTTP/open-uri, Base64/Zlib, `.ssh`/`.aws`/docker.sock, cron/systemd/shell rc, curl/wget, all `ENV[...]`/`ENV.fetch` reads, base64-like runs of 120+ chars.
- Sources consulted: the rubygems.org v2 version API (sha256 and created_at for all 134 lock entries, including the per-platform variants), the rubygems.org v1 gem API (download counts and source repos for key gems), the OSV querybatch API (117 unique name/version pairs, ecosystem RubyGems) plus bundler 4.0.10, `ruby/www.ruby-lang.org` `_data/releases.yml` (the official 4.0.5 sha256), the ruby-lang.org releases page, `ruby/ruby@v4.0.5` `lib/bundler/version.rb`, and the repo's `docker/server.Dockerfile`, `docker/server-entrypoint.sh`, `docker/compose.yaml` and `bench/nginx.conf`.

## Findings
- **concern**: `install.sh:8`. The Ruby source tarball `https://cache.ruby-lang.org/pub/ruby/4.0/ruby-4.0.5.tar.gz` is piped from curl straight into `tar -xz` and then compiled as root with no checksum check. The source is official, the version is pinned and the download is HTTPS. I downloaded it and its sha256 `7d6149079a63f8ae1d326c9fa65c6019ba2dc3155eae7b39159817911c88958e` matches ruby-lang.org's published value. Suggested fix for the author: verify it with `sha256sum -c`.
- **note**: `Gemfile.lock` (production group). The bundle installs precompiled native platform gems from rubygems.org: nokogiri, sqlite3 and ffi (`*-x86_64/aarch64-linux-gnu` `.so` files, with sqlite3 bundling SQLite 3.53.2) and thruster (a prebuilt Go binary). These are standard upstream release artifacts, checksum-pinned in the lock and not part of the submission tree. Whether they fall under the "don't ship prebuilt binaries" rule is a rules question for the owner, not a security one. thruster is `require: false` and start.sh never runs it.
- **note**: `Gemfile:29-38`. Gems the API doesn't need are in the default group and get installed: kamal (plus net-ssh, sshkit, ed25519, bcrypt_pbkdf, dotenv), thruster and image_processing/ruby-vips/mini_magick. kamal and thruster are `require: false` and none of them is used by the app code. This adds attack surface only, with no behaviour.
- **note**: `config/application.rb:3`, `config/cable.yml:7-9`. `rails/all` loads Action Cable, which Rails mounts at `/cable`. The production adapter is `redis` but the redis gem is not in the bundle, so a WebSocket hit on `/cable` would fail with a LoadError rather than dial `localhost:6379`. The server container also has no outbound network.
- **note**: `app/controllers/health_controller.rb:8`. On a DB failure `/health` echoes `error.message` to the client. This is a minor information leak, not a sandbox risk.
- **note** (N4): `config/credentials.yml.enc`. This is the only long encoded blob in the tree. It has the standard Rails `data--iv--tag` format, its key (`config/master.key`) is gitignored and absent, and nothing reads credentials at runtime because start.sh sets `SECRET_KEY_BASE` from `openssl rand`. It is inert.
- **note**: Dockerfile, `.kamal/`, `config/deploy.yml`, `bin/kamal`, `bin/thrust`, `bin/setup`, `.github/workflows/ci.yml` and `config/ci.rb` are unmodified generator output that the harness never uses. Only the `.sample` hooks contain backticks or `bundler/inline`, and Kamal does not run `.sample` files. `.kamal/secrets:20` would `cat config/master.key` only if someone ran kamal.
- **note**: `script/bench` is the author's local benchmark helper. It runs `docker run --network host --user root`. The harness doesn't invoke it and the owner shouldn't need to.
- **note**: `CLAUDE.md` is an AI-assistant conventions file with benign content (Rails style rules) and no injected instructions.
- **note**: env vars read: `SQLITE_PATH`, `JWT_SECRET`, `HOST`, `PORT` (expected), plus the standard Rails/Puma `RAILS_MAX_THREADS`, `RAILS_LOG_LEVEL`, `PIDFILE`, `BUNDLE_GEMFILE`, `SECRET_KEY_BASE`, `RUBY_YJIT_ENABLE`, `REDIS_URL` (only in unused cable config) and `CI` (test env only).
- Malicious or blocker-level: none.

## Dependencies
All gems come from `https://rubygems.org/` and are exactly pinned in Gemfile.lock (`BUNDLED WITH 4.0.10`, the same Bundler version Ruby 4.0.5 ships, so there's no Bundler self-download). The `CHECKSUMS` section covers all 134 specs. "sha ok" means the lockfile sha256 equals the sha rubygems.org reports for that exact version and platform. OSV querybatch returned no advisories and no MAL-* ids for any gem. Every name is the canonical, long-established gem: no typosquats, all owned by the expected upstream maintainers (Rails core, sparklemotion, puma, jwt, ruby core and so on). The newest releases (Rails 8.1.4, 2026-09-24; brakeman 8.1.0; parallel 2.3.0) are routine version bumps of old gems.

| name | version | pinned | registry check | OSV result |
|---|---|---|---|---|
| rails, railties, actioncable, actionmailbox, actionmailer, actionpack, actiontext, actionview, activejob, activemodel, activerecord, activestorage, activesupport | 8.1.4 | yes | sha ok (all 13) | none |
| action_text-trix | 2.1.19 | yes | sha ok | none |
| jwt | 3.3.0 | yes | sha ok | none |
| puma | 8.0.2 | yes | sha ok (ruby platform) | none |
| nio4r | 2.7.5 | yes | sha ok (ruby platform) | none |
| sqlite3 | 2.9.6 (6 linux platforms) | yes | sha ok (all 6) | none |
| nokogiri | 1.19.4 (6 linux platforms) | yes | sha ok (all 6) | none |
| ffi | 1.17.4 (6 linux platforms) | yes | sha ok (all 6) | none |
| thruster | 0.1.26 (ruby, x86_64-linux, aarch64-linux) | yes | sha ok (all 3) | none |
| bootsnap / msgpack | 1.26.0 / 1.8.5 | yes | sha ok | none |
| propshaft / importmap-rails / turbo-rails / stimulus-rails / jbuilder | 1.3.2 / 2.2.3 / 2.0.23 / 1.3.4 / 2.15.1 | yes | sha ok | none |
| kamal / sshkit / net-ssh / net-scp / net-sftp | 2.12.0 / 1.25.1 / 7.3.3 / 4.1.0 / 4.0.0 | yes | sha ok | none |
| ed25519 / bcrypt_pbkdf / dotenv | 1.4.0 / 1.1.2 / 3.2.0 | yes | sha ok | none |
| image_processing / ruby-vips / mini_magick | 1.14.0 / 2.3.0 / 5.4.0 | yes | sha ok | none |
| rack / rack-session / rack-test / rackup | 3.2.7 / 2.1.2 / 2.2.0 / 2.3.1 | yes | sha ok | none |
| loofah / rails-html-sanitizer / rails-dom-testing / crass | 2.25.2 / 1.7.1 / 2.3.0 / 1.0.7 | yes | sha ok | none |
| mail / mini_mime / marcel / net-imap / net-pop / net-smtp / net-protocol | 2.9.1 / 1.1.5 / 1.2.1 / 0.6.7 / 0.1.2 / 0.5.2 / 0.4.0 | yes | sha ok | none |
| concurrent-ruby / connection_pool / i18n / tzinfo / zeitwerk / globalid | 1.3.8 / 3.0.2 / 1.15.2 / 2.0.6 / 2.8.3 / 1.4.0 | yes | sha ok | none |
| websocket-driver / websocket-extensions / websocket | 0.8.2 / 0.1.5 / 1.2.11 | yes | sha ok | none |
| builder / erubi / erb / useragent / thor / rake | 3.3.0 / 1.13.1 / 6.0.7 / 0.16.11 / 1.5.0 / 13.4.2 | yes | sha ok | none |
| base64 / bigdecimal / date / drb / json / logger / securerandom / timeout / tsort / uri / ostruct | 0.3.0 / 4.1.3 / 3.5.1 / 2.2.3 / 3.0.2 / 1.7.0 / 0.4.1 / 0.6.1 / 0.2.0 / 1.1.1 / 0.6.3 | yes | sha ok | none |
| irb / reline / io-console / pp / prettyprint / prism / rdoc / rbs / racc | 1.18.0 / 0.7.0 / 0.9.4 / 0.6.4 / 0.2.0 / 1.9.0 / 8.1.0 / 4.2.0 / 1.8.1 | yes | sha ok | none |
| dev/test: debug / web-console / bindex / bundler-audit / brakeman | 1.11.1 / 4.3.0 / 0.8.1 / 0.9.3 / 8.1.0 | yes (not installed: build.sh sets `without development test`) | sha ok | none |
| dev/test: rubocop / rubocop-ast / rubocop-performance / rubocop-rails / rubocop-rails-omakase / parser / ast | 1.91.0 / 1.50.0 / 1.27.0 / 2.38.0 / 1.1.0 / 3.3.12.0 / 2.4.3 | yes (not installed) | sha ok | none |
| dev/test: language_server-protocol / lint_roller / parallel / rainbow / regexp_parser / ruby-progressbar / unicode-display_width / unicode-emoji | 3.17.0.6 / 1.1.0 / 2.3.0 / 3.1.1 / 2.13.1 / 1.13.0 / 3.3.0 / 4.3.0 | yes (not installed) | sha ok | none |
| dev/test: capybara / selenium-webdriver / xpath / addressable / public_suffix / matrix / rubyzip / minitest | 3.40.0 / 4.50.0 / 3.2.0 / 2.9.0 / 7.0.5 / 0.4.3 / 3.7.0 / 6.0.6 | yes (not installed) | sha ok | none |
| tzinfo-data | (windows/jruby only, not in lock) | n/a | n/a | n/a |
| bundler (BUNDLED WITH) | 4.0.10 | yes | exists 2026-04-08, ships with Ruby 4.0.5 | none |

## Downloads at build time
| URL | official? | pinned? | checksum verified? |
|---|---|---|---|
| Ubuntu apt mirrors via `apt-get install` (build-essential, curl, openssl, libssl-dev, libyaml-dev, zlib1g-dev, libffi-dev, libgmp-dev, rustc, tzdata), install.sh:5-6 | yes (distro repos) | no (distro current versions, normal for apt) | yes (apt-signed) |
| https://cache.ruby-lang.org/pub/ruby/4.0/ruby-4.0.5.tar.gz, install.sh:8 | yes | yes (4.0.5) | **no** in script; matched the official sha256 by hand on 2026-10-13 |
| https://rubygems.org gems via `bundle install`, build.sh:7 | yes | yes (Gemfile.lock) | yes (lockfile CHECKSUMS, all 134 verified against rubygems.org) |

Seccomp: `builtin`. Puma/nio4r use epoll and Ruby 4.0 with YJIT needs only mmap/mprotect, so nothing uses io_uring or any other syscall that Docker's default profile blocks. Puma listens only on `HOST:PORT` (no control app), and nothing needs extra capabilities, devices or mounts beyond `SQLITE_PATH`.
