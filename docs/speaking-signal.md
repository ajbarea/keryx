# Speaking signal

While keryx plays a line, it writes `speaking.json` into klepsydra's fleet folder, so the wall can show which session is speaking. keryx only writes; klepsydra reads. Turn it off with the `speaking_signal` setting (`KERYX_SPEAKING_SIGNAL=0`).

## Where

`<klepsydra dir>/fleet/speaking.json`, with the folder chosen as `hooks/klepsydra-fleet.sh` chooses it:

1. `$KLEPSYDRA_DIR`, when set.
2. Under WSL: `/mnt/c/Users/$USER/AppData/Local/dev.ajsoftworks.klepsydra`.
3. Elsewhere: `$XDG_DATA_HOME` (absolute only, else `~/.local/share`) plus `dev.ajsoftworks.klepsydra`.

keryx never creates the folder. If `fleet/` is missing or is a symlink, klepsydra is not installed and nothing is written. The file name is not a session UUID, so the hook's pruning leaves it alone.

## Schema (`v: 1`)

One JSON object on one line.

| Field | Type | Meaning |
| --- | --- | --- |
| `v` | int | Schema version, `1` |
| `voice` | string | The voice label speaking, as in `voices.json` (a blend reads `a+b`) |
| `terminal` | string | keryx's terminal key, `<pid>:<starttime>` of the Claude Code process; `""` outside one |
| `claude_pid` | int | Claude Code's pid. Absent when `terminal` is empty |
| `claude_start` | int | Its `/proc/<pid>/stat` field 22. Absent with `claude_pid` |
| `session_id` | string | Claude Code session id. Absent when unknown |
| `started_at` | float | Epoch seconds when the clip was handed to the player |
| `ends_at` | float | `started_at` plus the clip's length in seconds |
| `envelope` | float[] | RMS level, 20 values a second, `ceil(duration * 20)` long |

`claude_pid` and `claude_start` equal `claude.pid` and `claude.start` in a session card: keryx and the hook both take the nearest `claude`/`claude-code` ancestor of the hook process, so match a card on both numbers.

## Envelope

Each 50 ms window of the rendered clip (before playback) gives one RMS value. Values are divided by the loudest window of the clip, so the loudest is `1.0`, and rounded to 2 decimals. Silence is all `0.0`. Index `i` covers `started_at + i / 20` onward; the last window may be shorter.

## Lifetime

- A line plays sentence by sentence. Each sentence replaces the file, with its own `started_at`, `ends_at` and `envelope`. A repo-name announcement is a clip too.
- The file is removed when a clip is cut off (`keryx stop`, `/keryx off`, a new prompt, a failed play), when the queue goes quiet about a second after the last clip, and when the daemon exits. A cut-off removes the file only if that clip wrote it, so one session's stop does not clear another's line.
- Writes go to `speaking.json.<pid>.tmp` in the same folder, then `os.replace`, so a reader sees the old file or the new one, never half of one. Windows documents `MoveFileEx` replace as best effort, so a reader should treat a failed read or parse as "no file" and retry on the next change.
- Any write error is logged at debug and dropped; speech is unaffected.

## Staleness rule

A crash or a killed daemon leaves the last file behind. A reader must treat the file as not speaking when `ends_at` is before now, and the gap between sentences reads the same way. Clocks are one machine's (WSL and Windows share the host clock), so compare against the reader's wall clock. A reader may also check the card's process is alive.

## Example

```json
{"v":1,"voice":"af_heart","terminal":"48213:9120441","claude_pid":48213,"claude_start":9120441,"session_id":"3f1c0a52-7b1e-4c0e-9a55-2f6f0d1d7a10","started_at":1792520221.2,"ends_at":1792520223.7,"envelope":[0.12,0.55,1.0,0.8,0.31]}
```
