import { expect, test } from 'claude-code/testing'

import type { Engine } from 'claude-code/testing'

import { CURATE_NOW, CURATE_NOW_CALL, FakeM2b, SESSION_ID, STATUS, STATUS_ELSEWHERE, UNDO_CURATE, linesAt, pane, pressTab, start } from './harness'

const PANE = 'm2b'
const CORRECT = 'fact:correct'
const FIELD = 'fact:correct:field'
const UNDO = 'undo:correct'
const CORRECTING = 'fact:correcting'
const WAITING = 'fact:corrections'
const UNDO_MS = 5_000
const RIGHT = 'Dana lives in Porto now.'

/** Dana's fact file as `m2b source --json` names it: two lines, no evidence. */
function danaFile(): Record<string, unknown> {
  return { name: 'dana.md', kind: 'fact file', path: 'memory/dana.md', title: 'Dana', until: null, lines: ['My sister.', 'Lives in Zurich.'], earlier: [], evidence: [] }
}

function busyFake(): FakeM2b {
  const fake = new FakeM2b()
  fake.distillate = { facts: [{ statement: 'Dana is my sister', file: 'dana.md' }], current: [], topics: [] }
  fake.sourceAnswer = danaFile()
  return fake
}

/** The pane turned to Dana's fact file, from the tab Facts. */
async function factFileView($: Engine, columns = 80) {
  await $.command.run({ command: 'm2b-pane', args: '', origin: { kind: 'composer' }, presentation: { isFullscreen: false, columns: 100 } })
  const ui = await $.ui.mount({ ...pane(PANE, columns), surface: 'terminal' })
  await pressTab(ui, 'facts')
  await ui.press({ key: 'details:0' })
  return ui
}

type Mounted = Awaited<ReturnType<typeof factFileView>>

async function correctWith(ui: Mounted, text: string): Promise<void> {
  await ui.press({ key: CORRECT })
  await ui.input({ key: FIELD, text, kind: 'change' })
  await ui.input({ key: FIELD, text })
}

test("a fact file's view has correct under its title, and a press draws the field what is right", async ($, on) => {
  // Covers: B320
  await start($, on, busyFake())
  const ui = await factFileView($)

  expect((await linesAt(ui, 'part:fact'))?.slice(0, 3)).toEqual(['Dana', '[correct]', 'My sister.'])
  await ui.press({ key: CORRECT })

  expect(await linesAt(ui, CORRECTING)).toEqual(['what is right: (the fact as it should read)'])
  expect((await ui.find({ key: FIELD }))?.props['submitLabel']).toBe('keep')
  await ui.unmount()
})

test('a text and Enter offer undo for five seconds, then the correction is captured about the fact file and the view names it as it waits', async ($, on) => {
  // Covers: B320
  const fake = busyFake()
  const { clock } = await start($, on, fake)
  const ui = await factFileView($)

  await correctWith(ui, RIGHT)
  expect(await linesAt(ui, CORRECTING)).toEqual(['[undo] correcting', RIGHT])
  await clock.advance(UNDO_MS - 1)
  expect(fake.captured).toEqual([])
  await clock.advance(1)

  expect(fake.captured).toEqual([RIGHT])
  expect(fake.captureArgs).toEqual([['capture', '--source', 'claude', '--about', 'dana.md', '-']])
  expect(await linesAt(ui, CORRECTING)).toEqual(['[correct]'])
  expect(await linesAt(ui, WAITING)).toEqual(['1 correction waits for the next curation run:', `“${RIGHT}”`, '[curate now]'])
  await ui.unmount()
})

test('curate now beside the correction starts a run as it does in the overview', async ($, on) => {
  // Covers: B321
  const fake = busyFake()
  fake.corrections['dana.md'] = [{ capture: '20261125T080000Z-claude-ab12.md', first_line: RIGHT }]
  const { clock } = await start($, on, fake)
  const ui = await factFileView($)

  await ui.press({ key: CURATE_NOW })
  expect((await linesAt(ui, WAITING))?.at(-1)).toBe('[undo] starting a curation run')
  expect((await ui.find({ key: UNDO_CURATE }))?.type).toBe('Button')
  await clock.advance(UNDO_MS)

  expect(fake.curateCalls()).toEqual([CURATE_NOW_CALL])
  await ui.unmount()
})

