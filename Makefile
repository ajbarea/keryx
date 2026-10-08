.PHONY: lint test mod-test docs docs-build

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

# `claude -p "/keryx"` loads the plugin in a real engine, writing the types tsc reads into
# .claude-plugin/types/, and answers from the hooks module without calling a model. It runs in a
# bare environment and a fresh config, so no login or installed copy of keryx takes part.
mod-test:                   ## claude plugin test, a real-engine /keryx, and strict tsc on hooks/register.ts
	$(CLAUDE) plugin test .
	rm -rf .claude-plugin/types
	cfg=$$(mktemp -d); out=$$(env -i PATH="$$PATH" HOME="$$HOME" CLAUDE_CONFIG_DIR=$$cfg \
		timeout 120 $(CLAUDE) -p --plugin-dir . "/keryx" 2>&1); rm -rf $$cfg; \
		printf '%s\n' "$$out" | grep -q "Usage: /keryx" \
		|| { printf '%s\n' "$$out"; echo "FAIL: /keryx did not answer from the hooks module"; exit 1; }
	@test -f .claude-plugin/types/tsconfig.json || { echo "FAIL: loading the plugin wrote no types"; exit 1; }
	npx --yes -p typescript@$(TYPESCRIPT_VERSION) tsc --noEmit -p .

docs:                       ## Serve the documentation site with live reload
	uv run zensical serve

docs-build:                 ## Build the documentation site into site/; warnings fail the build
	uv run zensical build --clean --strict
