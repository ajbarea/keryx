# skill-context — keryx

Repo-specific facts the techne skills read. Logic lives in the skills; only facts belong here.

## repo

- name: keryx
- kind: Claude Code plugin (listed in the `techne` marketplace as `keryx@techne`; this repo
  has no marketplace of its own) with a Zensical docs site. Public.
- default_branch: main
- package_root: `src/keryx/` (hook, client, daemon, summarize, text, voice, voices, speaker,
  player, loudness, pronounce, procs, config). Plugin surface: `.claude-plugin/plugin.json`,
  `hooks/hooks.json`, `hooks/register.ts` (the `/keryx` mod command), `skills/pronounce/`,
  `bin/keryx`, `bin/keryx-replay`. `eval/` holds the summarizer evaluation.
- language: Python (>=3.12,<3.14); CI matrix covers 3.12 and 3.13. TypeScript for the hooks
  module.
- toolchain: uv, ruff (format + lint), ty (types), pytest
- cli_entrypoint: `bin/keryx <hook|replay-hook|on|off|status|say|again|pronounce|voices|stop|daemon>`
- runner: none. Targets run directly via `make`; there is no `logs/dev-<ts>-*.log` archive
  convention, so the audit's log-reconciliation phase is N/A.
- has: a `cuda` extra (about 2 GB of NVIDIA wheels, not installed in CI), WSL2-only playback
  through `powershell.exe`, no Docker, no frontend.

## audit

### Phase 1 — Lint

- `make lint` → `ruff format --check .`, `ruff check .`, `ty check`

### Phase 2 — Test

- `make test` → pytest with coverage. The suite never loads Kokoro.

### Phase 3 — Mod

- `make mod-test` → `claude plugin test`, a real-engine `/keryx`, and strict `tsc` on
  `hooks/register.ts`. Runs through `npx`, so it needs network.

### Phase 4 — Docs

- `make docs-build` → `zensical build --clean --strict`

### Fast audit

- `make lint` then `make test`

### do_not_run

- `make docs`: interactive server
- `bin/keryx daemon`, `bin/keryx say`, `bin/keryx voices`: start the daemon and play audio

## ci_audit

- workflows: `.github/workflows/ci.yml` (lint-and-test on 3.12 and 3.13, mod),
  `.github/workflows/docs.yml` (strict Zensical build, Pages deploy on main),
  `.github/workflows/dependabot-auto-merge.yml`
- referenced configs: `pyproject.toml` (`requires-python`, `[tool.ruff]`, dev group),
  `uv.lock`, `Makefile`, `zensical.toml`
- tool error markers: `ruff`, `ty`, `FAILED` / `passed` (pytest), `tsc`, `zensical`

## slop_ground_truth

- `docs/design.md` records every measurement; other docs state behaviour that traces to
  `src/keryx/` and `tests/`. A figure on the site must appear in `docs/design.md`, the README
  or a committed `eval/tally-*.txt`.
- The docs site pages describe code that exists: settings are `Config` in `config.py`, the
  commands are `COMMANDS` in `__main__.py`, the replay phrases are `_REPLAY` in `hook.py`.

## scan_scope

Skip paths:

- `.venv/`, `site/`, `eval/data/`, `__pycache__/`, `.ruff_cache/`, `.pytest_cache/`,
  `.claude-plugin/types/`, `uv.lock`

Subagent scan-area split:

- Library: `src/keryx/**/*.py`
- Plugin surface: `hooks/**`, `bin/*`, `skills/**`
- Tests: `tests/**`
- Config / build: `pyproject.toml`, `Makefile`, `.github/workflows/**`, `zensical.toml`
- Docs: `docs/**/*.md`, `README.md`

## docs_site

- config: `zensical.toml`
- workflow: `.github/workflows/docs.yml`
- css_files: `docs/stylesheets/landing.css`, `docs/stylesheets/extra.css`
- js_files: `docs/javascripts/reveal.js`
- build_command: `uv run --no-sync zensical build --clean --strict`
- site_url: `https://ajbarea.github.io/keryx/`
- action_pins: full-SHA pins with a `# vX.Y.Z` comment, kept current by Dependabot; the same
  pins as sphragis's `docs.yml`
- shared files: `overrides/`, `docs/javascripts/reveal.js` and `tests/test_docs_nav.py` come
  from `techne:docs-site`'s `scripts/sync_shared.py`; change them in techne, not here
