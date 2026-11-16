import { expect, test } from 'claude-code/testing'

import {
  BAND,
  CALM_ROW,
  CURATE_NOW_LINE,
  ENGINES_OWN_DRAWING,
  FakeM2b,
  HOME,
  NOW,
  ONLY_WHILE_WAITING,
  SHOWN_WITHOUT_ENTRY,
  TROUBLED_STATUS,
  TROUBLE_LINE,
  answerKeys,
  everyText,
  linesAt,
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

const CACHE = `${HOME}/.local/state/m2b/band-answer.json`
const UNDO_MS = 5_000
/** What the part about m2b says of curation for the status the fake answers while nothing is wrong. */
const CURATED = '2 in inbox · curated 18:02'

function cached(writtenAtMs: number, snapshot: unknown, status: string | null = null): string {
  return JSON.stringify({ writtenAtMs, value: { snapshot, status, version: '0.3.0' } })
}

test('a title with control characters or line breaks is drawn cleaned, and the band stays', async ($, on) => {
  // Covers: B95
  const fake = new FakeM2b()
    .candidate('c1', 'Remember? \u001b[31mred\u001b[0m alert\u0007 from the\nterminal')
    .candidate('c2', 'Remember? right-to-left \u202eoverride\r\nand a tab\there')
    .candidate('c3', '\ufeffRemember? \u001b(Bplain\u001b7 again\u009b31m\u2028and on')
  fake.review('r1', ['lint: \u001b]8;;http://example.invalid\u0007a link\u001b]8;;\u0007 in a.md'])
  await start($, on, fake)

  const band = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await shownBand(band)).toEqual(rowSaying('4 wait for you'))
  await band.unmount()

  const ui = await startView($)
  expect(await answerKeys(ui)).toHaveLength(7) // with ok on the review
  const shown = await texts(ui)
  expect(shown).toContain('Remember? plain again and on')
  expect(shown).toContain('Remember? red alert from the terminal')
  expect(shown).toContain('Remember? right-to-left override and a tab here')
  await pressTab(ui, 'review')
  expect(await texts(ui)).toContain('lint: a link in a.md')
  await ui.unmount()
})

test('an error line with control characters is drawn cleaned', async ($, on) => {
  // Covers: B95
  const fake = new FakeM2b().candidate('c1', 'Remember? Acme moved')
  fake.failure = 'reminders said \u001b[1mno\u001b[0m'
  await start($, on, fake)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await shownBand(ui)).toEqual(sentenceOfM2b('m2b could not read the tasks: reminders said no'))
  await ui.unmount()
})

test('keep and drop put -- before the task id, so an id that starts with a dash is not an option', async ($, on) => {
  // Covers: B94
  const fake = new FakeM2b().candidate('-h', 'Remember? A file named like an option')
  const { clock } = await start($, on, fake)
  const ui = await startView($)

  await ui.press({ key: 'keep:-h' })
  await clock.advance(UNDO_MS)

  expect(fake.writes()).toEqual([['tasks', 'complete', '--', '-h']])
  await ui.unmount()
})

test('M2B_HOME with a leading ~ resolves under HOME, as the core reads it', async ($, on) => {
  // Covers: B95
  const fake = new FakeM2b().candidate('c1', 'Remember? Acme moved')
  fake.home = `${HOME}/m2b-home`
  await start($, on, fake, { M2B_HOME: '~/m2b-home' })
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await shownBand(ui)).toEqual(rowSaying('1 waits for you'))
  await ui.unmount()
})

test('a shared answer of the wrong shape is loaded again instead of drawn', async ($, on) => {
  // Covers: B95
  const files: Files = new Map([[CACHE, cached(NOW - 10_000, { candidates: [null], review: null, error: null, shows: SHOWN_WITHOUT_ENTRY })]])
  const fake = new FakeM2b().candidate('c1', 'Remember? Acme moved')
  await start($, on, fake, {}, files)
  const band = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await shownBand(band)).toEqual(rowSaying('1 waits for you'))
  await band.unmount()
  const ui = await startView($)
  expect(await texts(ui)).toContain('Remember? Acme moved')
  expect(fake.calls.map(call => call[0])).toContain('band')
  await ui.unmount()
})

test('a shared review whose findings are not a list is loaded again instead of drawn', async ($, on) => {
  // Covers: B95
  const review = { id: 'r1', title: 'm2b: review', findings: 'abc' }
  const files: Files = new Map([[CACHE, cached(NOW - 10_000, { candidates: [], review, error: null, shows: SHOWN_WITHOUT_ENTRY })]])
  const fake = new FakeM2b().candidate('c1', 'Remember? Acme moved')
  await start($, on, fake, {}, files)
  const band = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await shownBand(band)).toEqual(rowSaying('1 waits for you'))
  await band.unmount()
  const ui = await startView($)
  expect(await texts(ui)).toContain('Remember? Acme moved')
  expect(await linesAt(ui, 'review:r1')).toBeNull()
  expect(await answerKeys(ui)).toEqual(['keep:c1', 'drop:c1'])
  await ui.unmount()
})

