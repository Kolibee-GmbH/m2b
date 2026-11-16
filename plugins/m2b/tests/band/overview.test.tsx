import { expect, test } from 'claude-code/testing'
import type { Engine } from 'claude-code/testing'

import { part, pathLine, row, said, topicLabel } from '../../hooks/look'
import type { ButtonSpec } from '../../hooks/look'
import { glanceLines, sessionLines, sessionPane } from '../../hooks/session-view'
import type { SessionActions, SessionModel } from '../../hooks/session-view'
import type { BandProposal, BandSession, BandSnapshot } from '../../types'
import {
  BAND,
  ENGINES_OWN_DRAWING,
  FakeM2b,
  PARTS,
  STATUS,
  buttonsAt,
  everyText,
  linesAt,
  lookOf,
  pane,
  partLines,
  partLook,
  pathPieces,
  shownParts,
  start,
  startView,
  texts,
} from './harness'

// The overview is tested twice over: as the mod draws it for a session, from what a fake m2b
// answers, and as `sessionPane` draws a model a test builds, through a render hook of the test's
// own. The second reaches the models no answer of the fake gives, and compares the pane with the
// two forms in text, which are made from the same model.

type On = Parameters<typeof start>[1]

const PANE = 'm2b'
const OWN = 'overview-alone'
const BLOCKS = 'blocks-alone'
const UNDO_MS = 5_000
const NOT_LOOKED = 'm2b has not looked yet.'
const NOT_KNOWN = 'm2b holds no note of what it gave this session; that does not say it gave nothing.'
const KEEPS = 'This session keeps what it was given and gets no more topics.'
const NOTHING_WAITS = 'Nothing waits for you.'
const NOTHING_DUE = 'Nothing due today.'
const PRINTED_WHOLE = 'The distillate was printed whole at the start.'
const REVIEW = 'Review of the last curation run'
const WHOLE_REVIEW = 'The whole review is in the tab Review.'
const CURATED = '2 in inbox · curated 18:02'
const OLDER = 'This session runs m2b 0.5.0 and m2b 0.6.0 is installed: run /reload-plugins.'
const LUMEN = '/home/alex/code/lumen'

/** How a line that may be skipped, one in the color of trouble and one that asks for something are drawn. */
const DIM = { color: undefined, dimColor: true, wrap: 'wrap' }
const TROUBLE = { color: 'error', dimColor: undefined, wrap: 'wrap' }
const ASKS = { color: 'warning', dimColor: undefined, wrap: 'wrap' }
const PLAIN = { color: undefined, dimColor: undefined, wrap: 'wrap' }

/** The frame of a part in a pane wide enough for one, and the bar down the left that stands in below that. */
const FRAMED = { borderStyle: 'round', paddingX: 1 }
const BARRED = { borderStyle: 'quote', paddingX: 0 }
const CALM = { borderColor: 'subtle', titleColor: 'remember', titleWeight: 'bold', countColor: undefined }
const WAITING = { borderColor: 'warning', titleColor: 'warning', titleWeight: 'bold', countColor: 'warning' }

const NO_ACTIONS: SessionActions = {
  press: async () => undefined,
  undo: async () => undefined,
  showTopic: async () => undefined,
  switchFolder: async () => undefined,
  undoFolder: async () => undefined,
}

const KNOWN: BandSession = { id: 's', known: true, topics: [], atStart: 'whole', offUnder: null, folder: null, error: null }
/** A session m2b could not look at: the look names nothing but why. */
const NOT_READ: BandSession = { ...KNOWN, known: false, atStart: null, error: 'the machine state cannot be read' }
const QUIET: BandSnapshot = { candidates: [], review: null, error: null, due: [] }

function proposed(id: string, text: string): BandProposal {
  return { id, kind: 'person', text, quote: text, day: '2026-03-12', topic: null, due: null }
}

/** What the overview draws from, with what a test sets and nothing else: nothing looked at, nothing said. */
function modelWith(parts: Partial<SessionModel>): SessionModel {
  return {
    given: null,
    notes: 0,
    rowNotice: null,
    folderNotice: null,
    snapshot: null,
    proposals: null,
    presses: {},
    health: null,
    versionLine: null,
    ...parts,
  }
}

/** A session with something in every part: five things that wait, three tasks due, two topics, its folder, its notes. */
const FULL = modelWith({
  given: {
    ...KNOWN,
    topics: [
      { name: 'Northwind', facts: 2, current: 1 },
      { name: 'Acme Ltd', facts: 1, current: 0 },
    ],
    folder: LUMEN,
  },
  notes: 2,
  snapshot: {
    candidates: [{ id: 'c1', title: 'Remember? Dana prefers tea' }],
    review: {
      id: 'r1',
      title: 'm2b: review',
      findings: ['lint: broken link in a.md'],
      changes: [{ kind: 'rewrote', file: 'sam.md', topic: 'Sam', parts: [] }],
    },
    error: null,
    // As the core names them: the earliest first.
    due: [
      { id: 'd1', title: 'Call the plumber', overdue: true },
      { id: 'd2', title: 'Return the ladder to Sam', overdue: true },
      { id: 'd3', title: 'Send the offer to Acme', overdue: false },
    ],
  },
  proposals: {
    waiting: [
      proposed('a1a1a1a1a1a1', 'Dana is head of IT at Northwind.'),
      proposed('b2b2b2b2b2b2', 'Call Sam about the ladder.'),
      proposed('c3c3c3c3c3c3', 'The spare key is in the shed.'),
    ],
    answered: 0,
    error: null,
  },
  health: { curation: CURATED, troubles: [] },
})

/** A session m2b looked at, with nothing in any part. */
const EMPTY = modelWith({ given: KNOWN, snapshot: QUIET, proposals: { waiting: [], answered: 0, error: null } })

