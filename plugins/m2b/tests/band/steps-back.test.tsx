import { expect, test } from 'claude-code/testing'
import type { CommandRunResult } from 'claude-code'
import type { Engine } from 'claude-code/testing'

import { lineBesidePane, topicsGiven } from '../../hooks/band'
import type { BandModel } from '../../hooks/band'
import { paneSight } from '../../hooks/pane-seat'
import { glanceLines } from '../../hooks/session-view'
import type { SessionModel } from '../../hooks/session-view'
import { BAND, ENGINES_OWN_DRAWING, FakeM2b, everyText, pane, start, texts } from './harness'

const PANE = 'm2b'
const CLOSED_BY_HAND = 'paneClosedByHand'
const UNDO_MS = 5_000
const BY_ITSELF = { id: PANE, title: 'm2b' }
const AS_A_DIALOG = { id: PANE, title: 'm2b', closeOnEscape: true, focus: true }
const TO_STAY = { id: PANE, title: 'm2b', focus: true }
const WIDE = { columns: 160, rows: 50, isFullscreen: true }
const NARROW = { columns: 120, rows: 50, isFullscreen: true }
const MAIN_SCREEN = { columns: 160, rows: 50, isFullscreen: false }
const NO_SURFACE = 'no-surface: no surface is attached'
const COUNTS = 'Waits for you: 2 to keep or drop, 1 proposal from your sessions, the review'
const TOPICS_ROW = '2 topics given to this session'

type Clock = { advance: (ms: number) => Promise<void> }
type Viewport = { columns: number; rows: number; isFullscreen?: boolean }
type Surface = 'terminal' | 'desktop'

function typed($: Engine, command: string, presentation = { isFullscreen: false, columns: 100 }): Promise<CommandRunResult> {
  return $.command.run({ command, args: '', origin: { kind: 'composer' }, presentation })
}

/** The band's drawing and the moment after it, in which the pane opens by itself where it may. */
async function drawBand($: Engine, clock: Clock, viewport: Viewport = WIDE, surface: Surface = 'terminal') {
  const ui = await $.ui.mount({ ...BAND, surface, viewport })
  await clock.advance(1)
  return ui
}

/** The pane's drawing in a seat, and the moment after it, in which the band learns of the seat. */
async function drawPane(
  $: Engine,
  clock: Clock,
  placement: 'dock' | 'inline' | 'widget' = 'dock',
  bodyColumns = 50,
  surface: Surface = 'terminal',
) {
  const ui = await $.ui.mount({ ...pane(PANE, bodyColumns, placement), surface })
  await clock.advance(1)
  return ui
}

/** A session that was given two topics, with a candidate, a question, a review, a proposal and two tasks due. */
function busyFake(): FakeM2b {
  const fake = new FakeM2b()
  fake.given = {
    topics: [
      { name: 'Northwind', facts: 3, current: 1 },
      { name: 'Acme Ltd', facts: 1, current: 0 },
    ],
    atStart: 'whole',
    offUnder: null,
  }
  fake.candidate('c1', 'Remember? Dana prefers tea')
  fake.question('q1', 'Still current? Planning the trip to Porto')
  fake.review('r1', ['lint: broken link in a.md'])
  fake.proposal('a1a1a1a1a1a1', 'Dana is head of IT at Northwind.', 'Dana runs IT at Northwind')
  fake.dueTasks = [
    { id: 'd1', title: 'Send the offer to Acme', due: '2026-03-14', overdue: false },
    { id: 'd2', title: 'Call the plumber', due: '2026-03-10', overdue: true },
  ]
  return fake
}

/** What the band draws on its own, on the main screen and before any pane. */
const ROWS_OF_TODAY = [
  'Remember? Dana prefers tea',
  'Still current? Planning the trip to Porto',
  '1 proposal from your sessions',
  'due today: Send the offer to Acme',
  'overdue: Call the plumber',
  'm2b: review',
  'lint: broken link in a.md',
]

function model(fields: Partial<BandModel> = {}): BandModel {
  return { snapshot: null, proposals: null, notice: null, proposalsNotice: null, versionLine: null, presses: {}, topics: 0, ...fields }
}

