import { expect, test } from 'claude-code/testing'

import { BAND, ENGINES_OWN_DRAWING, everyText, FakeM2b, start, STATUS, texts } from './harness'

const FAILED = {
  ...STATUS,
  run: { state: 'failed', started_at: '2026-03-14T18:00:05+01:00', message: 'the ingest step failed' },
}

test('tasks due today come first, then the most recent overdue ones, three quiet rows and "and N more"', async ($, on) => {
  // Covers: B102
  const fake = new FakeM2b().candidate('c1', 'Remember? Acme moved')
  fake.dueTasks = [
    { id: 't1', title: 'Return the \u001b[1mdrill\u001b[0m', due: '2026-03-12', overdue: true },
    { id: 't2', title: 'Call Dana', due: '2026-03-14', overdue: false },
    { id: 't3', title: 'Pay the invoice', due: '2026-03-14T16:00:00+01:00', overdue: true },
    { id: 't4', title: 'Water the plants', due: '2026-03-14', overdue: false },
  ]
  await start($, on, fake)

  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  const shown = await texts(ui)
  expect(shown.slice(1)).toEqual([
    'due today: Call Dana',
    'due today: Water the plants',
    'overdue: Pay the invoice',
    'and 1 more due',
  ])
  expect(await ui.findAll({ type: 'Button' })).toHaveLength(2)
  const rows = (await ui.findAll({ type: 'Text' })).filter(found => found.text.includes('Call Dana'))
  expect(rows.every(found => found.props['dimColor'] === true)).toBe(true)
  await ui.unmount()
})

test('without a task due, or with the setting off, the band draws nothing for them', async ($, on) => {
  // Covers: B102
  const fake = new FakeM2b()
  fake.dueTasks = null
  await start($, on, fake)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await everyText(ui)).toEqual([ENGINES_OWN_DRAWING])
  await ui.unmount()
})

test('due tasks alone draw the band', async ($, on) => {
  // Covers: B102
  const fake = new FakeM2b()
  fake.dueTasks = [{ id: 't2', title: 'Call Dana', due: '2026-03-14', overdue: false }]
  await start($, on, fake)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await texts(ui)).toEqual(['due today: Call Dana'])
  await ui.unmount()
})

test('a failed run is shown once in a session, naming where the review is', async ($, on) => {
  // Covers: B103
  const fake = new FakeM2b()
  fake.status = FAILED
  const { clock, toasts } = await start($, on, fake)

  await clock.advance(180_000)
  await $.turn.complete({ answer: 'done', durationMs: 5, isAborted: false, turnId: 't1', reason: 'answer' })
  await clock.advance(1)

  expect(toasts).toEqual([
    'm2b: the curation run of 2026-03-14 18:00 failed; its review task says why, and /m2b-review shows it',
  ])
})

test('a reload of the mod does not show the same failed run again; the next failed run is shown', async ($, on) => {
  // Covers: B103
  const fake = new FakeM2b()
  fake.status = FAILED
  const { clock, toasts } = await start($, on, fake)
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await clock.advance(60_000)
  expect(toasts).toHaveLength(1)

  fake.status = { ...FAILED, run: { ...FAILED.run, started_at: '2026-03-15T18:00:05+01:00' } }
  await clock.advance(60_000)
  expect(toasts).toHaveLength(2)
  expect(toasts[1]).toContain('2026-03-15 18:00')
})

test('a toast that cannot be shown leaves the status line as read', async ($, on) => {
  // Covers: B103
  const fake = new FakeM2b()
  fake.status = FAILED
  fake.toastFails = true
  const { statuses } = await start($, on, fake)
  expect(statuses.at(-1)).toBe('last run failed, see review')
})

test('a run that succeeded, or one still running, shows nothing', async ($, on) => {
  // Covers: B103
  const fake = new FakeM2b()
  fake.status = { ...STATUS, run: { state: 'running', started_at: '2026-03-14T18:00:05+01:00' } }
  const { clock, toasts } = await start($, on, fake)
  fake.status = { ...STATUS, run: { state: 'succeeded', started_at: '2026-03-14T18:00:05+01:00' } }
  await clock.advance(60_000)
  expect(toasts).toEqual([])
})
