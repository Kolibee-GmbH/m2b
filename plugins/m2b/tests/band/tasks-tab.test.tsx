import { expect, test } from 'claude-code/testing'
import type { CommandRunResult } from 'claude-code'
import type { Engine } from 'claude-code/testing'

import { beginTasks, fillTasks, forgetTasksUnless, heldTasks, holdsTasks, noteRefusal, parseTasks } from '../../hooks/tasks-tab'
import type { TasksLook } from '../../hooks/tasks-tab'
import {
  FakeM2b,
  TODAY,
  everyText,
  linesAt,
  lookOf,
  pane,
  piecesAt,
  pressTab,
  shownParts,
  shownTab,
  shownTabs,
  start,
  texts,
  viewButtons,
} from './harness'
import type { ShownPiece } from './harness'

const PANE = 'm2b'
const AS_A_DIALOG = { id: PANE, title: 'm2b', closeOnEscape: true, focus: true }
const UNDO_MS = 5_000
const TODOS = ['todos', '--json']
const READING = 'm2b is reading the task list…'
const NOTHING_OPEN = 'No open tasks.'
const OTHER_SHAPE = 'm2b answered something other than the task list'

const OFFER = 'Send Dana the Acme offer'
const LADDER = 'Return the ladder to Sam'
const CALL = 'Call Alex about the trip'
const HALL = 'Book the hall for the choir'
const SPRING = 'Clean the shed with Dana'
const PASSPORT = 'Renew the passport'
const PHOTOS = 'Sort the photos from Porto'
const TITLES = [OFFER, LADDER, CALL, HALL, SPRING, PASSPORT, PHOTOS]

function typed($: Engine, command: string, args = ''): Promise<CommandRunResult> {
  return $.command.run({ command, args, origin: { kind: 'composer' }, presentation: { isFullscreen: false, columns: 100 } })
}

async function startView($: Engine, columns = 80) {
  await typed($, 'm2b-pane')
  return $.ui.mount({ ...pane(PANE, columns), surface: 'terminal' })
}

type Pane = Awaited<ReturnType<typeof startView>>

/** The pane on the start view, then turned to the tab Tasks once m2b answered. */
async function tasksView($: Engine): Promise<Pane> {
  const ui = await startView($)
  await pressTab(ui, 'tasks')
  return ui
}

/**
 * An open task in every group the core names: one overdue, two due today (one at a time of day),
 * one later this week, and three later still, one of them at a time of day and one next year; and
 * one without a date.
 */
function fullList(): FakeM2b {
  return new FakeM2b()
    .todo('overdue', 't1', OFFER, '2026-03-10')
    .todo('due_within_7_days', 't2', LADDER, TODAY)
    .todo('due_within_7_days', 't3', CALL, `${TODAY}T10:00:00+01:00`)
    .todo('due_within_7_days', 't4', HALL, '2026-03-19')
    .todo('later', 't5', SPRING, '2026-04-02T09:30:00+02:00')
    .todo('later', 't6', PASSPORT, '2027-01-02')
    .todo('without_date', 't7', PHOTOS)
}

/** An owner's list with one task, due later. */
function oneTask(id = 't1', title = LADDER): FakeM2b {
  return new FakeM2b().todo('later', id, title, '2026-04-02')
}