test('fullscreen, wide: beside the docked pane the band draws one line, the counts of what waits', async ($, on) => {
  // Covers: B191
  const { clock, opened } = await start($, on, busyFake())
  const band = await drawBand($, clock)
  expect(opened).toEqual([BY_ITSELF])
  expect(await texts(band)).toEqual(expect.arrayContaining(ROWS_OF_TODAY))

  const beside = await drawPane($, clock)

  expect(await texts(band)).toEqual([COUNTS])
  const [counts] = await band.findAll({ type: 'Text', text: COUNTS })
  expect(counts?.props['color']).toBeUndefined()
  expect(counts?.props['wrap']).toBe('truncate-end')
  expect(await band.findAll({ type: 'Button' })).toHaveLength(0)
  // Nothing is lost: every row and its buttons stand in the pane.
  const inPane = await texts(beside)
  expect(inPane).toContain('Northwind: 3 facts, 1 current')
  expect(inPane).toContain('Remember? Dana prefers tea')
  expect(inPane).toContain('due today: Send the offer to Acme')
  expect(await beside.find({ key: 'keep:c1' })).toBeDefined()
  await beside.unmount()
  await band.unmount()
})

test('beside the docked pane a band with nothing to answer draws nothing of its own', async ($, on) => {
  // Covers: B191
  const fake = new FakeM2b()
  fake.given = { topics: [{ name: 'Northwind', facts: 3, current: 0 }], atStart: 'whole', offUnder: null }
  fake.dueTasks = [{ id: 'd1', title: 'Send the offer to Acme', due: '2026-03-14', overdue: false }]
  const { clock } = await start($, on, fake)
  const band = await drawBand($, clock)
  expect(await texts(band)).toContain('due today: Send the offer to Acme')

  const beside = await drawPane($, clock)

  expect(await everyText(band)).toEqual([ENGINES_OWN_DRAWING])
  await beside.unmount()
  await band.unmount()
})

for (const columns of [24, 40]) {
  test(`docked with a body of ${columns} columns: one line in the band, names with counts in the pane`, async ($, on) => {
    // Covers: B191
    const { clock } = await start($, on, busyFake())
    const band = await drawBand($, clock)

    const beside = await drawPane($, clock, 'dock', columns)

    expect(await texts(band)).toEqual([COUNTS])
    const inPane = await texts(beside)
    expect(inPane).toContain('Northwind: 3 facts, 1 current')
    expect(inPane).toContain('Acme Ltd: 1 fact')
    // A topic's lines come on a press, never into a pane this narrow by themselves.
    expect(await beside.find({ key: 'topic:0' })).toBeDefined()
    await beside.unmount()
    await band.unmount()
  })
}

test('a task list that cannot be read is the one line beside the docked pane', async ($, on) => {
  // Covers: B191
  const fake = busyFake()
  fake.failure = 'the task list did not answer'
  const { clock } = await start($, on, fake)
  const band = await drawBand($, clock)

  const beside = await drawPane($, clock)

  expect(await texts(band)).toEqual(['m2b could not read the tasks: the task list did not answer'])
  const [line] = await band.findAll({ type: 'Text', text: 'm2b could not read the tasks: the task list did not answer' })
  expect(line?.props['color']).toBe('error')
  expect(line?.props['wrap']).toBe('truncate-end')
  await beside.unmount()
  await band.unmount()
})

test('the hint that this session runs an older band is the one line beside the docked pane', async ($, on) => {
  // Covers: B191
  const fake = busyFake()
  fake.version = '0.4.0'
  const { clock } = await start($, on, fake)
  const band = await drawBand($, clock)

  const beside = await drawPane($, clock)

  const older = 'this session runs the band of m2b 0.3.0 while m2b 0.4.0 is installed: run /reload-plugins'
  expect(await texts(band)).toEqual([older])
  expect((await band.findAll({ type: 'Text', text: older }))[0]?.props['color']).toBe('warning')
  // The pane says nothing of it, so the band keeps the line.
  expect((await texts(beside)).join('\n')).not.toContain('/reload-plugins')
  await beside.unmount()
  await band.unmount()
})