const STORE_UNREAD = 'm2b could not look for proposals: the store at /home/alex/Notes cannot be read'
const SETTLED = 'Already settled in another session, nothing written: Remember? Dana prefers tea'
const NOT_TURNED_ON = 'm2b could not be turned on under /home/alex/code: the machine config cannot be written'
const RUN_FAILED = 'The last curation run failed: the ingest step failed'
const NO_CALENDAR = 'm2b could not reach the calendar: timed out'

/** A session with something wrong in every part but "Today": a store m2b could not read, two presses that wrote nothing, two troubles of m2b and an older m2b. */
const TROUBLED = modelWith({
  given: { ...KNOWN, topics: [{ name: 'Northwind', facts: 2, current: 0 }], offUnder: '/home/alex/code', folder: LUMEN },
  rowNotice: SETTLED,
  folderNotice: NOT_TURNED_ON,
  snapshot: QUIET,
  proposals: { waiting: [], answered: 0, error: 'the store at /home/alex/Notes cannot be read' },
  health: { curation: '2 in inbox', troubles: [RUN_FAILED, NO_CALENDAR] },
  versionLine: OLDER,
})

/**
 * A pane of the test's own that draws the overview of a model, at the width it is mounted with.
 * The hook is registered here, so this is called before the test's first call on `$`.
 */
function ownOverview($: Engine, on: On) {
  const held = { model: modelWith({}) }
  on('ui.render', { component: 'Pane', requestId: OWN }, (engine, e) => sessionPane(engine, e, held.model, NO_ACTIONS, e.props.bodyColumns))
  return (model: SessionModel, columns = 80) => {
    held.model = model
    return $.ui.mount({ ...pane(OWN, columns), plugin: 'test', surface: 'terminal' })
  }
}

/** A session that was given two topics in a folder, with a candidate, a question, the review, a proposal and two tasks due. */
function busyFake(): FakeM2b {
  const fake = new FakeM2b()
  fake.given = {
    topics: [
      { name: 'Northwind', facts: 3, current: 1 },
      { name: 'Acme Ltd', facts: 1, current: 0 },
    ],
    atStart: 'whole',
    offUnder: null,
    folder: LUMEN,
  }
  fake.candidate('c1', 'Remember? Dana prefers tea')
  fake.question('q1', 'Still current? Planning the trip to Porto')
  fake.review('r1', ['lint: broken link in a.md'])
  fake.proposal('a1a1a1a1a1a1', 'Dana is head of IT at Northwind.', 'Dana runs IT at Northwind')
  fake.dueTasks = [
    { id: 't1', title: 'Return the ladder', due: '2026-03-10', overdue: true },
    { id: 't2', title: 'Buy screws', due: '2026-03-14', overdue: false },
  ]
  return fake
}

test('the overview is four parts in one order, each under its title: what waits, today, this session, m2b', async ($, on) => {
  // Covers: B205
  await start($, on, busyFake())

  const ui = await startView($)

  const parts = await shownParts(ui)
  expect(parts.map(shown => [shown.key, shown.title])).toEqual([
    ['waits', 'Waits for you'],
    ['today', 'Today'],
    ['session', 'This session'],
    ['m2b', 'm2b'],
  ])
  expect(parts.map(shown => [shown.key, shown.title])).toEqual(Object.entries(PARTS))
  // Nothing of the view stands outside a part.
  const inParts = parts.flatMap(shown => [shown.title, ...(shown.count === null ? [] : [shown.count]), ...shown.lines])
  expect((await texts(ui)).filter(text => !inParts.some(line => line.includes(text)))).toEqual([])
  await ui.unmount()
})

test('while something waits the first part has its frame and its title in the color of what waits and says how many, the number the band says; every other part steps back and says no count', async ($, on) => {
  // Covers: B205
  await start($, on, busyFake())
  const band = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await everyText(band)).toContain('4 wait for you')
  await band.unmount()

  const ui = await startView($)

  expect((await shownParts(ui)).map(shown => shown.count)).toEqual(['4', null, null, null])
  expect(await partLook(ui, 'waits')).toEqual({ ...FRAMED, ...WAITING })
  for (const key of ['today', 'session', 'm2b'] as const) {
    expect(await partLook(ui, key)).toEqual({ ...FRAMED, ...CALM })
  }
  await ui.unmount()
})

test('while nothing waits the first part is framed and titled as every other, with no count and one line that steps back', async ($, on) => {
  // Covers: B205
  const fake = new FakeM2b()
  fake.dueTasks = [{ id: 't2', title: 'Buy screws', due: '2026-03-14', overdue: false }]
  await start($, on, fake)

  const ui = await startView($)

  expect((await shownParts(ui))[0]).toEqual({ key: 'waits', title: 'Waits for you', count: null, lines: [NOTHING_WAITS] })
  expect(await partLook(ui, 'waits')).toEqual({ ...FRAMED, ...CALM })
  expect(await lookOf(ui, NOTHING_WAITS)).toEqual(DIM)
  // A task due is read, not answered: it gives no part the color of what waits.
  expect(await partLook(ui, 'today')).toEqual({ ...FRAMED, ...CALM })
  await ui.unmount()
})

test('a part is a frame around its title from 36 columns of pane, and a bar down its left below that, at 24 columns too', async ($, on) => {
  // Covers: B205
  await start($, on, busyFake())

  for (const [columns, frame] of [
    [80, FRAMED],
    [36, FRAMED],
    [35, BARRED],
    [24, BARRED],
  ] as const) {
    const ui = await $.ui.mount({ ...pane(PANE, columns), surface: 'terminal' })

    expect(await partLook(ui, 'waits')).toEqual({ ...frame, ...WAITING })
    for (const key of ['today', 'session', 'm2b'] as const) {
      expect(await partLook(ui, key)).toEqual({ ...frame, ...CALM })
    }
    // The same parts with the same lines at every width.
    expect((await shownParts(ui)).map(shown => shown.lines.length)).toEqual([9, 2, 6, 1])
    await ui.unmount()
  }
})

