import { expect, test } from 'claude-code/testing'

import { parseBandShows } from '../../hooks/tasks'
import {
  BAND,
  CALM_ROW,
  ENGINES_OWN_DRAWING,
  FakeM2b,
  HOME,
  NOW,
  OPEN,
  STATUS,
  bandPieces,
  everyText,
  listedTask,
  partLines,
  rowSaying,
  shownBand,
  start,
  startView,
} from './harness'
import type { Files } from './harness'

const FAILED = {
  ...STATUS,
  run: { state: 'failed', started_at: '2026-03-14T18:00:05+01:00', message: 'the ingest step failed' },
}

/** A candidate and four tasks due as the core names them, earliest first: two overdue, two due today. */
function dueFake(): FakeM2b {
  const fake = new FakeM2b().candidate('c1', 'Remember? Acme moved')
  fake.dueTasks = [
    { id: 't1', title: 'Return the drill', due: '2026-03-12', overdue: true },
    { id: 't2', title: 'Call Dana', due: '2026-03-14', overdue: false },
    { id: 't3', title: 'Pay the \u001b[1minvoice\u001b[0m', due: '2026-03-14T16:00:00+01:00', overdue: true },
    { id: 't4', title: 'Water the plants', due: '2026-03-14', overdue: false },
  ]
  return fake
}

test('with count the tasks due are two counts in the row, the overdue ones first, each in its color', async ($, on) => {
  // Covers: B102
  const fake = dueFake()
  await start($, on, fake)

  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await shownBand(ui)).toEqual(rowSaying('1 waits for you  2 overdue  2 due today'))
  expect(await bandPieces(ui)).toEqual([
    { text: '1 waits for you', color: 'warning', dimColor: undefined },
    { text: '  2 overdue', color: 'error', dimColor: undefined },
    { text: '  2 due today', color: 'warning', dimColor: undefined },
  ])
  await ui.unmount()
})

test('with list the tasks due stand below the row by name: today first, then the most recent overdue ones, three and "and N more"', async ($, on) => {
  // Covers: B102
  const fake = dueFake()
  fake.shows = { place: 'above', dueTasks: 'list', topics: false }
  await start($, on, fake)

  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await shownBand(ui)).toEqual({
    isNamed: true,
    says: '1 waits for you',
    below: ['due today Call Dana', 'due today Water the plants', 'overdue Pay the invoice', 'and 1 more'],
    buttons: [OPEN],
  })
  // When it is due in its color and one width, so the titles start in one column; the title at full strength, cut where it is too long.
  expect(await listedTask(ui, 't2')).toEqual({
    due: { text: 'due today', color: 'warning', dimColor: undefined },
    title: { text: 'Call Dana', color: undefined, dimColor: undefined, wrap: 'truncate-end' },
  })
  expect(await listedTask(ui, 't3')).toEqual({
    due: { text: 'overdue  ', color: 'error', dimColor: undefined },
    title: { text: 'Pay the invoice', color: undefined, dimColor: undefined, wrap: 'truncate-end' },
  })
  expect(await listedTask(ui, 't1')).toBeNull()
  await ui.unmount()
})

test('with list and three tasks due or fewer, no line says there are more', async ($, on) => {
  // Covers: B102
  const fake = dueFake()
  fake.shows = { place: 'above', dueTasks: 'list', topics: false }
  fake.dueTasks = fake.dueTasks?.slice(0, 3) ?? null
  await start($, on, fake)

  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect((await shownBand(ui))?.below).toEqual(['due today Call Dana', 'overdue Pay the invoice', 'overdue Return the drill'])
  await ui.unmount()
})

test('with off the band says nothing of the tasks due, and the pane lists them all the same', async ($, on) => {
  // Covers: B102
  const fake = dueFake()
  fake.shows = { place: 'above', dueTasks: 'off', topics: false }
  await start($, on, fake)

  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await shownBand(ui)).toEqual(rowSaying('1 waits for you'))
  await ui.unmount()
  const inPane = await startView($)
  // Today's first, then the overdue ones, the most recent first.
  expect(await partLines(inPane, 'today')).toEqual([
    'due today Call Dana',
    'due today Water the plants',
    'overdue Pay the invoice',
    'overdue Return the drill',
  ])
  await inPane.unmount()
})

