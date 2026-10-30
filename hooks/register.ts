// cc-sync mod：在 session 開始與每回合結束時於背景執行 `cc-sync sync`，並提供 /sync。
// session 開始的同步結束後再跑 `cc-sync update` 自我更新（不與 sync 同時呼叫 claude plugin）。
// session.end 刻意不跑 git：該事件整條鏈只有很短的時間預算，逾時被殺在
// `git add` 中途會留下 index.lock；下一次 session.start 會補 commit 殘留變更。
import type { EngineInterface, Register } from 'claude-code'

type SectionDiff = { added: Record<string, unknown>; removed: string[]; changed: Record<string, unknown> }

export type SyncResult = {
  action: string
  ok: boolean
  committed: boolean
  pushed: boolean
  held: string[]
  changes: Record<string, SectionDiff>
  needs_restart: boolean
  warnings: string[]
  error: string | null
  remote?: string | null
  at: number
}

export type UpdateResult = {
  action: 'update'
  ok: boolean
  updated: boolean
  /** cc-sync 本身的版本 */
  from: string | null
  to: string | null
  /** 這次有升版的 plugin（同 marketplace） */
  plugins: { id: string; from: string | null; to: string | null }[]
  error: string | null
}

const TIMEOUT_MS = 5 * 60_000

export const cliArgv = (root: string, args: readonly string[]): string[] =>
  ['uv', 'run', '--project', root, '--frozen', '--quiet', 'cc-sync', ...args]

export const parseResult = <T = SyncResult>(stdout: string): T | null => {
  const line = stdout.trim().split('\n').at(-1) ?? ''
  try {
    return JSON.parse(line) as T
  } catch {
    return null
  }
}

export const USAGE = 'usage: /sync [now|status|confirm|update|init <git-url>|remote [git-url]]'

/** /sync 的參數：子命令與其後的值（URL）。 */
export const parseArgs = (args: string): { sub: string; value: string } => {
  const [sub = 'now', ...rest] = args.trim().split(/\s+/).filter(Boolean)
  return { sub, value: rest.join(' ') }
}

/** /sync remote 的輸出。 */
export const remoteText = (r: SyncResult): string =>
  !r.ok ? `remote: failed — ${r.error}`
  : r.pushed ? `sync location moved to ${r.remote} (existing data pushed)`
  : `sync location: ${r.remote}`

/** 自我更新的提示；沒升級時為 null。 */
export const updateNotice = (r: UpdateResult): string | null =>
  r.updated
    ? `updated ${r.plugins.map(p => `${p.id.split('@')[0]} ${p.from} → ${p.to}`).join(', ')} — restart Claude Code to apply`
    : null

/** /sync update 的輸出：升版提示與失敗原因可同時出現（部分 plugin 失敗）。 */
export const updateText = (r: UpdateResult): string =>
  [updateNotice(r), r.error && `update failed — ${r.error}`].filter(Boolean).join('\n')
  || `cc-sync is up to date (${r.to})`

const hhmm = (epochSeconds: number): string => new Date(epochSeconds * 1000).toTimeString().slice(0, 5)

const countChanges = (changes: SyncResult['changes']): string[] =>
  Object.entries(changes).map(([section, d]) => {
    const parts = [
      Object.keys(d.added).length && `+${Object.keys(d.added).length}`,
      d.removed.length && `-${d.removed.length}`,
      Object.keys(d.changed).length && `~${Object.keys(d.changed).length}`,
    ].filter(Boolean)
    return `${section} ${parts.join(' ')}`
  })

/** 狀態列文字：一眼看出最後一次同步是否健康。 */
export const statusLine = (r: SyncResult): string =>
  !r.ok ? `cc-sync ⚠ ${r.error ?? 'failed'}`
  : r.held.length ? `cc-sync ⚠ ${r.held.length} removals held · /sync confirm`
  : r.warnings.length ? `cc-sync ⚠ ${r.warnings.length} warning(s) · /sync status`
  : `cc-sync ✓ ${hhmm(r.at)}`