test('the tab Tasks reads the open tasks and shows a part for each group, in the order a day passes, each row when it is due, then its title, then done', async ($, on) => {
  // Covers: B222
  const fake = fullList()
  const { opened } = await start($, on, fake)
  const ui = await startView($)
  const [opensBefore, callsBefore] = [opened.length, fake.calls.length]

  await pressTab(ui, 'tasks')

  // The one call: the band holds nothing the open tasks change, and is not read again.
  expect(fake.calls.slice(callsBefore)).toEqual([TODOS])
  expect(opened.slice(opensBefore)).toEqual([AS_A_DIALOG])
  expect(await shownTab(ui)).toBe('tasks')
  expect(await shownParts(ui)).toEqual([
    { key: 'tasks:overdue', title: 'Overdue', count: null, lines: [`overdue ${OFFER}`, '[done]'] },
    {
      key: 'tasks:today',
      title: 'Today',
      count: null,
      lines: [`due today ${LADDER}`, '[done]', `due today 10:00 ${CALL}`, '[done]'],
    },
    { key: 'tasks:soon', title: 'Next 7 days', count: null, lines: [`Thu 19 Mar ${HALL}`, '[done]'] },
    {
      key: 'tasks:later',
      title: 'Later',
      count: null,
      lines: [`Thu 2 Apr 09:30 ${SPRING}`, '[done]', `Sat 2 Jan 2027 ${PASSPORT}`, '[done]'],
    },
    { key: 'tasks:undated', title: 'Without a date', count: null, lines: [PHOTOS, '[done]'] },
  ])
  expect(await viewButtons(ui)).toEqual(['done:t1', 'done:t2', 'done:t3', 'done:t4', 'done:t5', 'done:t6', 'done:t7'])
  await ui.unmount()
})

test('a group without tasks is left out, and today is taken out of the next seven days by the day the answer names', async ($, on) => {
  // Covers: B222
  const fake = new FakeM2b()
    .todo('due_within_7_days', 't1', HALL, '2026-03-16')
    .todo('due_within_7_days', 't2', LADDER, '2026-03-15')
    .todo('without_date', 't3', PHOTOS)
  // The core's day, not the clock's: a list read just after midnight counts the day it names.
  fake.todos.today = '2026-03-15'
  await start($, on, fake)

  const ui = await tasksView($)

  expect((await shownParts(ui)).map(part => [part.title, part.lines])).toEqual([
    ['Today', [`due today ${LADDER}`, '[done]']],
    ['Next 7 days', [`Mon 16 Mar ${HALL}`, '[done]']],
    ['Without a date', [PHOTOS, '[done]']],
  ])
  await ui.unmount()
})

/** A piece of text as drawn where a test names nothing else: to be read, in no color. */
function piece(text: string, look: Partial<ShownPiece> = {}): ShownPiece {
  return { text, color: undefined, dimColor: undefined, weight: undefined, strikethrough: undefined, ...look }
}

test('when a task is due is in the color the part Today gives it, kept whole on its line, and the title beside it wraps', async ($, on) => {
  // Covers: B222
  await start($, on, fullList())
  const ui = await tasksView($)

  expect(await piecesAt(ui, 'task:t1')).toEqual([piece('overdue', { color: 'error' }), piece(OFFER)])
  expect(await piecesAt(ui, 'task:t3')).toEqual([piece('due today 10:00', { color: 'warning' }), piece(CALL)])
  expect(await piecesAt(ui, 'task:t4')).toEqual([piece('Thu 19 Mar', { dimColor: true }), piece(HALL)])
  expect(await piecesAt(ui, 'task:t6')).toEqual([piece('Sat 2 Jan 2027', { dimColor: true }), piece(PASSPORT)])
  // Without a date there is no word for it, and the title stands alone.
  expect(await piecesAt(ui, 'task:t7')).toEqual([piece(PHOTOS)])
  expect((await lookOf(ui, 'due today'))?.color).toBe('warning')

  const kept = (await ui.findAll({ type: 'Box' })).filter(box => box.props['flexShrink'] === 0).map(box => box.text)
  expect(kept).toEqual(['overdue', 'due today', 'due today 10:00', 'Thu 19 Mar', 'Thu 2 Apr 09:30', 'Sat 2 Jan 2027'])
  for (const title of TITLES) {
    expect((await lookOf(ui, title))?.wrap).toBe('wrap')
  }
  await ui.unmount()
})

test('a title is drawn without what a terminal would run, in a narrow pane too', async ($, on) => {
  // Covers: B222
  const fake = oneTask('t1', 'Call\u001b[31m Dana\nabout\u0007 Acme')
  await start($, on, fake)
  const ui = await startView($, 24)
  await pressTab(ui, 'tasks')

  expect(await linesAt(ui, 'task:t1')).toEqual(['Thu 2 Apr Call Dana about Acme', '[done]'])
  expect((await everyText(ui)).filter(text => text.includes('\u001b') || text.includes('\n') || text.includes('\u0007'))).toEqual([])
  await ui.unmount()
})

