import { expect, test } from 'claude-code/testing'
import type { CommandRunResult } from 'claude-code'
import type { Engine } from 'claude-code/testing'

import { reviewLines, reviewPane, runOf, runWords } from '../../hooks/pane'
import type { ReviewModel } from '../../hooks/pane'
import type { RowActions } from '../../hooks/rows'
import type { BandReview, BandRun, BandSnapshot } from '../../types'
import {
  BAND,
  FakeM2b,
  HOME,
  NOW,
  SHOWN_WITHOUT_ENTRY,
  STATUS,
  insetsAt,
  linesAt,
  lookOf,
  pane,
  partLines,
  partLook,
  rowSaying,
  shownBand,
  shownParts,
  start,
  texts,
  viewButtons,
} from './harness'
import type { Files, TextLook } from './harness'

// The view of the review is tested twice over: as the mod draws it for a session, from what a
// fake m2b answers, and as `reviewPane` draws a model a test builds, through a render hook of the
// test's own, which reaches the runs and lists no answer of the fake gives.

type On = Parameters<typeof start>[1]

const PANE = 'm2b'
const OWN = 'view-alone'
const UNDO_MS = 5_000
const LAST_RUN = 'Last curation run'
const WAITS_FOR_YOU = 'Waits for you'
const NOTHING_WAITS = 'Nothing waits for you.'
const NOT_LOOKED = 'm2b has not looked yet.'
const NO_RUN_YET = 'No curation run yet.'
const RUN_NOT_READ = 'm2b could not read the last curation run.'
const REVIEW = 'Review of the last curation run'

/** How a line to be read, one that may be skipped and one in the color of trouble are drawn. */
const PLAIN: TextLook = { color: undefined, dimColor: undefined, wrap: 'wrap' }
const DIM: TextLook = { color: undefined, dimColor: true, wrap: 'wrap' }
const TROUBLE: TextLook = { color: 'error', dimColor: undefined, wrap: 'wrap' }
const LOOKS = { plain: PLAIN, quiet: DIM, trouble: TROUBLE } as const

/** A part as every other, and one in the color of what waits. */
const CALM = { borderStyle: 'round', paddingX: 1, borderColor: 'subtle', titleColor: 'remember', titleWeight: 'bold', countColor: undefined }
const WAITING = { ...CALM, borderColor: 'warning', titleColor: 'warning', countColor: 'warning' }

const NO_ACTIONS: RowActions = { press: async () => undefined, undo: async () => undefined }
const QUIET: BandSnapshot = { candidates: [], review: null, error: null }
/** A run of the day the tests are on, from 18:00 to 18:04 as the machine's clock says it. */
const TODAY: BandRun = { state: 'succeeded', startedAt: '2026-03-14T18:00:05+01:00', finishedAt: '2026-03-14T18:04:10+01:00', message: null }
const NO_RUN: BandRun = { state: 'none', startedAt: null, finishedAt: null, message: null }
const LONG_FINDING =
  'ingest: eleven captures were not filed because their photos are not downloaded; a copy of the run log is at /home/alex/.local/state/m2b/runs/20260314T170200Z.jsonl'

function typed($: Engine, command: string, args = ''): Promise<CommandRunResult> {
  return $.command.run({
    command,
    args,
    origin: { kind: 'composer' },
    presentation: { isFullscreen: false, columns: 100 },
  })
}

/** What the review's view draws from, with what a test sets: a list read with nothing in it, a run of today, nothing pressed. */
function reviewOf(parts: Partial<ReviewModel>): ReviewModel {
  return { snapshot: QUIET, run: TODAY, presses: {}, notice: null, nowMs: NOW, ...parts }
}

/**
 * A pane of the test's own that draws the review's view of a model. The hook is registered here,
 * so this is called before the test's first call on `$`.
 */
function ownReview($: Engine, on: On) {
  const held = { model: reviewOf({}) }
  on('ui.render', { component: 'Pane', requestId: OWN }, (engine, e) => reviewPane(engine, e, held.model, NO_ACTIONS, e.props.bodyColumns))
  return (model: ReviewModel) => {
    held.model = model
    return $.ui.mount({ ...pane(OWN), plugin: 'test', surface: 'terminal' })
  }
}

