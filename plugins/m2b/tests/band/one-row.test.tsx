import { expect, test } from 'claude-code/testing'
import type { CommandRunResult } from 'claude-code'
import type { Engine } from 'claude-code/testing'

import { bandLine, topicsGiven } from '../../hooks/band'
import type { BandModel } from '../../hooks/band'
import { tabKey } from '../../hooks/pane-tabs'
import { glanceLines } from '../../hooks/session-view'
import type { SessionModel } from '../../hooks/session-view'
import {
  BAND,
  ENGINES_OWN_DRAWING,
  FakeM2b,
  OPEN,
  bandPieces,
  everyText,
  lookOf,
  pane,
  partLines,
  pressTab,
  rowSaying,
  sentenceOfM2b,
  shownBand,
  shownParts,
  shownTab,
  shownTabs,
  start,
  texts,
} from './harness'

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
const OLDER_M2B = 'This session runs m2b 0.3.0 and m2b 0.4.0 is installed: run /reload-plugins.'
/** What the band of `busyFake` says on a machine without an entry for the band: what waits, and the tasks due as counts. */
const COUNTS = '4 wait for you  1 overdue  1 due today'
const ROW = rowSaying(COUNTS)
const WITH_TOPICS = rowSaying(`${COUNTS}  2 topics`)

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

/** The pane's drawing in a seat, and the moment after it. */
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

/** Four things that wait, one of each kind, and five tasks due as the core names them, earliest first: three overdue, two due today. */
function fullFake(): FakeM2b {
  const fake = new FakeM2b()
  fake.candidate('c1', 'Remember? Dana prefers tea')
  fake.question('q1', 'Still current? Planning the trip to Porto')
  fake.review('r1', ['lint: broken link in a.md'])
  fake.proposal('a1a1a1a1a1a1', 'Dana is head of IT at Northwind.', 'Dana runs IT at Northwind')
  fake.dueTasks = [
    { id: 'd1', title: 'Return the ladder to Sam', due: '2026-03-02', overdue: true },
    { id: 'd2', title: 'Call the plumber', due: '2026-03-10', overdue: true },
    { id: 'd3', title: 'Pay the invoice of Northwind', due: '2026-03-13', overdue: true },
    { id: 'd4', title: 'Send the offer to Acme', due: '2026-03-14', overdue: false },
    { id: 'd5', title: 'Water the plants', due: '2026-03-14', overdue: false },
  ]
  return fake
}

/** The keys of the parts the pane's view is drawn as: the overview's begin with what waits and what is due today. */
async function partKeys(ui: Parameters<typeof shownParts>[0]): Promise<string[]> {
  return (await shownParts(ui)).map(part => part.key)
}

const OVERVIEW_PARTS = ['waits', 'today', 'session', 'm2b']
const REVIEW_PARTS = ['run', 'waits']

function model(fields: Partial<BandModel> = {}): BandModel {
  return { snapshot: null, proposals: null, notice: null, topics: 0, ...fields }
}

test('with nothing waiting, no task due and nothing wrong the band draws nothing of its own, whatever the session was given', async ($, on) => {
  // Covers: B191
  const fake = new FakeM2b()
  fake.given = { topics: [{ name: 'Northwind', facts: 3, current: 0 }], atStart: 'whole', offUnder: null }
  const { clock } = await start($, on, fake)

  const band = await drawBand($, clock, MAIN_SCREEN)

  expect(await everyText(band)).toEqual([ENGINES_OWN_DRAWING])
  expect(await band.findAll({ type: 'Button' })).toEqual([])
  await band.unmount()
})

test('while a survey is up the band draws nothing of its own', async ($, on) => {
  await start($, on, busyFake())

  const band = await $.ui.mount({ ...BAND, props: { ...BAND.props, hasSurvey: true }, surface: 'terminal' })

  expect(await everyText(band)).toEqual([ENGINES_OWN_DRAWING])
  await band.unmount()
})

test('four things wait and five tasks are due, with count: one row of m2b, what waits, the overdue and the due today, and open', async ($, on) => {
  // Covers: B191, B102
  const { clock } = await start($, on, fullFake())

  const band = await drawBand($, clock, MAIN_SCREEN)

  expect(await shownBand(band)).toEqual(rowSaying('4 wait for you  3 overdue  2 due today'))
  expect(await bandPieces(band)).toEqual([
    { text: '4 wait for you', color: 'warning', dimColor: undefined },
    { text: '  3 overdue', color: 'error', dimColor: undefined },
    { text: '  2 due today', color: 'warning', dimColor: undefined },
  ])
  const [name] = await band.findAll({ type: 'Text', text: 'm2b' })
  expect(name?.text).toBe('m2b')
  expect(name?.props).toEqual({ color: 'remember', weight: 'bold' })
  await band.unmount()
})

test('four things wait and five tasks are due, with list: the row counts what waits, and three tasks stand below it with "and 2 more"', async ($, on) => {
  // Covers: B191, B102
  const fake = fullFake()
  fake.shows = { dueTasks: 'list', topics: false }
  const { clock } = await start($, on, fake)

  const band = await drawBand($, clock, MAIN_SCREEN)

  expect(await shownBand(band)).toEqual({
    isNamed: true,
    says: '4 wait for you',
    below: [
      'due today Send the offer to Acme',
      'due today Water the plants',
      'overdue Pay the invoice of Northwind',
      'and 2 more',
    ],
    buttons: [OPEN],
  })
  // A task is read, not answered: none of them has a button or a key of one.
  expect(await band.find({ key: 'task:d4' })).toBeDefined()
  expect(await band.find({ key: 'task:d2' })).toBeUndefined()
  await band.unmount()
})

