# IMPL

## Current: CITATION.cff for Zenodo (#106)

Slice: keryx gets a CITATION.cff that follows techne's citation convention (ajbarea/techne#428), so each Zenodo release record takes its title, creator (ORCID, affiliation) and keywords from the file instead of GitHub defaults.

✅ Done
- `CITATION.cff`: title "keryx: gives Claude Code a voice", concept DOI 10.5281/zenodo.23327640, ORCID, affiliation, keywords, MIT, repository and docs links; valid against CFF 1.2.0 (cffconvert).
- `tests/test_citation.py`: pyproject, plugin.json and CITATION.cff versions agree; date-released is ISO; no `.zenodo.json`.
- `Makefile`: `make lint` validates CITATION.cff.
- README Cite section points at the file.

📋 Next
- At each release, bump `version` and `date-released` in CITATION.cff with pyproject and plugin.json (the test fails otherwise).

## Verify
- `make lint` and `make test` clean; techne's sisters `citation.py` reads the file without file gaps.