function reviewedFake(): FakeM2b {
  const fake = new FakeM2b()
  for (const n of [1, 2, 3, 4]) {
    fake.candidate(`c${n}`, `Remember? Dana prefers tea ${n}`)
  }
  fake.question('q1', 'Still current? Planning the trip to Porto')
  fake.review('r1', ['lint: broken link in a.md', 'lint: broken link in b.md', 'ingest: x', LONG_FINDING])
  fake.status = {
    ...STATUS,
    run: {
      state: 'succeeded',
      started_at: '2026-03-14T18:00:05+01:00',
      finished_at: '2026-03-14T18:02:10+01:00',
      last_succeeded_at: '2026-03-14T18:02:10+01:00',
    },
  }
  return fake
}

test('the review command opens the pane with every finding whole, every candidate and the run', async ($, on) => {
  // Covers: B101
  const fake = reviewedFake()
  const { opened } = await start($, on, fake)

  const answer = await typed($, 'm2b-review')

  expect(opened.map(one => one.id)).toContain(PANE)
  expect(answer.text).toBe('the last curation run is in the m2b pane')
  const ui = await $.ui.mount({ ...pane(PANE), surface: 'terminal' })
  expect(await shownParts(ui)).toEqual([
    {
      key: 'run',
      title: LAST_RUN,
      count: null,
      lines: ['succeeded, 18:00 to 18:02', 'lint: broken link in a.md', 'lint: broken link in b.md', 'ingest: x', LONG_FINDING],
    },
    {
      key: 'waits',
      title: WAITS_FOR_YOU,
      // The review, four candidates and the question: the number the band says.
      count: '6',
      lines: [
        REVIEW,
        '[ok]',
        ...[1, 2, 3, 4].flatMap(n => [`Remember? Dana prefers tea ${n}`, '[keep] [drop]']),
        'Still current? Planning the trip to Porto',
        '[keep] [drop]',
      ],
    },
  ])
  expect(await viewButtons(ui)).toHaveLength(11) // with ok on the review
  await ui.unmount()
})

test('drop in the view of the review waits for undo as in the start view, undo writes nothing, and the band counts what is left', async ($, on) => {
  // Covers: B101
  const fake = reviewedFake()
  const { clock } = await start($, on, fake)
  await typed($, 'm2b-review')
  const ui = await $.ui.mount({ ...pane(PANE), surface: 'terminal' })
  const band = await $.ui.mount({ ...BAND, surface: 'terminal' })
  // Four candidates, the question and the review.
  expect(await shownBand(band)).toEqual(rowSaying('6 wait for you'))

  await ui.press({ key: 'drop:c4' })
  expect(await linesAt(ui, 'row:c4')).toEqual(['Remember? Dana prefers tea 4', '[undo] dropping'])
  await ui.press({ key: 'undo:c4' })
  await ui.press({ key: 'keep:q1' })
  await clock.advance(UNDO_MS)

  expect(fake.writes()).toEqual([['tasks', 'complete', '--', 'q1']])
  expect(await texts(ui)).not.toContain('Still current? Planning the trip to Porto')
  expect(await texts(ui)).toContain('Remember? Dana prefers tea 4')
  expect(await shownBand(band)).toEqual(rowSaying('5 wait for you'))
  await band.unmount()
  await ui.unmount()
})

test('a run that has not happened yet, and one that failed, say so', async ($, on) => {
  // Covers: B101, B209
  const fake = new FakeM2b()
  fake.status = { ...STATUS, run: { state: 'none' } }
  const { clock } = await start($, on, fake)
  await typed($, 'm2b-review')
  const ui = await $.ui.mount({ ...pane(PANE), surface: 'terminal' })
  // Before any run, with nothing to answer, that is all the view says.
  expect(await shownParts(ui)).toEqual([{ key: 'run', title: LAST_RUN, count: null, lines: [NO_RUN_YET] }])
  expect(await lookOf(ui, NO_RUN_YET)).toEqual(DIM)

  fake.status = {
    ...STATUS,
    run: { state: 'failed', started_at: '2026-03-14T18:00:05+01:00', message: 'ingest \u001b[31mfailed\u001b[0m' },
  }
  await clock.advance(60_000)
  // A run of today is named by its time; that it failed, and what it said, in the color of trouble.
  expect(await shownParts(ui)).toEqual([
    { key: 'run', title: LAST_RUN, count: null, lines: ['failed, started 18:00', 'ingest failed'] },
    { key: 'waits', title: WAITS_FOR_YOU, count: null, lines: [NOTHING_WAITS] },
  ])
  expect(await lookOf(ui, 'failed, started 18:00')).toEqual(TROUBLE)
  expect(await lookOf(ui, 'ingest failed')).toEqual(TROUBLE)
  expect(await lookOf(ui, NOTHING_WAITS)).toEqual(DIM)
  await ui.unmount()
})