test('what a press in the pane could not write is the one line, until the next prompt', async ($, on) => {
  // Covers: B191
  on('prompt.submit', (_, e) => ({ text: e.text, context: e.context }))
  const fake = busyFake()
  const { clock } = await start($, on, fake)
  const band = await drawBand($, clock)
  const beside = await drawPane($, clock)
  fake.beforeCandidateList = () => {
    const [task] = fake.tasks
    if (task !== undefined) {
      task.completed = true
    }
  }

  await beside.press({ key: 'drop:c1' })
  await clock.advance(UNDO_MS)

  expect(await texts(band)).toEqual(['Already settled in another session, nothing written: Remember? Dana prefers tea'])
  await $.prompt.submit({ text: 'go on', context: [], wait: false, origin: { kind: 'composer' } })
  expect(await texts(band)).toEqual(['Waits for you: 1 to keep or drop, 1 proposal from your sessions, the review'])
  await beside.unmount()
  await band.unmount()
})

test('the one line is what the pane does not show first, then an error, then the counts', () => {
  // Covers: B191
  const waits = {
    snapshot: {
      candidates: [{ id: 'c1', title: 'Remember? Dana prefers tea' }],
      review: { id: 'r1', title: 'm2b: review', findings: [] },
      error: null,
    },
    proposals: { waiting: [], answered: 0, error: null },
  }
  const unread = { snapshot: { candidates: [], review: null, error: 'm2b could not read the tasks: no answer' } }
  const noStore = { proposals: { waiting: [], answered: 0, error: 'the store is not downloaded' } }

  expect(lineBesidePane(model())).toBeNull()
  expect(lineBesidePane(model({ snapshot: { candidates: [], review: null, error: null } }))).toBeNull()
  expect(lineBesidePane(model(waits))).toEqual({ text: 'Waits for you: 1 to keep or drop, the review', tone: 'plain' })
  expect(lineBesidePane(model(unread))).toEqual({ text: 'm2b could not read the tasks: no answer', tone: 'error' })
  expect(lineBesidePane(model({ ...waits, ...noStore }))).toEqual({
    text: 'm2b could not look for proposals: the store is not downloaded',
    tone: 'error',
  })
  // Beside a task list that could not be read, the store is most often the same reason.
  expect(lineBesidePane(model({ ...unread, ...noStore }))?.text).toBe('m2b could not read the tasks: no answer')
  const older = { versionLine: 'this session runs the band of m2b 0.3.0 while m2b 0.4.0 is installed: run /reload-plugins' }
  expect(lineBesidePane(model({ ...unread, ...older }))).toEqual({ text: older.versionLine, tone: 'warning' })
  expect(lineBesidePane(model({ ...unread, ...older, proposalsNotice: 'not kept: answered already' }))).toEqual({
    text: 'not kept: answered already',
    tone: 'warning',
  })
  expect(
    lineBesidePane(model({ ...unread, ...older, proposalsNotice: 'not kept: answered already', notice: 'Already settled' })),
  ).toEqual({ text: 'Already settled', tone: 'warning' })
  // One line, whatever a text from the store holds.
  expect(lineBesidePane(model({ notice: 'first\nsecond\u001b[2J' }))?.text).toBe('first second')
})

test('the band steps back for a pane that is docked, shown, drawn and on its start view, and for no other', () => {
  // Covers: B191
  const shown = { isShown: true, isPlaced: true }
  expect(paneSight('dock', shown, true)).toBe('beside')
  // A seat this band does not know is treated as the dock, as Claude Code asks.
  expect(paneSight('rail', shown, true)).toBe('beside')
  // The block above the prompt and the small form of the desktop app do not take the band's rows.
  expect(paneSight('inline', shown, true)).toBe('shown')
  expect(paneSight('widget', shown, true)).toBe('shown')
  // Nor does a docked pane turned to the review, a search, the proposals or a topic.
  expect(paneSight('dock', shown, false)).toBe('shown')
  // Never drawn on this surface, closed since, a tab behind another plugin's pane, or not drawn.
  expect(paneSight(undefined, shown, true)).toBe('away')
  expect(paneSight('dock', undefined, true)).toBe('away')
  expect(paneSight('dock', { isShown: false, isPlaced: true }, true)).toBe('away')
  expect(paneSight('dock', { isShown: true, isPlaced: false }, true)).toBe('away')
  expect(paneSight('inline', { isShown: false, isPlaced: true }, true)).toBe('away')
  expect(paneSight('dock', { isShown: false, isPlaced: true }, false)).toBe('away')
})

