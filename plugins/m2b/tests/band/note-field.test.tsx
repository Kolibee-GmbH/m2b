import { expect, test } from 'claude-code/testing'

import { daysFromToday } from '../../hooks/note'
import { FakeM2b, NOW, PARTS, SESSION_ID, inView, noteLines, pane, start, startView, texts } from './harness'

const FIELD = 'note:field'
const UNDO = 'undo:note'
const UNDO_MS = 5_000
const EMPTY = ['note: (what to keep)', '● no day [today] [tomorrow] [in a week]']
const MONTH_NAMES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const inWords = (day: string) => `${Number(day.slice(8))} ${MONTH_NAMES[Number(day.slice(5, 7)) - 1]}`

type Mounted = Awaited<ReturnType<typeof startView>>

/** Types `text` into the field key by key, as the person does: each change reaches the module. */
async function typeInto(ui: Mounted, text: string): Promise<void> {
  await ui.input({ key: FIELD, text, kind: 'change' })
}

/** Types `text` and presses Enter. */
async function keep(ui: Mounted, text: string): Promise<void> {
  await typeInto(ui, text)
  await ui.input({ key: FIELD, text })
}

test('the overview draws the field note above its parts, and below it the day as four values, no day in force', async ($, on) => {
  // Covers: B318
  await start($, on, new FakeM2b())
  const ui = await startView($)

  expect(await noteLines(ui)).toEqual(EMPTY)
  const drawn = (await ui.findAll({})).map(found => found.key ?? '')
  expect(drawn.indexOf('note')).toBeLessThan(drawn.findIndex(key => key.startsWith('part:') || key === 'quiet'))
  expect((await ui.find({ key: FIELD }))?.props['submitLabel']).toBe('keep')
  await ui.unmount()
})

test('below 36 columns the field has no label, only its placeholder', async ($, on) => {
  // Covers: B318
  await start($, on, new FakeM2b())
  const ui = await $.ui.mount({ ...pane('m2b', 24), surface: 'terminal' })
  expect((await noteLines(ui))?.[0]).toBe('(note)')
  await ui.unmount()
})

test('a text and Enter offer undo for five seconds, then one capture is written, the field is empty and the session counts the note', async ($, on) => {
  // Covers: B318
  const fake = new FakeM2b()
  const { clock } = await start($, on, fake)
  const ui = await startView($)

  await keep(ui, 'Sam brings the plywood')
  expect(await noteLines(ui)).toEqual(['[undo] keeping', 'Sam brings the plywood'])
  await clock.advance(UNDO_MS - 1)
  expect(fake.captured).toEqual([])
  await clock.advance(1)

  expect(fake.captured).toEqual(['Sam brings the plywood'])
  expect(fake.captureArgs).toEqual([['capture', '--source', 'claude', '-']])
  expect(await noteLines(ui)).toEqual([...EMPTY, 'noted: Sam brings the plywood'])
  expect(await texts(ui)).toContain('1 note written in this session')
  await ui.unmount()
})

test('a day chosen below the field makes the capture a follow-up due that day, and the next note starts without a day', async ($, on) => {
  // Covers: B318
  const fake = new FakeM2b()
  const { clock } = await start($, on, fake)
  const ui = await startView($)
  const inAWeek = daysFromToday(7, NOW)

  await ui.press({ key: 'note:day:week' })
  expect((await noteLines(ui))?.[1]).toBe('[no day] [today] [tomorrow] ● in a week')
  await keep(ui, 'Return the ladder')
  expect(await noteLines(ui)).toEqual(['[undo] keeping, with a task due in a week', 'Return the ladder'])
  await clock.advance(UNDO_MS)

  expect(fake.captureArgs).toEqual([['capture', '--source', 'claude', '--json', '--follow-up', inAWeek, '-']])
  expect(await noteLines(ui)).toEqual([...EMPTY, `noted: Return the ladder; a task is due ${inWords(inAWeek)}`])
  await ui.unmount()
})

test('an empty text and Enter write nothing', async ($, on) => {
  // Covers: B318
  const fake = new FakeM2b()
  const { clock } = await start($, on, fake)
  const ui = await startView($)

  await keep(ui, '   ')
  await clock.advance(UNDO_MS * 2)

  expect(fake.calls.filter(call => call[0] === 'capture')).toEqual([])
  expect(await noteLines(ui)).toEqual(EMPTY)
  await ui.unmount()
})