test('the search command shows each hit with its file and line, without the model', async ($, on) => {
  // Covers: B101
  const fake = new FakeM2b()
  fake.searchHits = [
    { path: 'korpus/2026/03/20260312-sam.md', line: 4, text: 'Sam brings the \u001b[1mplywood\u001b[0m on Saturday' },
    { path: 'memory/people/sam.md', line: 2, text: 'Sam: neighbour, has a van' },
  ]
  fake.searchEvicted = ['korpus/2026/01/20260105-old.md']
  await start($, on, fake)

  const answer = await typed($, 'm2b-search', '-plywood "Sam"')

  expect(fake.calls.filter(call => call[0] === 'search')).toEqual([['search', '--json', '--', '-plywood "Sam"']])
  expect(answer.text).toBe('2 hits for -plywood "Sam" in the m2b pane')
  const ui = await $.ui.mount({ ...pane(PANE), surface: 'terminal' })
  expect(await shownParts(ui)).toEqual([
    {
      key: 'search',
      title: '2 hits for -plywood "Sam"',
      count: null,
      lines: [
        'korpus/2026/03/20260312-sam.md:4',
        'Sam brings the plywood on Saturday',
        'memory/people/sam.md:2',
        'Sam: neighbour, has a van',
        '1 file not downloaded, not searched',
      ],
    },
  ])
  await ui.unmount()
})

test('--word in front of the text searches whole words only', async ($, on) => {
  // Covers: B101
  const fake = new FakeM2b()
  fake.searchHits = [{ path: 'inbox/20261111-velo.md', line: 5, text: 'I service the Velo on Friday.' }]
  const { commands } = await start($, on, fake)

  const answer = await typed($, 'm2b-search', '--word  Velo ')

  expect(fake.calls.filter(call => call[0] === 'search')).toEqual([['search', '--json', '--word', '--', 'Velo']])
  expect(answer.text).toBe('1 hit for Velo, whole words only, in the m2b pane')
  expect(commands.find(command => command.name === 'm2b-search')).toMatchObject({ argumentHint: '[--word] <text>' })
})

test('--word without a text searches nothing, and a dash elsewhere stays part of the text', async ($, on) => {
  // Covers: B101
  const fake = new FakeM2b()
  await start($, on, fake)
  expect((await typed($, 'm2b-search', '--word')).text).toBe(
    'nothing searched: write what to look for after the command, as in /m2b-search plywood',
  )
  await typed($, 'm2b-search', '--wordy plywood')
  expect(fake.calls.filter(call => call[0] === 'search')).toEqual([['search', '--json', '--', '--wordy plywood']])
})

test('a search without hits, without text, or that fails is one clear line', async ($, on) => {
  // Covers: B101
  const fake = new FakeM2b()
  await start($, on, fake)

  expect((await typed($, 'm2b-search', '  ')).text).toBe(
    'nothing searched: write what to look for after the command, as in /m2b-search plywood',
  )
  expect(fake.calls.filter(call => call[0] === 'search')).toEqual([])

  expect((await typed($, 'm2b-search', 'plywood')).text).toBe('no hits for plywood')

  fake.searchHits = [{ path: 'memory/people/sam.md', line: 2, text: 'plywood' }]
  fake.searchCut = true
  expect((await typed($, 'm2b-search', 'plywood')).text).toBe(
    'too many hits for plywood to show; search for something narrower',
  )
  fake.searchCut = false

  fake.searchFails = 'the store at /home/alex/Notes cannot be read'
  expect((await typed($, 'm2b-search', 'plywood')).text).toBe(
    'could not search: the store at /home/alex/Notes cannot be read',
  )
})

test('showing the review and a search, drawn and left alone, asks m2b only band and search', async ($, on) => {
  // Covers: B101
  const fake = reviewedFake()
  fake.searchHits = [{ path: 'memory/people/sam.md', line: 2, text: 'Sam: neighbour' }]
  const { clock } = await start($, on, fake)
  await typed($, 'm2b-review')
  const review = await $.ui.mount({ ...pane(PANE), surface: 'terminal' })
  await clock.advance(60_000)
  await review.unmount()
  await typed($, 'm2b-search', 'Sam')
  const search = await $.ui.mount({ ...pane(PANE), surface: 'terminal' })
  await clock.advance(60_000)
  await search.unmount()
  expect(fake.writes()).toEqual([])
  expect(fake.calls.map(call => call[0]).every(verb => verb === 'band' || verb === 'search')).toBe(true)
})

