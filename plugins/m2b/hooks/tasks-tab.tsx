import type { EngineInterface, ResolveInput } from 'claude-code'

import type { BandPress, PaneView } from '../types'
import { DUE_TODAY, OVERDUE, part, pressLine, said, styleOf, tickMark, under } from './look'
import type { Tone } from './look'
import { runM2b } from './m2b'
import { plainLine } from './plain-text'
import { undoKey } from './rows'

/*
 * The tab "Tasks": every open task of the owner's list, as `m2b todos --json` answers at the
 * moment the tab is turned to, in groups by when each is due, and a mark before each that ticks
 * it. The review task, the candidates and the questions are not among them: the core leaves curator tasks out, and they
 * are answered under "Waits for you".
 *
 * The titles are this module's alone, for the opening that read them, and dropped the moment the
 * pane turns away, as a topic's lines are: the session's state is one every plugin can read, and a
 * task list holds far more than the tasks due today the band shows.
 */

/** One open task as the tab draws it; `due` as the core writes it, a day or a day with a time. */
export type OpenTask = { id: string; title: string; due: string | null }

export type TaskGroup = 'overdue' | 'today' | 'soon' | 'later' | 'undated'

export type TasksLook =
  | { state: 'reading' }
  | { state: 'read'; today: string; groups: Record<TaskGroup, OpenTask[]>; unreadable: string[] }
  | { state: 'failed'; error: string }

const GROUPS: readonly { group: TaskGroup; title: string }[] = [
  { group: 'overdue', title: 'Overdue' },
  { group: 'today', title: 'Today' },
  { group: 'soon', title: 'Next 7 days' },
  { group: 'later', title: 'Later' },
  { group: 'undated', title: 'Without a date' },
]

// The look the pane shows, with the press that asked for it, and what `m2b tasks complete` refused
// on a row, until the next press there. Both the module's own, gone when the pane turns away.
let held: { press: string; look: TasksLook } | null = null
const refusals = new Map<string, string>()

export function beginTasks(press: string): void {
  held = { press, look: { state: 'reading' } }
  refusals.clear()
}

/** Puts m2b's answer in place for the press that asked; false, and nothing kept, once the pane turned away. */
export function fillTasks(press: string, look: TasksLook): boolean {
  if (held === null || held.press !== press) {
    return false
  }
  held = { press, look }
  return true
}

export function heldTasks(press: string): TasksLook {
  return held !== null && held.press === press ? held.look : { state: 'reading' }
}

/** Whether anything is kept at all. Nothing outside the module can read what it keeps, so its tests ask this. */
export function holdsTasks(): boolean {
  return held !== null || refusals.size > 0
}

export function forgetTasksUnless(view: PaneView | null): void {
  if (held !== null && !(view !== null && view.kind === 'tasks' && view.press === held.press)) {
    held = null
    refusals.clear()
  }
}

/**
 * Notes what `m2b tasks complete` refused on a row, or clears it with null, for the opening
 * `opening` names alone: a refusal that comes once the pane turned away, or opened the tab anew,
 * is dropped with that opening.
 */
export function noteRefusal(opening: string, id: string, reason: string | null): void {
  if (held === null || held.press !== opening) {
    return
  }
  if (reason === null) {
    refusals.delete(id)
  } else {
    refusals.set(id, reason)
  }
}

// The presses stand in the session's state, which every plugin reads. With the markdown backend a
// task's id can be the name of its file, which often is its title; so a press is held under a
// number the module gives each id, and the id stays here. The numbers carry this load of the
// module: a press an earlier load is still writing keeps its row locked under its own key, which
// no row of this load bears.
const pressKeys = new Map<string, string>()
const LOAD = `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`

/** The key under which the presses hold a press on the mark of the task `id`. */
export function taskPressKey(id: string): string {
  let key = pressKeys.get(id)
  if (key === undefined) {
    key = `task:${LOAD}:${pressKeys.size + 1}`
    pressKeys.set(id, key)
  }
  return key
}

const READ_TIMEOUT_MS = 20_000
/** What a press on the mark says where the task is no longer open when its undo window is over. */
export const NO_LONGER_OPEN = 'it is no longer open in the task list; nothing was written'
// The exit of the core's command line for a command that ran and found something to act on.
const EXIT_PROBLEM = 1
const OTHER_SHAPE = 'm2b answered something other than the task list'
const READING = 'm2b is reading the task list…'
const NOTHING_OPEN = 'No open tasks.'
// The one part where no group can be named; a part never bears the name of its tab.
const OPEN_TASKS = 'Open'
const NOT_LISTED = 'Not listed'

