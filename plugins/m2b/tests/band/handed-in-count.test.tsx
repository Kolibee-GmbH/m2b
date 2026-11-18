import { expect, test } from 'claude-code/testing'

import { bandLine, belowPrompt } from '../../hooks/band'
import type { BandModel } from '../../hooks/band'
import { parseProposals } from '../../hooks/proposals'
import type { BandHealth } from '../../types'
import {
  BAND,
  CALM_ROW,
  CURATE_NOW,
  CURATE_NOW_LINE,
  FakeM2b,
  HOME,
  NOW,
  ONLY_WHILE_WAITING,
  SHOWN_WITHOUT_ENTRY,
  STATUS,
  STATUS_ELSEWHERE,
  bandPieces,
  buttonsAt,
  lookOf,
  partLines,
  rowSaying,
  shownBand,
  start,
  startView,
  viewButtons,
} from './harness'
import type { Files } from './harness'

const UNDO_MS = 5_000
const DANA = 'a1a1a1a1a1a1'
const ROW = 'row:curate'
const SHARED_ANSWER = `${HOME}/.local/state/m2b/band-answer.json`

const CURATED = '2 in inbox · curated 18:02'
const ONE_HANDED_IN = 'Waiting for the next curation run: 1 proposal handed in by a session.'
const TWO_HANDED_IN = 'Waiting for the next curation run: 2 proposals handed in by sessions.'
const HANDED_IN_AND_ANSWER = 'Waiting for the next curation run: 1 proposal handed in by a session, 1 answer of yours.'
const NOT_COUNTED = 'm2b could not look at what sessions handed in.'
const ELSEWHERE = 'Curation runs on tower-2.'

const DIM = { color: undefined, dimColor: true, wrap: 'wrap' }
const RUNNING = { ...STATUS, run: { state: 'running' } }

/** The calls that read the band's answer. */
function looks(fake: FakeM2b): string[][] {
  return fake.calls.filter(call => call[0] === 'band' && !call.includes('--session-only'))
}

test('while proposals a session handed in wait for a run, the part "m2b" of the overview says how many, stepped back, between the line about curation and curate now', async ($, on) => {
  // Covers: B241
  const fake = new FakeM2b()
  fake.handedInWaiting = 2
  const { clock } = await start($, on, fake)

  const ui = await startView($)

  expect(await partLines(ui, 'm2b')).toEqual([CURATED, TWO_HANDED_IN, CURATE_NOW_LINE])
  expect(await lookOf(ui, TWO_HANDED_IN)).toEqual(DIM)
  expect((await buttonsAt(ui, ROW)).map(button => button.key)).toEqual([CURATE_NOW])
  // They wait for the run, not for the person: the part of what waits has no row for them.
  expect(await partLines(ui, 'waits')).toEqual(['Nothing waits for you.'])

  // One is said in the singular, and once a run took them in the line is gone.
  fake.handedInWaiting = 1
  await clock.advance(60_000)
  expect(await partLines(ui, 'm2b')).toEqual([CURATED, ONE_HANDED_IN, CURATE_NOW_LINE])
  fake.handedInWaiting = 0
  await clock.advance(60_000)
  expect(await partLines(ui, 'm2b')).toEqual([CURATED, CURATE_NOW_LINE])
  await ui.unmount()
})

test('what sessions handed in and the answers that wait are one sentence above curate now, what was handed in first', async ($, on) => {
  // Covers: B241, B239
  const fake = new FakeM2b().proposal(DANA, 'Dana is head of IT at Northwind.')
  fake.handedInWaiting = 1
  // A proposal the person dropped: an answer waits, and drops alone start no run.
  const [dana] = fake.proposals ?? []
  if (dana !== undefined) {
    dana.answer = 'drop'
  }
  await start($, on, fake)

  const ui = await startView($)

  expect(await partLines(ui, 'm2b')).toEqual([CURATED, HANDED_IN_AND_ANSWER, CURATE_NOW_LINE])
  await ui.unmount()
})

test('on a machine that does not curate the line stands above the one that names the machine that does, and there is no button', async ($, on) => {
  // Covers: B241
  const fake = new FakeM2b()
  fake.status = STATUS_ELSEWHERE
  fake.handedInWaiting = 2
  await start($, on, fake)

  const ui = await startView($)

  expect(await partLines(ui, 'm2b')).toEqual([CURATED, TWO_HANDED_IN, ELSEWHERE])
  expect(await viewButtons(ui)).toEqual([])
  await ui.unmount()
})

test('while a run is under way nothing is said of what sessions handed in: the run takes it in', async ($, on) => {
  // Covers: B241
  const fake = new FakeM2b()
  fake.status = RUNNING
  fake.handedInWaiting = 2
  await start($, on, fake)

  const ui = await startView($)

  expect(await partLines(ui, 'm2b')).toEqual(['curating'])
  await ui.unmount()
})

