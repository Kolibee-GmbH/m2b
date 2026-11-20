import { expect, test } from 'claude-code/testing'

import {
  BAND,
  CALM_ROW,
  ENGINES_OWN_DRAWING,
  FakeM2b,
  NOW,
  ONLY_WHILE_WAITING,
  SHOWN_WITHOUT_ENTRY,
  STATUS,
  TROUBLED_STATUS,
  TROUBLE_LINE,
  answerKeys,
  everyText,
  fail,
  lookOf,
  partLines,
  pressTab,
  rowSaying,
  sentenceOfM2b,
  shownBand,
  start,
  startView,
  texts,
} from './harness'
import type { Files } from './harness'

const UNDO_MS = 5_000
const SLOW_RELOAD_MS = UNDO_MS + 5_000

test('five candidates and the review are one count in the band, and each a row with its buttons in the pane', async ($, on) => {
  // Covers: B31
  const fake = new FakeM2b()
  for (const n of [1, 2, 3, 4, 5]) {
    fake.candidate(`c${n}`, `Remember? Dana prefers tea ${n}`)
  }
  fake.review('r1', ['lint: broken link in a.md', 'lint: broken link in b.md', 'ingest: x', 'ingest: y'])
  await start($, on, fake)

  for (const surface of ['terminal', 'desktop'] as const) {
    const ui = await $.ui.mount({ ...BAND, surface })
    expect(await shownBand(ui)).toEqual(rowSaying('6 wait for you'))
    await ui.unmount()

    const inPane = await startView($, surface)
    const shown = await texts(inPane)
    for (const n of [1, 2, 3, 4, 5]) {
      expect(shown).toContain(`Remember? Dana prefers tea ${n}`)
    }
    expect(shown.some(line => /^and \d+ more/.test(line))).toBe(false)
    expect(shown).toContain('Review of the last curation run')
    expect(await answerKeys(inPane)).toEqual([
      ...[1, 2, 3, 4, 5].flatMap(n => [`keep:c${n}`, `drop:c${n}`]),
      'ok:r1',
    ])
    await inPane.unmount()
  }
})

test('nothing to show draws nothing of its own', async ($, on) => {
  const fake = new FakeM2b()
  fake.shows = ONLY_WHILE_WAITING
  await start($, on, fake)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await everyText(ui)).toEqual([ENGINES_OWN_DRAWING])
  await ui.unmount()
})

test('nothing to show is the calm row where the band is always there', async ($, on) => {
  // Covers: B213
  await start($, on, new FakeM2b())
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await shownBand(ui)).toEqual(CALM_ROW)
  await ui.unmount()
})

test('the band runs without any switch once m2b is set up', async ($, on) => {
  // Covers: B91
  const fake = new FakeM2b().candidate('c1', 'Remember? Acme moved')
  fake.status = TROUBLED_STATUS
  const { statuses } = await start($, on, fake)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await shownBand(ui)).toEqual(rowSaying('1 waits for you'))
  await ui.unmount()
  expect(statuses.at(-1)).toBe(TROUBLE_LINE)
  expect(fake.calls.some(call => call[0] === 'addons')).toBe(false)
})

test('before m2b is set up the band draws nothing, says nothing and asks m2b nothing', async ($, on) => {
  // Covers: B91
  const fake = new FakeM2b().candidate('c1', 'Remember? Acme moved')
  fake.status = TROUBLED_STATUS
  fake.isSetUp = false
  const { clock, statuses } = await start($, on, fake)
  await clock.advance(60_000)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await everyText(ui)).toEqual([ENGINES_OWN_DRAWING])
  await ui.unmount()
  expect(statuses.length).toBeGreaterThan(0)
  expect(statuses.every(text => text === undefined)).toBe(true)
  expect(fake.calls).toEqual([])
})

test('a machine config that goes away clears what the band showed', async ($, on) => {
  const fake = new FakeM2b().candidate('c1', 'Remember? Acme moved')
  fake.status = TROUBLED_STATUS
  const { clock, statuses } = await start($, on, fake)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await shownBand(ui)).toEqual(rowSaying('1 waits for you'))
  expect(statuses.at(-1)).toBe(TROUBLE_LINE)

  fake.isSetUp = false
  await clock.advance(60_000)
  expect(await everyText(ui)).toEqual([ENGINES_OWN_DRAWING])
  expect(statuses.at(-1)).toBeUndefined()
  await ui.unmount()
})