test('four things wait and five tasks are due, with off: the row counts what waits and says nothing of the tasks', async ($, on) => {
  // Covers: B191, B102
  const fake = fullFake()
  fake.shows = { dueTasks: 'off', topics: false }
  const { clock } = await start($, on, fake)

  const band = await drawBand($, clock, MAIN_SCREEN)

  expect(await shownBand(band)).toEqual(rowSaying('4 wait for you'))
  await band.unmount()
})

const ONE_THING: [string, (fake: FakeM2b) => FakeM2b][] = [
  ['a candidate', fake => fake.candidate('c1', 'Remember? Dana prefers tea')],
  ['a question', fake => fake.question('q1', 'Still current? Planning the trip to Porto')],
  ['a proposal', fake => fake.proposal('a1a1a1a1a1a1', 'Dana is head of IT at Northwind.')],
  ['the review', fake => fake.review('r1', ['lint: broken link in a.md', 'lint: broken link in b.md'])],
]

for (const [what, waits] of ONE_THING) {
  test(`${what} alone is one thing, and the row reads "1 waits for you"`, async ($, on) => {
    // Covers: B191
    const { clock } = await start($, on, waits(new FakeM2b()))

    const band = await drawBand($, clock, MAIN_SCREEN)

    expect(await shownBand(band)).toEqual(rowSaying('1 waits for you'))
    await band.unmount()
  })
}

test('the row counts the topics only with the setting on and for a session that was given some', async ($, on) => {
  // Covers: B192
  const fake = busyFake()
  const { clock } = await start($, on, fake)
  const band = await drawBand($, clock, MAIN_SCREEN)
  // Off, which a machine without an entry is.
  expect(await shownBand(band)).toEqual(ROW)

  fake.shows = { dueTasks: 'count', topics: true }
  await clock.advance(60_000)
  expect(await shownBand(band)).toEqual(WITH_TOPICS)
  // After what waits and the tasks due, and quiet: it needs no answer.
  expect((await bandPieces(band)).at(-1)).toEqual({ text: '  2 topics', color: undefined, dimColor: true })

  fake.shows = { dueTasks: 'off', topics: true }
  await clock.advance(60_000)
  expect(await shownBand(band)).toEqual(rowSaying('4 wait for you  2 topics'))

  // A core before the setting names none: off.
  fake.shows = null
  await clock.advance(60_000)
  expect(await shownBand(band)).toEqual(ROW)
  await band.unmount()
})

test('with the setting on, a session given no topic gets no count, and topics alone draw the band', async ($, on) => {
  // Covers: B192
  const fake = new FakeM2b()
  fake.shows = { dueTasks: 'count', topics: true }
  fake.given = { topics: [], atStart: 'whole', offUnder: null }
  on('prompt.submit', (_, e) => ({ text: e.text }))
  const { clock } = await start($, on, fake)
  const band = await drawBand($, clock, MAIN_SCREEN)
  expect(await everyText(band)).toEqual([ENGINES_OWN_DRAWING])

  // A topic that comes in with a prompt is counted once m2b has looked again.
  fake.given = { topics: [{ name: 'Northwind', facts: 3, current: 0 }], atStart: 'whole', offUnder: null }
  await $.prompt.submit({ text: 'what did Northwind order?', origin: { kind: 'composer' }, wait: false })
  await clock.advance(3_000)

  expect(await shownBand(band)).toEqual(rowSaying('1 topic'))
  await band.unmount()
})

test('fullscreen, wide: the band is the same row before the pane is docked and beside it, and every row to answer stands in the pane', async ($, on) => {
  // Covers: B191
  const { clock, opened } = await start($, on, busyFake())
  const band = await drawBand($, clock)
  expect(opened).toEqual([BY_ITSELF])
  expect(await shownBand(band)).toEqual(ROW)

  const beside = await drawPane($, clock)

  expect(await shownBand(band)).toEqual(ROW)
  // Nothing stands only in the band: every row and its buttons are in the pane.
  expect(await partLines(beside, 'waits')).toEqual([
    '1 proposal from your sessions',
    'in the tab Proposals',
    'Remember? Dana prefers tea',
    '[keep] [drop]',
    'Still current? Planning the trip to Porto',
    '[keep] [drop]',
    'Review of the last curation run',
    '[ok]',
    'The whole review is in the tab Review.',
  ])
  expect(await partLines(beside, 'today')).toEqual(['due today Send the offer to Acme', 'overdue Call the plumber'])
  expect(await partLines(beside, 'session')).toContain('[Northwind] 3 facts, 1 current')
  for (const key of ['keep:c1', 'drop:c1', 'keep:q1', 'drop:q1', 'ok:r1', tabKey('proposals', 'overview'), tabKey('review', 'overview')]) {
    expect(await beside.find({ key })).toBeDefined()
    expect(await band.find({ key })).toBeUndefined()
  }
  await beside.unmount()
  await band.unmount()
})

test('with nothing to answer, a task due is all the row counts, beside the docked pane as without it', async ($, on) => {
  // Covers: B191
  const fake = new FakeM2b()
  fake.given = { topics: [{ name: 'Northwind', facts: 3, current: 0 }], atStart: 'whole', offUnder: null }
  fake.dueTasks = [{ id: 'd1', title: 'Send the offer to Acme', due: '2026-03-14', overdue: false }]
  const { clock } = await start($, on, fake)
  const band = await drawBand($, clock)
  expect(await shownBand(band)).toEqual(rowSaying('1 due today'))

  const beside = await drawPane($, clock)

  expect(await shownBand(band)).toEqual(rowSaying('1 due today'))
  expect(await partLines(beside, 'today')).toEqual(['due today Send the offer to Acme'])
  await beside.unmount()
  await band.unmount()
})