/** Reads the open tasks as the list holds them now; whatever fails, the look says why. */
export async function readTasks($: EngineInterface): Promise<TasksLook> {
  const outcome = await runM2b($, ['todos', '--json'], READ_TIMEOUT_MS)
  if (!outcome.ok) {
    // A task file that holds no task ends the command with exit 1, after the tasks it could read.
    const answer = outcome.exitCode === EXIT_PROBLEM && outcome.stdout ? parseTasks(outcome.stdout) : null
    return answer !== null && answer.state === 'read' && answer.unreadable.length > 0 ? answer : { state: 'failed', error: outcome.error }
  }
  return outcome.isCut ? { state: 'failed', error: 'the task list was too long to read' } : parseTasks(outcome.stdout)
}

function isOpenTask(value: unknown): value is { id: string; title: string; due: string | null } {
  if (typeof value !== 'object' || value === null) {
    return false
  }
  const task = value as Record<string, unknown>
  return typeof task['id'] === 'string' && typeof task['title'] === 'string' && (task['due'] === null || typeof task['due'] === 'string')
}

function tasksOf(value: unknown): OpenTask[] | null {
  return Array.isArray(value) && value.every(isOpenTask) ? value.map(({ id, title, due }) => ({ id, title, due })) : null
}

/**
 * The answer of `m2b todos --json`, its group of the next seven days split into today and after:
 * the core counts today among them. One of any other shape is could not read, never no tasks.
 */
export function parseTasks(text: string): TasksLook {
  let answer: unknown
  try {
    answer = JSON.parse(text)
  } catch {
    return { state: 'failed', error: OTHER_SHAPE }
  }
  if (typeof answer !== 'object' || answer === null) {
    return { state: 'failed', error: OTHER_SHAPE }
  }
  const fields = answer as Record<string, unknown>
  const overdue = tasksOf(fields['overdue'])
  const soon = tasksOf(fields['due_within_7_days'])
  const later = tasksOf(fields['later'])
  const undated = tasksOf(fields['without_date'])
  const today = fields['today']
  if (overdue === null || soon === null || later === null || undated === null || typeof today !== 'string') {
    return { state: 'failed', error: OTHER_SHAPE }
  }
  const isToday = (task: OpenTask) => task.due !== null && dayOf(task.due) === today
  return {
    state: 'read',
    today,
    unreadable: unreadableOf(fields['unreadable']),
    groups: { overdue, today: soon.filter(isToday), soon: soon.filter(task => !isToday(task)), later, undated },
  }
}

/** The reasons the core gives for the task files it could not read; each names its file. */
function unreadableOf(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return []
  }
  return value.flatMap(item => (typeof item === 'object' && item !== null && typeof item['reason'] === 'string' ? [item['reason']] : []))
}

/** Whether a list read holds the task `id` as open. */
export function isOpenIn(look: Extract<TasksLook, { state: 'read' }>, id: string): boolean {
  return Object.values(look.groups).some(tasks => tasks.some(task => task.id === id))
}

function dayOf(due: string): string {
  return due.slice(0, 10)
}

const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'] as const
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'] as const
const DAY = /^(\d{4})-(\d{2})-(\d{2})/
const TIME = /T(\d{2}:\d{2})/

/**
 * When a task is due, in the words of the part "Today" where it is overdue or due today, else its
 * day (`Thu 20 Nov`, the year where it is not this one); a time of day follows the day.
 */
export function whenDue(task: OpenTask, group: TaskGroup, today: string): string {
  if (task.due === null) {
    return ''
  }
  const time = TIME.exec(task.due)?.[1]
  const at = time === undefined ? '' : ` ${time}`
  if (group === 'overdue') {
    return OVERDUE
  }
  if (group === 'today') {
    return `${DUE_TODAY}${at}`
  }
  const parts = DAY.exec(task.due)
  if (parts === null) {
    return plainLine(task.due)
  }
  const [, year, month, day] = parts
  const weekday = WEEKDAYS[new Date(`${year}-${month}-${day}T12:00:00Z`).getUTCDay()]
  const monthName = MONTHS[Number(month) - 1] ?? month
  const sameYear = year === today.slice(0, 4)
  return `${weekday} ${Number(day)} ${monthName}${sameYear ? '' : ` ${year}`}${at}`
}