test('an answer an older session shared, without the run, leaves the run line as it was', async ($, on) => {
  // Covers: B101
  const files: Files = new Map()
  const fake = reviewedFake()
  const { clock } = await start($, on, fake, {}, files)
  await typed($, 'm2b-review')
  // The refresh the command starts lands first; the older session writes after it.
  await clock.advance(1)
  const ui = await $.ui.mount({ ...pane(PANE), surface: 'terminal' })
  const older = { snapshot: { candidates: [], review: null, error: null, shows: SHOWN_WITHOUT_ENTRY }, status: null, version: '0.3.0' }
  files.set(`${HOME}/.local/state/m2b/band-answer.json`, JSON.stringify({ writtenAtMs: NOW + 59_500, value: older }))
  await clock.advance(60_000)
  expect((await partLines(ui, 'run'))?.[0]).toBe('succeeded, 18:00 to 18:02')
  await ui.unmount()
})

test('a shared answer whose run has the wrong shape is loaded again', async ($, on) => {
  // Covers: B101
  const snapshot = { candidates: [], review: null, error: null, shows: SHOWN_WITHOUT_ENTRY }
  const view = { snapshot, status: null, version: '0.3.0', run: { state: 7 } }
  const files: Files = new Map([[`${HOME}/.local/state/m2b/band-answer.json`, JSON.stringify({ writtenAtMs: NOW, value: view })]])
  const fake = reviewedFake()
  await start($, on, fake, {}, files)
  expect(fake.calls.map(call => call[0])).toContain('band')
})

test('where the pane cannot be shown, the command answers with its content instead of nothing', async ($, on) => {
  // Covers: B101
  const fake = reviewedFake()
  fake.paneWaits = 'no surface attached places panes'
  fake.searchHits = [{ path: 'memory/people/sam.md', line: 2, text: 'Sam: neighbour' }]
  await start($, on, fake)

  const review = (await typed($, 'm2b-review')).text ?? ''
  const search = (await typed($, 'm2b-search', 'Sam')).text ?? ''

  expect(review.split('\n').slice(0, 3)).toEqual([
    'the m2b pane cannot be shown here: no surface attached places panes',
    'Last curation run: succeeded, 18:00 to 18:02',
    REVIEW,
  ])
  expect(review).toContain(LONG_FINDING)
  expect(review).toContain('- Still current? Planning the trip to Porto')
  expect(search.split('\n')).toEqual([
    'the m2b pane cannot be shown here: no surface attached places panes',
    '1 hit for Sam',
    'memory/people/sam.md:2',
    '  Sam: neighbour',
  ])
})

test('the pane wraps findings and titles, where the band cuts its row', async ($, on) => {
  // Covers: B101
  const fake = reviewedFake()
  await start($, on, fake)
  await typed($, 'm2b-review')
  const wrapOf = async (ui: { findAll: (q: { type: string }) => Promise<{ text: string; props: Record<string, unknown> }[]> }, words: string) =>
    (await ui.findAll({ type: 'Text' })).find(found => found.text.includes(words))?.props['wrap']

  const inPane = await $.ui.mount({ ...pane(PANE, 24), surface: 'terminal' })
  expect(await wrapOf(inPane, 'lint: broken link in a.md')).toBe('wrap')
  expect(await wrapOf(inPane, 'Remember? Dana prefers tea 1')).toBe('wrap')
  await inPane.unmount()
  const inBand = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await wrapOf(inBand, '6 wait for you')).toBe('truncate-end')
  await inBand.unmount()
})

test('the text where the pane cannot be shown is kept short', async ($, on) => {
  // Covers: B101
  const fake = new FakeM2b()
  fake.paneWaits = 'no surface attached places panes'
  fake.searchHits = Array.from({ length: 30 }, (_, n) => ({ path: `korpus/n${n}.md`, line: 1, text: 'x'.repeat(400) }))
  await start($, on, fake)
  const lines = ((await typed($, 'm2b-search', 'x')).text ?? '').split('\n')
  expect(lines).toHaveLength(22)
  expect(lines.at(-1)).toBe('and 41 more lines')
  expect(Math.max(...lines.map(line => line.length))).toBeLessThanOrEqual(201)
})