test('a list without open tasks says so in one part, Open', async ($, on) => {
  // Covers: B222
  await start($, on, new FakeM2b())

  const ui = await tasksView($)

  expect(await shownParts(ui)).toEqual([{ key: 'tasks', title: 'Open', count: null, lines: [NOTHING_OPEN] }])
  expect((await lookOf(ui, NOTHING_OPEN))?.dimColor).toBe(true)
  expect(await viewButtons(ui)).toEqual([])
  await ui.unmount()
})

test('while m2b reads the list the view says so, then shows what it answered', async ($, on) => {
  // Covers: B222
  const fake = oneTask()
  fake.delayMs = args => (args[0] === 'todos' ? 2_000 : 0)
  const { clock } = await start($, on, fake)
  const ui = await startView($)

  const pressed = pressTab(ui, 'tasks')
  await clock.advance(1)
  expect(await shownParts(ui)).toEqual([{ key: 'tasks', title: 'Open', count: null, lines: [READING] }])
  expect((await lookOf(ui, READING))?.dimColor).toBe(true)

  await clock.advance(2_000)
  await pressed
  expect(await texts(ui)).toEqual(['Later', 'Thu 2 Apr', LADDER])
  await ui.unmount()
})

test('a list m2b could not read says why in the error color, never that nothing is open', async ($, on) => {
  // Covers: B222
  const fake = oneTask()
  fake.todosFails = 'tasks/a1b2.md is not downloaded to this machine'
  await start($, on, fake)

  const ui = await tasksView($)

  const line = 'm2b could not read the task list: tasks/a1b2.md is not downloaded to this machine'
  expect(await shownParts(ui)).toEqual([{ key: 'tasks', title: 'Open', count: null, lines: [line] }])
  expect((await lookOf(ui, line))?.color).toBe('error')
  expect(await texts(ui)).not.toContain(NOTHING_OPEN)
  await ui.unmount()
})

test('a task file m2b could not read is named in a part of its own, and the tasks it could read stand below it', async ($, on) => {
  // Covers: B222
  const fake = oneTask()
  fake.todosUnreadable = [{ path: 'tasks/a1b2.md', reason: 'tasks/a1b2.md holds no task' }]
  await start($, on, fake)

  const ui = await tasksView($)

  const line = 'm2b could not read tasks/a1b2.md holds no task; this task is not listed until the file is fixed.'
  const parts = await shownParts(ui)
  expect(parts[0]).toEqual({ key: 'tasks:unreadable', title: 'Not listed', count: null, lines: [line] })
  expect((await lookOf(ui, line))?.color).toBe('error')
  expect(parts.map(shown => shown.title)).toEqual(['Not listed', 'Later'])
  expect(await texts(ui)).toContain(LADDER)
  await ui.unmount()
})

test('a launcher that cannot be started says could not read', async ($, on) => {
  // Covers: B222
  const fake = oneTask()
  await start($, on, fake)
  const ui = await startView($)
  fake.runFails = 'timed out'

  await pressTab(ui, 'tasks')

  expect((await texts(ui)).some(line => line.startsWith('m2b could not read the task list: could not run '))).toBe(true)
  await ui.unmount()
})

