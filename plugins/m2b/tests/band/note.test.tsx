import { expect, test } from 'claude-code/testing'

import type { CommandRunResult } from 'claude-code'
import type { Engine } from 'claude-code/testing'

import { FakeM2b, HOME, start } from './harness'
import type { Files } from './harness'

const NOTE = 'm2b-note'

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

test('after a note the status line counts it, whatever another session stored a moment before', async ($, on) => {
  // Covers: B100
  const files: Files = new Map()
  const fake = new FakeM2b()
  const { clock, statuses } = await start($, on, fake, {}, files)
  const snapshot = { candidates: [], review: null, error: null }
  const other = { writtenAtMs: clock.now(), value: { snapshot, status: '2 in inbox', version: '0.3.0' } }
  files.set(`${HOME}/.local/state/m2b/band-view.json`, JSON.stringify(other))
  fake.status = { ...(fake.status as object), inbox: { count: 3, evicted: 0 } }

  await typed($, 'Sam brings the plywood')
  await clock.advance(1)

  expect(statuses.at(-1)).toBe('3 in inbox · curated 18:02')
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