test('a store without store.json shows the error line instead of an empty band', async ($, on) => {
  const fake = new FakeM2b().candidate('c1', 'Remember? Acme moved')
  fake.isStoreMissing = true
  await start($, on, fake)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect((await texts(ui)).join('\n')).toContain('m2b could not read the tasks: not set up: no store.json')
  await ui.unmount()
})

test('a session start whose note cannot be written still starts the band', async ($, on) => {
  on('fs.write', () => {
    throw new Error('EACCES: permission denied')
  })
  const fake = new FakeM2b().candidate('c1', 'Remember? Acme moved')
  await start($, on, fake)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await shownBand(ui)).toEqual(rowSaying('1 waits for you'))
  await ui.unmount()
})

test('a session start notes that the band ran, for m2b doctor', async ($, on) => {
  // Covers: B92
  const files: Files = new Map()
  await start($, on, new FakeM2b(), {}, files)
  expect(JSON.parse(files.get('/home/alex/.local/state/m2b/band-seen.json') ?? '{}')).toEqual({
    seenAt: '2026-03-14T17:30:00.000Z',
  })
})

test('before the core wrote its launcher the band starts nothing and says nothing', async ($, on) => {
  const fake = new FakeM2b().candidate('c1', 'Remember? Acme moved')
  fake.status = TROUBLED_STATUS
  fake.hasLauncher = false
  const { clock, statuses } = await start($, on, fake)
  await clock.advance(60_000)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await everyText(ui)).toEqual([ENGINES_OWN_DRAWING])
  await ui.unmount()
  expect(fake.calls).toEqual([])
  expect(statuses.every(text => text === undefined)).toBe(true)
})

test('inside a fenced curation step the band asks m2b nothing', async ($, on) => {
  const fake = new FakeM2b().candidate('c1', 'Remember? Acme moved')
  const { clock } = await start($, on, fake, { M2B_CURATION_RUN: '1' })
  await clock.advance(60_000)
  await $.turn.complete({ answer: 'done', durationMs: 5, isAborted: false, turnId: 't1', reason: 'answer' })
  await clock.advance(1)
  expect(fake.calls).toEqual([])
})

test('an answer another session stored within 55 seconds is used without starting m2b', async ($, on) => {
  const cache = '/home/alex/.local/state/m2b'
  const candidates = [
    { id: 'c8', title: 'Remember? From the other session' },
    { id: 'c9', title: 'Remember? From the other session too' },
  ]
  const files: Files = new Map([
    [
      `${cache}/band-answer.json`,
      JSON.stringify({
        writtenAtMs: NOW - 10_000,
        value: { snapshot: { candidates, review: null, error: null, shows: SHOWN_WITHOUT_ENTRY }, status: TROUBLE_LINE, version: '0.3.0' },
      }),
    ],
  ])
  const fake = new FakeM2b()
  const { clock, statuses } = await start($, on, fake, {}, files)
  // The answer names no place: in the desktop app the band's row is above the prompt.
  const ui = await $.ui.mount({ ...BAND, surface: 'desktop' })
  const inPane = await startView($)
  expect(await shownBand(ui)).toEqual(rowSaying('2 wait for you'))
  expect(await texts(inPane)).toContain('Remember? From the other session')
  expect(statuses.at(-1)).toBe(TROUBLE_LINE)
  expect(fake.calls).toEqual([])

  fake.candidate('c1', 'Remember? Acme moved')
  await clock.advance(60_000)
  expect(await shownBand(ui)).toEqual(rowSaying('1 waits for you'))
  expect(await texts(inPane)).toContain('Remember? Acme moved')
  expect(await texts(inPane)).not.toContain('Remember? From the other session')
  expect(statuses.at(-1)).toBeUndefined()
  expect(fake.calls.map(call => call[0])).toContain('band')
  expect(JSON.parse(files.get(`${cache}/band-answer.json`) ?? '{}').value.snapshot.candidates[0].id).toBe('c1')
  await inPane.unmount()
  await ui.unmount()
})

test('after its own turn a session reads again, whatever another session stored', async ($, on) => {
  const files: Files = new Map()
  const fake = new FakeM2b()
  fake.shows = ONLY_WHILE_WAITING
  const { clock } = await start($, on, fake, {}, files)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await everyText(ui)).toEqual([ENGINES_OWN_DRAWING])

  fake.candidate('c1', 'Remember? Acme moved')
  await clock.advance(10_000)
  await $.turn.complete({ answer: 'done', durationMs: 5, isAborted: false, turnId: 't1', reason: 'answer' })
  await clock.advance(1)
  expect(await shownBand(ui)).toEqual(rowSaying('1 waits for you'))
  await ui.unmount()
})