test('a shared answer stamped in the future is loaded again and replaced', async ($, on) => {
  // Covers: B95
  const snapshot = { candidates: [{ id: 'c9', title: 'Remember? From the future' }], review: null, error: null, shows: SHOWN_WITHOUT_ENTRY }
  const files: Files = new Map([[CACHE, cached(NOW + 3_600_000, snapshot)]])
  const fake = new FakeM2b().candidate('c1', 'Remember? Acme moved')
  await start($, on, fake, {}, files)
  const ui = await startView($)
  expect(await texts(ui)).toContain('Remember? Acme moved')
  expect(await texts(ui)).not.toContain('Remember? From the future')
  expect(JSON.parse(files.get(CACHE) ?? '{}').writtenAtMs).toBeLessThanOrEqual(NOW + 1)
  await ui.unmount()
})

test('a look that could not read the tasks is not stored for the other sessions', async ($, on) => {
  // Covers: B93
  const files: Files = new Map()
  const fake = new FakeM2b().candidate('c1', 'Remember? Acme moved')
  fake.failure = 'reminders show-lists failed: error: you need to grant reminders access'
  await start($, on, fake, {}, files)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await shownBand(ui)).toEqual(
    sentenceOfM2b('m2b could not read the tasks: reminders show-lists failed: error: you need to grant reminders access'),
  )
  expect(files.has(CACHE)).toBe(false)
  await ui.unmount()
})

test('a look another session stored that could not read the tasks is not taken: this session looks itself', async ($, on) => {
  // Covers: B93
  const unread = { candidates: [], review: null, error: 'm2b could not read the tasks: you need to grant reminders access' }
  const files: Files = new Map([[CACHE, cached(NOW - 10_000, unread)]])
  const fake = new FakeM2b().candidate('c1', 'Remember? Acme moved')
  await start($, on, fake, {}, files)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await shownBand(ui)).toEqual(rowSaying('1 waits for you'))
  expect(fake.calls.map(call => call[0])).toContain('band')
  expect(JSON.parse(files.get(CACHE) ?? '{}').value.snapshot.error).toBeNull()
  await ui.unmount()
})

test('a launcher that cannot be started shows one error line and the status line could not look', async ($, on) => {
  // Covers: B95
  const fake = new FakeM2b().candidate('c1', 'Remember? Acme moved')
  fake.runFails = 'timed out after 90000 ms'
  const { statuses } = await start($, on, fake)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  const shown = await shownBand(ui)
  const line = shown?.says ?? ''
  expect(shown).toEqual(sentenceOfM2b(line))
  expect(line).toStartWith(`m2b could not read the tasks: could not run ${HOME}/.local/bin/m2b: `)
  expect(line).toContain('timed out after 90000 ms')
  expect(statuses.at(-1)).toBe('could not look')
  await ui.unmount()
})

test('a failure inside the minute timer sets the status line to could not look', async ($, on) => {
  // Covers: B95
  const fake = new FakeM2b()
  fake.status = TROUBLED_STATUS
  const { clock, statuses } = await start($, on, fake)
  expect(statuses.at(-1)).toBe(TROUBLE_LINE)

  fake.existsFails = true
  await clock.advance(60_000)

  expect(statuses.at(-1)).toBe('could not look')
})

test('a failure in the reload after a turn sets the status line to could not look', async ($, on) => {
  // Covers: B95
  const fake = new FakeM2b()
  const { clock, statuses } = await start($, on, fake)
  fake.existsFails = true
  await $.turn.complete({ answer: 'done', durationMs: 5, isAborted: false, turnId: 't1', reason: 'answer' })
  await clock.advance(1)
  expect(statuses.at(-1)).toBe('could not look')
})

test('several turns while m2b is slow leave at most one reload waiting', async ($, on) => {
  // Covers: B95
  const fake = new FakeM2b()
  const { clock } = await start($, on, fake)
  fake.delayMs = args => (args[0] === 'band' ? 10_000 : 0)
  const before = fake.calls.length

  for (const turn of [1, 2, 3, 4, 5, 6]) {
    await $.turn.complete({ answer: 'done', durationMs: 5, isAborted: false, turnId: `t${turn}`, reason: 'answer' })
    await clock.advance(1_000)
  }
  await clock.advance(50_000)

  // The first turn's reload, and one more that reads after all of them.
  expect(fake.calls.slice(before)).toEqual([
    ['band', '--json'],
    ['band', '--json'],
  ])
})