test('while the docked pane is turned to another view, the band keeps its rows, and steps back again after back', async ($, on) => {
  // Covers: B191
  const { clock } = await start($, on, busyFake())
  const band = await drawBand($, clock)
  const beside = await drawPane($, clock)
  expect(await texts(band)).toEqual([COUNTS])

  // The review holds no row for the proposals and no task due; a search and a topic hold no row at all.
  await beside.press({ key: 'show:review' })

  const rows = await texts(band)
  expect(rows).toEqual(expect.arrayContaining(ROWS_OF_TODAY))
  // `back` above the view leads to what this session was given.
  expect(rows).not.toContain(TOPICS_ROW)
  expect(await band.find({ key: 'keep:c1' })).toBeDefined()

  await beside.press({ key: 'back' })
  await clock.advance(1)
  expect(await texts(band)).toEqual([COUNTS])
  await beside.unmount()
  await band.unmount()
})

test('a second session start in the same module leaves the band beside the docked pane at its one line', async ($, on) => {
  // Covers: B191
  const { clock } = await start($, on, busyFake())
  const band = await drawBand($, clock)
  const beside = await drawPane($, clock)
  // The pane stays up and is not drawn again: the module hands over the seats it holds once more.
  await beside.unmount()

  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await clock.advance(1)

  expect(await texts(band)).toEqual([COUNTS])
  await band.unmount()
})

test("a seat the session's state did not take is handed over with the pane's next drawing, and then no more", async ($, on) => {
  // Covers: B191
  let isRefusing = true
  let handed = 0
  on('state.set', (_, e, next) => {
    if (!JSON.stringify(e).includes('paneSeats')) {
      return next(e)
    }
    handed += 1
    return isRefusing ? { deny: 'the state is not written now' } : next(e)
  })
  const { clock } = await start($, on, busyFake())
  const band = await drawBand($, clock)
  const beside = await drawPane($, clock)
  // The band does not know of the seat, and draws all it has.
  expect(await texts(band)).toEqual(expect.arrayContaining(ROWS_OF_TODAY))

  isRefusing = false
  await beside.redraw()
  await clock.advance(1)
  expect(await texts(band)).toEqual([COUNTS])

  const before = handed
  await beside.redraw()
  await clock.advance(1)
  expect(handed).toBe(before)
  await beside.unmount()
  await band.unmount()
})

test('a close that a hook beneath held back leaves the band at its one line', async ($, on) => {
  // Covers: B191
  const fake = busyFake()
  const { clock, openPanes } = await start($, on, fake)
  const band = await drawBand($, clock)
  const beside = await drawPane($, clock)

  // A command whose pane is not placed closes it; here something beneath keeps it open.
  fake.isCloseHeld = true
  fake.paneWaits = 'no surface attached places panes'
  await typed($, 'm2b')
  fake.paneWaits = null
  expect(openPanes.has(PANE)).toBe(true)
  await band.redraw()

  expect(await texts(band)).toEqual([COUNTS])
  await beside.unmount()
  await band.unmount()
})

