# IMPL: #93 release 0.13.0 (PR #102)

Branch fix/release-version-93 (agy's; Opus agy-review-k 11-23). Merges LAST, after #99-#101, #103, #104.

## Done
- agy: version 0.13.0 in plugin.json, pyproject.toml, uv.lock; a ROADMAP "Completed" entry.
- Opus r1: ROADMAP entry dropped (ROADMAP is forward-only; release notes go on the GitHub
  release). The last tag is v0.11.0: 0.12.0 was never tagged.

## Next
1. After the others merge: merge main in, CI, merge.
2. Tag v0.13.0 on main, `gh release create v0.13.0` with notes for 0.12 + 0.13.
3. `claude plugin marketplace update` + `claude plugin update keryx@...` on both accounts; check
   the installed version reads 0.13.0 (`keryx status` / plugin cache path).
