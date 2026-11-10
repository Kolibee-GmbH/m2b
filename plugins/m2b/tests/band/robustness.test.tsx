import { expect, test } from 'claude-code/testing'

import { BAND, FakeM2b, HOME, NOW, start, texts } from './harness'
import type { Files } from './harness'

const CACHE = `${HOME}/.local/state/m2b/band-view.json`
const UNDO_MS = 5_000

function cached(writtenAtMs: number, snapshot: unknown, status = '7 in inbox'): string {
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

  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await ui.findAll({ type: 'Button' })).toHaveLength(6)
  const shown = await texts(ui)
  expect(shown).toContain('Remember? plain again and on')
  expect(shown).toContain('Remember? red alert from the terminal')
  expect(shown).toContain('Remember? right-to-left override and a tab here')
  expect(shown).toContain('lint: a link in a.md')
  await ui.unmount()
})

test('an error line with control characters is drawn cleaned', async ($, on) => {
  // Covers: B95
  const fake = new FakeM2b().candidate('c1', 'Remember? Acme moved')
  fake.failure = 'reminders said \u001b[1mno\u001b[0m'
  await start($, on, fake)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await texts(ui)).toEqual(['m2b could not read the tasks: reminders said no'])
  await ui.unmount()
})

test('keep and drop put -- before the task id, so an id that starts with a dash is not an option', async ($, on) => {
  // Covers: B94
  const fake = new FakeM2b().candidate('-h', 'Remember? A file named like an option')
  const { clock } = await start($, on, fake)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })

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
  expect(await ui.findAll({ type: 'Button' })).toHaveLength(2)
  await ui.unmount()
})

test('a shared answer of the wrong shape is loaded again instead of drawn', async ($, on) => {
  // Covers: B95
  const files: Files = new Map([[CACHE, cached(NOW - 10_000, { candidates: [null], review: null, error: null })]])
  const fake = new FakeM2b().candidate('c1', 'Remember? Acme moved')
  await start($, on, fake, {}, files)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await texts(ui)).toContain('Remember? Acme moved')
  expect(fake.calls.map(call => call[0])).toContain('band')
  await ui.unmount()
})

test('a shared review whose findings are not a list is loaded again instead of drawn', async ($, on) => {
  // Covers: B95
  const review = { id: 'r1', title: 'm2b: review', findings: 'abc' }
  const files: Files = new Map([[CACHE, cached(NOW - 10_000, { candidates: [], review, error: null })]])
  const fake = new FakeM2b().candidate('c1', 'Remember? Acme moved')
  await start($, on, fake, {}, files)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await texts(ui)).toEqual(['Remember? Acme moved'])
  await ui.unmount()
})

test('a shared answer stamped in the future is loaded again and replaced', async ($, on) => {
  // Covers: B95
  const snapshot = { candidates: [{ id: 'c9', title: 'Remember? From the future' }], review: null, error: null }
  const files: Files = new Map([[CACHE, cached(NOW + 3_600_000, snapshot)]])
  const fake = new FakeM2b().candidate('c1', 'Remember? Acme moved')
  await start($, on, fake, {}, files)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await texts(ui)).toContain('Remember? Acme moved')
  expect(await texts(ui)).not.toContain('Remember? From the future')
  expect(JSON.parse(files.get(CACHE) ?? '{}').writtenAtMs).toBeLessThanOrEqual(NOW + 1)
  await ui.unmount()
})

test('a launcher that cannot be started shows one error line and the status line could not look', async ($, on) => {
  // Covers: B95
  const fake = new FakeM2b().candidate('c1', 'Remember? Acme moved')
  fake.runFails = 'timed out after 90000 ms'
  const { statuses } = await start($, on, fake)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  const [line, ...rest] = await texts(ui)
  expect(rest).toEqual([])
  expect(line).toStartWith(`m2b could not read the tasks: could not run ${HOME}/.local/bin/m2b: `)
  expect(line).toContain('timed out after 90000 ms')
  expect(statuses.at(-1)).toBe('could not look')
  await ui.unmount()
})

test('a failure inside the minute timer sets the status line to could not look', async ($, on) => {
  // Covers: B95
  const fake = new FakeM2b()
  const { clock, statuses } = await start($, on, fake)
  expect(statuses.at(-1)).toBe('2 in inbox · curated 18:02')

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
  const { clock } = await start($, on, fake)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })

  await ui.press({ key: 'keep:c1' })
  fake.delayMs = args => (args[0] === 'band' && args.length === 2 ? 5_000 : 0)
  await clock.advance(UNDO_MS)
  expect(fake.writes()).toEqual([['tasks', 'complete', '--', 'c1']])

  // The reload after the write is still under way: the row offers nothing to press.
  expect(await ui.findAll({ type: 'Button' })).toHaveLength(0)
  await clock.advance(5_000)
  expect((await texts(ui)).join('\n')).not.toContain('Already settled')
  expect(fake.writes()).toHaveLength(1)
  await ui.unmount()
})