test('an answer of another shape is could not read, never a list without tasks', async ($, on) => {
  // Covers: B222
  const fake = oneTask()
  fake.todosPrints = JSON.stringify({ today: TODAY, overdue: 'none', due_within_7_days: [], later: [], without_date: [] })
  await start($, on, fake)

  const ui = await tasksView($)

  expect(await texts(ui)).toEqual(['Open', `m2b could not read the task list: ${OTHER_SHAPE}`])
  await ui.unmount()

  const empty = { today: TODAY, overdue: [], due_within_7_days: [], later: [], without_date: [] }
  const failed = { state: 'failed', error: OTHER_SHAPE }
  expect(parseTasks('not JSON')).toEqual(failed)
  expect(parseTasks('[]')).toEqual(failed)
  expect(parseTasks('null')).toEqual(failed)
  expect(parseTasks(JSON.stringify({ ...empty, today: undefined }))).toEqual(failed)
  expect(parseTasks(JSON.stringify({ ...empty, later: undefined }))).toEqual(failed)
  expect(parseTasks(JSON.stringify({ ...empty, overdue: [{ id: 't1', due: null }] }))).toEqual(failed)
  expect(parseTasks(JSON.stringify({ ...empty, overdue: [{ id: 't1', title: OFFER, due: 20260310 }] }))).toEqual(failed)
  expect(parseTasks(JSON.stringify(empty))).toEqual({
    state: 'read',
    today: TODAY,
    groups: { overdue: [], today: [], soon: [], later: [], undated: [] },
    unreadable: [],
  })
})

test('done writes nothing for five seconds: the row offers undo beside completing, then m2b completes that one task once', async ($, on) => {
  // Covers: B223
  const fake = oneTask()
  const { clock } = await start($, on, fake)
  const ui = await tasksView($)

  await ui.press({ key: 'done:t1' })

  expect(await linesAt(ui, 'task:t1')).toEqual([`Thu 2 Apr ${LADDER}`, '[undo] completing'])
  expect(await viewButtons(ui)).toEqual(['undo:t1'])
  await clock.advance(UNDO_MS - 1)
  expect(fake.writes()).toEqual([])

  await clock.advance(1)
  await clock.advance(1)
  expect(fake.writes()).toEqual([['tasks', 'complete', '--', 't1']])
  await clock.advance(60_000)
  expect(fake.writes()).toEqual([['tasks', 'complete', '--', 't1']])
  await ui.unmount()
})

test('undo within the five seconds takes the press back: nothing is written, and the row offers done again', async ($, on) => {
  // Covers: B223
  const fake = oneTask()
  const { clock } = await start($, on, fake)
  const ui = await tasksView($)

  await ui.press({ key: 'done:t1' })
  await clock.advance(UNDO_MS - 1_000)
  await ui.press({ key: 'undo:t1' })
  await clock.advance(10_000)

  expect(fake.writes()).toEqual([])
  expect(await linesAt(ui, 'task:t1')).toEqual([`Thu 2 Apr ${LADDER}`, '[done]'])
  await ui.unmount()
})

test('an id that starts with a dash stays one argument, after --', async ($, on) => {
  // Covers: B223
  const fake = oneTask('-r-ladder.md')
  const { clock } = await start($, on, fake)
  const ui = await tasksView($)

  await ui.press({ key: 'done:-r-ladder.md' })
  await clock.advance(UNDO_MS + 1)

  expect(fake.writes()).toEqual([['tasks', 'complete', '--', '-r-ladder.md']])
  await ui.unmount()
})

test('written, the tab reads the list again, the task is gone from it, and the band reads its counts again', async ($, on) => {
  // Covers: B223
  const fake = oneTask().todo('without_date', 't2', PHOTOS)
  const { clock } = await start($, on, fake)
  const ui = await tasksView($)
  await ui.press({ key: 'done:t1' })
  const callsBefore = fake.calls.length

  await clock.advance(UNDO_MS + 1)

  // The band reads its counts for reasons of its own too: what is checked is what follows the write.
  const after = fake.calls.slice(callsBefore)
  const written = after.findIndex(call => call[0] === 'tasks')
  expect(after[written]).toEqual(['tasks', 'complete', '--', 't1'])
  expect(after.slice(written + 1).filter(call => call[0] === 'todos')).toEqual([TODOS])
  expect(after.slice(written + 1).some(call => call[0] === 'band')).toBe(true)
  expect(await texts(ui)).toEqual(['Without a date', PHOTOS])
  expect(await viewButtons(ui)).toEqual(['done:t2'])
  await ui.unmount()
})