test('a row is its text first and its buttons on the line below, so a long text pushes no button aside', async ($, on) => {
  // Covers: B205
  const long = 'Remember? Dana prefers the green tea from the shop at the corner of the market over every other tea she has tried so far'
  const fake = busyFake()
  fake.candidate('c2', long)
  fake.reviewDetails = { changes: [{ kind: 'rewrote', file: 'sam.md', topic: 'Sam', parts: [] }], copies: [], paragraphs: [] }
  await start($, on, fake)

  for (const columns of [80, 24]) {
    const ui = await $.ui.mount({ ...pane(PANE, columns), surface: 'terminal' })

    expect(await linesAt(ui, 'row:c1')).toEqual(['Remember? Dana prefers tea', '[keep] [drop]'])
    expect(await linesAt(ui, 'row:c2')).toEqual([long, '[keep] [drop]'])
    expect(await lookOf(ui, long)).toEqual(PLAIN)
    // What stands beside the buttons is detail, and steps back.
    expect(await linesAt(ui, 'review:r1')).toEqual([REVIEW, '[ok] 1 fact changed: Sam'])
    expect(await lookOf(ui, '1 fact changed: Sam')).toEqual(DIM)
    // A row with nothing to press has its detail on the second line all the same.
    expect(await linesAt(ui, 'row:proposals')).toEqual(['1 proposal from your sessions', 'in the tab Proposals'])
    expect(await lookOf(ui, 'in the tab Proposals')).toEqual(DIM)
    await ui.unmount()
  }
})

test('keep and ok are the one accent button of their row; drop and the button that turns m2b off step back; a topic and undo are neither', async ($, on) => {
  // Covers: B205
  await start($, on, busyFake())
  const ui = await startView($)

  const accent = (key: string) => ({ key, label: key.split(':')[0], variant: 'primary', dimColor: undefined })
  expect(await buttonsAt(ui, 'row:c1')).toEqual([accent('keep:c1'), { key: 'drop:c1', label: 'drop', variant: undefined, dimColor: true }])
  expect(await buttonsAt(ui, 'row:q1')).toEqual([accent('keep:q1'), { key: 'drop:q1', label: 'drop', variant: undefined, dimColor: true }])
  expect(await buttonsAt(ui, 'review:r1')).toEqual([accent('ok:r1')])
  expect(await buttonsAt(ui, 'row:folder')).toEqual([{ key: 'folder:off', label: 'turn off here', variant: undefined, dimColor: true }])
  expect(await buttonsAt(ui, 'row:topic:0')).toEqual([{ key: 'topic:0', label: 'Northwind', variant: undefined, dimColor: false }])
  // No part holds more than one accent button in a row, and the view none outside the rows that are answered.
  const accents = (await ui.findAll({ type: 'Button' })).filter(button => button.props['variant'] === 'primary').map(button => button.key)
  expect(accents).toEqual(['keep:c1', 'keep:q1', 'ok:r1'])

  await ui.press({ key: 'keep:c1' })
  expect(await buttonsAt(ui, 'row:c1')).toEqual([{ key: 'undo:c1', label: 'undo', variant: undefined, dimColor: false }])
  await ui.press({ key: 'undo:c1' })
  await ui.unmount()
})

test('the three states of a press: the buttons below the text; while it waits undo and what it will do; while it is written that alone, stepped back', async ($, on) => {
  // Covers: B205
  const fake = busyFake()
  fake.delayMs = args => (args[0] === 'tasks' ? 2_000 : 0)
  const { clock } = await start($, on, fake)
  const ui = await startView($)
  expect(await linesAt(ui, 'row:c1')).toEqual(['Remember? Dana prefers tea', '[keep] [drop]'])

  await ui.press({ key: 'drop:c1' })
  await ui.press({ key: 'ok:r1' })
  expect(await linesAt(ui, 'row:c1')).toEqual(['Remember? Dana prefers tea', '[undo] dropping'])
  expect(await linesAt(ui, 'review:r1')).toEqual([REVIEW, '[undo] closing'])
  expect(await lookOf(ui, 'dropping')).toEqual(DIM)

  await clock.advance(UNDO_MS + 1)
  const waits = (await partLines(ui, 'waits')) ?? []
  expect(waits).toContain('dropping: Remember? Dana prefers tea')
  expect(waits).toContain(`closing: ${REVIEW}`)
  expect(waits).not.toContain('Remember? Dana prefers tea')
  expect(await lookOf(ui, 'dropping: Remember? Dana prefers tea')).toEqual(DIM)
  expect(await lookOf(ui, `closing: ${REVIEW}`)).toEqual(DIM)
  expect(await buttonsAt(ui, 'part:waits')).toEqual([
    { key: 'keep:q1', label: 'keep', variant: 'primary', dimColor: undefined },
    { key: 'drop:q1', label: 'drop', variant: undefined, dimColor: true },
  ])

  await clock.advance(10_000)
  expect(fake.writes()).toEqual([
    ['tasks', 'drop', '--', 'c1'],
    ['tasks', 'complete', '--', 'r1'],
  ])
  await ui.unmount()
})

