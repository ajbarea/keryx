import { describe, expect, test } from 'claude-code/testing'
import type { CommandSpec, On, ProcessRunInit, ProcessRunResult } from 'claude-code'

const PRESENTATION = { isFullscreen: false, columns: 120 } as const

// Stands in for the engine: command registration, and the keryx CLI.
function engine(on: On, cli: Partial<ProcessRunResult> = { stdout: 'speech off\n' }) {
  const registered: CommandSpec[] = []
  const runs: { argv: readonly string[]; init?: ProcessRunInit }[] = []
  on('command.register', ($, e) => {
    registered.push(e)
    return { value: { command: e.name } }
  })
  on('process.run', ($, e) => {
    runs.push(e)
    return { value: { exitCode: 0, stdout: '', stderr: '', isStdoutTruncated: false, isStderrTruncated: false, ...cli } }
  })
  return { registered, runs }
}

const run = (args: string) => ({
  command: 'keryx',
  args,
  origin: { kind: 'composer' as const },
  presentation: PRESENTATION,
})

describe('/keryx', () => {
  test('registers one immediate command at session start', async ($, on) => {
    const { registered } = engine(on)
    on('session.start', ($, e) => ({ cwd: e.cwd }))
    await $.session.start({ cwd: '/w', surface: 'terminal', isInteractive: true })
    expect(registered).toHaveLength(1)
    expect(registered[0]).toEqual(
      expect.objectContaining({ name: 'keryx', argumentHint: '[on|off|again|status]', immediate: true }),
    )
  })

  for (const sub of ['on', 'off', 'again', 'status']) {
    test(`/keryx ${sub} runs the CLI and shows its output`, async ($, on) => {
      const { runs } = engine(on, { stdout: `did ${sub}\n` })
      const out = await $.command.run(run(` ${sub} `))
      expect(runs).toHaveLength(1)
      expect(runs[0]!.argv[0]).toMatch(/\/bin\/keryx$/)
      expect(runs[0]!.argv.slice(1)).toEqual([sub])
      expect(runs[0]!.init?.timeoutMs).toBe(600_000)  // `on` may build the venv first
      expect(out.text).toBe(`did ${sub}`)
      expect(out.exitCode).toBe(0)
    })
  }

  test('an unknown or missing argument shows usage and runs nothing', async ($, on) => {
    const { runs } = engine(on)
    for (const args of ['', 'loud', 'off now', 'constructor']) {
      const out = await $.command.run(run(args))
      expect(out.text).toContain('Usage: /keryx on | off | again | status')
    }
    expect(runs).toEqual([])
  })

  test('a CLI that cannot run says so instead of failing the command', async ($, on) => {
    on('process.run', () => ({ deny: 'spawn bin/keryx ENOENT' }))
    const out = await $.command.run(run('off'))
    expect(out.text).toContain('keryx off failed')
    expect(out.text).toContain('ENOENT')
    expect(out.exitCode).toBe(1)
  })

  test('a CLI that prints nothing reports its exit status', async ($, on) => {
    engine(on, { exitCode: 3, stdout: '', stderr: '' })
    const out = await $.command.run(run('status'))
    expect(out.text).toBe('keryx status exited 3')
    expect(out.exitCode).toBe(3)
  })

  test('stderr is shown after stdout', async ($, on) => {
    engine(on, { stdout: 'speech on\n', stderr: 'daemon not running\n' })
    const out = await $.command.run(run('on'))
    expect(out.text).toBe('speech on\ndaemon not running')
  })
})