test('after its own turn a session reads again and the calm row counts, whatever another session stored', async ($, on) => {
  // Covers: B213
  const files: Files = new Map()
  const fake = new FakeM2b()
  const { clock } = await start($, on, fake, {}, files)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await shownBand(ui)).toEqual(CALM_ROW)

  fake.candidate('c1', 'Remember? Acme moved')
  await clock.advance(10_000)
  await $.turn.complete({ answer: 'done', durationMs: 5, isAborted: false, turnId: 't1', reason: 'answer' })
  await clock.advance(1)
  expect(await shownBand(ui)).toEqual(rowSaying('1 waits for you'))
  await ui.unmount()
})

test('a slow load never replaces an answer another session started later', async ($, on) => {
  const cache = '/home/alex/.local/state/m2b/band-answer.json'
  const files: Files = new Map()
  const fake = new FakeM2b().candidate('c1', 'Remember? Acme moved')
  fake.delayMs = args => (args[0] === 'band' ? 30_000 : 0)
  const { clock } = await start($, on, fake, {}, files)
  const snapshot = { candidates: [], review: null, error: null, shows: SHOWN_WITHOUT_ENTRY }
  const newer = { writtenAtMs: NOW + 5_000, value: { snapshot, status: null, version: '0.3.0' } }
  files.set(cache, JSON.stringify(newer))
  await clock.advance(31_000)
  expect(JSON.parse(files.get(cache) ?? '{}')).toEqual(newer)
})

test('keep completes the candidate and drop drops it', async ($, on) => {
  // Covers: B31
  const fake = new FakeM2b().candidate('c1', 'Remember? Alex runs on Tuesdays').candidate('c2', 'Remember? Acme moved')
  const { clock } = await start($, on, fake)
  const ui = await startView($)

  const before = fake.calls.length
  await ui.press({ key: 'keep:c1' })
  await clock.advance(UNDO_MS)
  await ui.press({ key: 'drop:c2' })
  await clock.advance(UNDO_MS)

  expect(fake.writes()).toEqual([
    ['tasks', 'complete', '--', 'c1'],
    ['tasks', 'drop', '--', 'c2'],
  ])
  // The look before each write reads the tasks alone, without the status and its probes.
  expect(fake.calls.slice(before)[0]).toEqual(['band', '--json', '--tasks-only'])
  expect(await answerKeys(ui)).toEqual([])
  expect(await texts(ui)).toContain('Nothing waits for you.')
  await ui.unmount()
})

test('a question whether a current item still holds is counted, shown and settled like a candidate', async ($, on) => {
  const fake = new FakeM2b().candidate('c1', 'Remember? Acme moved').question('q1', 'Still current? Planning the trip')
  const { clock } = await start($, on, fake)
  const band = await $.ui.mount({ ...BAND, surface: 'terminal' })
  const ui = await startView($)
  expect(await shownBand(band)).toEqual(rowSaying('2 wait for you'))
  expect(await answerKeys(ui)).toEqual(['keep:c1', 'drop:c1', 'keep:q1', 'drop:q1'])

  await ui.press({ key: 'drop:q1' })
  await clock.advance(UNDO_MS)

  expect(fake.writes()).toEqual([['tasks', 'drop', '--', 'q1']])
  expect(await answerKeys(ui)).toEqual(['keep:c1', 'drop:c1'])
  expect(await shownBand(band)).toEqual(rowSaying('1 waits for you'))
  await ui.unmount()
  await band.unmount()
})

test('after keep the tasks are read from m2b itself, not from the answer stored a moment before', async ($, on) => {
  const cache = '/home/alex/.local/state/m2b'
  const fake = new FakeM2b().candidate('c1', 'Remember? Acme moved')
  const files: Files = new Map([
    [
      `${cache}/band-answer.json`,
      JSON.stringify({
        writtenAtMs: NOW,
        value: {
          snapshot: { candidates: [{ id: 'c1', title: 'Remember? Acme moved' }], review: null, error: null, shows: SHOWN_WITHOUT_ENTRY },
          status: null,
          version: '0.3.0',
        },
      }),
    ],
  ])
  const { clock } = await start($, on, fake, {}, files)
  const ui = await startView($)
  expect(await answerKeys(ui)).toEqual(['keep:c1', 'drop:c1'])

  await ui.press({ key: 'keep:c1' })
  await clock.advance(UNDO_MS)

  expect(fake.writes()).toEqual([['tasks', 'complete', '--', 'c1']])
  expect(await answerKeys(ui)).toEqual([])
  expect(JSON.parse(files.get(`${cache}/band-answer.json`) ?? '{}').value.snapshot.candidates).toEqual([])
  await ui.unmount()
})