for (const columns of [24, 40]) {
  test(`docked with a body of ${columns} columns: the same row in the band, names with counts in the pane`, async ($, on) => {
    // Covers: B191
    const { clock } = await start($, on, busyFake())
    const band = await drawBand($, clock)

    const beside = await drawPane($, clock, 'dock', columns)

    expect(await shownBand(band)).toEqual(ROW)
    const inPane = await partLines(beside, 'session')
    // A topic's lines come on a press of its name, never into a pane this narrow by themselves.
    expect(inPane).toContain('[Northwind] 3 facts, 1 current')
    expect(inPane).toContain('[Acme Ltd] 1 fact')
    expect(await beside.find({ key: 'topic:0' })).toBeDefined()
    await beside.unmount()
    await band.unmount()
  })
}

test('a task list that cannot be read is the row, as one sentence in the color of trouble and without m2b before it, beside the docked pane too', async ($, on) => {
  // Covers: B191
  const fake = busyFake()
  fake.failure = 'the task list did not answer'
  const { clock } = await start($, on, fake)
  const band = await drawBand($, clock)
  const sentence = sentenceOfM2b('m2b could not read the tasks: the task list did not answer')
  expect(await shownBand(band)).toEqual(sentence)

  const beside = await drawPane($, clock)

  expect(await shownBand(band)).toEqual(sentence)
  expect(await bandPieces(band)).toEqual([{ text: sentence.says, color: 'error', dimColor: undefined }])
  expect(await band.findAll({ type: 'Text', text: /^m2b$/ })).toEqual([])
  await beside.unmount()
  await band.unmount()
})

test('proposals that could not be looked at are the row as one sentence, in place of the counts of what the task list holds', async ($, on) => {
  // Covers: B191
  const fake = busyFake()
  fake.proposalsError = 'the store at /home/alex/Notes cannot be read'
  const { clock } = await start($, on, fake)

  const band = await drawBand($, clock, MAIN_SCREEN)

  const sentence = sentenceOfM2b('m2b could not look for proposals: the store at /home/alex/Notes cannot be read')
  expect(await shownBand(band)).toEqual(sentence)
  expect(await bandPieces(band)).toEqual([{ text: sentence.says, color: 'error', dimColor: undefined }])
  await band.unmount()
})

test('that this session runs an older m2b is said in the pane, in the part about m2b, and the band keeps counting', async ($, on) => {
  // Covers: B96, B191
  const fake = busyFake()
  fake.version = '0.4.0'
  const { clock } = await start($, on, fake)
  const band = await drawBand($, clock)
  expect(await shownBand(band)).toEqual(ROW)

  const beside = await drawPane($, clock)

  expect(await shownBand(band)).toEqual(ROW)
  expect((await everyText(band)).join('\n')).not.toContain('/reload-plugins')
  // Above the line about curation, and in the color of what waits: it asks for a command.
  expect(await partLines(beside, 'm2b')).toEqual([OLDER_M2B, '2 in inbox · curated 18:02'])
  expect(await lookOf(beside, OLDER_M2B)).toEqual({ color: 'warning', dimColor: undefined, wrap: 'wrap' })
  await beside.unmount()
  await band.unmount()
})

test('what a press in the pane could not write is said in the pane where it was pressed, until the next prompt, and the band keeps counting', async ($, on) => {
  // Covers: B207, B191
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

  const refused = 'Already settled in another session, nothing written: Remember? Dana prefers tea'
  const counts = rowSaying('3 wait for you  1 overdue  1 due today')
  expect(fake.writes()).toEqual([])
  expect(await shownBand(band)).toEqual(counts)
  expect((await partLines(beside, 'waits'))?.[0]).toBe(refused)
  expect(await lookOf(beside, refused)).toEqual({ color: 'error', dimColor: undefined, wrap: 'wrap' })
  await $.prompt.submit({ text: 'go on', context: [], wait: false, origin: { kind: 'composer' } })
  expect(await shownBand(band)).toEqual(counts)
  expect(await texts(beside)).not.toContain(refused)
  await beside.unmount()
  await band.unmount()
})

for (const view of ['overview', 'review'] as const) {
  for (const [next, nextPress, written] of [
    ['keep on another row', 'keep:q1', ['tasks', 'complete', '--', 'q1']],
    ['ok on the review', 'ok:r1', ['tasks', 'complete', '--', 'r1']],
  ] as const) {
    test(`in the ${view === 'overview' ? 'overview' : 'view of the review'}, what a press could not write goes with ${next}, before that press is written`, async ($, on) => {
      // Covers: B207
      const fake = busyFake()
      const { clock } = await start($, on, fake)
      const band = await drawBand($, clock)
      const beside = await drawPane($, clock)
      if (view === 'review') {
        await pressTab(beside, 'review')
      }
      fake.beforeCandidateList = () => {
        const [task] = fake.tasks
        if (task !== undefined) {
          task.completed = true
        }
      }
      await beside.press({ key: 'drop:c1' })
      await clock.advance(UNDO_MS)
      const refused = 'Already settled in another session, nothing written: Remember? Dana prefers tea'
      expect((await partLines(beside, 'waits'))?.[0]).toBe(refused)
      expect(fake.writes()).toEqual([])

      await beside.press({ key: nextPress })

      // Gone at the press, while its undo still waits and nothing is written.
      expect(await texts(beside)).not.toContain(refused)
      expect(await beside.find({ key: `undo:${nextPress.slice(nextPress.indexOf(':') + 1)}` })).toBeDefined()
      await clock.advance(UNDO_MS - 1)
      expect(fake.writes()).toEqual([])
      expect(await texts(beside)).not.toContain(refused)
      await clock.advance(1)
      expect(fake.writes()).toEqual([[...written]])
      expect(await texts(beside)).not.toContain(refused)
      await beside.unmount()
      await band.unmount()
    })
  }
}

