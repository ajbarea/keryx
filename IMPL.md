# IMPL: #83 AGY replay parity and pronounce skill (PR #101)

Branch feat/agy-dual-runtime-compat (agy's; reviewed and fixed by Opus agy-review-k 11-23).
Push: `git push origin feat/agy-dual-runtime-compat:feat/agy-dual-runtime-compat`. Never push to main.

## Done
- agy: "say that again" in AGY replays and ends the turn from PreInvocation; engine tag; skill
  name + run_command.
- Opus r1, from a real capture (agy -p in a scratch folder, keryx disabled, klepsydra state in
  scratch; fixtures tests/fixtures/agy-pre-invocation-{0,1}.json):
  - AGY fires PreInvocation before EVERY model call of a turn with the same lastUserInput
    (invocationNum 0, 1, ...). Every call was read as a new prompt (on main too), and the replay
    would fire again on each. Now only invocationNum 0 is the prompt (hook.normalize).
  - The reply is the documented `{"terminationBehavior": "terminate"}`
    (antigravity.google/docs/hooks, PreInvocation): agy's undocumented metadata.user_markdown and
    an empty systemMessage (which the docs say stays in the conversation) removed.
  - Skill line made true on both runtimes.
- Guard mutation-checked (2 red). pytest full suite green.

- Opus r2 (fresh reader), settled on a live three-turn agy session (scratch hook returning
  terminate for "say that again", keryx disabled, klepsydra state in scratch):
  - invocationNum restarts at 0 each turn (fixture agy-pre-invocation-turn-2.json).
  - agy fires Stop after a terminate (terminationReason TERMINAL_CUSTOM_HOOK); keryx would read
    the previous reply from the transcript and say it again: now no reply (fixture
    agy-stop-after-terminate.json; the test fails without the fix).
  - The engine == agy guard now has a test (a Claude Code prompt hook never replays).
  - run_command dropped from the skill's allowed-tools (an unscoped shell grant).
- 716 passed; each new guard mutation-checked.

## Next
- Fresh verify pass, CI, merge (restore main's IMPL.md first).
