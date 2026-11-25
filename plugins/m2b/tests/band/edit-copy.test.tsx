import { expect, test } from 'claude-code/testing'

import type { Engine } from 'claude-code/testing'

import { focusAfterUndo } from '../../hooks/edit-copy'

import { CURATE_NOW, CURATE_NOW_CALL, FakeM2b, STATUS, STATUS_ELSEWHERE, editCopyPath, fail, linesAt, lookOf, pane, partLines, pressTab, start } from './harness'

const PANE = 'm2b'
const EDIT = 'fact:edit'
const EDITING = 'fact:editing'
const KEEP = 'fact:edit:keep'
const DISCARD = 'fact:edit:discard'
const UNDO = 'undo:edit'
const WAITING = 'fact:corrections'
const FACT_TAB = 'tab:fact:shown'
const UNDO_MS = 5_000
const COPY = editCopyPath('dana.md')
const TROUBLE = { color: 'error', dimColor: undefined, wrap: 'wrap' }

const OPEN = ['store', 'edit', '--json', '--', 'dana.md']
const KEEP_CALL = ['store', 'edit', '--json', '--keep', '--', 'dana.md']
const DISCARD_CALL = ['store', 'edit', '--json', '--discard', '--', 'dana.md']

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

/** The copy saved in the editor so that it differs from the fact file, and the view read again by its tab. */
async function savedInTheEditor(ui: Awaited<ReturnType<typeof factFileView>>, fake: FakeM2b): Promise<void> {
  fake.edits['dana.md'] = { differs: true, factFileChanged: false }
  await ui.press({ key: FACT_TAB })
}

test("a fact file's view has edit beside correct; a press makes the copy and the view names it whole, with discard", async ($, on) => {
  // Covers: B322
  const fake = busyFake()
  await start($, on, fake)
  const ui = await factFileView($)
  expect((await linesAt(ui, 'part:fact'))?.slice(0, 3)).toEqual(['Dana', '[correct] [edit]', 'My sister.'])

  await ui.press({ key: EDIT })

  expect(fake.editCalls()).toEqual([OPEN])
  expect(await linesAt(ui, EDITING)).toEqual(['an editing copy is open', COPY, '[discard]'])
  expect((await linesAt(ui, 'part:fact'))?.slice(0, 5)).toEqual(['Dana', '[correct] [edit]', 'an editing copy is open', COPY, '[discard]'])
  await ui.unmount()
})

test("the fact file's tab reads the file again, and a copy saved so it differs offers keep the edit and discard", async ($, on) => {
  // Covers: B322
  const fake = busyFake()
  await start($, on, fake)
  const ui = await factFileView($)
  await ui.press({ key: EDIT })
  const reads = fake.sourceCalls().length

  await savedInTheEditor(ui, fake)

  expect(fake.sourceCalls().length).toBe(reads + 1)
  expect(await linesAt(ui, EDITING)).toEqual(['your copy differs from the fact file', COPY, '[keep the edit] [discard]'])
  await ui.unmount()
})

test('a fact file that changed since the copy was made offers discard alone', async ($, on) => {
  // Covers: B322
  const fake = busyFake()
  fake.edits['dana.md'] = { differs: true, factFileChanged: true }
  await start($, on, fake)
  const ui = await factFileView($)

  expect(await linesAt(ui, EDITING)).toEqual(['the fact file changed since you opened the copy', COPY, '[discard]'])
  await ui.unmount()
})

test('keep the edit offers undo for five seconds, then keeps the copy, and the view says the edit waits for the next run', async ($, on) => {
  // Covers: B323
  const fake = busyFake()
  const { clock } = await start($, on, fake)
  const ui = await factFileView($)
  await ui.press({ key: EDIT })
  await savedInTheEditor(ui, fake)

  await ui.press({ key: KEEP })
  expect(await linesAt(ui, EDITING)).toEqual(['[undo] keeping the edit'])
  await clock.advance(UNDO_MS - 1)
  expect(fake.editCalls()).toEqual([OPEN])
  await clock.advance(1)

  expect(fake.editCalls()).toEqual([OPEN, KEEP_CALL])
  expect(await linesAt(ui, EDITING)).toBeNull()
  expect(await linesAt(ui, WAITING)).toEqual(['your edit waits for the next curation run', '[curate now]'])
  await ui.press({ key: CURATE_NOW })
  await clock.advance(UNDO_MS)
  expect(fake.curateCalls()).toEqual([CURATE_NOW_CALL])
  await ui.unmount()
})

test('undo of keep the edit keeps nothing, and the copy stays as it was', async ($, on) => {
  // Covers: B323
  const fake = busyFake()
  const { clock } = await start($, on, fake)
  const ui = await factFileView($)
  await ui.press({ key: EDIT })
  await savedInTheEditor(ui, fake)

  await ui.press({ key: KEEP })
  await ui.press({ key: UNDO })
  await clock.advance(UNDO_MS * 2)

  expect(fake.editCalls()).toEqual([OPEN])
  expect(await linesAt(ui, EDITING)).toEqual(['your copy differs from the fact file', COPY, '[keep the edit] [discard]'])
  await ui.unmount()
})