test('refused, the row stays and says why under it in the error color, until the next press on that row', async ($, on) => {
  // Covers: B223
  const fake = oneTask().todo('without_date', 't2', PHOTOS)
  fake.completeFails = 'the task list cannot be reached'
  const { clock } = await start($, on, fake)
  const ui = await tasksView($)
  const refusal = 'm2b could not complete it: the task list cannot be reached'

  await ui.press({ key: 'done:t1' })
  await clock.advance(UNDO_MS + 1)

  expect(fake.writes()).toEqual([['tasks', 'complete', '--', 't1']])
  expect(await linesAt(ui, 'task:t1')).toEqual([`Thu 2 Apr ${LADDER}`, '[done]', refusal])
  expect((await lookOf(ui, refusal))?.color).toBe('error')
  // The other row says nothing of it, and a press there leaves it standing.
  expect(await linesAt(ui, 'task:t2')).toEqual([PHOTOS, '[done]'])
  await ui.press({ key: 'done:t2' })
  expect(await texts(ui)).toContain(refusal)
  await ui.press({ key: 'undo:t2' })
  // The list is read once more, to see the task is still open before the write, and not after the
  // refusal; no minute that passes takes the line away.
  expect(fake.todosCalls()).toEqual([TODOS, TODOS])
  await clock.advance(60_000)
  expect(await texts(ui)).toContain(refusal)

  fake.completeFails = null
  await ui.press({ key: 'done:t1' })
  expect(await linesAt(ui, 'task:t1')).toEqual([`Thu 2 Apr ${LADDER}`, '[undo] completing'])
  await clock.advance(UNDO_MS + 1)
  expect(await texts(ui)).not.toContain(refusal)
  expect(await texts(ui)).toEqual(['Without a date', PHOTOS])
  await ui.unmount()
})

type On = Parameters<typeof start>[1]

/** Every write to the session's state from here on, as JSON: that state is one every plugin can read. */
function stateWrites(on: On): string[] {
  const writes: string[] = []
  on('state.set', (_, e, next) => {
    writes.push(JSON.stringify(e))
    return next(e)
  })
  return writes
}

test("the session's state, which every plugin can read, holds no title of a task and nothing a press could not write", async ($, on) => {
  // Covers: B224
  const fake = fullList()
  fake.completeFails = 'Send Dana the Acme offer is locked by another program'
  const writes = stateWrites(on)
  const { clock } = await start($, on, fake)
  const ui = await tasksView($)
  expect(await texts(ui)).toContain(OFFER)

  await ui.press({ key: 'done:t1' })
  await clock.advance(UNDO_MS + 1)
  expect(await texts(ui)).toContain('m2b could not complete it: Send Dana the Acme offer is locked by another program')
  fake.completeFails = null
  await ui.press({ key: 'done:t2' })
  await clock.advance(UNDO_MS + 1)
  await pressTab(ui, 'review')
  await pressTab(ui, 'tasks')
  await pressTab(ui, 'overview')

  const kept = writes.join('\n')
  // The view was in the state all along: what is checked is there.
  expect(kept).toContain('"kind":"tasks"')
  for (const title of TITLES) {
    expect(kept).not.toContain(title)
  }
  expect(kept).not.toContain('locked by another program')
  await ui.unmount()
})

for (const [to, label] of [
  ['overview', 'Overview'],
  ['proposals', 'Proposals'],
  ['review', 'Review'],
  ['settings', 'Settings'],
] as const) {
  test(`an answer that comes after the tab ${label} was pressed is dropped, and draws no task there`, async ($, on) => {
    // Covers: B224
    const fake = oneTask()
    fake.delayMs = args => (args[0] === 'todos' ? 2_000 : 0)
    const { clock } = await start($, on, fake)
    const ui = await startView($)

    const pressed = pressTab(ui, 'tasks')
    await clock.advance(1)
    expect(await texts(ui)).toEqual(['Open', READING])

    await pressTab(ui, to)
    await clock.advance(2_000)
    await pressed
    await clock.advance(1)

    expect(await shownTab(ui)).toBe(to)
    expect(await shownTabs(ui)).toHaveLength(5)
    expect(await everyText(ui)).not.toContain(LADDER)
    await ui.unmount()
  })
}