test('once the pane is closed, the band draws its rows again, with the row for this session', async ($, on) => {
  // Covers: B191
  const fake = busyFake()
  const { clock, openPanes } = await start($, on, fake)
  const band = await drawBand($, clock)
  const beside = await drawPane($, clock)
  expect(await texts(band)).toEqual([COUNTS])

  // A command whose pane no surface can show closes the pane it opened.
  fake.paneWaits = 'no surface attached places panes'
  await typed($, 'm2b-review')
  fake.paneWaits = null
  await beside.unmount()
  expect(openPanes.has(PANE)).toBe(false)

  expect(await texts(band)).toEqual(expect.arrayContaining([...ROWS_OF_TODAY, TOPICS_ROW]))

  // Opened again and not drawn on this surface yet: where it sat before it closed says nothing.
  await typed($, 'm2b', { isFullscreen: true, columns: 160 })
  expect(openPanes.has(PANE)).toBe(true)
  expect(await texts(band)).toEqual(expect.arrayContaining([...ROWS_OF_TODAY, TOPICS_ROW]))
  await band.unmount()
})

test('when Claude Code cannot say which panes are open, the band keeps its rows', async ($, on) => {
  // Covers: B191
  const fake = busyFake()
  const { clock } = await start($, on, fake)
  const band = await drawBand($, clock)
  const beside = await drawPane($, clock)
  expect(await texts(band)).toEqual([COUNTS])

  fake.panesFail = 'the session is closing'
  await band.redraw()

  expect(await texts(band)).toEqual(expect.arrayContaining([...ROWS_OF_TODAY, TOPICS_ROW]))
  await beside.unmount()
  await band.unmount()
})

test("while another plugin's pane is the one shown, the band keeps its rows and the row for this session", async ($, on) => {
  // Covers: B191
  const fake = busyFake()
  const { clock } = await start($, on, fake)
  const band = await drawBand($, clock)
  const beside = await drawPane($, clock)
  expect(await texts(band)).toEqual([COUNTS])

  fake.isPaneBehind = true
  await band.redraw()

  expect(await texts(band)).toEqual(expect.arrayContaining([...ROWS_OF_TODAY, TOPICS_ROW]))
  await beside.unmount()
  await band.unmount()
})

test('a pane that was docked and that Claude Code says is not drawn now leaves the band its rows', async ($, on) => {
  // Covers: B191
  const fake = busyFake()
  const { clock } = await start($, on, fake)
  const band = await drawBand($, clock)
  const beside = await drawPane($, clock)

  fake.paneWaits = 'an unrequested pane is placed from 144 columns; the terminal has 100'
  await band.redraw()

  expect(await texts(band)).toEqual(expect.arrayContaining([...ROWS_OF_TODAY, TOPICS_ROW]))
  await beside.unmount()
  await band.unmount()
})

test('the band of a surface steps back only for the pane docked on that surface', async ($, on) => {
  // Covers: B191
  const { clock } = await start($, on, busyFake())
  const onTerminal = await drawBand($, clock, MAIN_SCREEN)
  const onDesktop = await drawBand($, clock, WIDE, 'desktop')
  await typed($, 'm2b')

  const beside = await drawPane($, clock, 'dock', 50, 'desktop')

  expect(await texts(onDesktop)).toEqual([COUNTS])
  expect(await texts(onTerminal)).toEqual(expect.arrayContaining([...ROWS_OF_TODAY, TOPICS_ROW]))
  await beside.unmount()
  await onDesktop.unmount()
  await onTerminal.unmount()
})

test('not fullscreen: the band as it was, and one row with the topics this session was given', async ($, on) => {
  // Covers: B192
  const { clock, opened } = await start($, on, busyFake())

  const band = await drawBand($, clock, MAIN_SCREEN)

  expect(opened).toEqual([])
  expect(await texts(band)).toEqual(expect.arrayContaining([...ROWS_OF_TODAY, TOPICS_ROW]))
  // keep and drop on two rows, show on the proposals, ok on the review, and show on this session.
  expect(await band.findAll({ type: 'Button' })).toHaveLength(7)
  await band.unmount()
})

