# IMPL: #25 keryx status polish (PR #100)

Branch fix/status-polish-25 (agy's; reviewed and fixed by Opus agy-review-k 11-23).
Push: `git push origin fix/status-polish-25:fix/status-polish-25`. Never push to main.

## Done
- agy: Ollama on Windows only (ollama.exe) says start the Windows app; audio-dir names its
  source; /keryx status usage text; getting-started line.
- Opus r1: the docs line listed what status does not check (it now lists what it checks);
  the audio-dir fixes now give the exact value to write (`"audio_dir": "<default>"` in the
  config file) or say to remove the env var from the profile and restart keryx.
- Live: `KERYX_AUDIO_DIR=/tmp/bad keryx status` names the env as source with the new fix;
  plain `keryx status` all ok. ruff, ty clean; pytest 710 passed.

## Next
- Fresh-reader round, CI, merge (restore main's IMPL.md first).