test('a task no longer open when the five seconds are over is not completed, and its row says so', async ($, on) => {
  // Covers: B223
  const fake = oneTask().todo('without_date', 't2', PHOTOS)
  const { clock } = await start($, on, fake)
  const ui = await tasksView($)
  await ui.press({ key: 'done:t1' })
  // Another session ticked or dropped it meanwhile.
  fake.todos.later = fake.todos.later.filter(task => task.id !== 't1')

  await clock.advance(UNDO_MS + 1)

  expect(fake.writes()).toEqual([])
  expect(await texts(ui)).toContain('m2b could not complete it: it is no longer open in the task list; nothing was written')
  await ui.unmount()
})

test('a list m2b cannot read when the five seconds are over completes nothing and says why at the row', async ($, on) => {
  // Covers: B223
  const fake = oneTask()
  const { clock } = await start($, on, fake)
  const ui = await tasksView($)
  await ui.press({ key: 'done:t1' })
  fake.todosFails = 'the task list cannot be reached'

  await clock.advance(UNDO_MS + 1)

  expect(fake.writes()).toEqual([])
  expect(await texts(ui)).toContain('m2b could not complete it: the task list cannot be reached')
  await ui.unmount()
})

test('a reload of the mod, which starts the session again, leaves the pane on its start view and keeps no title', async ($, on) => {
  // Covers: B224
  const fake = oneTask()
  const { clock } = await start($, on, fake)
  const ui = await tasksView($)
  expect(await texts(ui)).toContain(LADDER)

  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await clock.advance(1)

  const shown = await texts(ui)
  expect(shown).toContain('Waits for you')
  expect(shown).not.toContain(LADDER)
  expect(shown).not.toContain(READING)
  await ui.unmount()
})

test('a press is held in the state under a key that names no task, and the key of another load of the module', async ($, on) => {
  // Covers: B224
  const fake = oneTask('call-the-plumber-on-friday.md', 'Call the plumber on Friday')
  const writes = stateWrites(on)
  await start($, on, fake)
  const ui = await tasksView($)

  await ui.press({ key: 'done:call-the-plumber-on-friday.md' })

  const presses = writes.filter(write => write.includes('bandPresses') && write.includes('waiting'))
  expect(presses.length).toBeGreaterThan(0)
  expect(presses.every(write => !write.includes('plumber'))).toBe(true)
  expect(presses.some(write => /"task:[a-z0-9]+:\d+"/.test(write))).toBe(true)
  await ui.unmount()
})

test('an answer to an earlier opening of the tab does not fill a later one', async ($, on) => {
  // Covers: B224
  const fake = oneTask()
  let reads = 0
  fake.delayMs = args => (args[0] !== 'todos' ? 0 : (reads += 1) === 1 ? 2_000 : 5_000)
  const { clock } = await start($, on, fake)
  const ui = await startView($)

  const first = pressTab(ui, 'tasks')
  await clock.advance(1)
  await pressTab(ui, 'overview')
  // The list changed between the two openings: the later answer is the one to show.
  fake.todos.later = [{ id: 't2', title: PASSPORT, notes: '', due: '2026-04-02' }]
  const second = pressTab(ui, 'tasks')
  await clock.advance(2_000)
  await first

  expect(await texts(ui)).toEqual(['Open', READING])
  await clock.advance(5_000)
  await second
  expect(await texts(ui)).toEqual(['Later', 'Thu 2 Apr', PASSPORT])
  await ui.unmount()
})