test('a press on curate now takes the line away with the start of the run', async ($, on) => {
  // Covers: B241, B216
  const fake = new FakeM2b()
  fake.handedInWaiting = 2
  const { clock } = await start($, on, fake)
  const ui = await startView($)

  await ui.press({ key: CURATE_NOW })
  expect(await partLines(ui, 'm2b')).toEqual([CURATED, TWO_HANDED_IN, '[undo] starting a curation run'])
  await clock.advance(UNDO_MS)

  expect(await partLines(ui, 'm2b')).toEqual(['curating'])
  await ui.unmount()
})

test('a core from before the count leaves it out, and the part says nothing of what sessions handed in', async ($, on) => {
  // Covers: B241
  const fake = new FakeM2b()
  fake.handedInWaiting = null
  await start($, on, fake)

  const ui = await startView($)

  expect(await partLines(ui, 'm2b')).toEqual([CURATED, CURATE_NOW_LINE])
  await ui.unmount()
})

test('a count that is no count is could not look, never "none handed in"', () => {
  // Covers: B241
  const part = (handedIn: unknown): unknown => ({ proposals: [], answered: 0, handed_in: handedIn })

  expect(parseProposals(part(2))).toEqual({ waiting: [], answered: 0, handedIn: 2, error: null })
  expect(parseProposals({ proposals: [], answered: 0 })).toEqual({ waiting: [], answered: 0, handedIn: 0, error: null })
  // The core's word for a folder it could not list: the proposals are still listed.
  expect(parseProposals(part(null))).toEqual({ waiting: [], answered: 0, handedIn: null, error: null })
  for (const other of ['2', -1, 1.5, [2]]) {
    const parsed = parseProposals(part(other))
    expect(parsed.error).toBe('m2b answered something other than the proposals that wait')
    expect(parsed.handedIn).toBe(0)
  }
})

test('where m2b could not count what sessions handed in, the part says so in the color of trouble, also while a run is under way, and the proposals are still there to answer', async ($, on) => {
  // Covers: B241
  const fake = new FakeM2b().proposal(DANA, 'Dana is head of IT at Northwind.')
  fake.proposalsPart = {
    proposals: [{ id: DANA, kind: 'person', text: 'Dana is head of IT at Northwind.', quote: 'Dana runs IT', day: '2026-03-12', topic: null, due: null }],
    answered: 0,
    handed_in: null,
  }
  const { clock } = await start($, on, fake)

  const ui = await startView($)

  expect(await partLines(ui, 'm2b')).toEqual([CURATED, NOT_COUNTED, CURATE_NOW_LINE])
  expect(await lookOf(ui, NOT_COUNTED)).toEqual({ color: 'error', dimColor: undefined, wrap: 'wrap' })
  expect((await partLines(ui, 'waits'))?.[0]).toBe('1 proposal from your sessions')

  fake.status = RUNNING
  await clock.advance(60_000)
  expect(await partLines(ui, 'm2b')).toEqual(['curating', NOT_COUNTED])
  await ui.unmount()
})

test('a shared answer of a band from before the count is not taken for "none handed in": m2b is asked, and the part is drawn from its own answer', async ($, on) => {
  // Covers: B241
  const snapshot = { candidates: [], review: null, error: null, due: [], shows: SHOWN_WITHOUT_ENTRY }
  const health = { curation: CURATED, troubles: [], curates: true, isCurating: false }
  const before = { snapshot, status: null, version: '0.3.0', health, curatingMachine: 'tower-1', proposals: { waiting: [], answered: 0, error: null } }
  const files: Files = new Map([[SHARED_ANSWER, JSON.stringify({ writtenAtMs: NOW - 1_000, value: before })]])
  const fake = new FakeM2b()
  fake.handedInWaiting = 2
  await start($, on, fake, {}, files)

  const ui = await startView($)

  expect(looks(fake)).toEqual([['band', '--json']])
  expect(await partLines(ui, 'm2b')).toEqual([CURATED, TWO_HANDED_IN, CURATE_NOW_LINE])
  await ui.unmount()
})

test('a shared answer that carries the count is taken without asking m2b', async ($, on) => {
  // Covers: B241
  const snapshot = { candidates: [], review: null, error: null, due: [], shows: SHOWN_WITHOUT_ENTRY }
  const health = { curation: CURATED, troubles: [], curates: true, isCurating: false }
  const shared = { snapshot, status: null, version: '0.3.0', health, curatingMachine: 'tower-1', proposals: { waiting: [], answered: 0, handedIn: 1, error: null } }
  const files: Files = new Map([[SHARED_ANSWER, JSON.stringify({ writtenAtMs: NOW - 1_000, value: shared })]])
  const fake = new FakeM2b()
  await start($, on, fake, {}, files)

  const ui = await startView($)

  expect(looks(fake)).toEqual([])
  expect(await partLines(ui, 'm2b')).toEqual([CURATED, ONE_HANDED_IN, CURATE_NOW_LINE])
  await ui.unmount()
})

const CURATES: BandHealth = { curation: CURATED, troubles: [], curates: true, isCurating: false }
const ONE_WAITS = { candidates: [{ id: 'c1', title: 'Remember? Dana prefers tea' }], review: null, error: null }
const NOTHING_WAITS = { candidates: [], review: null, error: null }

