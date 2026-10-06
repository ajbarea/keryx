import type { Register } from 'claude-code'

// The keryx CLI subcommands /keryx runs, and the line each shows in /keryx's usage.
export const SUBCOMMANDS: Record<string, string> = {
  on: 'turn speech back on; the next prompt starts the daemon',
  off: 'stop speech, shut the daemon down and free its VRAM',
  again: "say this terminal's last line again",
  status: 'show the settings and whether the daemon is running',
}
const USAGE = ['Usage: /keryx on | off | again | status', ...Object.entries(SUBCOMMANDS).map(([k, v]) => `  ${k}: ${v}`)].join('\n')
// `keryx on` may build the venv on its first run, which takes minutes.
const RUN_TIMEOUT_MS = 10 * 60_000

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    // Immediate, so /keryx off cuts speech while Claude is still working.
    await $.command.register({
      name: 'keryx',
      description: 'keryx speech: on, off, again or status',
      argumentHint: '[on|off|again|status]',
      immediate: true,
    })
    return next(e)
  })

  on('command.run', { command: 'keryx' }, async ($, e) => {
    const sub = e.args.trim()
    if (!Object.hasOwn(SUBCOMMANDS, sub)) return { text: USAGE }
    let run
    try {
      run = await $.process.run([`${$.plugin.root}/bin/keryx`, sub], { timeoutMs: RUN_TIMEOUT_MS })
    } catch (err) {
      return { text: `keryx ${sub} failed: ${err instanceof Error ? err.message : String(err)}`, exitCode: 1 }
    }
    const out = [run.stdout.trim(), run.stderr.trim()].filter(Boolean).join('\n')
    // exitCode is what `claude -p "/keryx off"` exits with; an interactive session ignores it.
    return { text: out || `keryx ${sub} exited ${run.exitCode}`, exitCode: Math.min(Math.max(run.exitCode, 0), 255) }
  })
}
