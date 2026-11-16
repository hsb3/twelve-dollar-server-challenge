# Shortcuts for the Docker benchmark stack (docs/benchmark-stack.md). Bare `make` lists them.
# Variables given on the command line (NGINX=1, SCENARIO=stairs, DURATION=...) reach docker/bench.sh.
.DEFAULT_GOAL := help
DC := docker compose -f docker/compose.yaml
VUS ?= 100

.PHONY: help bench dashboard dashboard-stop ps down ingest check-runs seed reviews screenshots

help:  ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

bench:  ## Run a benchmark: make bench S=<submission> VUS=10000 [NGINX=1] [SCENARIO=stairs]
	@test -n "$(S)" || { echo "usage: make bench S=<submission> [VUS=10000] [NGINX=1] [SCENARIO=...]"; exit 2; }
	bash docker/bench.sh $(S) $(VUS)

dashboard:  ## Start Grafana on http://localhost:3000
	$(DC) up -d grafana

screenshots:  ## Screenshot the dashboard: make screenshots OUT=name.png RUNS="<run_id> ..." [MIN=8]
	@test -n "$(OUT)" -a -n "$(RUNS)" || { echo 'usage: make screenshots OUT=name.png RUNS="<run_id> ..." [MIN=8]'; exit 2; }
	mkdir -p docs/img && $(DC) up -d grafana && $(DC) run --rm --build shots python /screenshot.py $(OUT) $(or $(MIN),8) $(RUNS)

dashboard-stop:  ## Stop Grafana
	$(DC) stop grafana

ps:  ## Show the stack's containers
	$(DC) --profile tools --profile viz ps -a

down:  ## Stop and remove every stack container (results and images stay)
	$(DC) --profile tools --profile viz down

ingest:  ## Rebuild results/runs.db from every saved run
	$(DC) run --rm -T tools node --no-warnings docker/ingest.mjs results/*/

check-runs:  ## Check every run in results/ has all its data files and complete samples
	$(DC) run --rm -T tools node --no-warnings docker/ingest.mjs --check results/*/

seed:  ## Build seed/feed.db and seed/tokens.json
	$(DC) run --rm -T tools bash seed/make-seed.sh

reviews:  ## List security reviews and whether each still matches its submission
	@for f in docker/reviews/*.md; do n=$$(basename $$f .md); \
		v=$$(sed -n 's/^verdict: *//p' $$f); s=$$(sed -n 's/^seccomp: *//p' $$f); t=$$(sed -n 's/^tree: *//p' $$f); \
		c=$$(git rev-parse -q --verify HEAD:submissions/$$n); [ "$$t" = "$$c" ] && m=current || m=STALE; \
		printf "  %-34s %-5s %-11s %s\n" $$n $$v $$s $$m; done