/** /sync 的輸出：完整摘要。 */
export const summary = (r: SyncResult): string =>
  [
    `${r.action}: ${r.ok ? 'ok' : `failed — ${r.error}`}`,
    r.committed && 'committed local changes',
    r.pushed && 'pushed',
    ...countChanges(r.changes).map(c => `pulled ${c}`),
    r.needs_restart && 'plugin set changed: restart Claude Code to apply',
    r.held.length && `held ${r.held.length} removals (run /sync confirm to push them):\n  ${r.held.join('\n  ')}`,
    ...r.warnings.map(w => `warning: ${w}`),
  ].filter(Boolean).join('\n')

// 模組變數：熱重載時歸零即可，不需跨重載保存
const state: { running: Promise<SyncResult | null> | null; again: boolean } = { running: null, again: false }

async function run<T = SyncResult>($: EngineInterface, args: readonly string[]): Promise<T | null> {
  try {
    const r = await $.process.run(cliArgv($.plugin.root, args), { timeoutMs: TIMEOUT_MS })
    const result = parseResult<T>(r.stdout)
    if (!result) {
      $.ui.status(`cc-sync ⚠ ${(r.stderr || r.stdout).trim().split('\n').at(-1) ?? 'no output'}`)
      return null
    }
    return result
  } catch (err) {
    $.ui.status(`cc-sync ⚠ cannot run uv: ${String(err)}`)
    return null
  }
}

function report($: EngineInterface, r: SyncResult | null): void {
  if (!r) return
  $.ui.status(statusLine(r))
  if (r.needs_restart) $.ui.toast('cc-sync: plugins changed on another machine — restart Claude Code to apply')
  if (r.held.length) $.ui.toast(`cc-sync: ${r.held.length} removals held — run /sync confirm`, { timeoutMs: 10_000 })
}

/** 背景同步；進行中再被要求時合併成一次補跑。 */
function syncInBackground($: EngineInterface): void {
  if (state.running) {
    state.again = true
    return
  }
  state.running = run($, ['sync'])
  void state.running.then(r => {
    report($, r)
    state.running = null
    if (state.again) {
      state.again = false
      syncInBackground($)
    }
  })
}

/** 失敗（多半是離線）不打擾；/sync update 會顯示原因。 */
async function updateInBackground($: EngineInterface): Promise<void> {
  const r = await run<UpdateResult>($, ['update'])
  const notice = r && updateNotice(r)
  if (notice) $.ui.toast(notice, { timeoutMs: 10_000 })
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'sync',
      description: 'cc-sync: sync now, show status, confirm held removals, update cc-sync, or set the sync repo',
      argumentHint: '[now|status|confirm|update|init <git-url>|remote [git-url]]',
    })
    const started = await next(e)
    syncInBackground($)
    void state.running?.then(() => updateInBackground($))
    return started
  })

  on('turn.complete', async ($, e, next) => {
    const done = await next(e)
    if (e.agentId === undefined) syncInBackground($)
    return done
  })

  on('command.run', { command: 'sync' }, async ($, e) => {
    const { sub: arg, value } = parseArgs(e.args)
    if (arg === 'status') {
      const r = await run($, ['status'])
      return { text: r && 'ok' in r ? summary(r) : 'cc-sync: no sync has run yet' }
    }
    if (!['now', 'confirm', 'update', 'init', 'remote'].includes(arg) || (arg === 'init' && !value)) {
      return { text: USAGE }
    }
    if (state.running) await state.running
    if (arg === 'init') {
      const r = await run($, ['bootstrap', value])
      report($, r)
      return { text: r ? summary(r) : 'cc-sync: no result (see status line)' }
    }
    if (arg === 'remote') {
      const r = await run($, value ? ['remote', value] : ['remote'])
      return { text: r ? remoteText(r) : 'cc-sync: no result (see status line)' }
    }
    if (arg === 'update') {
      const u = await run<UpdateResult>($, ['update'])
      return { text: u ? updateText(u) : 'cc-sync: no result (see status line)' }
    }
    const r = await run($, arg === 'confirm' ? ['sync', '--force'] : ['sync'])
    report($, r)
    return { text: r ? summary(r) : 'cc-sync: no result (see status line)' }
  })
}