/** A run as the status part of the band's answer names it, and how the view says it. */
const RUNS: [what: string, run: BandRun | null, says: string, tone: keyof typeof LOOKS][] = [
  ['a run of today', TODAY, 'succeeded, 18:00 to 18:04', 'plain'],
  [
    'a run of today that began and ended in one minute',
    { ...TODAY, finishedAt: '2026-03-14T18:00:50+01:00' },
    'succeeded, 18:00',
    'plain',
  ],
  [
    'a run of a day before',
    { ...TODAY, startedAt: '2026-03-13T18:00:05+01:00', finishedAt: '2026-03-13T18:04:10+01:00' },
    'succeeded, 2026-03-13',
    'plain',
  ],
  [
    'a run that began the day before and ended today',
    { ...TODAY, startedAt: '2026-03-13T23:58:00+01:00', finishedAt: '2026-03-14T00:03:00+01:00' },
    'succeeded, 2026-03-13 to 00:03',
    'plain',
  ],
  ['a run under way', { ...TODAY, state: 'running', finishedAt: null }, 'running, started 18:00', 'plain'],
  ['a run without a start', { ...TODAY, startedAt: null, finishedAt: null }, 'succeeded', 'plain'],
  ['a failed run', { ...TODAY, state: 'failed', finishedAt: '2026-03-14T18:01:00+01:00' }, 'failed, 18:00 to 18:01', 'trouble'],
  ['an interrupted run', { ...TODAY, state: 'interrupted', finishedAt: null }, 'interrupted, started 18:00', 'trouble'],
  ['no run yet', NO_RUN, NO_RUN_YET, 'quiet'],
  [
    'a run m2b could not read, with the reason',
    { state: 'unreadable', startedAt: null, finishedAt: null, message: 'the run state is not JSON' },
    'm2b could not read the last curation run: the run state is not JSON',
    'trouble',
  ],
  ['a run m2b could not read, without a reason', { state: 'unreadable', startedAt: null, finishedAt: null, message: null }, RUN_NOT_READ, 'trouble'],
  ['a status that names no run', null, RUN_NOT_READ, 'trouble'],
]

test("the run's line says how the run went and when: the time for a run of today and the date for one before, each said once", () => {
  // Covers: B209, B101
  for (const [what, run, says, tone] of RUNS) {
    expect([what, runWords(run, NOW)]).toEqual([what, { text: says, tone }])
  }
  // The same run a day later is named by its date.
  expect(runWords(TODAY, NOW + 24 * 60 * 60_000).text).toBe('succeeded, 2026-03-14')
  // A time that is no moment is drawn like any text from outside: as one plain line.
  const escape = String.fromCharCode(27)
  const dirty = runWords({ ...TODAY, startedAt: `soon${escape}[2J\nnow`, finishedAt: null }, NOW).text
  expect(dirty).not.toContain(escape)
  expect(dirty).not.toContain('\n')
  expect(dirty.startsWith('succeeded, started soon')).toBe(true)
})

for (const [what, run, says, tone] of RUNS) {
  test(`the view of the review says ${what} in one line under "Last curation run", ${tone === 'trouble' ? 'in the color of trouble' : tone === 'quiet' ? 'stepped back' : 'to be read'}`, async ($, on) => {
    // Covers: B209, B101
    const draw = ownReview($, on)

    const ui = await draw(reviewOf({ run, snapshot: { ...QUIET, candidates: [{ id: 'c1', title: 'Remember? Dana prefers tea' }] } }))

    expect((await shownParts(ui))[0]).toEqual({ key: 'run', title: LAST_RUN, count: null, lines: [says] })
    expect(await lookOf(ui, says)).toEqual(LOOKS[tone])
    // The title names the run, so the line does not.
    expect((await texts(ui)).filter(text => text.startsWith(`${LAST_RUN}:`))).toEqual([])
    expect(await partLook(ui, 'run')).toEqual(CALM)
    await ui.unmount()
  })
}

test("what a run said stands below its line in the line's color, and the reason m2b could not read a run is part of that line alone", async ($, on) => {
  // Covers: B101
  const draw = ownReview($, on)

  const failed = await draw(reviewOf({ run: { ...TODAY, state: 'failed', finishedAt: null, message: 'the ingest step failed' } }))
  expect(await partLines(failed, 'run')).toEqual(['failed, started 18:00', 'the ingest step failed'])
  expect(await lookOf(failed, 'the ingest step failed')).toEqual(TROUBLE)
  await failed.unmount()

  const succeeded = await draw(reviewOf({ run: { ...TODAY, message: 'filed 3 notes' } }))
  expect(await partLines(succeeded, 'run')).toEqual(['succeeded, 18:00 to 18:04', 'filed 3 notes'])
  expect(await lookOf(succeeded, 'filed 3 notes')).toEqual(PLAIN)
  await succeeded.unmount()

  const unread = await draw(reviewOf({ run: runOf({ run: { error: 'the run state is not JSON' } }) }))
  expect(await partLines(unread, 'run')).toEqual(['m2b could not read the last curation run: the run state is not JSON'])
  await unread.unmount()
})