test('what a press could not write stays while another press, made before it was said, is written: only a press after it takes it away', async ($, on) => {
  // Covers: B207
  const fake = busyFake()
  const { clock } = await start($, on, fake)
  const beside = await drawPane($, clock)
  fake.beforeCandidateList = () => {
    const [task] = fake.tasks
    if (task !== undefined) {
      task.completed = true
    }
  }
  // Two presses whose five seconds overlap.
  await beside.press({ key: 'drop:c1' })
  await clock.advance(1_000)
  await beside.press({ key: 'keep:q1' })
  await clock.advance(UNDO_MS - 1_000)
  const refused = 'Already settled in another session, nothing written: Remember? Dana prefers tea'
  expect((await partLines(beside, 'waits'))?.[0]).toBe(refused)

  await clock.advance(1_000)

  expect(fake.writes()).toEqual([['tasks', 'complete', '--', 'q1']])
  expect((await partLines(beside, 'waits'))?.[0]).toBe(refused)
  await beside.unmount()
})

test('the row is a sentence where there is one: why open showed no pane, then the task list m2b could not read, then the store; else the counts', () => {
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
  const counts = (text: string) => ({ parts: [{ text, tone: 'waits' }], isNamed: true, listed: [], more: 0 })
  const sentence = (text: string, tone: string, isNamed: boolean) => ({ parts: [{ text, tone }], isNamed, listed: [], more: 0 })

  expect(bandLine(model())).toBeNull()
  expect(bandLine(model({ snapshot: { candidates: [], review: null, error: null } }))).toBeNull()
  // A session's topics alone are nothing to draw where the machine does not show them.
  expect(bandLine(model({ snapshot: { candidates: [], review: null, error: null }, topics: 0 }))).toBeNull()
  expect(bandLine(model(waits))).toEqual(counts('2 wait for you'))
  expect(bandLine(model(unread))).toEqual(sentence('m2b could not read the tasks: no answer', 'trouble', false))
  expect(bandLine(model({ ...waits, ...noStore }))).toEqual(
    sentence('m2b could not look for proposals: the store is not downloaded', 'trouble', false),
  )
  // Beside a task list that could not be read, the store is most often the same reason.
  expect(bandLine(model({ ...unread, ...noStore }))?.parts).toEqual([{ text: 'm2b could not read the tasks: no answer', tone: 'trouble' }])
  const notShown = 'the m2b pane cannot be shown here: no surface attached places panes; /m2b-pane answers with the lines'
  expect(bandLine(model({ ...unread, ...noStore, notice: notShown }))).toEqual(sentence(notShown, 'trouble', true))
  expect(bandLine(model({ ...waits, notice: notShown }))).toEqual(sentence(notShown, 'trouble', true))
  // One line, whatever a text from the store holds.
  expect(bandLine(model({ notice: 'first\nsecond\u001b[2J' }))?.parts).toEqual([{ text: 'first second', tone: 'trouble' }])
  // Only a sentence that begins with m2b's name as a word stands without it.
  expect(bandLine(model({ notice: 'm2b could not open its pane: the session is closing' }))?.isNamed).toBe(false)
  expect(bandLine(model({ notice: 'm2bis not m2b' }))?.isNamed).toBe(true)
})

test('the counts of the row: what waits, then the tasks due as the machine shows them, then the topics where it shows them', () => {
  // Covers: B191
  const due = [
    { id: 'd1', title: 'Return the ladder to Sam', overdue: true },
    { id: 'd2', title: 'Call the plumber', overdue: true },
    { id: 'd3', title: 'Send the offer to Acme', overdue: false },
    { id: 'd4', title: 'Water the plants', overdue: false },
    { id: 'd5', title: 'Call Dana', overdue: false },
  ]
  const snapshot = { candidates: [{ id: 'c1', title: 'Remember? Dana prefers tea' }], review: null, error: null, due }
  const showing = (dueTasks: 'off' | 'count' | 'list', topics: boolean) =>
    bandLine(model({ snapshot: { ...snapshot, shows: { dueTasks, topics } }, topics: 2 }))
  const waits = { text: '1 waits for you', tone: 'waits' }
  const topics = { text: '2 topics', tone: 'quiet' }

  expect(showing('count', true)).toEqual({
    parts: [waits, { text: '2 overdue', tone: 'overdue' }, { text: '3 due today', tone: 'dueToday' }, topics],
    isNamed: true,
    listed: [],
    more: 0,
  })
  // Today's first, then the overdue ones, the most recent first.
  expect(showing('list', true)).toEqual({ parts: [waits, topics], isNamed: true, listed: [due[2], due[3], due[4]], more: 2 })
  expect(showing('off', false)).toEqual({ parts: [waits], isNamed: true, listed: [], more: 0 })
  // An answer that names no settings is drawn as a machine without an entry shows it.
  expect(bandLine(model({ snapshot, topics: 2 }))).toEqual(showing('count', false))
  // Tasks to list, or topics, draw the band where nothing waits; with off and no topics there is nothing to draw.
  const idle = { candidates: [], review: null, error: null, due: due.slice(0, 1) }
  expect(bandLine(model({ snapshot: { ...idle, shows: { dueTasks: 'list', topics: false } } }))).toEqual({
    parts: [],
    isNamed: true,
    listed: [due[0]],
    more: 0,
  })
  expect(bandLine(model({ snapshot: { ...idle, shows: { dueTasks: 'off', topics: true } }, topics: 1 }))?.parts).toEqual([
    { text: '1 topic', tone: 'quiet' },
  ])
  expect(bandLine(model({ snapshot: { ...idle, shows: { dueTasks: 'off', topics: true } } }))).toBeNull()
})