test('on a machine that does not curate the line names the machine that does, with nothing to press', async ($, on) => {
  // Covers: B321
  const fake = busyFake()
  fake.status = STATUS_ELSEWHERE
  fake.corrections['dana.md'] = [{ capture: '20261125T080000Z-claude-ab12.md', first_line: RIGHT }]
  await start($, on, fake)
  const ui = await factFileView($)

  expect(await linesAt(ui, WAITING)).toEqual(['1 correction waits for the next curation run on tower-2:', `“${RIGHT}”`])
  await ui.unmount()
})

test('the view opened again before a run names the correction that waits, read from the core', async ($, on) => {
  // Covers: B321
  const fake = busyFake()
  fake.corrections['dana.md'] = [
    { capture: '20261125T080000Z-claude-ab12.md', first_line: RIGHT },
    { capture: '20261125T090000Z-claude-cd34.md', first_line: 'Birthday on 4 March.' },
  ]
  await start($, on, fake)
  const ui = await factFileView($)

  expect((await linesAt(ui, WAITING))?.slice(0, 3)).toEqual(['2 corrections wait for the next curation run:', `“${RIGHT}”`, '“Birthday on 4 March.”'])
  await ui.unmount()
})

test('once a run under way ends, the view reads its fact file again and names what the core says now', async ($, on) => {
  // Covers: B321
  const fake = busyFake()
  fake.status = { ...STATUS, run: { state: 'running' } }
  fake.corrections['dana.md'] = [{ capture: '20261125T080000Z-claude-ab12.md', first_line: RIGHT }]
  const { clock } = await start($, on, fake)
  const ui = await factFileView($)
  expect((await linesAt(ui, WAITING))?.at(-1)).toBe('A curation run is under way.')

  // The run applied the correction: the file says what is right, and nothing waits.
  fake.sourceAnswer = { ...danaFile(), lines: ['My sister.', RIGHT] }
  fake.corrections['dana.md'] = []
  fake.status = STATUS
  await clock.advance(60_000)

  expect(await linesAt(ui, 'part:fact')).toEqual(['Dana', '[correct]', 'My sister.', RIGHT])
  expect(await linesAt(ui, WAITING)).toBeNull()
  await ui.unmount()
})

test("a field opened for another fact file while a correction waits keeps what is typed there when that correction lands", async ($, on) => {
  // Covers: B321
  const fake = busyFake()
  fake.distillate = { facts: [{ statement: 'Dana is my sister', file: 'dana.md' }, { statement: 'Sam lends us the ladder', file: 'sam.md' }], current: [], topics: [] }
  const { clock } = await start($, on, fake)
  const ui = await factFileView($)

  await correctWith(ui, RIGHT)
  await pressTab(ui, 'facts')
  await ui.press({ key: 'details:1' })
  await ui.press({ key: CORRECT })
  await ui.input({ key: FIELD, text: 'Sam lends the long ladder', kind: 'change' })
  await clock.advance(UNDO_MS)

  expect(fake.captureArgs).toEqual([['capture', '--source', 'claude', '--about', 'dana.md', '-']])
  expect(await linesAt(ui, CORRECTING)).toEqual(['what is right: Sam lends the long ladder'])
  await ui.unmount()
})

test('each fact file keeps its own draft: one typed for another file leaves it as it was', async ($, on) => {
  // Covers: B321
  const fake = busyFake()
  fake.distillate = { facts: [{ statement: 'Dana is my sister', file: 'dana.md' }, { statement: 'Sam lends us the ladder', file: 'sam.md' }], current: [], topics: [] }
  await start($, on, fake)
  const ui = await factFileView($)
  await ui.press({ key: CORRECT })
  await ui.input({ key: FIELD, text: 'Dana lives in Por', kind: 'change' })

  await pressTab(ui, 'facts')
  await ui.press({ key: 'details:1' })
  await ui.press({ key: CORRECT })
  await ui.input({ key: FIELD, text: 'Sam lends the long', kind: 'change' })
  await pressTab(ui, 'facts')
  await ui.press({ key: 'details:0' })

  expect(await linesAt(ui, CORRECTING)).toEqual(['what is right: Dana lives in Por'])
  await ui.unmount()
})