test('the view of the review says that nothing waits only where m2b could read the list and it holds nothing', async ($, on) => {
  // Covers: B101, B208
  const draw = ownReview($, on)
  const waitsOf = async (model: ReviewModel) => {
    const ui = await draw(model)
    const drawn = { lines: await partLines(ui, 'waits'), look: await partLook(ui, 'waits'), says: await lookOf(ui, NOTHING_WAITS) }
    await ui.unmount()
    return drawn
  }
  const candidate = { id: 'c1', title: 'Remember? Dana prefers tea' }
  const review: BandReview = { id: 'r1', title: 'm2b: review', findings: [] }

  // Read and empty after a run: the one line, stepped back, in a part framed as any other.
  expect(await waitsOf(reviewOf({}))).toEqual({ lines: [NOTHING_WAITS], look: CALM, says: DIM })
  // A list m2b could not read is not an empty one.
  const unread = 'm2b could not read the tasks: the task list did not answer'
  expect(await waitsOf(reviewOf({ snapshot: { ...QUIET, error: unread } }))).toEqual({ lines: [unread], look: CALM, says: null })
  // Nor is one with a row in it, or one where the last press wrote nothing.
  expect(await waitsOf(reviewOf({ snapshot: { ...QUIET, candidates: [candidate] } }))).toEqual({
    lines: ['Remember? Dana prefers tea', '[keep] [drop]'],
    look: WAITING,
    says: null,
  })
  expect(await waitsOf(reviewOf({ snapshot: { ...QUIET, review } }))).toEqual({ lines: [REVIEW, '[ok]'], look: WAITING, says: null })
  const settled = 'Already settled in another session, nothing written: Remember? Dana prefers tea'
  expect(await waitsOf(reviewOf({ notice: settled }))).toEqual({ lines: [settled, NOTHING_WAITS], look: CALM, says: DIM })
})

test('before any run the view of the review has no part for what waits, unless something does', async ($, on) => {
  // Covers: B101, B208
  const draw = ownReview($, on)

  const none = await draw(reviewOf({ run: NO_RUN }))
  expect(await shownParts(none)).toEqual([{ key: 'run', title: LAST_RUN, count: null, lines: [NO_RUN_YET] }])
  await none.unmount()

  const waiting = await draw(reviewOf({ run: NO_RUN, snapshot: { ...QUIET, candidates: [{ id: 'c1', title: 'Remember? Dana prefers tea' }] } }))
  expect(await shownParts(waiting)).toEqual([
    { key: 'run', title: LAST_RUN, count: null, lines: [NO_RUN_YET] },
    { key: 'waits', title: WAITS_FOR_YOU, count: '1', lines: ['Remember? Dana prefers tea', '[keep] [drop]'] },
  ])
  await waiting.unmount()
})

test("before the band's first answer the view of the review says once that m2b has not looked, stepped back: not that it could not read the run, and not that nothing waits", async ($, on) => {
  // Covers: B101, B208
  const draw = ownReview($, on)

  const ui = await draw(reviewOf({ snapshot: null, run: null }))

  // Neither the run nor the list was read yet: one part, one line, and no second part to say it again.
  expect(await partLines(ui, 'run')).toEqual([NOT_LOOKED])
  expect(await lookOf(ui, NOT_LOOKED)).toEqual(DIM)
  expect(await partLines(ui, 'waits')).toBeNull()
  expect(await texts(ui)).toEqual([LAST_RUN, NOT_LOOKED])
  await ui.unmount()
})

test("where the band's look fails, the view of the review says so for the run and for the list, each in the color of trouble, and never that nothing waits", async ($, on) => {
  // Covers: B101
  const fake = reviewedFake()
  fake.statusFails = true
  await start($, on, fake)

  await typed($, 'm2b-review')
  const ui = await $.ui.mount({ ...pane(PANE), surface: 'terminal' })

  const tasksNotRead = 'm2b could not read the tasks: could not read the machine config'
  expect(await shownParts(ui)).toEqual([
    { key: 'run', title: LAST_RUN, count: null, lines: [RUN_NOT_READ] },
    { key: 'waits', title: WAITS_FOR_YOU, count: null, lines: [tasksNotRead] },
  ])
  expect(await lookOf(ui, RUN_NOT_READ)).toEqual(TROUBLE)
  expect(await lookOf(ui, tasksNotRead)).toEqual(TROUBLE)
  expect(await partLook(ui, 'waits')).toEqual(CALM)
  expect(await viewButtons(ui)).toEqual([])
  await ui.unmount()
})