test('a command that turns the pane away and a new opening read the list anew and show none of the titles read before', async ($, on) => {
  // Covers: B224
  const fake = oneTask()
  await start($, on, fake)
  const ui = await tasksView($)
  expect(await texts(ui)).toContain(LADDER)

  await typed($, 'm2b-review')
  expect(await everyText(ui)).not.toContain(LADDER)
  fake.todos.later = []
  await typed($, 'm2b-pane')
  await pressTab(ui, 'tasks')

  expect(fake.todosCalls()).toEqual([TODOS, TODOS])
  expect(await texts(ui)).toEqual(['Open', NOTHING_OPEN])
  await ui.unmount()
})

// What the module keeps cannot be read from outside it, and the engine loads the mod's modules
// apart from a test's own import. So the keeping is tested here on the module itself; the tests
// above hold what it comes to in the pane and in the session's state.

const READ_LIST: TasksLook = {
  state: 'read',
  today: TODAY,
  groups: { overdue: [], today: [], soon: [], later: [{ id: 't1', title: LADDER, due: '2026-04-02' }], undated: [] },
  unreadable: [],
}

test('the titles are kept for the opening that read them, and turning the pane to any other view drops them with what a press could not write', () => {
  // Covers: B224
  beginTasks('p1')
  expect(heldTasks('p1')).toEqual({ state: 'reading' })
  expect(fillTasks('p1', READ_LIST)).toBe(true)
  expect(heldTasks('p1')).toEqual(READ_LIST)

  // A redraw of that very opening keeps them.
  forgetTasksUnless({ kind: 'tasks', press: 'p1', drawn: 3 })
  expect(heldTasks('p1')).toEqual(READ_LIST)

  for (const other of [
    null,
    { kind: 'proposals' },
    { kind: 'review' },
    { kind: 'settings', press: 'p1', aside: null, drawn: 0 },
    { kind: 'topic', name: 'Acme Ltd', press: 'p1', isRead: true },
    { kind: 'tasks', press: 'p2', drawn: 0 },
  ] as const) {
    beginTasks('p1')
    fillTasks('p1', READ_LIST)
    noteRefusal('p1', 't1', 'the task list cannot be reached')
    expect(holdsTasks()).toBe(true)

    forgetTasksUnless(other)

    expect(holdsTasks()).toBe(false)
    expect(heldTasks('p1')).toEqual({ state: 'reading' })
  }
})

test('a new opening keeps nothing of the one before, and an answer for an opening the pane left is not kept', () => {
  // Covers: B224
  beginTasks('p1')
  fillTasks('p1', READ_LIST)
  noteRefusal('p1', 't1', 'the task list cannot be reached')
  beginTasks('p2')
  expect(heldTasks('p1')).toEqual({ state: 'reading' })
  expect(heldTasks('p2')).toEqual({ state: 'reading' })
  expect(fillTasks('p1', READ_LIST)).toBe(false)
  forgetTasksUnless(null)
  expect(holdsTasks()).toBe(false)

  beginTasks('p1')
  forgetTasksUnless(null)
  expect(fillTasks('p1', READ_LIST)).toBe(false)
  expect(holdsTasks()).toBe(false)
})

test('what a press could not write is not kept once the pane turned away before m2b refused it', () => {
  // Covers: B224
  beginTasks('p1')
  fillTasks('p1', READ_LIST)
  forgetTasksUnless(null)

  noteRefusal('p1', 't1', 'the task list cannot be reached')

  expect(holdsTasks()).toBe(false)
  forgetTasksUnless({ kind: 'tasks', press: 'none', drawn: 0 })
})

test('a refusal that comes after the tab was opened anew is not said in the new opening', async ($, on) => {
  // Covers: B224
  const fake = oneTask()
  const { clock } = await start($, on, fake)
  const ui = await tasksView($)
  await ui.press({ key: 'done:t1' })
  await pressTab(ui, 'overview')
  await pressTab(ui, 'tasks')
  fake.completeFails = 'the task list cannot be reached'

  await clock.advance(UNDO_MS + 1)

  expect(fake.writes()).toEqual([['tasks', 'complete', '--', 't1']])
  expect(await texts(ui)).not.toContain('m2b could not complete it: the task list cannot be reached')
  await ui.unmount()
})
