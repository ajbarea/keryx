# Reply clips

keryx keeps each session's latest spoken reply as one WAV beside klepsydra's fleet folder, so the wall can play it again from the session's card. keryx only writes; klepsydra reads. Turn it off with the `reply_clips` setting (`KERYX_REPLY_CLIPS=0`).

## Where

`<klepsydra dir>/replies/<session id>.wav`, where `<klepsydra dir>` is the folder holding `fleet/`, chosen as for the [speaking signal](speaking-signal.md#where). keryx creates `replies/` only when `fleet/` is a real folder (not missing, not a symlink), and writes nothing while `replies/` is a symlink.

## What a clip holds

- One reply: the sentences keryx said for a Claude Code session's reply, in order, with 0.25 s of silence between them. The repo-name announcement is left out.
- 16-bit PCM mono at Kokoro's rate (24 kHz), the same format as keryx's playback slots.
- Only a reply keryx synthesized to the end. A reply cut off before its last sentence was synthesized (a new prompt, `keryx stop`) leaves the session's previous clip in place. Notices (approvals, questions) and replays (`keryx again`) are not kept.
- The file is named by the Claude Code session id, lower-case, as in the hook input. A `/clear` starts a new session id, so the new session has no clip until it replies.

## Lifetime

- A clip is written to `tmp-<pid>-<session id>.wav` in the same folder, then moved over the old clip with `os.replace`, so a reader sees the old clip or the new one.
- After each write keryx keeps the 32 newest clips by modification time and deletes the rest. It also deletes its own temp files older than a minute. Other files in the folder are left alone.
- Any write error is logged at debug and dropped; speech is unaffected.

## Privacy

A clip is the spoken summary of a reply, the same words the speakers played. It stays on the machine. A reader that serves it elsewhere (klepsydra's phone wall) should give it the visibility it gives the reply text.
