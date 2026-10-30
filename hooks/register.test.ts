import { expect, test } from 'claude-code/testing'

import {
  cliArgv, parseArgs, parseResult, remoteText, statusLine, summary, updateNotice, updateText, USAGE,
  type SyncResult, type UpdateResult,
} from './register.ts'

const OK: SyncResult = {
  action: 'sync', ok: true, committed: true, pushed: true, held: [],
  changes: { plugins: { added: { 'a@m': true }, removed: ['b@m'], changed: {} } },
  needs_restart: true, warnings: [], error: null, at: 0,
}
const UPDATED: UpdateResult = {
  action: 'update', ok: true, updated: true, from: '0.1.0', to: '0.1.1', error: null,
  plugins: [
    { id: 'cc-sync@cc-sync', from: '0.1.0', to: '0.1.1' },
    { id: 'cc-statusline@cc-sync', from: '0.1.1', to: '0.1.2' },
  ],
}

test('pure helpers', () => {
  expect(cliArgv('/p', ['sync'])).toEqual(['uv', 'run', '--project', '/p', '--frozen', '--quiet', 'cc-sync', 'sync'])
  expect(parseResult(`noise\n${JSON.stringify(OK)}\n`)).toEqual(OK)
  expect(parseResult('not json')).toBeNull()
  expect(statusLine({ ...OK, ok: false, error: 'boom' })).toBe('cc-sync ⚠ boom')
  expect(statusLine({ ...OK, held: ['x', 'y'] })).toBe('cc-sync ⚠ 2 removals held · /sync confirm')
  expect(statusLine(OK)).toBeUndefined()
  expect(summary(OK)).toMatch(/^sync: ok \(\d\d:\d\d\)/)
  expect(summary(OK)).toContain('pulled plugins +1 -1')
  expect(summary(OK)).toContain('restart Claude Code')
  expect(updateNotice(UPDATED)).toBe('updated cc-sync 0.1.0 → 0.1.1, cc-statusline 0.1.1 → 0.1.2 — restart Claude Code to apply')
  expect(updateNotice({ ...UPDATED, updated: false, plugins: [] })).toBeNull()
  expect(updateText({ ...UPDATED, ok: false, plugins: UPDATED.plugins.slice(1), error: 'cc-sync@cc-sync update failed: x' }))
    .toBe('updated cc-statusline 0.1.1 → 0.1.2 — restart Claude Code to apply\nupdate failed — cc-sync@cc-sync update failed: x')
  expect(parseArgs('')).toEqual({ sub: 'now', value: '' })
  expect(parseArgs('  init  https://example.com/me/data.git ')).toEqual({ sub: 'init', value: 'https://example.com/me/data.git' })
  expect(remoteText({ ...OK, pushed: false, remote: 'u' })).toBe('sync location: u')
  expect(remoteText({ ...OK, remote: 'u' })).toBe('sync location moved to u (existing data pushed)')
  expect(remoteText({ ...OK, ok: false, error: 'boom' })).toBe('remote: failed — boom')
})

function engine(on: Parameters<Parameters<typeof test>[1]>[1], result: SyncResult, update: UpdateResult = UPDATED) {
  const runs: string[][] = []
  const statuses: (string | undefined)[] = []
  const toasts: string[] = []
  on('command.register', () => ({ value: { command: 'sync' } }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('turn.complete', () => ({ text: '' }))
  on('process.run', (_, e) => {
    runs.push([...e.argv])
    const out = e.argv.at(-1) === 'update' ? update : result
    return { value: { exitCode: 0, stdout: JSON.stringify(out), stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
  })
  on('ui.status', (_, e) => {
    statuses.push(e.text)
    return { value: undefined }
  })
  on('ui.toast', (_, e) => {
    toasts.push(e.text)
    return { value: undefined }
  })
  return { runs, statuses, toasts }
}

const TURN = { answer: '', durationMs: 1, isAborted: false, turnId: 't', reason: 'answer' } as const

test('main-loop turns sync, subagent turns do not, /sync waits and summarizes', async ($, on) => {
  const { runs, statuses } = engine(on, { ...OK, needs_restart: false, changes: {} })
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await $.turn.complete({ ...TURN, agentId: 'sub-1' })
  await $.turn.complete(TURN)

  const { text } = await $.command.run({ command: 'sync', args: 'now' })
  expect(text).toContain('sync: ok')
  // session.start + 主迴圈一次（子 agent 不觸發，進行中的請求合併）+ /sync；另有 session.start 後的一次 update
  const syncs = runs.filter(argv => argv.at(-1) === 'sync')
  expect(syncs.length).toBeGreaterThanOrEqual(2)
  expect(syncs.length).toBeLessThanOrEqual(3)
  expect(runs.filter(argv => argv.at(-1) === 'update').length).toBeLessThanOrEqual(1)
  expect(statuses.at(-1)).toBeUndefined()
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

test('session start updates cc-sync after its sync and toasts the new version', async ($, on) => {
  const { runs, toasts } = engine(on, { ...OK, needs_restart: false })
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await $.command.run({ command: 'sync', args: 'status' })  // 讓背景工作有機會跑完
  const order = runs.map(argv => argv.at(-1))
  expect(order.indexOf('update')).toBeGreaterThan(order.indexOf('sync'))
  expect(toasts).toContain(updateNotice(UPDATED))
})

test('/sync update reports up to date or failure', async ($, on) => {
  engine(on, OK, { ...UPDATED, updated: false, from: '0.1.1', plugins: [] })
  expect((await $.command.run({ command: 'sync', args: 'update' })).text).toBe('cc-sync is up to date (0.1.1)')
})

test('/sync update shows the failure reason', async ($, on) => {
  engine(on, OK, { ...UPDATED, ok: false, updated: false, plugins: [], error: 'marketplace update failed: offline' })
  expect((await $.command.run({ command: 'sync', args: 'update' })).text).toBe('update failed — marketplace update failed: offline')
})

test('/sync init bootstraps with the given URL and needs one', async ($, on) => {
  const { runs } = engine(on, { ...OK, action: 'seed' })
  expect((await $.command.run({ command: 'sync', args: 'init' })).text).toBe(USAGE)
  expect(runs).toEqual([])
  expect((await $.command.run({ command: 'sync', args: 'init git@example.com:me/data.git' })).text).toContain('seed: ok')
  expect(runs.at(-1)?.slice(-2)).toEqual(['bootstrap', 'git@example.com:me/data.git'])
})

test('/sync remote shows or moves the sync location', async ($, on) => {
  const { runs } = engine(on, { ...OK, pushed: false, remote: 'https://example.com/me/data.git' })
  expect((await $.command.run({ command: 'sync', args: 'remote' })).text).toBe('sync location: https://example.com/me/data.git')
  expect(runs.at(-1)?.at(-1)).toBe('remote')
  await $.command.run({ command: 'sync', args: 'remote https://example.com/me/new.git' })
  expect(runs.at(-1)?.slice(-2)).toEqual(['remote', 'https://example.com/me/new.git'])
})
