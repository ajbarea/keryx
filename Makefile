.PHONY: lint test mod-test

# The Claude Code and TypeScript builds the hooks module is tested and type-checked on, through
# npx, so local runs and CI judge the same output. Mods need Claude Code 2.1.287 or later.
CLAUDE_CODE_VERSION := 2.1.291
TYPESCRIPT_VERSION := 7.0.2
CLAUDE := npx --yes @anthropic-ai/claude-code@$(CLAUDE_CODE_VERSION)

lint:                       ## ruff format --check, ruff check, ty
	uv run ruff format --check .
	uv run ruff check .
	uv run ty check

test:                       ## Run the test suite with coverage
	uv run pytest --cov=keryx --cov-branch --cov-report=term-missing

# tsc reads the types the engine writes into .claude-plugin/types/ when it loads the plugin; an
# unauthenticated -p run, in a fresh config directory, loads it and stops before calling a model.
mod-test:                   ## claude plugin test + strict tsc on hooks/register.ts
	$(CLAUDE) plugin test .
	cfg=$$(mktemp -d); env -u ANTHROPIC_API_KEY CLAUDE_CONFIG_DIR=$$cfg \
		$(CLAUDE) -p --plugin-dir . "load only" >/dev/null 2>&1; rm -rf $$cfg
	@test -f .claude-plugin/types/tsconfig.json || { echo "FAIL: loading the plugin wrote no types"; exit 1; }
	npx --yes -p typescript@$(TYPESCRIPT_VERSION) tsc --noEmit -p .
