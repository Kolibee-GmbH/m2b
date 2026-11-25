import { expect, test } from 'claude-code/testing'

import type { CommandRunResult } from 'claude-code'
import type { Engine } from 'claude-code/testing'

import { dayOf } from '../../hooks/note'
import { FakeM2b, HOME, NOW, SHOWN_WITHOUT_ENTRY, TROUBLED_STATUS, TROUBLE_LINE, start } from './harness'
import type { Files } from './harness'

const NOTE = 'm2b-note'
const ZURICH = (ms: number) => (ms >= Date.UTC(2026, 2, 29, 1) && ms < Date.UTC(2026, 9, 25, 1) ? 120 : 60)
const NEW_YORK = () => -300
// The harness clock as the machine that runs the tests reads it: its today and tomorrow.
const TODAY = dayOf('today', NOW) ?? ''
const TOMORROW = dayOf('tomorrow', NOW) ?? ''
const MONTH_NAMES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const inWords = (day: string) => `${Number(day.slice(8))} ${MONTH_NAMES[Number(day.slice(5, 7)) - 1]}`

/** `/m2b-note <args>` as the person types it at the prompt. */
function typed($: Engine, args: string): Promise<CommandRunResult> {
  return $.command.run({
    command: NOTE,
    args,
    origin: { kind: 'composer' },
    presentation: { isFullscreen: false, columns: 100 },
  })
}

test('the note command writes its text into the inbox at once and shows how it begins', async ($, on) => {
  // Covers: B100
  const fake = new FakeM2b()
  const { commands } = await start($, on, fake)
  expect(commands.map(command => command.name)).toContain(NOTE)

  const answer = await typed($, 'Sam brings the plywood on Saturday, the long boards too')

  expect(fake.captured).toEqual(['Sam brings the plywood on Saturday, the long boards too'])
  expect(fake.calls.filter(call => call[0] === 'capture')).toEqual([['capture', '--source', 'claude', '-']])
  expect(answer.text).toBe('noted: Sam brings the plywood on Saturday, the long board…')
})

test('the note command keeps quotes, dollar signs and dashes as written', async ($, on) => {
  // Covers: B100
  const fake = new FakeM2b()
  await start($, on, fake)
  await typed($, `--help is not an option: "$HOME" and 'single' quotes`)
  expect(fake.captured).toEqual([`--help is not an option: "$HOME" and 'single' quotes`])
})

test('the note command with no text writes nothing and says what it needs', async ($, on) => {
  // Covers: B100
  const fake = new FakeM2b()
  await start($, on, fake)
  const answer = await typed($, '   ')
  expect(fake.captured).toEqual([])
  expect(fake.calls.filter(call => call[0] === 'capture')).toEqual([])
  expect(answer.text).toBe('nothing noted: write the text after the command, as in /m2b-note Sam brings the plywood')
})

test('a failure of m2b is one line', async ($, on) => {
  // Covers: B100
  const fake = new FakeM2b()
  fake.captureFails = 'the inbox is not writable: /home/alex/Notes/inbox'
  await start($, on, fake)
  const answer = await typed($, 'Sam brings the plywood')
  expect(answer.text).toBe('not noted: the inbox is not writable: /home/alex/Notes/inbox')
})

test('the confirmation is cleaned like every text the band draws', async ($, on) => {
  // Covers: B100
  const fake = new FakeM2b()
  await start($, on, fake)
  const answer = await typed($, 'Sam \u001b[31mbrings\u001b[0m the\nplywood')
  expect(fake.captured).toEqual(['Sam \u001b[31mbrings\u001b[0m the\nplywood'])
  expect(answer.text).toBe('noted: Sam brings the plywood')
})

test('the note command is declared to run while a turn is working', async ($, on) => {
  // Covers: B100
  const { commands } = await start($, on, new FakeM2b())
  expect(commands.find(command => command.name === NOTE)?.immediate).toBe(true)
})

test('before m2b is set up the note command writes nothing and says how to set it up', async ($, on) => {
  // Covers: B100
  const fake = new FakeM2b()
  fake.isSetUp = false
  await start($, on, fake)
  const answer = await typed($, 'Sam brings the plywood')
  expect(fake.calls).toEqual([])
  expect(answer.text).toBe('not noted: m2b is not set up on this machine; /m2b:m2b sets it up')
})

test('after a note the status line is read again, whatever another session stored a moment before', async ($, on) => {
  // Covers: B100
  const files: Files = new Map()
  const fake = new FakeM2b()
  const { clock, statuses } = await start($, on, fake, {}, files)
  expect(statuses.at(-1)).toBeUndefined()
  const snapshot = { candidates: [], review: null, error: null, shows: SHOWN_WITHOUT_ENTRY }
  const other = { writtenAtMs: clock.now(), value: { snapshot, status: null, version: '0.3.0' } }
  files.set(`${HOME}/.local/state/m2b/band-answer.json`, JSON.stringify(other))
  fake.status = TROUBLED_STATUS
  const before = fake.calls.length

  await typed($, 'Sam brings the plywood')
  await clock.advance(1)

  expect(fake.calls.slice(before).map(call => call.slice(0, 2))).toEqual([
    ['capture', '--source'],
    ['band', '--json'],
  ])
  expect(statuses.at(-1)).toBe(TROUBLE_LINE)
})

test('a setup check that cannot look is one line too', async ($, on) => {
  // Covers: B100
  const fake = new FakeM2b()
  await start($, on, fake)
  fake.existsFails = true
  const answer = await typed($, 'Sam brings the plywood')
  expect(answer.text).toStartWith('not noted: could not look whether m2b is set up: ')
  expect(fake.captured).toEqual([])
})

