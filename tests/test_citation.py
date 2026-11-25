"""CITATION.cff is the citation Zenodo and GitHub read; its version moves with each release."""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _cff(key: str) -> str:
    text = (ROOT / "CITATION.cff").read_text()
    m = re.search(rf'^{key}:\s*"?([^"\n]+?)"?\s*$', text, re.MULTILINE)
    assert m, f"CITATION.cff has no {key}"
    return m.group(1)


def test_versions_are_in_step():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())["version"]
    assert project == plugin == _cff("version")


def test_release_date_is_an_iso_date():
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", _cff("date-released"))


def test_citation_cff_is_the_only_citation_file():
    # Zenodo ignores CITATION.cff entirely when a .zenodo.json sits beside it.
    assert not (ROOT / ".zenodo.json").exists()