test('discard offers undo for five seconds, then removes the copy and keeps nothing', async ($, on) => {
  // Covers: B323
  const fake = busyFake()
  const { clock } = await start($, on, fake)
  const ui = await factFileView($)
  await ui.press({ key: EDIT })
  await savedInTheEditor(ui, fake)

  await ui.press({ key: DISCARD })
  expect(await linesAt(ui, EDITING)).toEqual(['[undo] discarding the copy'])
  await clock.advance(UNDO_MS)

  expect(fake.editCalls()).toEqual([OPEN, DISCARD_CALL])
  expect(fake.keptEdits).toEqual({})
  expect(await linesAt(ui, EDITING)).toBeNull()
  expect(await linesAt(ui, WAITING)).toBeNull()
  await ui.unmount()
})

test('a copy m2b would not keep says why in the error color, and the copy stays', async ($, on) => {
  // Covers: B323
  const fake = busyFake()
  fake.keepRefusal = fail('the copy of dana.md is empty; m2b store edit --discard dana.md drops it')
  const { clock } = await start($, on, fake)
  const ui = await factFileView($)
  await ui.press({ key: EDIT })
  await savedInTheEditor(ui, fake)

  await ui.press({ key: KEEP })
  await clock.advance(UNDO_MS)

  const notKept = 'not kept: the copy of dana.md is empty; m2b store edit --discard dana.md drops it'
  expect(await linesAt(ui, EDITING)).toEqual(['your copy differs from the fact file', COPY, '[keep the edit] [discard]', notKept])
  expect(await lookOf(ui, notKept)).toEqual(TROUBLE)
  await ui.unmount()
})

test('a press while a run is under way says what m2b said, in the error color, and makes no copy', async ($, on) => {
  // Covers: B322
  const fake = busyFake()
  const refusal = 'a curation run is under way; edit the fact file once it has finished'
  fake.editRefusal = fail(refusal)
  await start($, on, fake)
  const ui = await factFileView($)

  await ui.press({ key: EDIT })

  expect(await linesAt(ui, EDITING)).toEqual([refusal])
  expect(await lookOf(ui, refusal)).toEqual(TROUBLE)
  expect(fake.edits).toEqual({})
  await ui.unmount()
})

test('a fact file that lives only in the cloud is named with the command that fetches it', async ($, on) => {
  // Covers: B322
  const fake = busyFake()
  const refusal = 'memory/dana.md is not downloaded to this machine; m2b fetch memory/dana.md fetches it'
  fake.editRefusal = fail(refusal)
  await start($, on, fake)
  const ui = await factFileView($)

  await ui.press({ key: EDIT })

  expect(await linesAt(ui, EDITING)).toEqual([refusal])
  await ui.unmount()
})

test('in a session without a screen the view names the path alone', async ($, on) => {
  // Covers: B322
  const fake = busyFake()
  fake.editNotOpened = 'this session runs over SSH: the file would open on a screen nobody at it sees'
  await start($, on, fake)
  const ui = await factFileView($)

  await ui.press({ key: EDIT })

  expect(await linesAt(ui, EDITING)).toEqual(['an editing copy is open', COPY, '[discard]'])
  await ui.unmount()
})

test('a kept edit that waits is named on the machine that does not curate with the machine that does', async ($, on) => {
  // Covers: B323
  const fake = busyFake()
  fake.status = STATUS_ELSEWHERE
  fake.keptEdits['dana.md'] = ['20261125T101500Z-cli-ef56.md']
  await start($, on, fake)
  const ui = await factFileView($)

  expect(await linesAt(ui, WAITING)).toEqual(['your edit waits for the next curation run on tower-2'])
  await ui.unmount()
})

test('a correction and a kept edit that wait share one line about the run and one curate now', async ($, on) => {
  // Covers: B323
  const fake = busyFake()
  fake.corrections['dana.md'] = [{ capture: '20261125T080000Z-claude-ab12.md', first_line: 'Dana lives in Porto now.' }]
  fake.keptEdits['dana.md'] = ['20261125T101500Z-cli-ef56.md']
  await start($, on, fake)
  const ui = await factFileView($)

  expect(await linesAt(ui, WAITING)).toEqual([
    '1 correction waits for the next curation run:',
    '“Dana lives in Porto now.”',
    'your edit waits for the next curation run',
    '[curate now]',
  ])
  await ui.unmount()
})

test('once a run under way ends, the view reads the file again and no longer names the edit it put in place', async ($, on) => {
  // Covers: B323
  const fake = busyFake()
  fake.status = { ...STATUS, run: { state: 'running' } }
  fake.keptEdits['dana.md'] = ['20261125T101500Z-cli-ef56.md']
  const { clock } = await start($, on, fake)
  const ui = await factFileView($)

  fake.sourceAnswer = { ...danaFile(), lines: ['My sister.', 'Lives in Porto.'] }
  fake.keptEdits['dana.md'] = []
  fake.status = STATUS
  await clock.advance(60_000)

  expect(await linesAt(ui, 'part:fact')).toEqual(['Dana', '[correct] [edit]', 'My sister.', 'Lives in Porto.'])
  await ui.unmount()
})

