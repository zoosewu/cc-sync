// cc-statusline mod：在輸入框上方畫狀態列，取代各機的 statusline.ps1／.sh。
// 第 1 行 模型│context%│目錄(分支*)│時長│effort；第 2 行 5h／7d 用量條與重置時間（太窄則分兩行）。
// 資料放模組變數、變動時 $.ui.invalidate 重繪；熱重載會重跑 session.start 補回。
import type { EngineInterface, Register } from 'claude-code'

export type Limit = { kind: string; percentUsed: number; resetsAt?: string }

export type Snapshot = {
  model: string
  contextPct: number
  dir: string
  branch: string
  dirty: boolean
  startedAt: number
  effort: string
  limits: Limit[]
}

// 配色與符號沿用舊腳本
export const COLOR = {
  blue: '#0099ff', orange: '#ffb055', green: '#00af50', cyan: '#56b6c2',
  red: '#ff5555', yellow: '#e6c800', white: '#dcdcdc', magenta: '#b48cff', track: '#4a4a4a',
} as const

const BAR_WIDTH = 15
const LIMITS = [
  { label: 'current', kind: 'five_hour', withDate: false },
  { label: 'weekly', kind: 'seven_day', withDate: true },
]
const GIT_TIMEOUT_MS = 5_000
const TICK_MS = 60_000

export const pctColor = (pct: number): string =>
  pct >= 90 ? COLOR.red : pct >= 70 ? COLOR.yellow : pct >= 50 ? COLOR.orange : COLOR.green

/** 細線進度條，半格精度：已用 `━`（尾端半格 `╸`），未用的軌道另以暗色畫。 */
export const bar = (pct: number, width = BAR_WIDTH): { filled: string; empty: string } => {
  const halves = Math.round((Math.min(100, Math.max(0, pct)) * width * 2) / 100)
  const full = Math.floor(halves / 2)
  const half = halves % 2
  return { filled: '━'.repeat(full) + (half ? '╸' : ''), empty: '━'.repeat(width - full - half) }
}

export const duration = (ms: number): string => {
  const s = Math.max(0, Math.floor(ms / 1000))
  return s >= 3600 ? `${Math.floor(s / 3600)}h${Math.floor((s % 3600) / 60)}m`
    : s >= 60 ? `${Math.floor(s / 60)}m`
    : `${s}s`
}

const MONTHS = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec']

/** `5:30pm`，或 `oct 31, 5:30pm`（本地時間）。 */
export const resetTime = (iso: string | undefined, withDate: boolean): string => {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const h = d.getHours()
  const time = `${h % 12 || 12}:${String(d.getMinutes()).padStart(2, '0')}${h < 12 ? 'am' : 'pm'}`
  return withDate ? `${MONTHS[d.getMonth()]} ${d.getDate()}, ${time}` : time
}

/** `claude-opus-5-5[1m]` → `Opus 5.5 (1M)`；看不懂的照原樣。 */
export const modelLabel = (model: string): string => {
  const m = /^claude-([a-z]+)-(\d+)(?:-(\d+))?(?:-\d{8})?(\[1m\])?$/i.exec(model.trim())
  if (!m) return model || 'Claude'
  const [, family = '', major, minor, long] = m
  const name = family.charAt(0).toUpperCase() + family.slice(1)
  return `${name} ${major}${minor ? `.${minor}` : ''}${long ? ' (1M)' : ''}`
}

export const effortMark = (effort: string): { glyph: string; color?: string } =>
  ['high', 'xhigh', 'max'].includes(effort) ? { glyph: '●', color: COLOR.magenta }
  : effort === 'low' ? { glyph: '◔' }
  : { glyph: '◑' }

const basename = (path: string): string => path.replace(/[\\/]+$/, '').split(/[\\/]/).at(-1) || path

// 模組變數：熱重載時歸零，session.start 重新填
const snap: Snapshot = {
  model: '', contextPct: 0, dir: '', branch: '', dirty: false, startedAt: 0, effort: 'default', limits: [],
}
let tick: { cancel: () => void } | null = null

async function git($: EngineInterface, cwd: string, args: string[]): Promise<string | null> {
  try {
    const r = await $.process.run(['git', '-C', cwd, ...args], { timeoutMs: GIT_TIMEOUT_MS })
    return r.exitCode === 0 ? r.stdout.trim() : null
  } catch {
    return null
  }
}

/** 模型、目錄、分支；回合結束與 session 開始時更新（不在繪製時跑 git）。 */
async function refresh($: EngineInterface): Promise<void> {
  const cwd = await $.session.cwd()
  snap.model = await $.session.model()
  snap.dir = basename(cwd)
  snap.branch = (await git($, cwd, ['symbolic-ref', '--short', 'HEAD'])) ?? ''
  snap.dirty = snap.branch !== '' && ((await git($, cwd, ['status', '--porcelain'])) ?? '') !== ''
  $.ui.invalidate('ui.render')
}