test('not fullscreen: a press on the row opens the pane as a dialog, and the row goes while the block shows', async ($, on) => {
  // Covers: B192
  const { clock, opened } = await start($, on, busyFake())
  const band = await drawBand($, clock, MAIN_SCREEN)

  await band.press({ key: 'show:session' })
  expect(opened).toEqual([AS_A_DIALOG])
  const block = await drawPane($, clock, 'inline', 100)

  expect(await texts(block)).toContain('Northwind: 3 facts, 1 current')
  // Above the prompt the pane is a block to read and close: the band keeps every row it has.
  const below = await texts(band)
  expect(below).toEqual(expect.arrayContaining(ROWS_OF_TODAY))
  expect(below).not.toContain(TOPICS_ROW)
  await block.unmount()
  await band.unmount()
})

test('fullscreen, narrow: the pane waits undrawn, the band carries the row, and a press shows the pane to stay', async ($, on) => {
  // Covers: B192
  const fake = busyFake()
  fake.paneWaits = 'an unrequested pane is placed from 144 columns; the terminal has 120'
  const { clock, opened, openPanes } = await start($, on, fake)

  const band = await drawBand($, clock, NARROW)

  expect(opened).toEqual([BY_ITSELF])
  expect(openPanes.has(PANE)).toBe(true)
  expect(await texts(band)).toEqual(expect.arrayContaining([...ROWS_OF_TODAY, TOPICS_ROW]))

  // A pane the person asks for is placed at any width.
  fake.paneWaits = null
  await band.press({ key: 'show:session' })

  expect(opened).toEqual([BY_ITSELF, TO_STAY])
  const beside = await drawPane($, clock)
  expect(await texts(band)).toEqual([COUNTS])
  await beside.unmount()
  await band.unmount()
})

test('fullscreen, too narrow to dock: a press on the row opens the pane as a dialog', async ($, on) => {
  // Covers: B192
  const fake = busyFake()
  fake.paneWaits = 'an unrequested pane is placed from 144 columns; the terminal has 100'
  const { clock, opened } = await start($, on, fake)
  const band = await drawBand($, clock, { columns: 109, rows: 50, isFullscreen: true })

  fake.paneWaits = null
  await band.press({ key: 'show:session' })

  // Below 110 columns the pane is a block above the prompt, which Escape closes.
  expect(opened).toEqual([BY_ITSELF, AS_A_DIALOG])
  await band.unmount()
})

test('the row names one topic as one, and asks again what the session was given', async ($, on) => {
  // Covers: B192
  const fake = new FakeM2b()
  fake.given = { topics: [{ name: 'Northwind', facts: 3, current: 0 }], atStart: 'whole', offUnder: null }
  const { clock } = await start($, on, fake)
  const band = await drawBand($, clock, MAIN_SCREEN)
  expect(await texts(band)).toEqual(['1 topic given to this session'])
  const looksBefore = fake.looks.length

  await band.press({ key: 'show:session' })
  await clock.advance(1)

  expect(fake.looks.length).toBe(looksBefore + 1)
  await band.unmount()
})

test('a press on the row turns a pane left on another view to the view it starts in', async ($, on) => {
  // Covers: B192
  const fake = busyFake()
  const { clock } = await start($, on, fake)
  const band = await drawBand($, clock)
  await typed($, 'm2b-review', { isFullscreen: true, columns: 160 })
  const beside = await drawPane($, clock)
  expect(await texts(beside)).not.toContain('In this session')
  // Another plugin's pane comes in front, so the band carries the row.
  fake.isPaneBehind = true
  await band.redraw()

  await band.press({ key: 'show:session' })

  expect(await texts(beside)).toContain('In this session')
  await beside.unmount()
  await band.unmount()
})

test('a session given no topic, not known, not looked at or not readable gets no row', async ($, on) => {
  // Covers: B192
  const known = { id: 's', known: true, atStart: 'whole', offUnder: null, error: null }
  const topic = { name: 'Northwind', facts: 3, current: 0 }
  expect(topicsGiven({ ...known, topics: [topic, { ...topic, name: 'Acme Ltd' }] })).toBe(2)
  expect(topicsGiven({ ...known, topics: [] })).toBe(0)
  expect(topicsGiven(null)).toBe(0)
  expect(topicsGiven({ ...known, known: false, topics: [topic] })).toBe(0)
  expect(topicsGiven({ ...known, topics: [topic], error: 'm2b did not answer' })).toBe(0)

  const fake = new FakeM2b()
  fake.given = { topics: [], atStart: 'whole', offUnder: null }
  const { clock } = await start($, on, fake)
  const band = await drawBand($, clock, MAIN_SCREEN)
  expect(await everyText(band)).toEqual([ENGINES_OWN_DRAWING])
  await band.unmount()
})