test('while the docked pane is turned to another view, and after the tab Overview, the band is the same row', async ($, on) => {
  // Covers: B191
  const { clock } = await start($, on, busyFake())
  const band = await drawBand($, clock)
  const beside = await drawPane($, clock)
  expect(await shownBand(band)).toEqual(ROW)

  await pressTab(beside, 'review')

  expect(await partKeys(beside)).toEqual(REVIEW_PARTS)
  expect(await shownBand(band)).toEqual(ROW)

  await pressTab(beside, 'overview')
  await clock.advance(1)
  expect(await partKeys(beside)).toEqual(OVERVIEW_PARTS)
  expect(await shownBand(band)).toEqual(ROW)
  await beside.unmount()
  await band.unmount()
})

test('a second session start in the same module leaves the band the same row', async ($, on) => {
  // Covers: B191
  const { clock } = await start($, on, busyFake())
  const band = await drawBand($, clock)
  const beside = await drawPane($, clock)
  // The pane stays up and is not drawn again.
  await beside.unmount()

  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await clock.advance(1)

  expect(await shownBand(band)).toEqual(ROW)
  await band.unmount()
})

test('a close that a hook beneath held back leaves the band the same row', async ($, on) => {
  // Covers: B191
  const fake = busyFake()
  const { clock, openPanes } = await start($, on, fake)
  const band = await drawBand($, clock)
  const beside = await drawPane($, clock)

  // A command whose pane is not placed closes it; here something beneath keeps it open.
  fake.isCloseHeld = true
  fake.paneWaits = 'no surface attached places panes'
  await typed($, 'm2b-pane')
  fake.paneWaits = null
  expect(openPanes.has(PANE)).toBe(true)
  await band.redraw()

  expect(await shownBand(band)).toEqual(ROW)
  await beside.unmount()
  await band.unmount()
})

test('once the pane is closed, and when it is open again and not drawn yet, the band is the same row', async ($, on) => {
  // Covers: B191
  const fake = busyFake()
  const { clock, openPanes } = await start($, on, fake)
  const band = await drawBand($, clock)
  const beside = await drawPane($, clock)
  expect(await shownBand(band)).toEqual(ROW)

  // A command whose pane no surface can show closes the pane it opened.
  fake.paneWaits = 'no surface attached places panes'
  await typed($, 'm2b-review')
  fake.paneWaits = null
  await beside.unmount()
  expect(openPanes.has(PANE)).toBe(false)

  expect(await shownBand(band)).toEqual(ROW)

  await typed($, 'm2b-pane', { isFullscreen: true, columns: 160 })
  expect(openPanes.has(PANE)).toBe(true)
  expect(await shownBand(band)).toEqual(ROW)
  await band.unmount()
})

const PANE_NOT_IN_VIEW: [string, (fake: FakeM2b) => void][] = [
  [
    'Claude Code cannot say which panes are open',
    fake => {
      fake.panesFail = 'the session is closing'
    },
  ],
  [
    "another plugin's pane is the one shown",
    fake => {
      fake.isPaneBehind = true
    },
  ],
  [
    'Claude Code says the pane that was docked is not drawn now',
    fake => {
      fake.paneWaits = 'an unrequested pane is placed from 144 columns; the terminal has 100'
    },
  ],
]

for (const [situation, arrange] of PANE_NOT_IN_VIEW) {
  test(`when ${situation}, the band is the same row`, async ($, on) => {
    // Covers: B191
    const fake = busyFake()
    const { clock } = await start($, on, fake)
    const band = await drawBand($, clock)
    const beside = await drawPane($, clock)
    expect(await shownBand(band)).toEqual(ROW)

    arrange(fake)
    await band.redraw()

    expect(await shownBand(band)).toEqual(ROW)
    await beside.unmount()
    await band.unmount()
  })
}

test('the bands of two surfaces are the same row, whichever of them the pane is docked on', async ($, on) => {
  // Covers: B191
  const { clock } = await start($, on, busyFake())
  const onTerminal = await drawBand($, clock, MAIN_SCREEN)
  const onDesktop = await drawBand($, clock, WIDE, 'desktop')
  await typed($, 'm2b-pane')

  const beside = await drawPane($, clock, 'dock', 50, 'desktop')

  expect(await shownBand(onDesktop)).toEqual(ROW)
  expect(await shownBand(onTerminal)).toEqual(ROW)
  await beside.unmount()
  await onDesktop.unmount()
  await onTerminal.unmount()
})

test('not fullscreen: no pane opens by itself, and the band is the one row, with the count of topics where the machine shows it', async ($, on) => {
  // Covers: B192
  const fake = busyFake()
  fake.shows = { dueTasks: 'count', topics: true }
  const { clock, opened } = await start($, on, fake)

  const band = await drawBand($, clock, MAIN_SCREEN)

  expect(opened).toEqual([])
  expect(await shownBand(band)).toEqual(WITH_TOPICS)
  await band.unmount()
})