test('a count of none is not said: no 0 beside a title, no "0 facts" beside a topic, no line for notes or proposals there are none of', async ($, on) => {
  // Covers: B205
  const draw = ownOverview($, on)
  const topics = [
    { name: 'Northwind', facts: 3, current: 0 },
    { name: 'Acme Ltd', facts: 0, current: 2 },
    { name: 'Riverside Choir', facts: 0, current: 0 },
    { name: 'Lumen', facts: null, current: null },
    { name: 'Globex', facts: 1, current: 1 },
  ]
  const review = { id: 'r1', title: 'm2b: review', findings: [], changes: [] }

  const ui = await draw({ ...EMPTY, given: { ...KNOWN, topics }, snapshot: { ...QUIET, review } })

  expect(await partLines(ui, 'session')).toEqual([
    '[Northwind] 3 facts',
    '[Acme Ltd] 2 current',
    '[Riverside Choir]',
    '[Lumen]',
    '[Globex] 1 fact, 1 current',
    PRINTED_WHOLE,
  ])
  // A review whose run changed no fact has nothing beside ok.
  expect(await linesAt(ui, 'review:r1')).toEqual([REVIEW, '[ok]'])
  expect((await shownParts(ui)).map(shown => shown.count)).toEqual(['1', null, null])
  expect((await texts(ui)).filter(text => /(^|\D)0(\D|$)/.test(text))).toEqual([])
  await ui.unmount()

  const empty = await draw(EMPTY)
  expect((await shownParts(empty)).map(shown => shown.count)).toEqual([null, null, null])
  expect((await texts(empty)).filter(text => /\d/.test(text))).toEqual([])
  await empty.unmount()
})

test('a part with nothing in it is one line that steps back, and the part about m2b is left out where there is nothing to say', async ($, on) => {
  // Covers: B205
  const draw = ownOverview($, on)

  const ui = await draw(EMPTY)

  expect(await shownParts(ui)).toEqual([
    { key: 'waits', title: 'Waits for you', count: null, lines: [NOTHING_WAITS] },
    { key: 'today', title: 'Today', count: null, lines: [NOTHING_DUE] },
    { key: 'session', title: 'This session', count: null, lines: [PRINTED_WHOLE] },
  ])
  expect(await lookOf(ui, NOTHING_WAITS)).toEqual(DIM)
  expect(await lookOf(ui, NOTHING_DUE)).toEqual(DIM)
  await ui.unmount()
})

test('no part is drawn as its title alone', async ($, on) => {
  // Covers: B205
  const draw = ownOverview($, on)

  const ui = await draw({ ...EMPTY, given: { ...KNOWN, atStart: null } })

  expect((await shownParts(ui)).filter(shown => shown.lines.length === 0).map(shown => shown.title)).toEqual([])
  await ui.unmount()
})

test('that m2b has not looked yet stands once in the view: in the first part while nothing was read, in the part of the session while only that was not', async ($, on) => {
  // Covers: B205
  const draw = ownOverview($, on)
  const said = async (ui: Parameters<typeof texts>[0]): Promise<number> => (await texts(ui)).filter(text => text === NOT_LOOKED).length

  // Nothing read yet: the first part says so, and no other part is drawn.
  const unread = await draw(modelWith({}))
  expect(await shownParts(unread)).toEqual([{ key: 'waits', title: 'Waits for you', count: null, lines: [NOT_LOOKED] }])
  expect(await lookOf(unread, NOT_LOOKED)).toEqual(DIM)
  expect(await partLook(unread, 'waits')).toEqual({ ...FRAMED, ...CALM })
  expect(await said(unread)).toBe(1)
  await unread.unmount()

  // The band was read and the session was not: its own part says so, alone.
  const half = await draw({ ...EMPTY, given: null })
  expect((await shownParts(half)).map(shown => [shown.key, shown.lines])).toEqual([
    ['waits', [NOTHING_WAITS]],
    ['today', [NOTHING_DUE]],
    ['session', [NOT_LOOKED]],
  ])
  expect(await lookOf(half, NOT_LOOKED)).toEqual(DIM)
  expect(await said(half)).toBe(1)
  await half.unmount()

  // The session was read and the band was not: the first part says so, and the session's part says what it holds.
  const other = await draw(modelWith({ given: { ...KNOWN, topics: [{ name: 'Northwind', facts: 3, current: 0 }] } }))
  expect((await shownParts(other)).map(shown => [shown.key, shown.lines])).toEqual([
    ['waits', [NOT_LOOKED]],
    ['session', ['[Northwind] 3 facts', PRINTED_WHOLE]],
  ])
  expect(await said(other)).toBe(1)
  await other.unmount()
})

test('that the session keeps what it was given is said only where m2b is off and knows what it gave: never beside "holds no note of what it gave", nor beside a look that failed', async ($, on) => {
  // Covers: B185
  const draw = ownOverview($, on)
  const off = { offUnder: '/home/alex/code', folder: LUMEN }
  const offRow = ['m2b is off under this folder.', '/home/alex/code', '[turn on here]']

  const known = await draw({ ...EMPTY, given: { ...KNOWN, ...off } })
  expect(await partLines(known, 'session')).toEqual([PRINTED_WHOLE, ...offRow, KEEPS])
  expect(await lookOf(known, KEEPS)).toEqual(DIM)
  await known.unmount()

  const notKnown = await draw({ ...EMPTY, given: { ...KNOWN, ...off, known: false, atStart: null } })
  expect(await partLines(notKnown, 'session')).toEqual([NOT_KNOWN, ...offRow])
  expect(await lookOf(notKnown, NOT_KNOWN)).toEqual(DIM)
  await notKnown.unmount()

  const failed = await draw({ ...EMPTY, given: { ...NOT_READ, ...off } })
  const lines = (await partLines(failed, 'session')) ?? []
  expect(lines[0]).toBe('m2b could not look up what it gave this session: the machine state cannot be read')
  expect(lines).not.toContain(KEEPS)
  expect(await lookOf(failed, lines[0] ?? '')).toEqual(TROUBLE)
  await failed.unmount()

  // While m2b is on, the session gets its topics: nothing to say.
  const whileOn = await draw({ ...EMPTY, given: { ...KNOWN, folder: LUMEN } })
  expect(await partLines(whileOn, 'session')).toEqual([PRINTED_WHOLE, 'm2b is on in this folder.', LUMEN, '[turn off here]'])
  await whileOn.unmount()
})

