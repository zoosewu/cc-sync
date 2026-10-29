import { expect, test } from 'claude-code/testing'

import { cliArgv, parseResult, statusLine, summary, type SyncResult } from './register.ts'

const OK: SyncResult = {
  action: 'sync', ok: true, committed: true, pushed: true, held: [],
  changes: { plugins: { added: { 'a@m': true }, removed: ['b@m'], changed: {} } },
  needs_restart: true, warnings: [], error: null, at: 0,
}

test('pure helpers', () => {
  expect(cliArgv('/p', ['sync'])).toEqual(['uv', 'run', '--project', '/p', '--frozen', '--quiet', 'cc-sync', 'sync'])
  expect(parseResult(`noise\n${JSON.stringify(OK)}\n`)).toEqual(OK)
  expect(parseResult('not json')).toBeNull()
  expect(statusLine({ ...OK, ok: false, error: 'boom' })).toBe('cc-sync ⚠ boom')
  expect(statusLine({ ...OK, held: ['x', 'y'] })).toBe('cc-sync ⚠ 2 removals held · /sync confirm')
  expect(statusLine(OK)).toMatch(/^cc-sync ✓ \d\d:\d\d$/)
  expect(summary(OK)).toContain('pulled plugins +1 -1')
  expect(summary(OK)).toContain('restart Claude Code')
})

function engine(on: Parameters<Parameters<typeof test>[1]>[1], result: SyncResult) {
  const runs: string[][] = []
  const statuses: (string | undefined)[] = []
  on('command.register', () => ({ value: { command: 'sync' } }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('turn.complete', () => ({ text: '' }))
  on('process.run', (_, e) => {
    runs.push([...e.argv])
    return { value: { exitCode: 0, stdout: JSON.stringify(result), stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
  })
  on('ui.status', (_, e) => {
    statuses.push(e.text)
    return { value: undefined }
  })
  on('ui.toast', () => ({ value: undefined }))
  return { runs, statuses }
}

const TURN = { answer: '', durationMs: 1, isAborted: false, turnId: 't', reason: 'answer' } as const

test('main-loop turns sync, subagent turns do not, /sync waits and summarizes', async ($, on) => {
  const { runs, statuses } = engine(on, { ...OK, needs_restart: false, changes: {} })
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await $.turn.complete({ ...TURN, agentId: 'sub-1' })
  await $.turn.complete(TURN)

  const { text } = await $.command.run({ command: 'sync', args: 'now' })
  expect(text).toContain('sync: ok')
  // session.start + 主迴圈一次（子 agent 不觸發，進行中的請求合併）+ /sync
  expect(runs.every(argv => argv.slice(-1)[0] === 'sync')).toBe(true)
  expect(runs.length).toBeGreaterThanOrEqual(2)
  expect(runs.length).toBeLessThanOrEqual(3)
  expect(statuses.at(-1)).toMatch(/^cc-sync ✓/)
})

test('a subagent turn alone never syncs', async ($, on) => {
  const { runs } = engine(on, OK)
  await $.turn.complete({ ...TURN, agentId: 'sub-1' })
  await $.command.run({ command: 'sync', args: 'bogus' })
  expect(runs).toEqual([])
})

test('/sync confirm forces, /sync rejects unknown args', async ($, on) => {
  const { runs } = engine(on, OK)
  expect((await $.command.run({ command: 'sync', args: 'confirm' })).text).toContain('pushed')
  expect(runs.at(-1)?.slice(-2)).toEqual(['sync', '--force'])
  expect((await $.command.run({ command: 'sync', args: 'bogus' })).text).toContain('usage')
})