test('after the pane was closed by hand the band carries the row, and a press on it is the word to open it again', async ($, on) => {
  // Covers: B192
  const fake = busyFake()
  fake.stored = { [CLOSED_BY_HAND]: true }
  const { clock, opened } = await start($, on, fake)
  const band = await drawBand($, clock)
  expect(opened).toEqual([])
  expect(await texts(band)).toContain(TOPICS_ROW)

  await band.press({ key: 'show:session' })

  expect(opened).toEqual([TO_STAY])
  expect(fake.stored[CLOSED_BY_HAND]).toBeUndefined()
  await band.unmount()
})

test('where the pane cannot be shown, a press on the row says so in the band and leaves no pane open', async ($, on) => {
  // Covers: B192
  const fake = busyFake()
  fake.paneWaits = 'no surface attached places panes'
  const { clock, openPanes } = await start($, on, fake)
  const band = await drawBand($, clock, MAIN_SCREEN)

  await band.press({ key: 'show:session' })

  expect(openPanes.has(PANE)).toBe(false)
  expect(await texts(band)).toContain(
    'the m2b pane cannot be shown here: no surface attached places panes; /m2b answers with the lines',
  )
  await band.unmount()
})

test('a press on the row that Claude Code refuses to open a pane for says so in the band', async ($, on) => {
  // Covers: B192
  const fake = busyFake()
  const { clock, opened } = await start($, on, fake)
  const band = await drawBand($, clock, MAIN_SCREEN)

  fake.openFails = 'another plugin holds the pane m2b'
  await band.press({ key: 'show:session' })

  expect(opened).toEqual([])
  expect((await texts(band)).some(line => line.startsWith('the m2b pane could not be opened:'))).toBe(true)
  expect((await texts(band)).some(line => line.endsWith('; /m2b answers with the lines'))).toBe(true)
  await band.unmount()
})

test('a session that was not looked at under its id gets no row', async ($, on) => {
  // Covers: B192
  const fake = busyFake()
  const { clock } = await start($, on, fake)
  const band = await drawBand($, clock, MAIN_SCREEN)
  expect(await texts(band)).toContain(TOPICS_ROW)

  // After `/clear` the session goes on under another id, and what was kept is about the ended one.
  fake.sessionId = '7c9e6679-7425-40de-944b-e07fc1f90ae7'
  await band.redraw()

  expect(await texts(band)).not.toContain(TOPICS_ROW)
  await band.unmount()
})

test('the desktop app: docked there, the band of the app draws the one line', async ($, on) => {
  // Covers: B191
  const { clock } = await start($, on, busyFake())
  const band = await drawBand($, clock, WIDE, 'desktop')
  await typed($, 'm2b', { isFullscreen: true, columns: 160 })

  const beside = await drawPane($, clock, 'dock', 60, 'desktop')

  expect(await texts(band)).toEqual([COUNTS])
  await beside.unmount()
  await band.unmount()
})

test('the desktop app: as a widget the pane draws counts and no button, and the band keeps its rows', async ($, on) => {
  // Covers: B193
  const { clock } = await start($, on, busyFake())
  const band = await drawBand($, clock, WIDE, 'desktop')
  await typed($, 'm2b', { isFullscreen: true, columns: 160 })

  const widget = await drawPane($, clock, 'widget', 30, 'desktop')

  expect(await texts(widget)).toEqual(['2 topics in this session', '4 wait for you', '1 due today, 1 overdue'])
  expect(await widget.findAll({ type: 'Button' })).toHaveLength(0)
  // A click may not reach a widget: keep, drop and ok stay in the band, and the widget says the topics.
  const below = await texts(band)
  expect(below).toEqual(expect.arrayContaining(ROWS_OF_TODAY))
  expect(below).not.toContain(TOPICS_ROW)
  await widget.unmount()
  await band.unmount()
})