test('the part about m2b is one line that steps back while all is well', async ($, on) => {
  // Covers: B206
  await start($, on, new FakeM2b())

  const ui = await startView($)

  expect((await shownParts(ui)).at(-1)).toEqual({ key: 'm2b', title: 'm2b', count: null, lines: [CURATED] })
  expect(await lookOf(ui, CURATED)).toEqual(DIM)
  expect(await partLook(ui, 'm2b')).toEqual({ ...FRAMED, ...CALM })
  await ui.unmount()
})

test('the part about m2b says each thing that is wrong as a sentence with its reason, in the color of trouble, above the line about curation', async ($, on) => {
  // Covers: B206
  const fake = new FakeM2b()
  fake.status = {
    inbox: { count: 2, evicted: 0 },
    run: { state: 'failed', started_at: '2026-03-14T18:00:05+01:00', message: 'the ingest step failed' },
    store_error: 'bad json in line 3',
    backends: { tasks: { state: 'reachable', detail: '' }, calendar: { state: 'not reachable', detail: 'timed out' } },
  }
  const { statuses } = await start($, on, fake)

  const ui = await startView($)

  const troubles = [RUN_FAILED, 'm2b could not read store.json: bad json in line 3', NO_CALENDAR]
  expect(await partLines(ui, 'm2b')).toEqual([...troubles, '2 in inbox'])
  for (const trouble of troubles) {
    expect(await lookOf(ui, trouble)).toEqual(TROUBLE)
  }
  expect(await lookOf(ui, '2 in inbox')).toEqual(DIM)
  // Something is wrong with m2b, and nothing waits for an answer: the part keeps its own frame.
  expect(await partLook(ui, 'm2b')).toEqual({ ...FRAMED, ...CALM })
  // The status line has room for what is wrong alone; why stands in the pane.
  expect(statuses.at(-1)).toBe('last curation run failed · could not read store.json · calendar not reachable')
  await ui.unmount()
})

test('a trouble the answer gives no reason for is a sentence that ends with a full stop', async ($, on) => {
  // Covers: B206
  const fake = new FakeM2b()
  fake.status = { ...STATUS, run: { state: 'interrupted' }, backends: { tasks: { state: 'not reachable', detail: '' } } }
  await start($, on, fake)

  const ui = await startView($)

  expect(await partLines(ui, 'm2b')).toEqual(['The last curation run was interrupted.', 'm2b could not reach the tasks.', '2 in inbox'])
  await ui.unmount()
})

test('the part about m2b is left out where m2b has nothing wrong and nothing to say of curation, and says an older m2b alone where that is all', async ($, on) => {
  // Covers: B206, B96
  const fake = new FakeM2b()
  // An empty inbox and a last run without a time: nothing to say of curation.
  fake.status = { inbox: { count: 0, evicted: 0 }, run: { state: 'succeeded' }, backends: {} }
  const { clock } = await start($, on, fake)
  const ui = await startView($)
  expect(await partLines(ui, 'm2b')).toBeNull()
  expect((await shownParts(ui)).map(shown => shown.key)).toEqual(['waits', 'today', 'session'])

  fake.version = '0.4.0'
  await clock.advance(60_000)

  const older = 'This session runs m2b 0.3.0 and m2b 0.4.0 is installed: run /reload-plugins.'
  expect(await partLines(ui, 'm2b')).toEqual([older])
  expect(await lookOf(ui, older)).toEqual(ASKS)
  await ui.unmount()
})

test('in the part about m2b what is wrong stands first, then that the session runs an older m2b, then the line about curation', async ($, on) => {
  // Covers: B206
  const draw = ownOverview($, on)

  const ui = await draw(TROUBLED)

  expect(await partLines(ui, 'm2b')).toEqual([RUN_FAILED, NO_CALENDAR, OLDER, '2 in inbox'])
  expect(await lookOf(ui, RUN_FAILED)).toEqual(TROUBLE)
  expect(await lookOf(ui, NO_CALENDAR)).toEqual(TROUBLE)
  expect(await lookOf(ui, OLDER)).toEqual(ASKS)
  expect(await lookOf(ui, '2 in inbox')).toEqual(DIM)
  await ui.unmount()

  // No answer read yet, and one that names neither a trouble nor a line: no part.
  for (const health of [null, { curation: null, troubles: [] }]) {
    const none = await draw({ ...EMPTY, health })
    expect(await partLines(none, 'm2b')).toBeNull()
    await none.unmount()
  }
})

test('what m2b said to a press on a row that wrote nothing stands in the part that waits, in the color of trouble, above the rows, and the band does not say it', async ($, on) => {
  // Covers: B207
  on('prompt.submit', (_, e) => ({ text: e.text }))
  const fake = busyFake()
  const { clock } = await start($, on, fake)
  const band = await $.ui.mount({ ...BAND, surface: 'terminal' })
  const ui = await startView($)
  fake.beforeCandidateList = () => {
    const [task] = fake.tasks
    if (task !== undefined) {
      task.completed = true
    }
  }

  await ui.press({ key: 'keep:c1' })
  await clock.advance(UNDO_MS)

  expect(fake.writes()).toEqual([])
  expect(await partLines(ui, 'waits')).toEqual([
    SETTLED,
    '1 proposal from your sessions',
    'in the tab Proposals',
    'Still current? Planning the trip to Porto',
    '[keep] [drop]',
    REVIEW,
    '[ok]',
    WHOLE_REVIEW,
  ])
  expect(await lookOf(ui, SETTLED)).toEqual(TROUBLE)
  expect((await texts(ui)).filter(text => text === SETTLED)).toHaveLength(1)
  expect((await everyText(band)).join('\n')).not.toContain('Already settled')
  expect((await everyText(band)).filter(text => text !== ENGINES_OWN_DRAWING)).toContain('3 wait for you  1 overdue  1 due today')

  // The next press on a row clears what the last one was told, before it writes.
  await ui.press({ key: 'drop:q1' })
  await clock.advance(UNDO_MS)
  expect(fake.writes()).toEqual([['tasks', 'drop', '--', 'q1']])
  expect(await texts(ui)).not.toContain(SETTLED)
  await ui.unmount()
  await band.unmount()
})