test('not fullscreen: open opens the pane as a dialog in the view it starts in, and the row stays as it is while the block shows', async ($, on) => {
  // Covers: B191
  const fake = busyFake()
  fake.shows = { dueTasks: 'count', topics: true }
  const { clock, opened } = await start($, on, fake)
  const band = await drawBand($, clock, MAIN_SCREEN)

  await band.press({ key: OPEN })
  expect(opened).toEqual([AS_A_DIALOG])
  const block = await drawPane($, clock, 'inline', 100)

  expect((await texts(block))[0]).toBe('Waits for you')
  expect(await partLines(block, 'session')).toContain('[Northwind] 3 facts, 1 current')
  expect(await shownBand(band)).toEqual(WITH_TOPICS)
  await block.unmount()
  await band.unmount()
})

test('fullscreen, narrow: the pane waits undrawn, the band is the same row, and open shows the pane to stay', async ($, on) => {
  // Covers: B191
  const fake = busyFake()
  fake.paneWaits = 'an unrequested pane is placed from 144 columns; the terminal has 120'
  const { clock, opened, openPanes } = await start($, on, fake)

  const band = await drawBand($, clock, NARROW)

  expect(opened).toEqual([BY_ITSELF])
  expect(openPanes.has(PANE)).toBe(true)
  expect(await shownBand(band)).toEqual(ROW)

  // A pane the person asks for is placed at any width.
  fake.paneWaits = null
  await band.press({ key: OPEN })

  expect(opened).toEqual([BY_ITSELF, TO_STAY])
  const beside = await drawPane($, clock)
  expect(await shownBand(band)).toEqual(ROW)
  await beside.unmount()
  await band.unmount()
})

test('fullscreen, too narrow to dock: open opens the pane as a dialog', async ($, on) => {
  // Covers: B191
  const fake = busyFake()
  fake.paneWaits = 'an unrequested pane is placed from 144 columns; the terminal has 100'
  const { clock, opened } = await start($, on, fake)
  const band = await drawBand($, clock, { columns: 109, rows: 50, isFullscreen: true })

  fake.paneWaits = null
  await band.press({ key: OPEN })

  // Below 110 columns the pane is a block above the prompt, which Escape closes.
  expect(opened).toEqual([BY_ITSELF, AS_A_DIALOG])
  await band.unmount()
})

test('the row names one topic as one, and open asks again what the session was given', async ($, on) => {
  // Covers: B192
  const fake = new FakeM2b()
  fake.shows = { dueTasks: 'count', topics: true }
  fake.given = { topics: [{ name: 'Northwind', facts: 3, current: 0 }], atStart: 'whole', offUnder: null }
  const { clock } = await start($, on, fake)
  const band = await drawBand($, clock, MAIN_SCREEN)
  expect(await shownBand(band)).toEqual(rowSaying('1 topic'))
  const looksBefore = fake.looks.length

  await band.press({ key: OPEN })
  await clock.advance(1)

  expect(fake.looks.length).toBe(looksBefore + 1)
  await band.unmount()
})

test('open turns a pane left on another view to the view it starts in', async ($, on) => {
  // Covers: B191
  const fake = busyFake()
  const { clock } = await start($, on, fake)
  const band = await drawBand($, clock)
  await typed($, 'm2b-review', { isFullscreen: true, columns: 160 })
  const beside = await drawPane($, clock)
  expect(await partKeys(beside)).toEqual(REVIEW_PARTS)

  await band.press({ key: OPEN })

  expect(await shownTab(beside)).toBe('overview')
  expect(await partKeys(beside)).toEqual(OVERVIEW_PARTS)
  await beside.unmount()
  await band.unmount()
})

const OPEN_IS_THE_ONE_BUTTON: [string, (fake: FakeM2b) => void][] = [
  ['the row counts', () => undefined],
  [
    'tasks are listed below the row',
    fake => {
      fake.shows = { dueTasks: 'list', topics: true }
    },
  ],
  [
    'the task list cannot be read',
    fake => {
      fake.failure = 'the task list did not answer'
    },
  ],
  [
    'the proposals could not be looked at',
    fake => {
      fake.proposalsError = 'the store at /home/alex/Notes cannot be read'
    },
  ],
  [
    'the session runs an older m2b',
    fake => {
      fake.version = '0.4.0'
    },
  ],
]

for (const [situation, arrange] of OPEN_IS_THE_ONE_BUTTON) {
  test(`where ${situation}, open is the band's one button, and it opens the pane in the view it starts in`, async ($, on) => {
    // Covers: B191
    const fake = busyFake()
    arrange(fake)
    const { clock, opened } = await start($, on, fake)
    const band = await drawBand($, clock, MAIN_SCREEN)
    const buttons = await band.findAll({ type: 'Button' })
    expect(buttons.map(button => [button.key, button.props['label']])).toEqual([[OPEN, 'open']])
    const writesBefore = fake.writes().length

    await band.press({ key: OPEN })

    expect(opened).toEqual([AS_A_DIALOG])
    const block = await drawPane($, clock, 'inline', 100)
    expect((await texts(block))[0]).toBe('Waits for you')
    expect(await shownTab(block)).toBe('overview')
    // The button shows the pane and writes nothing.
    expect(fake.writes()).toHaveLength(writesBefore)
    expect(fake.answers()).toEqual([])
    await block.unmount()
    await band.unmount()
  })
}