test('the part "Waits for you" of the review is in the color of what waits and counts its rows while any wait, the review among them', async ($, on) => {
  // Covers: B208
  const fake = reviewedFake()
  const { clock } = await start($, on, fake)
  await typed($, 'm2b-review')
  const ui = await $.ui.mount({ ...pane(PANE), surface: 'terminal' })

  expect((await shownParts(ui)).map(part => [part.title, part.count])).toEqual([
    [LAST_RUN, null],
    [WAITS_FOR_YOU, '6'],
  ])
  expect(await partLook(ui, 'run')).toEqual(CALM)
  expect(await partLook(ui, 'waits')).toEqual(WAITING)

  for (const task of fake.tasks) {
    task.completed = true
  }
  await clock.advance(60_000)

  expect((await shownParts(ui)).map(part => [part.title, part.count])).toEqual([
    [LAST_RUN, null],
    [WAITS_FOR_YOU, null],
  ])
  expect(await partLook(ui, 'waits')).toEqual(CALM)
  expect(await partLines(ui, 'waits')).toEqual([NOTHING_WAITS])
  await ui.unmount()
})

/** A review whose run rewrote one fact and filed two notes, with one finding no change stands for. */
const SAM_REVIEW: BandReview = {
  id: 'r1',
  title: 'm2b: review',
  findings: ['ingest: rewrote the facts line "- Sam, neighbour, Lee (sam.md)"', 'lint: broken link in a.md'],
  told: ['ingest: rewrote the facts line "- Sam, neighbour, Lee (sam.md)"'],
  changes: [
    {
      kind: 'rewrote',
      file: 'sam.md',
      topic: 'Sam',
      parts: [
        { text: 'Sam, neighbour', change: 'same' },
        { text: ' (carpenter)', change: 'added' },
        { text: ', Lee', change: 'removed' },
      ],
    },
  ],
  copies: [{ path: '/home/alex/copy', captures: 2 }],
}

test('the text of the review for a surface without a pane uses the words of the pane: the run, the review with its changed facts, then every candidate', async ($, on) => {
  // Covers: B101
  const draw = ownReview($, on)
  const snapshot: BandSnapshot = { ...QUIET, review: SAM_REVIEW, candidates: [{ id: 'c1', title: 'Remember? Dana prefers tea' }] }

  const ui = await draw(reviewOf({ snapshot }))

  expect(await shownParts(ui)).toEqual([
    {
      key: 'run',
      title: LAST_RUN,
      count: null,
      lines: [
        'succeeded, 18:00 to 18:04',
        'Sam (sam.md)',
        'Sam, neighbour (carpenter), Lee',
        'facts before the run; 2 notes filed:',
        '/home/alex/copy',
        'lint: broken link in a.md',
      ],
    },
    {
      key: 'waits',
      title: WAITS_FOR_YOU,
      count: '2',
      lines: [REVIEW, '[ok] 1 fact changed: Sam', 'Remember? Dana prefers tea', '[keep] [drop]'],
    },
  ])
  // In the text the title of the first part stands before the run's line, and marks stand in for the colors of a change.
  expect(reviewLines(snapshot, TODAY, NOW)).toEqual([
    'Last curation run: succeeded, 18:00 to 18:04',
    'Review of the last curation run, 1 fact changed: Sam',
    '  Sam (sam.md): Sam, neighbour[+ (carpenter)][-, Lee]',
    '  facts before the run: /home/alex/copy; 2 notes filed',
    '  lint: broken link in a.md',
    '- Remember? Dana prefers tea',
  ])
  await ui.unmount()
})