test('a candidate settled in another session is not written, and the pane says so where it was pressed', async ($, on) => {
  // Covers: B30, B207
  const fake = new FakeM2b().candidate('c1', 'Remember? Alex runs on Tuesdays')
  fake.shows = ONLY_WHILE_WAITING
  const { clock } = await start($, on, fake)
  const band = await $.ui.mount({ ...BAND, surface: 'terminal' })
  const ui = await startView($)
  fake.beforeCandidateList = () => {
    const task = fake.tasks[0]
    if (task !== undefined) {
      task.completed = true
    }
  }

  await ui.press({ key: 'drop:c1' })
  await clock.advance(UNDO_MS)

  const refused = 'Already settled in another session, nothing written: Remember? Alex runs on Tuesdays'
  expect(fake.writes()).toEqual([])
  expect(await partLines(ui, 'waits')).toEqual([refused, 'Nothing waits for you.'])
  expect(await lookOf(ui, refused)).toEqual({ color: 'error', dimColor: undefined, wrap: 'wrap' })
  // Nothing waits any more, and the band says nothing of the press.
  expect(await everyText(band)).toEqual([ENGINES_OWN_DRAWING])
  expect(await answerKeys(ui)).toEqual([])
  await ui.unmount()
  await band.unmount()
})

test('a candidate settled in another session leaves a band that is always there calm, with no word of the press', async ($, on) => {
  // Covers: B207, B213
  const fake = new FakeM2b().candidate('c1', 'Remember? Alex runs on Tuesdays')
  const { clock } = await start($, on, fake)
  const band = await $.ui.mount({ ...BAND, surface: 'terminal' })
  const ui = await startView($)
  fake.beforeCandidateList = () => {
    const task = fake.tasks[0]
    if (task !== undefined) {
      task.completed = true
    }
  }

  await ui.press({ key: 'drop:c1' })
  await clock.advance(UNDO_MS)

  expect(fake.writes()).toEqual([])
  expect(await partLines(ui, 'waits')).toEqual([
    'Already settled in another session, nothing written: Remember? Alex runs on Tuesdays',
    'Nothing waits for you.',
  ])
  expect(await shownBand(band)).toEqual(CALM_ROW)
  await ui.unmount()
  await band.unmount()
})

test('a failing command shows one error line', async ($, on) => {
  // Covers: X11
  const fake = new FakeM2b().candidate('c1', 'Remember? Alex runs on Tuesdays')
  fake.failure = 'reminders did not answer within 20 seconds'
  await start($, on, fake)

  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await shownBand(ui)).toEqual(
    sentenceOfM2b('m2b could not read the tasks: reminders did not answer within 20 seconds'),
  )
  await ui.unmount()
})

test('the band reloads every 60 seconds and after each turn', async ($, on) => {
  // Covers: B31
  const fake = new FakeM2b()
  fake.shows = ONLY_WHILE_WAITING
  const { clock } = await start($, on, fake)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await everyText(ui)).toEqual([ENGINES_OWN_DRAWING])

  fake.candidate('c1', 'Remember? Acme moved')
  await clock.advance(60_000)
  expect(await shownBand(ui)).toEqual(rowSaying('1 waits for you'))

  fake.candidate('c2', 'Remember? Dana likes tea')
  await $.turn.complete({ answer: 'done', durationMs: 5, isAborted: false, turnId: 't1', reason: 'answer' })
  await clock.advance(1)
  expect(await shownBand(ui)).toEqual(rowSaying('2 wait for you'))
  await ui.unmount()
})

test('a band that is always there is calm until a reload finds something, every 60 seconds and after each turn', async ($, on) => {
  // Covers: B31, B213
  const fake = new FakeM2b()
  const { clock } = await start($, on, fake)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await shownBand(ui)).toEqual(CALM_ROW)

  fake.candidate('c1', 'Remember? Acme moved')
  await clock.advance(60_000)
  expect(await shownBand(ui)).toEqual(rowSaying('1 waits for you'))

  fake.candidate('c2', 'Remember? Dana likes tea')
  await $.turn.complete({ answer: 'done', durationMs: 5, isAborted: false, turnId: 't1', reason: 'answer' })
  await clock.advance(1)
  expect(await shownBand(ui)).toEqual(rowSaying('2 wait for you'))
  await ui.unmount()
})