test('a press the mod had not written when it was loaded again is forgotten, not half done', async ($, on) => {
  // Covers: B94
  const fake = new FakeM2b().candidate('c1', 'Remember? Acme moved')
  const { clock } = await start($, on, fake)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })

  await ui.press({ key: 'drop:c1' })
  // A reload of the mod (an update, /reload-plugins) runs session.start again.
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await clock.advance(UNDO_MS * 2)

  expect(fake.writes()).toEqual([])
  expect(await ui.findAll({ type: 'Button' })).toHaveLength(2)
  await ui.unmount()
})

test('a write under way keeps its row locked across a reload of the mod until it lands', async ($, on) => {
  // Covers: B94
  const fake = new FakeM2b().candidate('c1', 'Remember? Acme moved').candidate('c2', 'Remember? Dana likes tea')
  const { clock } = await start($, on, fake)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  fake.delayMs = args => (args[0] === 'tasks' ? 30_000 : 0)
  const buttons = async (): Promise<(string | undefined)[]> =>
    (await ui.findAll({ type: 'Button' })).map(button => button.key)

  await ui.press({ key: 'keep:c1' })
  await clock.advance(UNDO_MS)
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await clock.settle()

  expect(await buttons()).toEqual(['keep:c2', 'drop:c2'])
  await clock.advance(30_000)
  expect(fake.writes()).toEqual([['tasks', 'complete', '--', 'c1']])
  expect(await buttons()).toEqual(['keep:c2', 'drop:c2'])
  await ui.unmount()
})

test('a write that never returns frees its row at its deadline', async ($, on) => {
  // Covers: B95
  const fake = new FakeM2b().candidate('c1', 'Remember? Acme moved')
  const { clock } = await start($, on, fake)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  fake.delayMs = args => (args[0] === 'tasks' ? 3_600_000 : 0)

  await ui.press({ key: 'keep:c1' })
  await clock.advance(UNDO_MS)
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await clock.advance(179_000)
  expect(await texts(ui)).toContain('working…')

  await clock.advance(2_000)
  expect(await texts(ui)).not.toContain('working…')
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
  const other = { candidates: [{ id: 'c9', title: 'Remember? From the other session' }], review: null, error: null }
  files.set(CACHE, cached(clock.now(), other))
  fake.candidate('c1', 'Remember? Acme moved')
  await clock.advance(10_000)

  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await texts(ui)).toContain('Remember? Acme moved')
  expect(await texts(ui)).not.toContain('Remember? From the other session')
  await ui.unmount()
})

test('a reload under way when m2b stops being set up does not draw the band again', async ($, on) => {
  // Covers: B95
  const fake = new FakeM2b().candidate('c1', 'Remember? Acme moved')
  const { clock, statuses } = await start($, on, fake)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  fake.delayMs = args => (args[0] === 'band' ? 80_000 : 0)

  await clock.advance(60_000)
  fake.isSetUp = false
  await clock.advance(100_000)

  expect(await texts(ui)).toEqual(['engine'])
  expect(statuses.at(-1)).toBeUndefined()
  await ui.unmount()
})

test('a session whose band is older than the installed m2b says to run /reload-plugins', async ($, on) => {
  // Covers: B96
  const fake = new FakeM2b()
  fake.version = '0.3.1'
  fake.bandVersion = '0.3.0'
  await start($, on, fake)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await texts(ui)).toEqual([
    'this session runs the band of m2b 0.3.0 while m2b 0.3.1 is installed: run /reload-plugins',
  ])
  await ui.unmount()
})

test('a band newer than the installed m2b, as from a checkout, says nothing about versions', async ($, on) => {
  // Covers: B96
  const fake = new FakeM2b()
  fake.version = '0.3.0'
  fake.bandVersion = '0.10.0'
  await start($, on, fake)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await texts(ui)).toEqual(['engine'])
  await ui.unmount()
})

test('a band of the installed version says nothing about versions', async ($, on) => {
  // Covers: B96
  const fake = new FakeM2b().candidate('c1', 'Remember? Acme moved')
  await start($, on, fake)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect((await texts(ui)).join('\n')).not.toContain('/reload-plugins')
  await ui.unmount()
})