test('a copy that differs and is not kept is counted in the part about m2b, and no state of the session names the file or the copy', async ($, on) => {
  // Covers: B324
  const written: string[] = []
  on('state.set', { plugin: 'm2b' }, async (_, e, next) => {
    written.push(JSON.stringify(e.value))
    return next(e)
  })
  const fake = busyFake()
  fake.edits['dana.md'] = { differs: true, factFileChanged: false }
  await start($, on, fake)
  await $.command.run({ command: 'm2b-pane', args: '', origin: { kind: 'composer' }, presentation: { isFullscreen: false, columns: 100 } })
  const ui = await $.ui.mount({ ...pane(PANE, 80), surface: 'terminal' })

  expect(await partLines(ui, 'm2b')).toContain('1 edited copy not kept yet')
  await pressTab(ui, 'facts')
  await ui.press({ key: 'details:0' })
  await ui.press({ key: EDIT })
  expect(written.filter(value => value.includes('dana.md') || value.includes('edits/'))).toEqual([])
  await ui.unmount()
})

test('two copies that differ are counted as copies; one that does not differ is not counted', async ($, on) => {
  // Covers: B324
  const fake = busyFake()
  fake.edits['dana.md'] = { differs: true, factFileChanged: false }
  fake.edits['sam.md'] = { differs: true, factFileChanged: false }
  fake.edits['alex.md'] = { differs: false, factFileChanged: false }
  await start($, on, fake)
  await $.command.run({ command: 'm2b-pane', args: '', origin: { kind: 'composer' }, presentation: { isFullscreen: false, columns: 100 } })
  const ui = await $.ui.mount({ ...pane(PANE, 80), surface: 'terminal' })

  expect(await partLines(ui, 'm2b')).toContain('2 edited copies not kept yet')
  await ui.unmount()
})

test('a second press on edit while the core makes the copy starts nothing', async ($, on) => {
  // Covers: B322
  const fake = busyFake()
  fake.delayMs = args => (args[0] === 'store' && args[1] === 'edit' ? 2_000 : 0)
  const { clock } = await start($, on, fake)
  const ui = await factFileView($)

  const first = ui.press({ key: EDIT })
  await clock.advance(1)
  await ui.press({ key: EDIT })
  await clock.advance(2_000)
  await first

  expect(fake.editCalls()).toEqual([OPEN])
  await ui.unmount()
})

test("a copy saved after the band last read is counted in the overview once the fact file's tab read it again", async ($, on) => {
  // Covers: B324
  const fake = busyFake()
  const { clock } = await start($, on, fake)
  const ui = await factFileView($)
  await ui.press({ key: EDIT })
  // Every read the opening of the views asked for has run: the band last read before the save.
  await clock.advance(1)
  const reads = fake.calls.filter(call => call[0] === 'band').length

  await savedInTheEditor(ui, fake)
  await clock.advance(1)

  expect(fake.calls.filter(call => call[0] === 'band').length).toBe(reads + 1)
  await pressTab(ui, 'overview')
  expect(await partLines(ui, 'm2b')).toContain('1 edited copy not kept yet')
  await ui.unmount()
})

test('edit stays beside an open correction field, and a correction field left empty keeps it reachable', async ($, on) => {
  // Covers: B322
  const fake = busyFake()
  await start($, on, fake)
  const ui = await factFileView($)

  await ui.press({ key: 'fact:correct' })
  expect(await linesAt(ui, 'fact:correcting')).toEqual(['what is right: (the fact as it should read)', '[edit]'])
  await ui.press({ key: EDIT })

  expect(fake.editCalls()).toEqual([OPEN])
  await ui.unmount()
})

// The kit shows no move of the focus the mod asks for (see the tabs' tests): the key it names is held here.
test('undo of keep the edit asks for the focus on keep the edit, undo of discard on discard', () => {
  // Covers: B323
  expect(focusAfterUndo('keep the edit')).toBe(KEEP)
  expect(focusAfterUndo('discard')).toBe(DISCARD)
})

test('a core from before the copies names no count, and the part about m2b says nothing of copies', async ($, on) => {
  // Covers: B324
  const fake = busyFake()
  fake.countsEdits = false
  fake.edits['dana.md'] = { differs: true, factFileChanged: false }
  await start($, on, fake)
  await $.command.run({ command: 'm2b-pane', args: '', origin: { kind: 'composer' }, presentation: { isFullscreen: false, columns: 100 } })
  const ui = await $.ui.mount({ ...pane(PANE, 80), surface: 'terminal' })

  expect(((await partLines(ui, 'm2b')) ?? []).filter(line => line.includes('edited cop'))).toEqual([])
  await ui.unmount()
})