const TONES: Readonly<Record<TaskGroup, Tone>> = {
  overdue: 'overdue',
  today: 'dueToday',
  soon: 'quiet',
  later: 'quiet',
  undated: 'quiet',
}

/** What a row's buttons do: the mark completes the task after the undo window, `undo` takes the press back. */
export type TaskActions = {
  done: (task: OpenTask) => Promise<void>
  undo: (id: string) => Promise<void>
}

/**
 * One task on its lines: the mark that ticks it, when it is due in its group's color, its title;
 * while a press waits, `undo` and what it will do, the title below; while it writes, that line alone;
 * what the command refused stands below the row until the next press there.
 */
function taskRow(
  $: EngineInterface,
  e: ResolveInput,
  task: OpenTask,
  group: TaskGroup,
  today: string,
  pressed: BandPress | undefined,
  actions: TaskActions,
) {
  const ui = $.ui.resolve(e)
  const { Box, Text } = ui
  const title = plainLine(task.title)
  if (pressed?.phase === 'writing') {
    return <Box key={`task:${task.id}`}>{said(ui, `completing: ${title}`, 'quiet')}</Box>
  }
  const when = whenDue(task, group, today)
  // The mark and the day are kept whole, so a narrow pane wraps the title and never breaks them.
  const line =
    pressed?.phase === 'waiting' ? (
      // The title below: beside `[ undo ] completing` a narrow pane would leave it a column or two.
      <Box flexDirection="column">
        {pressLine(ui, [{ key: undoKey(task.id), label: 'undo', kind: 'default', onPress: () => actions.undo(task.id) }], 'completing')}
        <Text wrap="wrap">{title}</Text>
      </Box>
    ) : (
      <Box flexDirection="row" columnGap={1}>
        <Box flexShrink={0}>
          {tickMark(ui, { key: `done:${task.id}`, onPress: () => actions.done(task) })}
        </Box>
        {when !== '' && (
          <Box flexShrink={0}>
            <Text {...styleOf(TONES[group])}>{when}</Text>
          </Box>
        )}
        <Text wrap="wrap">{title}</Text>
      </Box>
    )
  const refusal = refusals.get(task.id)
  return (
    <Box key={`task:${task.id}`} flexDirection="column">
      {line}
      {refusal !== undefined && under(ui, `m2b could not complete it: ${plainLine(refusal)}`, 'trouble')}
    </Box>
  )
}

/** The tab's view: one part for each group that holds a task, in the order a day passes. */
export function tasksPane(
  $: EngineInterface,
  e: ResolveInput,
  look: TasksLook,
  presses: Record<string, BandPress>,
  actions: TaskActions,
  columns: number,
) {
  const ui = $.ui.resolve(e)
  if (look.state !== 'read') {
    const line =
      look.state === 'reading' ? said(ui, READING, 'quiet') : said(ui, `m2b could not read the task list: ${plainLine(look.error)}`, 'trouble')
    return part(ui, { key: 'tasks', title: OPEN_TASKS, waits: false, columns }, [line])
  }
  const shown = GROUPS.filter(({ group }) => look.groups[group].length > 0)
  const notListed = look.unreadable.map(reason => said(ui, `m2b could not read ${plainLine(reason)}; this task is not listed until the file is fixed.`, 'trouble'))
  if (shown.length === 0) {
    return part(ui, { key: 'tasks', title: OPEN_TASKS, waits: false, columns }, [
      ...notListed,
      ...(notListed.length === 0 ? [said(ui, NOTHING_OPEN, 'quiet')] : []),
    ])
  }
  const parts = shown.map(({ group, title }) =>
    part(
      ui,
      { key: `tasks:${group}`, title, waits: false, columns },
      look.groups[group].map(task => taskRow($, e, task, group, look.today, presses[taskPressKey(task.id)], actions)),
    ),
  )
  return notListed.length === 0 ? parts : [part(ui, { key: 'tasks:unreadable', title: NOT_LISTED, waits: false, columns }, notListed), ...parts]
}
