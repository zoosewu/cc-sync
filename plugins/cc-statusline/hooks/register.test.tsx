import { expect, test } from 'claude-code/testing'

import { bar, COLOR, duration, effortMark, modelLabel, pctColor, resetTime } from './register.tsx'

const BAND = {
  plugin: 'cc-statusline',
  component: 'AbovePrompt',
  props: { hasSurvey: false, isWorking: false, maxRows: 10, bodyColumns: 100, scroll: { offset: 0, bodyRows: 10 } },
} as const

test('pure helpers', () => {
  expect(pctColor(95)).toBe(COLOR.red)
  expect(pctColor(70)).toBe(COLOR.yellow)
  expect(pctColor(50)).toBe(COLOR.orange)
  expect(pctColor(10)).toBe(COLOR.green)
  expect(bar(42)).toEqual({ filled: '━━━━━━╸', empty: '━'.repeat(8) })
  expect(bar(40)).toEqual({ filled: '━━━━━━', empty: '━'.repeat(9) })
  expect(bar(150)).toEqual({ filled: '━'.repeat(15), empty: '' })
  expect(bar(-5)).toEqual({ filled: '', empty: '━'.repeat(15) })
  expect(duration(42_000)).toBe('42s')
  expect(duration(5 * 60_000)).toBe('5m')
  expect(duration(3_900_000)).toBe('1h5m')
  expect(modelLabel('claude-opus-5-5')).toBe('Opus 5.5')
  expect(modelLabel('claude-sonnet-5-5[1m]')).toBe('Sonnet 5.5 (1M)')
  expect(modelLabel('Opus 5.5')).toBe('Opus 5.5')
  expect(effortMark('high')).toEqual({ glyph: '●', color: COLOR.magenta })
  expect(effortMark('low')).toEqual({ glyph: '◔' })
  expect(effortMark('default')).toEqual({ glyph: '◑' })
  expect(resetTime(undefined, false)).toBe('')
  expect(resetTime('2026-10-30T17:05:00', false)).toBe('5:05pm')
  expect(resetTime('2026-11-02T09:00:00', true)).toBe('nov 2, 9:00am')
})

function engine(on: Parameters<Parameters<typeof test>[1]>[1], opts: { branch?: string; dirty?: boolean; usage?: object } = {}) {
  const start = 1_000_000
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('session.cwd', () => ({ value: '/work/cc-sync' }))
  on('session.model', () => ({ value: 'claude-opus-5-5' }))
  on('session.usage', () => ({
    value: opts.usage ?? {
      startedAt: start,
      context: { window: 200_000, tokens: 46_000, percent: 23 },
      rateLimits: [
        { kind: 'five_hour', percentUsed: 41.5, resetsAt: '2026-10-30T17:05:00' },
        { kind: 'seven_day', percentUsed: 92, resetsAt: '2026-11-02T09:00:00' },
      ],
    },
  }))
  on('settings.read', () => ({ value: { effortLevel: 'high' } }))
  on('process.run', (_, e) => {
    const isStatus = e.argv.includes('status')
    const ok = opts.branch !== undefined
    const stdout = isStatus ? (opts.dirty ? ' M x' : '') : (opts.branch ?? '')
    return { value: { exitCode: ok ? 0 : 128, stdout, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
  })
  on('clock.every', () => ({ value: { cancel: () => {} } }))
  on('clock.now', () => ({ value: start + 3_900_000 }))
  on('ui.invalidate', () => ({ value: undefined }))
}

test('the band draws both lines from the session', async ($, on) => {
  engine(on, { branch: 'main', dirty: true })
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })

  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  const all = (await ui.find({ type: 'Box' }))?.text ?? ''
  expect(all).toContain('Opus 5.5')
  expect(all).toContain('ctx 23%')
  expect(all).toContain('cc-sync (main*)')
  expect(all).toContain('1h5m')
  expect(all).toContain('● high')
  expect(all).toContain(`current ━━━━━━╸${'━'.repeat(8)}  42% ⟳ 5:05pm │ weekly ${'━'.repeat(15)}  92% ⟳ nov 2, 9:00am`)
  await ui.unmount()
})

test('a wide band puts everything on one line', async ($, on) => {
  engine(on, { branch: 'main' })
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })

  const ui = await $.ui.mount({ ...BAND, surface: 'terminal', props: { ...BAND.props, bodyColumns: 200 } })
  const all = (await ui.find({ type: 'Box' }))?.text ?? ''
  expect(all).toContain('● high │ current ━')
  await ui.unmount()
})

test('a narrow band puts the limits on two aligned lines', async ($, on) => {
  engine(on, { branch: 'main' })
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })

  const ui = await $.ui.mount({ ...BAND, surface: 'terminal', props: { ...BAND.props, bodyColumns: 60 } })
  const all = (await ui.find({ type: 'Box' }))?.text ?? ''
  expect(all).not.toContain('5:05pm │ weekly')
  expect(all).toContain('current ━')
  expect(all).toContain('weekly  ━')
  await ui.unmount()
})

test('outside git and before any rate-limit reading, only the first line', async ($, on) => {
  engine(on, { usage: { startedAt: 0, context: { window: 200_000 }, rateLimits: [] } })
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })

  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  const all = (await ui.find({ type: 'Box' }))?.text ?? ''
  expect(all).toContain('cc-sync')
  expect(all).not.toContain('(')
  expect(all).not.toContain('current')
  await ui.unmount()
})

test('a survey takes the band', async ($, on) => {
  engine(on, { branch: 'main' })
  on('ui.render', ($, e) => {
    const { Text } = $.ui.resolve(e)
    return <Text>engine</Text>
  })
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })

  const ui = await $.ui.mount({ ...BAND, surface: 'terminal', props: { ...BAND.props, hasSurvey: true } })
  expect((await ui.find({ type: 'Text' }))?.text).toBe('engine')
  await ui.unmount()
})
