import { expect, test } from 'claude-code/testing'
import type { CommandRunResult } from 'claude-code'
import type { Engine } from 'claude-code/testing'

import { UNDO_ALL } from '../../hooks/proposals'
import { undoKey } from '../../hooks/rows'
import { UNDO_FOLDER } from '../../hooks/session-view'
import { FakeM2b, pane, start, texts } from './harness'

// After a press on keep, drop, ok, keep all or the folder's button the mod asks for the focus on
// that row's undo. A move it asks for fails in the kit and reaches no hook of a test, so what
// makes it work is held on the views as drawn: the key the mod names is a button once the press
// waits, and was none before. Claude Code looks a key up in what is drawn when the focus is asked
// for; one the view drew before the press would be found at its old place.

const PANE = 'm2b'
const DANA = 'a1a1a1a1a1a1'
const LADDER = 'b2b2b2b2b2b2'
const ACME = '/home/alex/code/acme'

function typed($: Engine, command: string): Promise<CommandRunResult> {
  return $.command.run({ command, args: '', origin: { kind: 'composer' }, presentation: { isFullscreen: false, columns: 100 } })
}

/** A session in a folder, with a candidate, a question, the review and two proposals to answer. */
function busyFake(): FakeM2b {
  const fake = new FakeM2b()
  fake.given = { topics: [{ name: 'Acme Ltd', facts: 3, current: 0 }], atStart: 'whole', offUnder: null, folder: ACME }
  fake.candidate('c1', 'Remember? Dana prefers tea')
  fake.question('q1', 'Still current? Planning the trip to Porto')
  fake.review('r1', ['lint: broken link in a.md'])
  fake.proposal(DANA, 'Dana is head of IT at Northwind.').proposal(LADDER, 'Call Sam about the ladder.')
  return fake
}

/** A press that waits for undo: what it is, the command of the view it is made in, its key, and the key of its row's undo. */
type Press = { what: string; command: string; key: string; undo: string; says: string; arrange?: (fake: FakeM2b) => void }

const PRESSES: readonly Press[] = [
  { what: 'keep on a candidate in the start view', command: 'm2b-pane', key: 'keep:c1', undo: undoKey('c1'), says: 'keeping: Remember? Dana prefers tea' },
  { what: 'drop on a candidate in the start view', command: 'm2b-pane', key: 'drop:c1', undo: undoKey('c1'), says: 'dropping: Remember? Dana prefers tea' },
  {
    what: 'drop on a question in the start view',
    command: 'm2b-pane',
    key: 'drop:q1',
    undo: undoKey('q1'),
    says: 'dropping: Still current? Planning the trip to Porto',
  },
  { what: 'ok on the review in the start view', command: 'm2b-pane', key: 'ok:r1', undo: undoKey('r1'), says: 'closing: m2b: review' },
  { what: 'drop on a candidate in the view of the review', command: 'm2b-review', key: 'drop:c1', undo: undoKey('c1'), says: 'dropping: Remember? Dana prefers tea' },
  { what: 'ok on the review in its own view', command: 'm2b-review', key: 'ok:r1', undo: undoKey('r1'), says: 'closing: m2b: review' },
  { what: 'keep on a proposal', command: 'm2b-proposals', key: `keep:${DANA}`, undo: undoKey(DANA), says: 'keeping: Dana is head of IT at Northwind.' },
  { what: 'drop on a proposal', command: 'm2b-proposals', key: `drop:${LADDER}`, undo: undoKey(LADDER), says: 'dropping: Call Sam about the ladder.' },
  { what: 'keep all', command: 'm2b-proposals', key: 'keep-all', undo: UNDO_ALL, says: 'keeping all 2 proposals' },
  { what: 'the button that leaves m2b out of the folder', command: 'm2b-pane', key: 'folder:off', undo: UNDO_FOLDER, says: `leaving m2b out of ${ACME}` },
  {
    what: 'the button that turns the distillate on again',
    command: 'm2b-pane',
    key: 'folder:on',
    undo: UNDO_FOLDER,
    says: `turning the distillate on under ${ACME}`,
    arrange: fake => {
      fake.given = { topics: [], atStart: 'whole', offUnder: ACME, folder: ACME }
    },
  },
]

test('the key of undo names its row: a task or a proposal by its id, keep all and the folder by their own', () => {
  // Covers: B201
  expect(undoKey('c1')).toBe('undo:c1')
  expect(undoKey(DANA)).toBe(`undo:${DANA}`)
  expect(UNDO_ALL).toBe('undo:all')
  expect(UNDO_FOLDER).toBe('undo:folder')
  // No two presses that can wait in one view share a key.
  expect(new Set([undoKey('c1'), undoKey('q1'), undoKey('r1'), undoKey(DANA), UNDO_ALL, UNDO_FOLDER]).size).toBe(6)
})

for (const { what, command, key, undo, says, arrange } of PRESSES) {
  test(`after ${what}, undo of that row is a button the view draws once the press waits, and was none before the press`, async ($, on) => {
    // Covers: B201
    const fake = busyFake()
    arrange?.(fake)
    const { clock } = await start($, on, fake)
    await typed($, command)
    const ui = await $.ui.mount({ ...pane(PANE), surface: 'terminal' })
    const buttons = async (): Promise<string[]> => (await ui.findAll({ type: 'Button' })).map(button => String(button.key))
    const before = await buttons()
    expect(before).toContain(key)
    expect(before).not.toContain(undo)

    await ui.press({ key })

    const waiting = await buttons()
    expect(waiting).toContain(undo)
    expect(waiting.filter(drawn => drawn === undo)).toHaveLength(1)
    // The row draws undo in place of what was pressed.
    expect(waiting).not.toContain(key)
    expect((await texts(ui)).some(line => line.includes(says))).toBe(true)

    // Undo takes the press back and writes nothing: Enter pressed twice leaves everything as it was.
    await ui.press({ key: undo })
    await clock.advance(10_000)
    expect(await buttons()).toEqual(before)
    expect(fake.writes()).toEqual([])
    expect(fake.answers()).toEqual([])
    expect(fake.folderCalls()).toEqual([])
    await ui.unmount()
  })
}

test('a press that waits leaves the other rows as they were: only its own row draws undo', async ($, on) => {
  // Covers: B201
  const fake = busyFake()
  await start($, on, fake)
  await typed($, 'm2b-pane')
  const ui = await $.ui.mount({ ...pane(PANE), surface: 'terminal' })
  const undos = async (): Promise<string[]> =>
    (await ui.findAll({ type: 'Button' })).map(button => String(button.key)).filter(drawn => drawn.startsWith('undo:'))

  await ui.press({ key: 'drop:c1' })
  expect(await undos()).toEqual([undoKey('c1')])
  // The row below keeps both its buttons, where the focus would stand if it were left at its place.
  expect(await ui.find({ key: 'keep:q1' })).toBeDefined()
  expect(await ui.find({ key: 'drop:q1' })).toBeDefined()

  await ui.press({ key: 'ok:r1' })
  await ui.press({ key: 'folder:off' })
  expect(await undos()).toEqual([UNDO_FOLDER, undoKey('c1'), undoKey('r1')])
  await ui.unmount()
})