test('a widget says what it could not look at, and draws the counts whatever view the pane was turned to', async ($, on) => {
  // Covers: B193
  const fake = new FakeM2b()
  fake.given = null
  fake.failure = 'the task list did not answer'
  fake.review('r1', ['lint: broken link in a.md'])
  const { clock } = await start($, on, fake)
  await typed($, 'm2b-review', { isFullscreen: true, columns: 160 })

  const widget = await drawPane($, clock, 'widget', 30, 'desktop')

  expect(await texts(widget)).toEqual(['m2b holds no note of this session.', 'The task list could not be read.'])
  expect(await widget.find({ key: 'back' })).toBeUndefined()
  await widget.unmount()
})

test('the small form says each thing it could not count in place of the count', () => {
  // Covers: B193
  const known = { id: 's', known: true, topics: [], atStart: 'whole', offUnder: null, error: null }
  const topic = { name: 'Northwind', facts: 3, current: 0 }
  const quiet = { candidates: [], review: null, error: null, due: [] }
  const glance = (fields: Partial<SessionModel>): string[] =>
    glanceLines({ given: null, notes: 0, notice: null, snapshot: null, proposals: null, presses: {}, ...fields })

  expect(glance({})).toEqual(['m2b has not looked yet.'])
  expect(glance({ given: { ...known, error: 'm2b did not answer' } })).toEqual(['m2b could not look at this session.'])
  expect(glance({ given: { ...known, known: false } })).toEqual(['m2b holds no note of this session.'])
  expect(glance({ given: known, snapshot: quiet })).toEqual(['No topic was given.', 'Nothing waits for you.'])
  expect(glance({ given: { ...known, topics: [topic] }, snapshot: quiet })[0]).toBe('1 topic in this session')
  const one = { ...quiet, candidates: [{ id: 'c1', title: 'Remember? Dana prefers tea' }] }
  expect(glance({ given: known, snapshot: one })[1]).toBe('1 waits for you')
  const review = { id: 'r1', title: 'm2b: review', findings: [] }
  expect(glance({ given: known, snapshot: { ...one, review } })[1]).toBe('2 wait for you')
  const noStore = { waiting: [], answered: 0, error: 'the store is not downloaded' }
  expect(glance({ given: known, snapshot: one, proposals: noStore })[1]).toBe(
    'm2b could not look for proposals: the store is not downloaded',
  )
  const due = [
    { id: 'd1', title: 'Send the offer to Acme', overdue: false },
    { id: 'd2', title: 'Call the plumber', overdue: true },
    { id: 'd3', title: 'Return the ladder', overdue: true },
  ]
  expect(glance({ given: known, snapshot: { ...quiet, due } })[2]).toBe('1 due today, 2 overdue')
  expect(glance({ given: known, snapshot: { ...quiet, due: due.slice(1) } })[2]).toBe('2 overdue')
  expect(glance({ given: known, snapshot: { ...quiet, due: due.slice(0, 1) } })[2]).toBe('1 due today')
})

test('claude -p, no surface: nothing opens or stays open, and the m2b command answers as text', async ($, on) => {
  // Covers: B185
  const fake = busyFake()
  fake.paneWaits = NO_SURFACE
  const { clock, opened, openPanes } = await start($, on, fake)
  await clock.advance(60_000)
  // No surface draws a band, so nothing asks for a pane.
  expect(opened).toEqual([])

  const { text } = (await typed($, 'm2b')) as { text: string }

  expect(openPanes.has(PANE)).toBe(false)
  const lines = text.split('\n')
  expect(lines[0]).toBe(`the m2b pane cannot be shown here: ${NO_SURFACE}`)
  expect(lines).toContain('  Northwind: 3 facts, 1 current')
  expect(lines).toContain('  1 proposal from your sessions: /m2b-proposals')
  expect(lines).toContain('  due today: Send the offer to Acme')
})