test('a text of escape codes alone notes nothing', async ($, on) => {
  // Covers: B100
  const fake = new FakeM2b()
  await start($, on, fake)
  const answer = await typed($, '\u001b[31m\u001b[0m')
  expect(fake.captured).toEqual([])
  expect(answer.text).toStartWith('nothing noted:')
})

test('the confirmation never cuts an emoji in half', async ($, on) => {
  // Covers: B100
  await start($, on, new FakeM2b())
  const answer = await typed($, `${'a'.repeat(49)}\u{1f6e0}\u{1f6e0} and more`)
  expect(answer.text).toBe(`noted: ${'a'.repeat(49)}\u{1f6e0}…`)
})

test('with --due tomorrow the note gets a task due the next day on the owner clock, and the answer names it', async ($, on) => {
  // Covers: B317
  const fake = new FakeM2b()
  await start($, on, fake)

  const answer = await typed($, '--due tomorrow Call Sam about the long boards')

  expect(fake.captured).toEqual(['Call Sam about the long boards'])
  expect(fake.captureArgs).toEqual([['capture', '--source', 'claude', '--json', '--follow-up', TOMORROW, '-']])
  expect(answer.text).toBe(`noted: Call Sam about the long boards; a task is due ${inWords(TOMORROW)}`)
})

test('with --due today or a day as YYYY-MM-DD the task is due that day', async ($, on) => {
  // Covers: B317
  const fake = new FakeM2b()
  await start($, on, fake)

  await typed($, '--due today Call Sam')
  const answer = await typed($, '--due=2027-01-04 Return the ladder')

  expect(fake.captureArgs.map(args => args[5])).toEqual([TODAY, '2027-01-04'])
  expect(fake.captured).toEqual(['Call Sam', 'Return the ladder'])
  expect(answer.text).toBe('noted: Return the ladder; a task is due 4 Jan 2027')
})

test('today and tomorrow are the days of the owner clock, also where UTC has another day', () => {
  // Covers: B317
  const lateInZurich = Date.UTC(2026, 10, 25, 23, 30)
  expect(dayOf('today', lateInZurich, ZURICH)).toBe('2026-11-26')
  expect(dayOf('tomorrow', lateInZurich, ZURICH)).toBe('2026-11-27')
  const eveningInNewYork = Date.UTC(2026, 10, 26, 2, 0)
  expect(dayOf('today', eveningInNewYork, NEW_YORK)).toBe('2026-11-25')
  expect(dayOf('tomorrow', eveningInNewYork, NEW_YORK)).toBe('2026-11-26')
  // The night summer time ends in Zurich: tomorrow is the next date, not the same one twice.
  const beforeTheChange = Date.UTC(2026, 9, 24, 22, 30)
  expect(dayOf('tomorrow', beforeTheChange, ZURICH)).toBe('2026-10-26')
})

test('a day that is no day writes nothing and names the forms that are taken', async ($, on) => {
  // Covers: B317
  const fake = new FakeM2b()
  await start($, on, fake)
  const forms = 'nothing noted: --due takes today, tomorrow or YYYY-MM-DD'

  expect((await typed($, '--due monday Call Sam')).text).toBe(`${forms}, not monday`)
  expect((await typed($, '--due 2026-02-30 Call Sam')).text).toBe(`${forms}, not 2026-02-30`)
  expect((await typed($, '--due')).text).toBe(`${forms}, before the text`)
  expect(fake.calls.filter(call => call[0] === 'capture')).toEqual([])
})

test('a day without a text writes nothing and says what it needs', async ($, on) => {
  // Covers: B317
  const fake = new FakeM2b()
  await start($, on, fake)
  const answer = await typed($, '--due tomorrow   ')
  expect(fake.calls.filter(call => call[0] === 'capture')).toEqual([])
  expect(answer.text).toBe('nothing noted: write the text after the day, as in /m2b-note --due tomorrow Call Sam')
})

test('where the task list cannot be reached the note is written and the answer says so in the core words', async ($, on) => {
  // Covers: B317
  const fake = new FakeM2b()
  fake.captureNotice = 'the follow-up task waits for the next curation run: Reminders did not answer'
  await start($, on, fake)

  const answer = await typed($, '--due tomorrow Call Sam')

  expect(fake.captured).toEqual(['Call Sam'])
  expect(answer.text).toBe('noted: Call Sam; the follow-up task waits for the next curation run: Reminders did not answer')
})

test('a note whose task could not be confirmed says it was noted, never "not noted"', async ($, on) => {
  // Covers: B317
  const fake = new FakeM2b()
  fake.captureFails = 'inbox/20260314-173000-claude-ab12.md was captured, but its follow-up task: the list did not answer'
  await start($, on, fake)

  const answer = await typed($, '--due tomorrow Call Sam')

  expect(answer.text).toBe(
    'noted: Call Sam; inbox/20260314-173000-claude-ab12.md was captured, but its follow-up task: the list did not answer',
  )
})

test('a word that only begins with --due is part of the text', async ($, on) => {
  // Covers: B317
  const fake = new FakeM2b()
  await start($, on, fake)
  await typed($, '--duel at dawn is a film title')
  expect(fake.captured).toEqual(['--duel at dawn is a film title'])
  expect(fake.captureArgs).toEqual([['capture', '--source', 'claude', '-']])
})