test('the text for a surface without panes has the same parts in the same order and words as the pane, and the small form counts in that order: a session with something in every part', async ($, on) => {
  // Covers: B205, B193
  const draw = ownOverview($, on)

  const ui = await draw(FULL)

  expect(await shownParts(ui)).toEqual([
    {
      key: 'waits',
      title: 'Waits for you',
      count: '5',
      lines: [
        '3 proposals from your sessions',
        'in the tab Proposals',
        'Remember? Dana prefers tea',
        '[keep] [drop]',
        REVIEW,
        '[ok] 1 fact changed: Sam',
        WHOLE_REVIEW,
      ],
    },
    {
      key: 'today',
      title: 'Today',
      count: null,
      lines: ['due today Send the offer to Acme', 'overdue Return the ladder to Sam', 'overdue Call the plumber'],
    },
    {
      key: 'session',
      title: 'This session',
      count: null,
      lines: [
        '[Northwind] 2 facts, 1 current',
        '[Acme Ltd] 1 fact',
        PRINTED_WHOLE,
        'm2b is on in this folder.',
        LUMEN,
        '[turn off here]',
        '2 notes written in this session',
      ],
    },
    { key: 'm2b', title: 'm2b', count: null, lines: [CURATED] },
  ])
  // A line has no button and no tab to press: what waits is named with the command that shows it.
  expect(sessionLines(FULL)).toEqual([
    'Waits for you',
    '  3 proposals from your sessions: /m2b-proposals',
    '  Remember? Dana prefers tea',
    `  ${REVIEW}, 1 fact changed: Sam: /m2b-review`,
    'Today',
    '  due today: Send the offer to Acme',
    '  overdue: Return the ladder to Sam',
    '  overdue: Call the plumber',
    'This session',
    '  Northwind: 2 facts, 1 current',
    '  Acme Ltd: 1 fact',
    `  ${PRINTED_WHOLE}`,
    `  m2b is on in this folder: ${LUMEN}`,
    '  2 notes written in this session',
    'm2b',
    `  ${CURATED}`,
  ])
  expect(glanceLines(FULL)).toEqual(['5 wait for you', '2 overdue, 1 due today', '2 topics in this session'])
  await ui.unmount()
})

test('the pane, the text and the small form of a session with nothing in any part: each part says so in one line, and the small form that nothing waits', async ($, on) => {
  // Covers: B205, B193
  const draw = ownOverview($, on)

  const ui = await draw(EMPTY)

  expect((await shownParts(ui)).map(shown => [shown.title, ...shown.lines])).toEqual([
    ['Waits for you', NOTHING_WAITS],
    ['Today', NOTHING_DUE],
    ['This session', PRINTED_WHOLE],
  ])
  expect(sessionLines(EMPTY)).toEqual(['Waits for you', `  ${NOTHING_WAITS}`, 'Today', `  ${NOTHING_DUE}`, 'This session', `  ${PRINTED_WHOLE}`])
  expect(glanceLines(EMPTY)).toEqual([NOTHING_WAITS])
  await ui.unmount()
})

test('the pane, the text and the small form of a session m2b has not looked at say so once each, and leave out every part but the first', async ($, on) => {
  // Covers: B205, B193
  const draw = ownOverview($, on)
  const unread = modelWith({})
  const half = { ...EMPTY, given: null }

  const ui = await draw(unread)
  expect((await shownParts(ui)).map(shown => [shown.title, ...shown.lines])).toEqual([['Waits for you', NOT_LOOKED]])
  expect(sessionLines(unread)).toEqual(['Waits for you', `  ${NOT_LOOKED}`])
  expect(glanceLines(unread)).toEqual([NOT_LOOKED])
  await ui.unmount()

  // Where only the session was not looked at, its part says so in all three.
  const besideTheBand = await draw(half)
  expect((await shownParts(besideTheBand)).map(shown => [shown.title, ...shown.lines])).toEqual([
    ['Waits for you', NOTHING_WAITS],
    ['Today', NOTHING_DUE],
    ['This session', NOT_LOOKED],
  ])
  expect(sessionLines(half)).toEqual(['Waits for you', `  ${NOTHING_WAITS}`, 'Today', `  ${NOTHING_DUE}`, 'This session', `  ${NOT_LOOKED}`])
  expect(glanceLines(half)).toEqual([NOTHING_WAITS, NOT_LOOKED])
  await besideTheBand.unmount()
})