test('the text of the review says no run yet, a run m2b could not read and that nothing waits in the sentences of the pane, under the same rule', () => {
  // Covers: B101
  // Before any run, with nothing to answer, one sentence says it all, as in the pane.
  expect(reviewLines(QUIET, NO_RUN, NOW)).toEqual([NO_RUN_YET])
  expect(reviewLines({ ...QUIET, candidates: [{ id: 'c1', title: 'Remember? Dana prefers tea' }] }, NO_RUN, NOW)).toEqual([
    NO_RUN_YET,
    '- Remember? Dana prefers tea',
  ])
  // A list read with nothing in it, after a run.
  expect(reviewLines(QUIET, { ...TODAY, startedAt: '2026-03-13T18:00:05+01:00', finishedAt: '2026-03-13T18:04:10+01:00' }, NOW)).toEqual([
    'Last curation run: succeeded, 2026-03-13',
    NOTHING_WAITS,
  ])
  expect(reviewLines(QUIET, { ...TODAY, state: 'failed', finishedAt: null, message: 'the ingest step failed' }, NOW)).toEqual([
    'Last curation run: failed, started 18:00',
    'the ingest step failed',
    NOTHING_WAITS,
  ])
  // Not read is never "nothing waits": neither the list nor the run.
  expect(reviewLines(null, null, NOW)).toEqual([NOT_LOOKED])
  // A list that was read and a run that was not: m2b could not read the run.
  expect(reviewLines(QUIET, null, NOW)).toEqual([RUN_NOT_READ, NOTHING_WAITS])
  expect(reviewLines({ ...QUIET, error: 'm2b could not read the tasks: the task list did not answer' }, TODAY, NOW)).toEqual([
    'Last curation run: succeeded, 18:00 to 18:04',
    'm2b could not read the tasks: the task list did not answer',
  ])
  expect(reviewLines(QUIET, { state: 'unreadable', startedAt: null, finishedAt: null, message: 'the run state is not JSON' }, NOW)).toEqual([
    'm2b could not read the last curation run: the run state is not JSON',
    NOTHING_WAITS,
  ])
})

test('the view of a search is one part under the search in words: the place of each hit, stepped back, and its text indented whole below it', async ($, on) => {
  // Covers: B101
  const fake = new FakeM2b()
  fake.searchHits = [
    { path: 'korpus/2026/03/20260312-sam.md', line: 4, text: 'Sam brings the plywood on Saturday' },
    { path: 'memory/people/sam.md', line: 2, text: 'Sam: neighbour, has a van' },
  ]
  await start($, on, fake)
  await typed($, 'm2b-search', 'Sam')
  const ui = await $.ui.mount({ ...pane(PANE), surface: 'terminal' })

  expect(await shownParts(ui)).toEqual([
    {
      key: 'search',
      title: '2 hits for Sam',
      count: null,
      lines: ['korpus/2026/03/20260312-sam.md:4', 'Sam brings the plywood on Saturday', 'memory/people/sam.md:2', 'Sam: neighbour, has a van'],
    },
  ])
  // A search is read, not answered: its part never takes the color of what waits.
  expect(await partLook(ui, 'search')).toEqual(CALM)
  expect(await lookOf(ui, 'korpus/2026/03/20260312-sam.md:4')).toEqual(DIM)
  expect(await lookOf(ui, 'Sam brings the plywood on Saturday')).toEqual(PLAIN)
  expect(await insetsAt(ui, 'part:search')).toEqual([
    { paddingLeft: 2, lines: ['Sam brings the plywood on Saturday'] },
    { paddingLeft: 2, lines: ['Sam: neighbour, has a van'] },
  ])
  expect(await viewButtons(ui)).toEqual([])
  await ui.unmount()
})

test('after its hits the view of a search says how many more there are and which files were not searched, stepped back', async ($, on) => {
  // Covers: B101
  const fake = new FakeM2b()
  fake.searchHits = Array.from({ length: 103 }, (_, n) => ({ path: `korpus/n${n}.md`, line: n + 1, text: `plywood ${n}` }))
  fake.searchEvicted = ['korpus/2026/01/20260105-old.md', 'korpus/2026/01/20260106-old.md']
  fake.searchUnreadable = [{ path: 'korpus/locked.md', reason: 'permission denied' }]
  await start($, on, fake)
  await typed($, 'm2b-search', '--word plywood')
  const ui = await $.ui.mount({ ...pane(PANE), surface: 'terminal' })

  const [search] = await shownParts(ui)
  expect(search?.title).toBe('103 hits for plywood, whole words only')
  // A hundred hits, each its place and its text, then what the search left out.
  expect(search?.lines).toHaveLength(203)
  expect(search?.lines.slice(0, 2)).toEqual(['korpus/n0.md:1', 'plywood 0'])
  const notes = ['and 3 more hits', '2 files not downloaded, not searched', '1 file could not be read']
  expect(search?.lines.slice(200)).toEqual(notes)
  for (const note of notes) {
    expect(await lookOf(ui, note)).toEqual(DIM)
  }
  await ui.unmount()
})