function handedIn(count: number | null, fields: Partial<BandModel> = {}): BandModel {
  return {
    snapshot: NOTHING_WAITS,
    proposals: { waiting: [], answered: 0, handedIn: count, error: null },
    notice: null,
    topics: 0,
    health: CURATES,
    ...fields,
  }
}

test('while proposals sessions handed in wait for a run, the band counts them in its row, at full strength on the machine that curates, and the count is gone once a run took them in', async ($, on) => {
  // Covers: B243
  const fake = new FakeM2b()
  fake.handedInWaiting = 2
  const { clock } = await start($, on, fake)

  const band = await $.ui.mount({ ...BAND, surface: 'terminal' })

  expect(await shownBand(band)).toEqual(rowSaying('2 handed in'))
  expect(await bandPieces(band)).toEqual([{ text: '2 handed in', color: undefined, dimColor: undefined }])
  fake.handedInWaiting = 1
  await clock.advance(60_000)
  expect(await shownBand(band)).toEqual(rowSaying('1 handed in'))
  fake.handedInWaiting = 0
  await clock.advance(60_000)
  expect(await shownBand(band)).toEqual(CALM_ROW)
  await band.unmount()
})

test('on a machine that does not curate the band counts what sessions handed in stepped back: no run can be started there', async ($, on) => {
  // Covers: B243
  const fake = new FakeM2b()
  fake.status = STATUS_ELSEWHERE
  fake.handedInWaiting = 1
  await start($, on, fake)

  const band = await $.ui.mount({ ...BAND, surface: 'terminal' })

  expect(await shownBand(band)).toEqual(rowSaying('1 handed in'))
  expect(await bandPieces(band)).toEqual([{ text: '1 handed in', color: undefined, dimColor: true }])
  await band.unmount()
})

test('while a run is under way the band says nothing of what sessions handed in, as the overview does', async ($, on) => {
  // Covers: B243
  const fake = new FakeM2b()
  fake.status = RUNNING
  fake.handedInWaiting = 2
  await start($, on, fake)

  const band = await $.ui.mount({ ...BAND, surface: 'terminal' })

  expect(await shownBand(band)).toEqual(CALM_ROW)
  await band.unmount()
})

test('what sessions handed in draws a band that is there only while something waits', async ($, on) => {
  // Covers: B243, B213
  const fake = new FakeM2b()
  fake.shows = ONLY_WHILE_WAITING
  const { clock } = await start($, on, fake)
  const band = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await shownBand(band)).toBeNull()

  fake.handedInWaiting = 1
  await clock.advance(60_000)

  expect(await shownBand(band)).toEqual(rowSaying('1 handed in'))
  await band.unmount()
})

test('in the row what sessions handed in stands after what waits for the person and before the tasks due and the topics', () => {
  // Covers: B243
  const due = [
    { id: 'd1', title: 'Return the ladder to Sam', overdue: true },
    { id: 'd2', title: 'Call Dana', overdue: false },
  ]
  const snapshot = { ...ONE_WAITS, due, shows: { place: 'above' as const, dueTasks: 'count' as const, topics: true } }

  expect(bandLine(handedIn(2, { snapshot, topics: 1 }))?.parts).toEqual([
    { text: '1 waits for you', tone: 'waits' },
    { text: '2 handed in', tone: 'plain' },
    { text: '1 overdue', tone: 'overdue' },
    { text: '1 due today', tone: 'dueToday' },
    { text: '1 topic', tone: 'quiet' },
  ])
  // Where the row below the prompt has no room for every count, the last go first: what was handed in stays beside what waits.
  const line = bandLine(handedIn(2, { snapshot: { ...snapshot, shows: { ...snapshot.shows, place: 'below' } }, topics: 1 }))
  expect(line).not.toBeNull()
  const narrow = line === null ? null : belowPrompt(line, '? for shortcuts', 100, 'm2b-pane')
  expect(narrow).toEqual({
    kind: 'row',
    line: { ...line, parts: [{ text: '1 waits for you', tone: 'waits' }, { text: '2 handed in', tone: 'plain' }, { text: '…', tone: 'quiet' }] },
  })
})

test('the row counts nothing handed in where none waits, where m2b could not count them, and before m2b said how it stands it counts them stepped back', () => {
  // Covers: B243
  const calm = { parts: [], isNamed: true, isCalm: true, listed: [], more: 0 }

  expect(bandLine(handedIn(0))).toEqual(calm)
  // Could not count is said in the pane, in the color of trouble: the row does not turn it into a number.
  expect(bandLine(handedIn(null))).toEqual(calm)
  expect(bandLine(handedIn(1, { health: null }))?.parts).toEqual([{ text: '1 handed in', tone: 'quiet' }])
  expect(bandLine(handedIn(1, { health: { ...CURATES, curates: null } }))?.parts).toEqual([{ text: '1 handed in', tone: 'quiet' }])
  expect(bandLine(handedIn(1, { health: { ...CURATES, isCurating: true } }))).toEqual(calm)
})