test('undo writes nothing and puts the text and its day back in the field', async ($, on) => {
  // Covers: B318
  const fake = new FakeM2b()
  const { clock } = await start($, on, fake)
  const ui = await startView($)

  await ui.press({ key: 'note:day:tomorrow' })
  await keep(ui, 'Call Sam')
  await clock.advance(UNDO_MS - 1_000)
  await ui.press({ key: UNDO })
  await clock.advance(UNDO_MS * 2)

  expect(fake.calls.filter(call => call[0] === 'capture')).toEqual([])
  expect(await noteLines(ui)).toEqual(['note: Call Sam', '[no day] [today] ● tomorrow [in a week]'])
  await ui.unmount()
})

test('a note m2b could not write says why and puts the text back in the field', async ($, on) => {
  // Covers: B318
  const fake = new FakeM2b()
  fake.captureFails = 'the inbox is not writable: /home/alex/Notes/inbox'
  const { clock } = await start($, on, fake)
  const ui = await startView($)

  await keep(ui, 'Call Sam')
  await clock.advance(UNDO_MS)

  expect(await noteLines(ui)).toEqual([
    'note: Call Sam',
    EMPTY[1],
    'not noted: the inbox is not writable: /home/alex/Notes/inbox',
  ])
  expect(await texts(ui)).not.toContain('1 note written in this session')
  await ui.unmount()
})

test('a text half typed and the day chosen stay as they were over a read of the band and a pane opened again', async ($, on) => {
  // Covers: B319
  const { clock } = await start($, on, new FakeM2b())
  let ui = await startView($)

  await ui.press({ key: 'note:day:today' })
  await typeInto(ui, 'Sam brings the ply')
  await clock.advance(61_000)
  expect(await noteLines(ui)).toEqual(['note: Sam brings the ply', '[no day] ● today [tomorrow] [in a week]'])

  await ui.unmount()
  ui = await startView($)
  expect(await noteLines(ui)).toEqual(['note: Sam brings the ply', '[no day] ● today [tomorrow] [in a week]'])
  await ui.unmount()
})

test('a session that starts again starts with an empty field and no day', async ($, on) => {
  // Covers: B319
  await start($, on, new FakeM2b())
  const ui = await startView($)
  await ui.press({ key: 'note:day:today' })
  await typeInto(ui, 'Sam brings the ply')

  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })

  expect(await noteLines(ui)).toEqual(EMPTY)
  await ui.unmount()
})

test('after /clear the field is empty, without a day and without what the last write said', async ($, on) => {
  // Covers: B319
  const { clock } = await start($, on, new FakeM2b())
  const ui = await startView($)
  await keep(ui, 'Sam brings the plywood')
  await clock.advance(UNDO_MS)
  await ui.press({ key: 'note:day:tomorrow' })
  await typeInto(ui, 'Call Dana')

  await $.session.end({ reason: 'clear', sessionId: SESSION_ID, resume: { id: SESSION_ID } })

  expect(await noteLines(ui)).toEqual(EMPTY)
  await ui.unmount()
})

test('what is typed is written into no state of the session, half typed, waiting or written', async ($, on) => {
  // Covers: B319
  const written: string[] = []
  // Every value m2b writes to the session's state passes here, as a hook of another plugin sees it.
  on('state.set', { plugin: 'm2b' }, async ($state, e, next) => {
    written.push(JSON.stringify(e.value))
    return next(e)
  })
  const fake = new FakeM2b()
  const { clock } = await start($, on, fake)
  const ui = await startView($)

  await ui.press({ key: 'note:day:tomorrow' })
  await keep(ui, 'Dana keeps the spare key')
  await clock.advance(UNDO_MS)

  expect(fake.captured).toEqual(['Dana keeps the spare key'])
  expect(written.some(value => value.includes('"tomorrow"'))).toBe(true)
  expect(written.filter(value => value.includes('spare key'))).toEqual([])
  await ui.unmount()
})

test('the typed text is drawn as a plain line: an escape code is not drawn and a line break is a space', async ($, on) => {
  // Covers: B318
  const fake = new FakeM2b()
  await start($, on, fake)
  const ui = await startView($)

  await keep(ui, 'Sam \u001b[31mbrings\u001b[0m the\nplywood')

  expect((await noteLines(ui))?.[1]).toBe('Sam brings the plywood')
  await ui.unmount()
})

test('the field leaves the parts of the overview as they were', async ($, on) => {
  // Covers: B318
  await start($, on, new FakeM2b())
  const ui = await startView($)
  const lines = await texts(ui)
  expect(lines.some(line => line.includes('what to keep') || line.includes('no day'))).toBe(false)
  expect(lines.includes(PARTS.waits) || lines.some(line => line.startsWith('Nothing waits'))).toBe(true)
  expect((await inView(ui, 'Button')).map(button => button.key ?? '').some(key => key.startsWith('note:'))).toBe(false)
  await ui.unmount()
})