test('a session given no topic, not known, not looked at or not readable gets no count of topics', async ($, on) => {
  // Covers: B192
  const known = { id: 's', known: true, atStart: 'whole', offUnder: null, error: null }
  const topic = { name: 'Northwind', facts: 3, current: 0 }
  expect(topicsGiven({ ...known, topics: [topic, { ...topic, name: 'Acme Ltd' }] })).toBe(2)
  expect(topicsGiven({ ...known, topics: [] })).toBe(0)
  expect(topicsGiven(null)).toBe(0)
  expect(topicsGiven({ ...known, known: false, topics: [topic] })).toBe(0)
  expect(topicsGiven({ ...known, topics: [topic], error: 'm2b did not answer' })).toBe(0)

  const fake = new FakeM2b()
  fake.shows = { dueTasks: 'count', topics: true }
  fake.given = { topics: [], atStart: 'whole', offUnder: null }
  const { clock } = await start($, on, fake)
  const band = await drawBand($, clock, MAIN_SCREEN)
  expect(await everyText(band)).toEqual([ENGINES_OWN_DRAWING])

  // A session m2b holds no note of, and one whose look failed.
  fake.given = null
  await $.turn.complete({ answer: 'done', durationMs: 5, isAborted: false, turnId: 't1', reason: 'answer' })
  await clock.advance(1)
  expect(await everyText(band)).toEqual([ENGINES_OWN_DRAWING])
  fake.given = { topics: [topic], atStart: 'whole', offUnder: null }
  fake.lookFails = 'the machine state cannot be read'
  await $.turn.complete({ answer: 'done', durationMs: 5, isAborted: false, turnId: 't2', reason: 'answer' })
  await clock.advance(1)
  expect(await everyText(band)).toEqual([ENGINES_OWN_DRAWING])

  fake.lookFails = null
  await $.turn.complete({ answer: 'done', durationMs: 5, isAborted: false, turnId: 't3', reason: 'answer' })
  await clock.advance(1)
  expect(await shownBand(band)).toEqual(rowSaying('1 topic'))
  await band.unmount()
})

test('after the pane was closed by hand it does not open by itself, the band is the same row, and open is the word to open it again', async ($, on) => {
  // Covers: B191
  const fake = busyFake()
  fake.stored = { [CLOSED_BY_HAND]: true }
  const { clock, opened } = await start($, on, fake)
  const band = await drawBand($, clock)
  expect(opened).toEqual([])
  expect(await shownBand(band)).toEqual(ROW)

  await band.press({ key: OPEN })

  expect(opened).toEqual([TO_STAY])
  expect(fake.stored[CLOSED_BY_HAND]).toBeUndefined()
  await band.unmount()
})

test('where the pane cannot be shown, open says so in the band, where it was pressed, until the next prompt, and leaves no pane open', async ($, on) => {
  // Covers: B191, B207
  on('prompt.submit', (_, e) => ({ text: e.text }))
  const fake = busyFake()
  fake.paneWaits = 'no surface attached places panes'
  const { clock, openPanes } = await start($, on, fake)
  const band = await drawBand($, clock, MAIN_SCREEN)

  await band.press({ key: OPEN })

  expect(openPanes.has(PANE)).toBe(false)
  const notShown = 'the m2b pane cannot be shown here: no surface attached places panes; /m2b-pane answers with the lines'
  expect(await shownBand(band)).toEqual(rowSaying(notShown))
  expect(await bandPieces(band)).toEqual([{ text: notShown, color: 'error', dimColor: undefined }])

  await $.prompt.submit({ text: 'go on', origin: { kind: 'composer' }, wait: false })
  expect(await shownBand(band)).toEqual(ROW)
  await band.unmount()
})

test('an open that Claude Code refuses says so in the band', async ($, on) => {
  // Covers: B191
  const fake = busyFake()
  const { clock, opened } = await start($, on, fake)
  const band = await drawBand($, clock, MAIN_SCREEN)

  fake.openFails = 'another plugin holds the pane m2b'
  await band.press({ key: OPEN })

  expect(opened).toEqual([])
  const shown = await shownBand(band)
  expect(shown).toEqual(rowSaying(shown?.says ?? ''))
  expect(shown?.says).toStartWith('the m2b pane could not be opened:')
  expect(shown?.says).toEndWith('; /m2b-pane answers with the lines')
  await band.unmount()
})

test('a session that was not looked at under its id gets no count of topics', async ($, on) => {
  // Covers: B192
  const fake = busyFake()
  fake.shows = { dueTasks: 'count', topics: true }
  const { clock } = await start($, on, fake)
  const band = await drawBand($, clock, MAIN_SCREEN)
  expect(await shownBand(band)).toEqual(WITH_TOPICS)

  // After `/clear` the session goes on under another id, and what was kept is about the ended one.
  fake.sessionId = '7c9e6679-7425-40de-944b-e07fc1f90ae7'
  await band.redraw()

  expect(await shownBand(band)).toEqual(ROW)
  await band.unmount()
})

test('the desktop app: docked there, the band of the app is the same row', async ($, on) => {
  // Covers: B191
  const { clock } = await start($, on, busyFake())
  const band = await drawBand($, clock, WIDE, 'desktop')
  expect(await shownBand(band)).toEqual(ROW)
  await typed($, 'm2b-pane', { isFullscreen: true, columns: 160 })

  const beside = await drawPane($, clock, 'dock', 60, 'desktop')

  expect(await shownBand(band)).toEqual(ROW)
  await beside.unmount()
  await band.unmount()
})