test('the row stays locked until the reload after a keep has landed', async ($, on) => {
  // Covers: B94
  const fake = new FakeM2b().candidate('c1', 'Remember? Acme moved')
  fake.shows = ONLY_WHILE_WAITING
  const { clock } = await start($, on, fake)
  const band = await $.ui.mount({ ...BAND, surface: 'terminal' })
  const ui = await startView($)

  await ui.press({ key: 'keep:c1' })
  fake.delayMs = args => (args[0] === 'band' && args.length === 2 ? 5_000 : 0)
  await clock.advance(UNDO_MS)
  expect(fake.writes()).toEqual([['tasks', 'complete', '--', 'c1']])

  // The reload after the write is still under way: the row offers nothing to press, and still counts.
  expect(await answerKeys(ui)).toEqual([])
  expect(await texts(ui)).toContain('keeping: Remember? Acme moved')
  expect(await shownBand(band)).toEqual(rowSaying('1 waits for you'))
  await clock.advance(5_000)
  expect(await texts(ui)).not.toContain('keeping: Remember? Acme moved')
  expect(await everyText(band)).toEqual([ENGINES_OWN_DRAWING])
  expect(fake.writes()).toHaveLength(1)
  await ui.unmount()
  await band.unmount()
})

test('a band that is always there counts the locked row until the reload after a keep has landed, and is calm then', async ($, on) => {
  // Covers: B94, B213
  const fake = new FakeM2b().candidate('c1', 'Remember? Acme moved')
  const { clock } = await start($, on, fake)
  const band = await $.ui.mount({ ...BAND, surface: 'terminal' })
  const ui = await startView($)

  await ui.press({ key: 'keep:c1' })
  fake.delayMs = args => (args[0] === 'band' && args.length === 2 ? 5_000 : 0)
  await clock.advance(UNDO_MS)
  expect(fake.writes()).toEqual([['tasks', 'complete', '--', 'c1']])

  expect(await shownBand(band)).toEqual(rowSaying('1 waits for you'))
  await clock.advance(5_000)
  expect(await texts(ui)).not.toContain('keeping: Remember? Acme moved')
  expect(await shownBand(band)).toEqual(CALM_ROW)
  expect(fake.writes()).toHaveLength(1)
  await ui.unmount()
  await band.unmount()
})

test('a press the mod had not written when it was loaded again is forgotten, not half done', async ($, on) => {
  // Covers: B94
  const fake = new FakeM2b().candidate('c1', 'Remember? Acme moved')
  const { clock } = await start($, on, fake)
  const ui = await startView($)

  await ui.press({ key: 'drop:c1' })
  // A reload of the mod (an update, /reload-plugins) runs session.start again.
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await clock.advance(UNDO_MS * 2)

  expect(fake.writes()).toEqual([])
  expect(await answerKeys(ui)).toEqual(['keep:c1', 'drop:c1'])
  await ui.unmount()
})

test('a write under way keeps its row locked across a reload of the mod until it lands', async ($, on) => {
  // Covers: B94
  const fake = new FakeM2b().candidate('c1', 'Remember? Acme moved').candidate('c2', 'Remember? Dana likes tea')
  const { clock } = await start($, on, fake)
  const ui = await startView($)
  fake.delayMs = args => (args[0] === 'tasks' ? 30_000 : 0)

  await ui.press({ key: 'keep:c1' })
  await clock.advance(UNDO_MS)
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await clock.settle()

  expect(await answerKeys(ui)).toEqual(['keep:c2', 'drop:c2'])
  await clock.advance(30_000)
  expect(fake.writes()).toEqual([['tasks', 'complete', '--', 'c1']])
  expect(await answerKeys(ui)).toEqual(['keep:c2', 'drop:c2'])
  await ui.unmount()
})

test('a write that never returns frees its row at its deadline', async ($, on) => {
  // Covers: B95
  const fake = new FakeM2b().candidate('c1', 'Remember? Acme moved')
  const { clock } = await start($, on, fake)
  const ui = await startView($)
  fake.delayMs = args => (args[0] === 'tasks' ? 3_600_000 : 0)

  await ui.press({ key: 'keep:c1' })
  await clock.advance(UNDO_MS)
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await clock.advance(179_000)
  // No reload lands behind the write, so the row is the one that was pressed: locked, with nothing to press.
  expect(await texts(ui)).toContain('keeping: Remember? Acme moved')
  expect(await answerKeys(ui)).toEqual([])

  await clock.advance(2_000)
  expect(await texts(ui)).not.toContain('keeping: Remember? Acme moved')
  expect(await answerKeys(ui)).toEqual(['keep:c1', 'drop:c1'])
  await ui.unmount()
})