test('the status line says what m2b status names as wrong, is cleared while nothing is, and says when it could not look', async ($, on) => {
  const fake = new FakeM2b()
  const { clock, statuses } = await start($, on, fake)
  expect(statuses.length).toBeGreaterThan(0)
  expect(statuses.at(-1)).toBeUndefined()

  fake.status = { ...STATUS, run: { state: 'failed' } }
  await clock.advance(60_000)
  expect(statuses.at(-1)).toBe('last curation run failed')

  // A run under way is nothing wrong.
  fake.status = { ...STATUS, run: { state: 'running' } }
  await clock.advance(60_000)
  expect(statuses.at(-1)).toBeUndefined()

  fake.statusFails = true
  await clock.advance(60_000)
  expect(statuses.at(-1)).toBe('could not look')
})

test('a subagent finishing its turn does not reload the band', async ($, on) => {
  const fake = new FakeM2b()
  const { clock } = await start($, on, fake)
  const before = fake.calls.length

  await $.turn.complete({
    answer: 'done',
    durationMs: 5,
    isAborted: false,
    turnId: 't2',
    agentId: 'a1',
    reason: 'answer',
  })
  await clock.advance(1)

  expect(fake.calls.length).toBe(before)
})

test('a write that fails shows one error line and the candidate comes back on the next reload', async ($, on) => {
  // Covers: X11
  const fake = new FakeM2b().candidate('c1', 'Remember? Alex runs on Tuesdays')
  const { clock } = await start($, on, fake)
  const band = await $.ui.mount({ ...BAND, surface: 'terminal' })
  const ui = await startView($)
  const handle = fake.handle.bind(fake)
  fake.handle = argv => (argv[2] === 'complete' ? fail('the task list is read-only') : handle(argv))

  await ui.press({ key: 'keep:c1' })
  await clock.advance(UNDO_MS)
  const line = 'm2b could not keep "Remember? Alex runs on Tuesdays": the task list is read-only'
  expect(await shownBand(band)).toEqual(sentenceOfM2b(line))
  expect(await texts(ui)).toContain(line)

  fake.handle = handle
  await clock.advance(60_000)
  expect(await answerKeys(ui)).toEqual(['keep:c1', 'drop:c1'])
  expect(await shownBand(band)).toEqual(rowSaying('1 waits for you'))
  await ui.unmount()
  await band.unmount()
})

/**
 * Delays the first band answer after `armed()` is called by longer than the undo window: a reload
 * that read before the click and is still running when the write is due.
 */
function slowFirstCandidateList(fake: FakeM2b): () => void {
  let isArmed = false
  fake.delayMs = args => {
    if (isArmed && args[0] === 'band') {
      isArmed = false
      return SLOW_RELOAD_MS
    }
    return 0
  }
  return () => {
    isArmed = true
  }
}

test('a reload that read before keep was pressed does not bring the candidate back', async ($, on) => {
  const fake = new FakeM2b().candidate('c1', 'Remember? Acme moved')
  fake.shows = ONLY_WHILE_WAITING
  const arm = slowFirstCandidateList(fake)
  const { clock } = await start($, on, fake)
  const band = await $.ui.mount({ ...BAND, surface: 'terminal' })
  const ui = await startView($)
  arm()
  await clock.advance(60_000)

  await ui.press({ key: 'keep:c1' })
  await clock.advance(SLOW_RELOAD_MS)

  expect(fake.writes()).toEqual([['tasks', 'complete', '--', 'c1']])
  expect(await answerKeys(ui)).toEqual([])
  expect(await texts(ui)).not.toContain('Remember? Acme moved')
  expect(await everyText(band)).toEqual([ENGINES_OWN_DRAWING])
  await ui.unmount()
  await band.unmount()
})

