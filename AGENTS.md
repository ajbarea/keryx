# keryx setup runbook

This is the setup guide for keryx, written for an agent guiding a user. keryx runs on WSL2 under Windows. Run `keryx status` first and work through the lines it marks `missing`.

## Rules

- `keryx status` only reads. Run it again after each fix.
- The user runs, with `!`, any fix that contains `sudo`, needs a browser or needs an admin password. After the user approves, the agent may run any other fix.
- Report only what `keryx status` printed.
- Never stop the keryx daemon to test a fix.

## 1. Check where things stand

Run `keryx status` (or `/keryx status` in Claude Code). It prints the settings as JSON, then one line per check: `ok`, `optional`, `missing` or `n/a`, the check's name, and a detail, with `fix:` lines under a missing one. The last line is `result: ready`, or `result: missing` with the names that failed. If the shell says keryx needs uv, install uv first.

## 2. Fix each missing line

| Check | What to do |
| --- | --- |
| `uv` | Run the fix line, then open a new terminal. |
| `powershell.exe` | keryx is running outside WSL2 and cannot play audio there. |
| `ollama` | Start Ollama: the Windows app, or `ollama serve` in WSL. If it is not installed, install it from https://ollama.com/download. |
| `model` | Run the fix line, `ollama pull <model>`. |
| `ollama-memory` | Marked `optional`, so the result stays ready. The drop-in in its fix line needs sudo, so the user runs it with `!`. Restarting Ollama unloads every model, so ask first. `n/a` means Ollama is not a systemd service; see docs/troubleshooting.md. |
| `audio-dir` | Windows plays audio only from its own drives. Remove the override, or point `KERYX_AUDIO_DIR` at a folder on a Windows drive. |

## 3. Check the result

Run `keryx status` again until it prints `result: ready`, then `keryx say "keryx is working"`.

## Cite

keryx ships in the techne marketplace. Cite techne through its [CITATION.cff](https://github.com/ajbarea/techne/blob/main/CITATION.cff); the docs are at https://ajbarea.github.io/techne/.