test('the pane and the text say what is wrong in the same parts and words, and the small form says what could not be read in place of its count', async ($, on) => {
  // Covers: B205, B193
  const draw = ownOverview($, on)

  const ui = await draw(TROUBLED)

  expect((await shownParts(ui)).map(shown => [shown.title, ...shown.lines])).toEqual([
    ['Waits for you', STORE_UNREAD, SETTLED],
    ['Today', NOTHING_DUE],
    ['This session', '[Northwind] 2 facts', PRINTED_WHOLE, 'm2b is off under this folder.', '/home/alex/code', '[turn on here]', KEEPS, NOT_TURNED_ON],
    ['m2b', RUN_FAILED, NO_CALENDAR, OLDER, '2 in inbox'],
  ])
  for (const line of [STORE_UNREAD, SETTLED, NOT_TURNED_ON, RUN_FAILED, NO_CALENDAR]) {
    expect(await lookOf(ui, line)).toEqual(TROUBLE)
  }
  // Nothing waits for an answer: what is wrong colors its own line, not the frame.
  expect((await shownParts(ui))[0]?.count).toBeNull()
  expect(await partLook(ui, 'waits')).toEqual({ ...FRAMED, ...CALM })
  expect(sessionLines(TROUBLED)).toEqual([
    'Waits for you',
    `  ${STORE_UNREAD}`,
    `  ${SETTLED}`,
    'Today',
    `  ${NOTHING_DUE}`,
    'This session',
    '  Northwind: 2 facts',
    `  ${PRINTED_WHOLE}`,
    '  m2b is off under /home/alex/code',
    `  ${KEEPS}`,
    `  ${NOT_TURNED_ON}`,
    'm2b',
    `  ${RUN_FAILED}`,
    `  ${NO_CALENDAR}`,
    `  ${OLDER}`,
    '  2 in inbox',
  ])
  expect(glanceLines(TROUBLED)).toEqual([STORE_UNREAD, '1 topic in this session'])
  await ui.unmount()

  // A task list m2b could not read: one line in the first part, no part "Today", and no second line about the store.
  const unread = {
    ...TROUBLED,
    rowNotice: null,
    given: NOT_READ,
    snapshot: { ...QUIET, error: 'm2b could not read the tasks: Reminders did not answer' },
  }
  const notLookedUp = 'm2b could not look up what it gave this session: the machine state cannot be read'
  const tasks = await draw(unread)
  expect((await shownParts(tasks)).slice(0, 2).map(shown => [shown.title, ...shown.lines])).toEqual([
    ['Waits for you', 'm2b could not read the tasks: Reminders did not answer'],
    ['This session', notLookedUp, NOT_TURNED_ON],
  ])
  expect(sessionLines(unread).slice(0, 5)).toEqual([
    'Waits for you',
    '  m2b could not read the tasks: Reminders did not answer',
    'This session',
    `  ${notLookedUp}`,
    `  ${NOT_TURNED_ON}`,
  ])
  expect(glanceLines(unread)).toEqual(['The task list could not be read.', 'm2b could not look at this session.'])
  await tasks.unmount()
})

test('a line of the pane and of the text is one plain line, whatever a title, a topic or a reason holds', async ($, on) => {
  // Covers: B205
  const draw = ownOverview($, on)
  const odd = modelWith({
    given: { ...KNOWN, topics: [{ name: 'North\u001b[31mwind', facts: 1, current: 0 }] },
    rowNotice: 'Already settled in another session,\nnothing written: Dana\u0007',
    snapshot: { ...QUIET, candidates: [{ id: 'c1', title: 'Remember? \u001b[2JDana\nprefers tea' }] },
    health: { curation: '2 in\tinbox', troubles: ['The last curation run failed: the ingest\u001b[0m step failed'] },
    versionLine: 'This session runs\nan older m2b.',
  })

  const ui = await draw(odd)

  const inPane = (await shownParts(ui)).flatMap(shown => shown.lines)
  const asText = sessionLines(odd)
  for (const line of [...inPane, ...asText]) {
    expect(/[\u0000-\u001f\u007f-\u009f]/.test(line)).toBe(false)
  }
  expect(inPane).toContain('Already settled in another session, nothing written: Dana')
  expect(inPane).toContain('Remember? Dana prefers tea')
  expect(inPane).toContain('[Northwind] 1 fact')
  expect(inPane).toContain(RUN_FAILED)
  expect(inPane).toContain('2 in inbox')
  expect(asText).toContain('  Northwind: 1 fact')
  expect(asText).toContain(`  ${RUN_FAILED}`)
  expect(asText).toContain('  This session runs an older m2b.')
  await ui.unmount()
})

test('a part on its own: a box under its key with the title first, in the frame and colors of its state, the count only where one is given, then what stands in it', async ($, on) => {
  // Covers: B205
  let drawn: 'calm' | 'waits' | 'narrow' = 'calm'
  on('ui.render', { component: 'Pane', requestId: BLOCKS }, (engine, e) => {
    const ui = engine.ui.resolve(e)
    const { Box } = ui
    const body = [said(ui, 'first'), said(ui, 'second', 'quiet')]
    return (
      <Box flexDirection="column">
        {drawn === 'calm' && part(ui, { key: 'waits', title: 'Calm', waits: false, columns: 36 }, body)}
        {drawn === 'waits' && part(ui, { key: 'waits', title: 'Waiting', waits: true, count: '3', columns: 80 }, body)}
        {drawn === 'narrow' && part(ui, { key: 'waits', title: 'Narrow', waits: true, count: null, columns: 35 }, body)}
      </Box>
    )
  })
  const mounted = () => $.ui.mount({ ...pane(BLOCKS), plugin: 'test', surface: 'terminal' })

  const calm = await mounted()
  expect(await shownParts(calm)).toEqual([{ key: 'waits', title: 'Calm', count: null, lines: ['first', 'second'] }])
  expect(await partLook(calm, 'waits')).toEqual({ ...FRAMED, ...CALM })
  expect((await calm.find({ key: 'part:waits' }))?.props['flexDirection']).toBe('column')
  await calm.unmount()

  drawn = 'waits'
  const waiting = await mounted()
  expect(await shownParts(waiting)).toEqual([{ key: 'waits', title: 'Waiting', count: '3', lines: ['first', 'second'] }])
  expect(await partLook(waiting, 'waits')).toEqual({ ...FRAMED, ...WAITING })
  await waiting.unmount()

  // Narrow, and waiting without a count: the bar in the color of what waits, and no count drawn.
  drawn = 'narrow'
  const narrow = await mounted()
  expect(await shownParts(narrow)).toEqual([{ key: 'waits', title: 'Narrow', count: null, lines: ['first', 'second'] }])
  expect(await partLook(narrow, 'waits')).toEqual({ ...BARRED, ...WAITING, countColor: undefined })
  await narrow.unmount()
})

