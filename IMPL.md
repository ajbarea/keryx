# IMPL

## Current: nothing in flight

The first version shipped in #1 and is installed on the workstation. Pick the next item from
`ROADMAP.md`; voice choice by ear is the cheapest.

## Install state

- Installed from the local marketplace (`claude plugin marketplace add ~/ajsoftworks/keryx`).
- The plugin cache is keyed by version: after changing code, bump `version` in
  `.claude-plugin/plugin.json` and `pyproject.toml`, or `claude plugin uninstall` then
  `install`, or `claude plugin update` reports "already at the latest version".