async function measure($: EngineInterface): Promise<void> {
  const u = await $.session.usage()
  snap.startedAt = u.startedAt
  snap.contextPct = u.context.percent ?? 0
  snap.limits = u.rateLimits
}

/** 每分鐘重繪一次，讓時長跟著走。 */
function startTick($: EngineInterface): void {
  tick?.cancel()
  tick = $.clock.every(TICK_MS, () => $.ui.invalidate('ui.render'))
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    const started = await next(e)
    const effort = await $.settings.read({ key: 'effortLevel' })
    if (typeof effort === 'string') snap.effort = effort
    await measure($)
    await refresh($)
    startTick($)
    return started
  })

  on('session.measure', ($, e, next) => {
    snap.contextPct = e.context.percent ?? snap.contextPct
    snap.limits = e.rateLimits
    $.ui.invalidate('ui.render')
    return next(e)
  })

  // 實際送出的 effort（降級後的值）；只看主迴圈
  on('turn.step', async function* ($, e, next) {
    if (e.agentId === undefined && e.effort !== undefined && String(e.effort) !== snap.effort) {
      snap.effort = String(e.effort)
      $.ui.invalidate('ui.render')
    }
    return yield* next(e)
  })

  on('turn.complete', async ($, e, next) => {
    const done = await next(e)
    if (e.agentId === undefined) await refresh($)
    return done
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    if (e.props.hasSurvey || !snap.model) return next(e)
    const { Box, Text } = $.ui.resolve(e)
    const now = await $.clock.now()
    const effort = effortMark(snap.effort)
    const sep = <Text dimColor> │ </Text>
    const limits = LIMITS.flatMap(({ label, kind, withDate }) => {
      const l = snap.limits.find(x => x.kind === kind)
      if (!l) return []
      const pct = Math.round(l.percentUsed)
      return [{ label, pct, pctText: `${String(pct).padStart(3)}%`, ...bar(pct), reset: resetTime(l.resetsAt, withDate) }]
    })
    const dur = snap.startedAt ? duration(now - snap.startedAt) : ''
    // 寬度估算（✍️ 字串長度 2 恰等於顯示寬度）；放得下就併行：全部一行 → 標頭＋用量一行 → 用量分兩行、標籤對齊
    const headerWidth = [
      modelLabel(snap.model), `✍️ ${snap.contextPct}%`,
      snap.dir + (snap.branch ? ` (${snap.branch}${snap.dirty ? '*' : ''})` : ''),
      ...(dur ? [`⏱ ${dur}`] : []), `${effort.glyph} ${snap.effort}`,
    ].join(' │ ').length
    const limitsWidth = limits.reduce((w, x) =>
      w + x.label.length + 1 + BAR_WIDTH + 1 + x.pctText.length + (x.reset ? 3 + x.reset.length : 0), 3 * (limits.length - 1))
    const cols = e.props.bodyColumns
    const layout = limits.length === 0 ? 'none'
      : headerWidth + 3 + limitsWidth <= cols ? 'single'
      : limitsWidth <= cols ? 'two'
      : 'three'
    const labelPad = layout === 'three' ? Math.max(0, ...limits.map(x => x.label.length)) : 0
    const limitText = limits.map(x => (
      <Text key={x.label}>
        <Text color={COLOR.white}>{x.label.padEnd(labelPad)}</Text>{' '}
        <Text color={pctColor(x.pct)}>{x.filled}</Text><Text color={COLOR.track}>{x.empty}</Text>{' '}
        <Text color={pctColor(x.pct)}>{x.pctText}</Text>
        {x.reset ? <Text> <Text dimColor>⟳</Text> <Text color={COLOR.white}>{x.reset}</Text></Text> : null}
      </Text>
    ))
    const joined = limitText.map((t, i) => <Text key={String(i)}>{i ? sep : null}{t}</Text>)

    return (
      <Box flexDirection="column">
        <Text wrap="truncate-end">
          <Text color={COLOR.blue}>{modelLabel(snap.model)}</Text>
          {sep}
          <Text>✍️ </Text><Text color={pctColor(snap.contextPct)}>{snap.contextPct}%</Text>
          {sep}
          <Text color={COLOR.cyan}>{snap.dir}</Text>
          {snap.branch
            ? <Text color={COLOR.green}> ({snap.branch}{snap.dirty ? <Text color={COLOR.red}>*</Text> : null})</Text>
            : null}
          {dur ? <Text>{sep}<Text dimColor>⏱ </Text><Text color={COLOR.white}>{dur}</Text></Text> : null}
          {sep}
          <Text color={effort.color} dimColor={!effort.color}>{effort.glyph} {snap.effort}</Text>
          {layout === 'single' ? <Text>{sep}{joined}</Text> : null}
        </Text>
        {layout === 'two' ? <Text wrap="truncate-end">{joined}</Text> : null}
        {layout === 'three' ? limitText : null}
      </Box>
    )
  })
}