test('a turn that ends while a minute reload waits makes that reload read for itself', async ($, on) => {
  // Covers: B95
  const files: Files = new Map()
  const fake = new FakeM2b()
  let isSlowArmed = false
  fake.delayMs = args => {
    if (isSlowArmed && args[0] === 'band') {
      isSlowArmed = false
      return 70_000
    }
    return 0
  }
  const { clock } = await start($, on, fake, {}, files)
  isSlowArmed = true
  // The minute's reload at 60 s runs until 130 s; the one at 120 s waits behind it.
  await clock.advance(121_000)
  await $.turn.complete({ answer: 'done', durationMs: 5, isAborted: false, turnId: 't1', reason: 'answer' })
  await clock.advance(5_000)
  const other = { candidates: [{ id: 'c9', title: 'Remember? From the other session' }], review: null, error: null, shows: SHOWN_WITHOUT_ENTRY }
  files.set(CACHE, cached(clock.now(), other))
  fake.candidate('c1', 'Remember? Acme moved')
  await clock.advance(10_000)

  const ui = await startView($)
  expect(await texts(ui)).toContain('Remember? Acme moved')
  expect(await texts(ui)).not.toContain('Remember? From the other session')
  await ui.unmount()
})

test('a reload under way when m2b stops being set up does not draw the band again', async ($, on) => {
  // Covers: B95
  const fake = new FakeM2b().candidate('c1', 'Remember? Acme moved')
  fake.status = TROUBLED_STATUS
  const { clock, statuses } = await start($, on, fake)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  fake.delayMs = args => (args[0] === 'band' ? 80_000 : 0)

  await clock.advance(60_000)
  fake.isSetUp = false
  await clock.advance(100_000)

  expect(await everyText(ui)).toEqual([ENGINES_OWN_DRAWING])
  expect(statuses.at(-1)).toBeUndefined()
  await ui.unmount()
})

test('a session that runs an older m2b than the installed one says to run /reload-plugins, in the pane and not in the band', async ($, on) => {
  // Covers: B96
  const fake = new FakeM2b()
  fake.shows = ONLY_WHILE_WAITING
  fake.version = '0.3.1'
  fake.bandVersion = '0.3.0'
  await start($, on, fake)
  const band = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await everyText(band)).toEqual([ENGINES_OWN_DRAWING])
  await band.unmount()

  const ui = await startView($)
  const older = 'This session runs m2b 0.3.0 and m2b 0.3.1 is installed: run /reload-plugins.'
  expect(await partLines(ui, 'm2b')).toEqual([older, CURATED, CURATE_NOW_LINE])
  expect(await lookOf(ui, older)).toEqual({ color: 'warning', dimColor: undefined, wrap: 'wrap' })
  await ui.unmount()
})

test('a session that runs an older m2b than the installed one leaves a band that is always there calm: the pane says to run /reload-plugins', async ($, on) => {
  // Covers: B96, B213
  const fake = new FakeM2b()
  fake.version = '0.3.1'
  fake.bandVersion = '0.3.0'
  await start($, on, fake)
  const band = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await shownBand(band)).toEqual(CALM_ROW)
  expect((await everyText(band)).join('\n')).not.toContain('/reload-plugins')
  await band.unmount()

  const ui = await startView($)
  expect(await partLines(ui, 'm2b')).toEqual(['This session runs m2b 0.3.0 and m2b 0.3.1 is installed: run /reload-plugins.', CURATED, CURATE_NOW_LINE])
  await ui.unmount()
})

test('a band newer than the installed m2b, as from a checkout, says nothing about versions', async ($, on) => {
  // Covers: B96
  const fake = new FakeM2b()
  fake.shows = ONLY_WHILE_WAITING
  fake.version = '0.3.0'
  fake.bandVersion = '0.10.0'
  await start($, on, fake)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await everyText(ui)).toEqual([ENGINES_OWN_DRAWING])
  await ui.unmount()
  const beside = await startView($)
  expect(await partLines(beside, 'm2b')).toEqual([CURATED, CURATE_NOW_LINE])
  await beside.unmount()
})

test('a band newer than the installed m2b, as from a checkout, is calm where it is always there and says nothing about versions', async ($, on) => {
  // Covers: B96, B213
  const fake = new FakeM2b()
  fake.version = '0.3.0'
  fake.bandVersion = '0.10.0'
  await start($, on, fake)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await shownBand(ui)).toEqual(CALM_ROW)
  await ui.unmount()
  const beside = await startView($)
  expect(await partLines(beside, 'm2b')).toEqual([CURATED, CURATE_NOW_LINE])
  await beside.unmount()
})

test('a band of the installed version says nothing about versions', async ($, on) => {
  // Covers: B96
  const fake = new FakeM2b().candidate('c1', 'Remember? Acme moved')
  await start($, on, fake)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await shownBand(ui)).toEqual(rowSaying('1 waits for you'))
  await ui.unmount()
  const beside = await startView($)
  expect(await partLines(beside, 'm2b')).toEqual([CURATED, CURATE_NOW_LINE])
  await beside.unmount()
})