test('the desktop app: as a widget the pane draws counts in the order of the overview, no tab and no button, and the band is the same row', async ($, on) => {
  // Covers: B193, B204
  const { clock } = await start($, on, busyFake())
  const band = await drawBand($, clock, WIDE, 'desktop')
  await typed($, 'm2b-pane', { isFullscreen: true, columns: 160 })

  const widget = await drawPane($, clock, 'widget', 30, 'desktop')

  expect(await texts(widget)).toEqual(['4 wait for you', '1 overdue, 1 due today', '2 topics in this session'])
  expect(await widget.findAll({ type: 'Button' })).toHaveLength(0)
  expect(await shownTabs(widget)).toEqual([])
  expect(await shownBand(band)).toEqual(ROW)
  await widget.unmount()
  await band.unmount()
})

test('a widget says what it could not look at, and draws the counts and no tab whatever view the pane was turned to', async ($, on) => {
  // Covers: B193, B204
  const fake = new FakeM2b()
  fake.given = null
  fake.failure = 'the task list did not answer'
  fake.review('r1', ['lint: broken link in a.md'])
  const { clock } = await start($, on, fake)
  await typed($, 'm2b-review', { isFullscreen: true, columns: 160 })

  const widget = await drawPane($, clock, 'widget', 30, 'desktop')

  expect(await texts(widget)).toEqual(['The task list could not be read.', 'm2b holds no note of this session.'])
  // Turned to the review, whose tab a pane beside the chat marks: the small form draws no tab and no button.
  expect(await shownTabs(widget)).toEqual([])
  expect(await widget.findAll({ type: 'Button' })).toHaveLength(0)
  await widget.unmount()
})

test('the small form is in the order of the overview: what waits, the tasks due, the topics; it says each thing it could not count in place of the count, and no count of none', () => {
  // Covers: B193
  const known = { id: 's', known: true, topics: [], atStart: 'whole', offUnder: null, error: null }
  const topic = { name: 'Northwind', facts: 3, current: 0 }
  const quiet = { candidates: [], review: null, error: null, due: [] }
  const glance = (fields: Partial<SessionModel>): string[] =>
    glanceLines({
      given: null,
      notes: 0,
      rowNotice: null,
      folderNotice: null,
      snapshot: null,
      proposals: null,
      presses: {},
      health: null,
      versionLine: null,
      ...fields,
    })
  const notLooked = 'm2b has not looked yet.'

  // Nothing read yet is said once, also where the session was not looked at either.
  expect(glance({})).toEqual([notLooked])
  expect(glance({ given: { ...known, error: 'm2b did not answer' } })).toEqual([notLooked, 'm2b could not look at this session.'])
  expect(glance({ given: { ...known, known: false } })).toEqual([notLooked, 'm2b holds no note of this session.'])
  expect(glance({ snapshot: quiet })).toEqual(['Nothing waits for you.', notLooked])
  // A session given no topic gets no line: a count of none is not said.
  expect(glance({ given: known, snapshot: quiet })).toEqual(['Nothing waits for you.'])
  expect(glance({ given: { ...known, topics: [topic] }, snapshot: quiet })).toEqual(['Nothing waits for you.', '1 topic in this session'])
  expect(glance({ given: { ...known, topics: [topic, topic] }, snapshot: quiet })[1]).toBe('2 topics in this session')
  const one = { ...quiet, candidates: [{ id: 'c1', title: 'Remember? Dana prefers tea' }] }
  expect(glance({ given: known, snapshot: one })).toEqual(['1 waits for you'])
  const review = { id: 'r1', title: 'm2b: review', findings: [] }
  expect(glance({ given: known, snapshot: { ...one, review } })).toEqual(['2 wait for you'])
  const noStore = { waiting: [], answered: 0, error: 'the store is not downloaded' }
  expect(glance({ given: known, snapshot: one, proposals: noStore })).toEqual([
    'm2b could not look for proposals: the store is not downloaded',
  ])
  const unread = { ...quiet, error: 'm2b could not read the tasks: no answer' }
  expect(glance({ given: known, snapshot: unread, proposals: noStore })).toEqual(['The task list could not be read.'])
  const due = [
    { id: 'd1', title: 'Send the offer to Acme', overdue: false },
    { id: 'd2', title: 'Call the plumber', overdue: true },
    { id: 'd3', title: 'Return the ladder', overdue: true },
  ]
  expect(glance({ given: { ...known, topics: [topic] }, snapshot: { ...one, due } })).toEqual([
    '1 waits for you',
    '2 overdue, 1 due today',
    '1 topic in this session',
  ])
  expect(glance({ given: known, snapshot: { ...quiet, due: due.slice(1) } })).toEqual(['Nothing waits for you.', '2 overdue'])
  expect(glance({ given: known, snapshot: { ...quiet, due: due.slice(0, 1) } })).toEqual(['Nothing waits for you.', '1 due today'])
})

test('claude -p, no surface: nothing opens or stays open, and /m2b-pane answers as text', async ($, on) => {
  // Covers: B185
  const fake = busyFake()
  fake.paneWaits = NO_SURFACE
  const { clock, opened, openPanes } = await start($, on, fake)
  await clock.advance(60_000)
  // No surface draws a band, so nothing asks for a pane.
  expect(opened).toEqual([])

  const { text } = (await typed($, 'm2b-pane')) as { text: string }

  expect(openPanes.has(PANE)).toBe(false)
  const lines = text.split('\n')
  expect(lines[0]).toBe(`the m2b pane cannot be shown here: ${NO_SURFACE}`)
  expect(lines).toContain('  Northwind: 3 facts, 1 current')
  expect(lines).toContain('  1 proposal from your sessions: /m2b-proposals')
  expect(lines).toContain('  due today: Send the offer to Acme')
})