test('a reload that read before keep was pressed does not bring the count back to a band that is always there', async ($, on) => {
  // Covers: B213
  const fake = new FakeM2b().candidate('c1', 'Remember? Acme moved')
  const arm = slowFirstCandidateList(fake)
  const { clock } = await start($, on, fake)
  const band = await $.ui.mount({ ...BAND, surface: 'terminal' })
  const ui = await startView($)
  arm()
  await clock.advance(60_000)

  await ui.press({ key: 'keep:c1' })
  await clock.advance(SLOW_RELOAD_MS)

  expect(fake.writes()).toEqual([['tasks', 'complete', '--', 'c1']])
  expect(await answerKeys(ui)).toEqual([])
  expect(await texts(ui)).not.toContain('Remember? Acme moved')
  expect(await shownBand(band)).toEqual(CALM_ROW)
  await ui.unmount()
  await band.unmount()
})

test('a reload that read before a failed write does not hide the error', async ($, on) => {
  // Covers: X11
  const fake = new FakeM2b().candidate('c1', 'Remember? Acme moved')
  const arm = slowFirstCandidateList(fake)
  const { clock } = await start($, on, fake)
  const band = await $.ui.mount({ ...BAND, surface: 'terminal' })
  const ui = await startView($)
  const handle = fake.handle.bind(fake)
  fake.handle = argv => (argv[2] === 'complete' ? fail('the task list is read-only') : handle(argv))
  arm()
  await clock.advance(60_000)

  await ui.press({ key: 'keep:c1' })
  await clock.advance(SLOW_RELOAD_MS)

  expect(await shownBand(band)).toEqual(sentenceOfM2b('m2b could not keep "Remember? Acme moved": the task list is read-only'))
  await ui.unmount()
  await band.unmount()
})

test('a reload starts exactly one m2b process for the band and the status line', async ($, on) => {
  // Covers: B93
  const fake = new FakeM2b().candidate('c1', 'Remember? Acme moved').question('q1', 'Still current? Porto')
  fake.review('r1', ['lint: broken link in a.md'])
  fake.status = TROUBLED_STATUS
  const { clock, statuses } = await start($, on, fake)
  const before = fake.calls.length

  await clock.advance(60_000)

  expect(fake.calls.slice(before)).toEqual([['band', '--json']])
  expect(statuses.at(-1)).toBe(TROUBLE_LINE)
  const band = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await shownBand(band)).toEqual(rowSaying('3 wait for you'))
  await band.unmount()
  const ui = await startView($)
  expect(await answerKeys(ui)).toEqual(['keep:c1', 'drop:c1', 'keep:q1', 'drop:q1', 'ok:r1'])
  await pressTab(ui, 'review')
  expect(await texts(ui)).toContain('lint: broken link in a.md')
  await ui.unmount()
})

test('two quick presses on the same candidate write once', async ($, on) => {
  const fake = new FakeM2b().candidate('c1', 'Remember? Acme moved')
  const { clock } = await start($, on, fake)
  const ui = await startView($)

  await Promise.all([ui.press({ key: 'keep:c1' }), ui.press({ key: 'drop:c1' })])
  await clock.advance(UNDO_MS)

  expect(fake.writes()).toEqual([['tasks', 'complete', '--', 'c1']])
  await ui.unmount()
})

test('a prompt enters as typed and clears what m2b said to the last press that wrote nothing', async ($, on) => {
  // Covers: B207
  on('prompt.submit', (_, e) => ({ text: e.text, context: e.context }))
  const fake = new FakeM2b().candidate('c1', 'Remember? Alex runs on Tuesdays').candidate('c2', 'Remember? Acme moved')
  const { clock } = await start($, on, fake)
  const band = await $.ui.mount({ ...BAND, surface: 'terminal' })
  const ui = await startView($)
  fake.beforeCandidateList = () => {
    const task = fake.tasks[0]
    if (task !== undefined) {
      task.completed = true
    }
  }
  await ui.press({ key: 'drop:c1' })
  await clock.advance(UNDO_MS)
  const notice = 'Already settled in another session, nothing written: Remember? Alex runs on Tuesdays'
  expect(await partLines(ui, 'waits')).toEqual([notice, 'Remember? Acme moved', '[keep] [drop]'])
  expect(await shownBand(band)).toEqual(rowSaying('1 waits for you'))

  const entered = await $.prompt.submit({
    text: 'what is on today?',
    context: ['from another plugin'],
    wait: false,
    origin: { kind: 'composer' },
  })

  expect(entered).toEqual({ text: 'what is on today?', context: ['from another plugin'] })
  expect(await partLines(ui, 'waits')).toEqual(['Remember? Acme moved', '[keep] [drop]'])
  expect(await shownBand(band)).toEqual(rowSaying('1 waits for you'))
  await ui.unmount()
  await band.unmount()
})