test('a row on its own: the text in its tone, and one line below with the buttons in their order and the detail beside them; no second line where there is neither', async ($, on) => {
  // Covers: B205
  const pressed: string[] = []
  const press = (key: string, label: string, kind: ButtonSpec['kind']): ButtonSpec => ({ key, label, kind, onPress: () => void pressed.push(key) })
  on('ui.render', { component: 'Pane', requestId: BLOCKS }, (engine, e) => {
    const ui = engine.ui.resolve(e)
    const { Box } = ui
    return (
      <Box flexDirection="column">
        {row(ui, { key: 'both', text: 'Keep this?', buttons: [press('yes', 'yes', 'accent'), press('no', 'no', 'quiet')], detail: 'said by Dana' })}
        {row(ui, { key: 'buttons', text: 'Undo this?', tone: 'waits', buttons: [press('undo', 'undo', 'default')] })}
        {row(ui, { key: 'detail', text: 'Three wait', buttons: [], detail: 'in the tab Proposals' })}
        {row(ui, { key: 'alone', text: 'Nothing to press', tone: 'quiet', buttons: [], detail: null })}
      </Box>
    )
  })
  const ui = await $.ui.mount({ ...pane(BLOCKS), plugin: 'test', surface: 'terminal' })

  expect(await linesAt(ui, 'both')).toEqual(['Keep this?', '[yes] [no] said by Dana'])
  expect(await buttonsAt(ui, 'both')).toEqual([
    { key: 'yes', label: 'yes', variant: 'primary', dimColor: undefined },
    { key: 'no', label: 'no', variant: undefined, dimColor: true },
  ])
  expect(await lookOf(ui, 'Keep this?')).toEqual(PLAIN)
  expect(await lookOf(ui, 'said by Dana')).toEqual(DIM)
  expect(await linesAt(ui, 'buttons')).toEqual(['Undo this?', '[undo]'])
  expect(await lookOf(ui, 'Undo this?')).toEqual(ASKS)
  expect(await linesAt(ui, 'detail')).toEqual(['Three wait', 'in the tab Proposals'])
  expect(await linesAt(ui, 'alone')).toEqual(['Nothing to press'])
  expect(await lookOf(ui, 'Nothing to press')).toEqual(DIM)
  // The text is the row's first child, a column: the buttons can only stand below it.
  for (const key of ['both', 'buttons', 'detail', 'alone']) {
    expect((await ui.find({ key }))?.props['flexDirection']).toBe('column')
  }

  await ui.press({ key: 'no' })
  await ui.press({ key: 'yes' })
  expect(pressed).toEqual(['no', 'yes'])
  await ui.unmount()
})

test('a path on its own: whole, one text for each folder, every character written as it is read', async ($, on) => {
  // Covers: B205
  const paths = ['/home/alex/code/acme', '/home/alex/my code/acme ltd', '/x/ac\u001bme\n', '/x/acme ', 'acme', '/', '/x/ac\\me']
  on('ui.render', { component: 'Pane', requestId: BLOCKS }, (engine, e) => {
    const ui = engine.ui.resolve(e)
    const { Box } = ui
    return (
      <Box flexDirection="column">
        {paths.map((path, at) => (
          <Box key={`path:${at}`}>{pathLine(ui, path)}</Box>
        ))}
      </Box>
    )
  })
  const ui = await $.ui.mount({ ...pane(BLOCKS), plugin: 'test', surface: 'terminal' })
  const pieces = (at: number): Promise<string[]> => pathPieces(ui, `path:${at}`)

  expect(await pieces(0)).toEqual(['/home', '/alex', '/code', '/acme'])
  // A space in a name is part of its piece: the path breaks before a slash and nowhere else.
  expect(await pieces(1)).toEqual(['/home', '/alex', '/my code', '/acme ltd'])
  // What a terminal would run, a line break and a space at the end are written out in their place.
  expect(await pieces(2)).toEqual(['/x', '/ac\\x1bme\\x0a'])
  expect(await pieces(3)).toEqual(['/x', '/acme\\x20'])
  // A path without a slash is one piece, and the root is itself.
  expect(await pieces(4)).toEqual(['acme'])
  expect(await pieces(5)).toEqual(['/'])
  // A backslash in a name is doubled, so it is not read as a character written out.
  expect(await pieces(6)).toEqual(['/x', '/ac\\\\me'])
  // Put together again, the pieces are the path, and each steps back as detail does.
  expect((await pieces(1)).join('')).toBe(paths[1])
  expect(await lookOf(ui, '/my code')).toEqual({ color: undefined, dimColor: true, wrap: undefined })
  await ui.unmount()
})

test("a topic's label is its name on one line, whole up to 20 characters and cut to 19 and an ellipsis beyond", () => {
  // Covers: B190
  expect(topicLabel('Northwind')).toBe('Northwind')
  expect(topicLabel('Northwind Trading Co')).toBe('Northwind Trading Co')
  expect(Array.from('Northwind Trading Co')).toHaveLength(20)
  expect(topicLabel('Riverside Community Choir')).toBe('Riverside Community…')
  expect(Array.from(topicLabel('Riverside Community Choir'))).toHaveLength(20)
  // Counted in characters, not in the units a string is stored in.
  expect(topicLabel('😀'.repeat(20))).toBe('😀'.repeat(20))
  expect(topicLabel('😀'.repeat(21))).toBe(`${'😀'.repeat(19)}…`)
  // What a terminal would run and a line break never reach a label.
  expect(topicLabel('Ac\u001b[31mme\nLtd')).toBe('Acme Ltd')
})

test("a topic's button on the overview carries the label, and its counts stand beside it, stepped back", async ($, on) => {
  // Covers: B190
  const draw = ownOverview($, on)
  const topics = [
    { name: 'Riverside Community Choir', facts: 2, current: 1 },
    { name: 'Northwind', facts: null, current: null },
  ]

  const ui = await draw({ ...EMPTY, given: { ...KNOWN, topics } })

  expect(await linesAt(ui, 'row:topic:0')).toEqual(['[Riverside Community…] 2 facts, 1 current'])
  expect(await lookOf(ui, '2 facts, 1 current')).toEqual(DIM)
  expect(await linesAt(ui, 'row:topic:1')).toEqual(['[Northwind]'])
  await ui.unmount()
})
