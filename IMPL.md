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

## Next
- Fresh-reader round, CI, merge (restore main's IMPL.md first).