test('undo writes nothing and puts the text back in the field', async ($, on) => {
  // Covers: B320
  const fake = busyFake()
  const { clock } = await start($, on, fake)
  const ui = await factFileView($)

  await correctWith(ui, RIGHT)
  await clock.advance(UNDO_MS - 1_000)
  await ui.press({ key: UNDO })
  await clock.advance(UNDO_MS * 2)

  expect(fake.calls.filter(call => call[0] === 'capture')).toEqual([])
  expect(await linesAt(ui, CORRECTING)).toEqual([`what is right: ${RIGHT}`])
  await ui.unmount()
})

test('an empty text and Enter write nothing and leave the field open', async ($, on) => {
  // Covers: B320
  const fake = busyFake()
  const { clock } = await start($, on, fake)
  const ui = await factFileView($)

  await correctWith(ui, '  ')
  await clock.advance(UNDO_MS * 2)

  expect(fake.calls.filter(call => call[0] === 'capture')).toEqual([])
  expect(await linesAt(ui, CORRECTING)).toEqual(['what is right: (the fact as it should read)'])
  await ui.unmount()
})

test('a correction m2b could not write says why and puts the text back in the field', async ($, on) => {
  // Covers: B320
  const fake = busyFake()
  fake.captureFails = 'the inbox is not writable: /home/alex/Notes/inbox'
  const { clock } = await start($, on, fake)
  const ui = await factFileView($)

  await correctWith(ui, RIGHT)
  await clock.advance(UNDO_MS)

  expect(await linesAt(ui, CORRECTING)).toEqual([`what is right: ${RIGHT}`, 'not kept: the inbox is not writable: /home/alex/Notes/inbox'])
  await ui.unmount()
})

test('a text half typed is drawn again when the view of the same fact file is opened again, and gone after /clear', async ($, on) => {
  // Covers: B321
  await start($, on, busyFake())
  const ui = await factFileView($)
  await ui.press({ key: CORRECT })
  await ui.input({ key: FIELD, text: 'Dana lives in Por', kind: 'change' })

  // Escape in this view turns the pane to the overview: the field is gone from view, its text is not.
  await pressTab(ui, 'overview')
  await pressTab(ui, 'facts')
  await ui.press({ key: 'details:0' })
  expect(await linesAt(ui, CORRECTING)).toEqual(['what is right: Dana lives in Por'])

  await $.session.end({ reason: 'clear', sessionId: SESSION_ID, resume: { id: SESSION_ID } })
  await pressTab(ui, 'facts')
  await ui.press({ key: 'details:0' })
  expect(await linesAt(ui, CORRECTING)).toEqual(['[correct]'])
  await ui.unmount()
})

test('what is typed as a correction is written into no state of the session', async ($, on) => {
  // Covers: B321
  const written: string[] = []
  on('state.set', { plugin: 'm2b' }, async (_, e, next) => {
    written.push(JSON.stringify(e.value))
    return next(e)
  })
  const fake = busyFake()
  const { clock } = await start($, on, fake)
  const ui = await factFileView($)

  await correctWith(ui, RIGHT)
  await clock.advance(UNDO_MS)

  expect(fake.captured).toEqual([RIGHT])
  expect(written.filter(value => value.includes('Porto') || value.includes('dana.md'))).toEqual([])
  await ui.unmount()
})

test('below 36 columns the field has no label, only its placeholder', async ($, on) => {
  // Covers: B320
  await start($, on, busyFake())
  const ui = await factFileView($, 24)
  await ui.press({ key: CORRECT })
  expect(await linesAt(ui, CORRECTING)).toEqual(['(what is right)'])
  await ui.unmount()
})