for (const dueTasks of ['off', 'count', 'list'] as const) {
  test(`without a task due the band draws nothing for them, with ${dueTasks} too`, async ($, on) => {
    // Covers: B102
    const fake = new FakeM2b()
    fake.shows = { place: 'waiting', dueTasks, topics: false }
    await start($, on, fake)
    const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
    expect(await everyText(ui)).toEqual([ENGINES_OWN_DRAWING])
    await ui.unmount()
  })

  test(`without a task due a band that is always there is calm and says nothing of them, with ${dueTasks} too`, async ($, on) => {
    // Covers: B102, B213
    const fake = new FakeM2b()
    fake.shows = { place: 'above', dueTasks, topics: false }
    await start($, on, fake)
    const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
    expect(await shownBand(ui)).toEqual(CALM_ROW)
    await ui.unmount()
  })
}

test('tasks due alone draw the band: as a count, or by name below a row that says nothing else, and not at all with off', async ($, on) => {
  // Covers: B102
  const fake = new FakeM2b()
  fake.shows = { place: 'waiting', dueTasks: 'count', topics: false }
  fake.dueTasks = [{ id: 't2', title: 'Call Dana', due: '2026-03-14', overdue: false }]
  const { clock } = await start($, on, fake)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await shownBand(ui)).toEqual(rowSaying('1 due today'))

  fake.shows = { place: 'waiting', dueTasks: 'list', topics: false }
  await clock.advance(60_000)
  expect(await shownBand(ui)).toEqual({ isNamed: true, says: '', below: ['due today Call Dana'], buttons: [OPEN] })

  fake.shows = { place: 'waiting', dueTasks: 'off', topics: false }
  await clock.advance(60_000)
  expect(await everyText(ui)).toEqual([ENGINES_OWN_DRAWING])
  await ui.unmount()
})

test('tasks due alone, where the band is always there: a count, or their names below a row that says nothing else, and with off the calm row', async ($, on) => {
  // Covers: B102, B213
  const fake = new FakeM2b()
  fake.dueTasks = [{ id: 't2', title: 'Call Dana', due: '2026-03-14', overdue: false }]
  const { clock } = await start($, on, fake)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await shownBand(ui)).toEqual(rowSaying('1 due today'))

  fake.shows = { place: 'above', dueTasks: 'list', topics: false }
  await clock.advance(60_000)
  expect(await shownBand(ui)).toEqual({ isNamed: true, says: '', below: ['due today Call Dana'], buttons: [OPEN] })

  fake.shows = { place: 'above', dueTasks: 'off', topics: false }
  await clock.advance(60_000)
  expect(await shownBand(ui)).toEqual(CALM_ROW)
  await ui.unmount()
})

test('an answer without the band part, as of a core before it, shows the tasks it names under due as counts', async ($, on) => {
  // Covers: B102
  const fake = dueFake()
  fake.shows = null
  const { clock } = await start($, on, fake)

  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await shownBand(ui)).toEqual(rowSaying('1 waits for you  2 overdue  2 due today'))

  // That core names no task while its setting is off: none is known, and none is counted.
  fake.dueTasks = null
  await clock.advance(60_000)
  expect(await shownBand(ui)).toEqual(rowSaying('1 waits for you'))
  await ui.unmount()
  const inPane = await startView($)
  expect(await partLines(inPane, 'today')).toEqual(['Tasks due are not shown.'])
  await inPane.unmount()
})

test('a shared answer of a band before the settings, with tasks due and no word on how to show them, is not taken: m2b is asked, and the tasks are shown as its own answer says', async ($, on) => {
  // Covers: B102, B213
  const due = [
    { id: 't1', title: 'Return the drill', overdue: true },
    { id: 't2', title: 'Call Dana', overdue: false },
  ]
  const stored = { snapshot: { candidates: [], review: null, error: null, due }, status: null, version: '0.3.0' }
  const files: Files = new Map([[`${HOME}/.local/state/m2b/band-answer.json`, JSON.stringify({ writtenAtMs: NOW - 1_000, value: stored })]])
  const fake = new FakeM2b()
  fake.shows = { place: 'above', dueTasks: 'list', topics: false }
  fake.dueTasks = [{ id: 't4', title: 'Water the plants', due: '2026-03-14', overdue: false }]
  await start($, on, fake, {}, files)

  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(fake.calls).toEqual([['band', '--json']])
  // Neither the tasks the older band shared nor counts: the machine lists them, and m2b names one.
  expect(await shownBand(ui)).toEqual({ isNamed: true, says: '', below: ['due today Water the plants'], buttons: [OPEN] })
  await ui.unmount()
})

test('a shared answer whose settings of the band are of another shape is loaded again instead of drawn', async ($, on) => {
  // Covers: B102
  const snapshot = { candidates: [], review: null, error: null, due: [], shows: { place: 'above', dueTasks: 'rows', topics: false } }
  const stored = { snapshot, status: null, version: '0.3.0' }
  const files: Files = new Map([[`${HOME}/.local/state/m2b/band-answer.json`, JSON.stringify({ writtenAtMs: NOW - 1_000, value: stored })]])
  const fake = dueFake()
  await start($, on, fake, {}, files)

  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(fake.calls).toEqual([['band', '--json']])
  expect(await shownBand(ui)).toEqual(rowSaying('1 waits for you  2 overdue  2 due today'))
  await ui.unmount()
})

test('the band part is read whole or not at all: a value this band does not know leaves what a machine without an entry shows', () => {
  // Covers: B102
  expect(parseBandShows({ due_tasks: 'list', topics: true })).toEqual({ place: 'above', dueTasks: 'list', topics: true })
  expect(parseBandShows({ due_tasks: 'off', topics: false })).toEqual({ place: 'above', dueTasks: 'off', topics: false })
  expect(parseBandShows({ due_tasks: 'count', topics: false })).toEqual({ place: 'above', dueTasks: 'count', topics: false })
  expect(parseBandShows(undefined)).toBeUndefined()
  expect(parseBandShows({ due_tasks: 'rows', topics: true })).toBeUndefined()
  expect(parseBandShows({ due_tasks: true, topics: true })).toBeUndefined()
  expect(parseBandShows({ due_tasks: 'list' })).toBeUndefined()
  expect(parseBandShows({ due_tasks: 'list', topics: 'yes' })).toBeUndefined()
  expect(parseBandShows(['list', true])).toBeUndefined()
  // Beside a place it knows, too.
  expect(parseBandShows({ place: 'below', due_tasks: 'rows', topics: true })).toBeUndefined()
  expect(parseBandShows({ place: 'below', due_tasks: 'list', topics: 'yes' })).toBeUndefined()
})

test('the place of the band is one of three; a core that names none has the band above, and a place this band does not know leaves the part unread', () => {
  // Covers: B213
  const rest = { due_tasks: 'list', topics: true }
  for (const place of ['above', 'below', 'waiting'] as const) {
    expect(parseBandShows({ place, ...rest })).toEqual({ place, dueTasks: 'list', topics: true })
  }
  expect(parseBandShows(rest)).toEqual({ place: 'above', dueTasks: 'list', topics: true })
  for (const unknown of ['beside', 'Above', '', true, null, ['above']]) {
    expect(parseBandShows({ place: unknown, ...rest })).toBeUndefined()
  }
})

test('a failed run is shown once in a session, by the time it started today, naming where the review is', async ($, on) => {
  // Covers: B103, B209
  const fake = new FakeM2b()
  fake.status = FAILED
  const { clock, toasts } = await start($, on, fake)

  await clock.advance(180_000)
  await $.turn.complete({ answer: 'done', durationMs: 5, isAborted: false, turnId: 't1', reason: 'answer' })
  await clock.advance(1)

  expect(toasts).toEqual(['m2b: the curation run of 18:00 failed; its review task says why, and /m2b-review shows it'])
})

test('a failed run of a day before is named by its date', async ($, on) => {
  // Covers: B103, B209
  const fake = new FakeM2b()
  fake.status = { ...FAILED, run: { ...FAILED.run, started_at: '2026-03-13T18:00:05+01:00' } }
  const { toasts } = await start($, on, fake)

  expect(toasts).toEqual(['m2b: the curation run of 2026-03-13 failed; its review task says why, and /m2b-review shows it'])
})

test('a reload of the mod does not show the same failed run again; the next failed run is shown', async ($, on) => {
  // Covers: B103
  const fake = new FakeM2b()
  fake.status = FAILED
  const { clock, toasts } = await start($, on, fake)
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await clock.advance(60_000)
  expect(toasts).toHaveLength(1)

  fake.status = { ...FAILED, run: { ...FAILED.run, started_at: '2026-03-14T18:20:05+01:00' } }
  await clock.advance(60_000)
  expect(toasts).toEqual([
    'm2b: the curation run of 18:00 failed; its review task says why, and /m2b-review shows it',
    'm2b: the curation run of 18:20 failed; its review task says why, and /m2b-review shows it',
  ])
})

test('a toast that cannot be shown leaves the status line as read', async ($, on) => {
  // Covers: B103
  const fake = new FakeM2b()
  fake.status = FAILED
  fake.toastFails = true
  const { statuses } = await start($, on, fake)
  expect(statuses.at(-1)).toBe('last curation run failed')
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
