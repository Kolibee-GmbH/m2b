import type { CommandSpec, EngineInterface, ResolveInput } from 'claude-code'

import type {
  BandDueTask,
  BandHealth,
  BandPress,
  BandProposals,
  BandSession,
  BandSnapshot,
  FolderSwitch,
  SessionTopic,
} from '../types'
import {
  NOTHING_WAITS,
  NOT_LOOKED,
  WAITS_FOR_YOU,
  button,
  dueCounts,
  part,
  pathLine,
  pressLine,
  row,
  said,
  taskLine,
  topicLabel,
  topicsCount,
  waitForYou,
} from './look'
import type { Tone } from './look'
import { plainLine, wholePath } from './plain-text'
import { answeredLine, couldNotLookLine, countLine, errorBesideTasks } from './proposals'
import { CURATE_PRESS, CURATE_ROW, REVIEW, candidateRow, changesSummary, curateButton, reviewRow } from './rows'
import type { CurateActions, RowActions } from './rows'

export { CURATE_NOW, CURATE_PRESS, UNDO_CURATE } from './rows'

/*
 * The view the m2b pane starts in, its overview: four parts in one order, what needs the person
 * first. "Waits for you" holds what the band only counts, each with its buttons; "Today" the tasks
 * due; "This session" what m2b gave this session, so the owner sees which topic's facts it holds
 * without scrolling to its start, and whether m2b is on in its folder; "m2b" how m2b itself
 * stands. The proposals, the review, the settings, a topic's lines and a search are the pane's
 * other views, each under its tab.
 *
 * A part says nothing it has nothing to say about: a count of none is not said, an empty part is
 * one line that steps back, and a part m2b has not looked at is left out, except the first, which
 * says so once.
 */

// Not `m2b`: Claude Code gives the plugin's skill of that name the short name `/m2b`. A command
// named so does not appear in its menu, and the name typed starts the skill, with a model turn.
export const SESSION_COMMAND: CommandSpec = {
  name: 'm2b-pane',
  description: 'Show in a pane what waits for you, what is due today, what m2b gave this session and how m2b stands',
  immediate: true,
}

export const SESSION_PLACED = 'what waits for you and this session are in the m2b pane'

const TODAY = 'Today'
const THIS_SESSION = 'This session'
const M2B_ITSELF = 'm2b'
// Not known is a session this machine holds no note of: started under an earlier m2b, or without m2b's hooks.
const NOT_KNOWN = 'm2b holds no note of what it gave this session; that does not say it gave nothing.'
// Turning m2b off reaches this session too: the prompt hook adds no topic where it is off.
const KEEPS = 'This session keeps what it was given and gets no more topics.'
const NOTHING_DUE = 'Nothing due today.'
const TASKS_NOT_READ = 'The task list could not be read.'
// Where the answer names no tasks due: from a core before it named them whatever the band shows.
const DUE_NOT_SHOWN = 'Tasks due are not shown.'
// Where the things a row only counts or names are shown whole: under their tab, which a line cannot press.
const IN_PROPOSALS = 'in the tab Proposals'
const WHOLE_REVIEW = 'The whole review is in the tab Review.'
const ON_HERE = 'm2b is on in this folder.'
const OFF_HERE = 'm2b is off under this folder.'
// The short forms of the small pane, where the long ones would be most of what it draws.
const NO_NOTE = 'm2b holds no note of this session.'
const SESSION_NOT_READ = 'm2b could not look at this session.'

// How the session's start printed the distillate, as the core names it.
const PRINTED = new Map([
  ['whole', 'The distillate was printed whole at the start.'],
  ['cut', 'The distillate was printed at the start, cut to fit.'],
  ['none', 'There was no distillate to print at the start.'],
])

// The press on the button for the session's folder, among the presses on rows, which go by a task's or a proposal's id.
export const FOLDER_PRESS = 'distillate:folder'
/** The key of `undo` on the folder's row, drawn only while that press waits. */
export const UNDO_FOLDER = 'undo:folder'
/**
 * Everything the overview draws from. `notes` are the notes this session wrote through the mod.
 * `rowNotice` is what m2b said to the last press on a candidate, a question or the review that
 * wrote nothing, `folderNotice` the same for the folder's button, `curateNotice` why a press on
 * `curate now` started no run. `versionLine` says that this session runs an older m2b than the
 * one installed. `curatingMachine` names the machine that curates the store, null where none is
 * known: a setting's value, which the caller holds outside the session's state.
 */
export type SessionModel = {
  given: BandSession | null
  notes: number
  rowNotice: string | null
  folderNotice: string | null
  curateNotice: string | null
  snapshot: BandSnapshot | null
  proposals: BandProposals | null
  presses: Record<string, BandPress>
  health: BandHealth | null
  curatingMachine: string | null
  versionLine: string | null
}

/**
 * What the overview's buttons do: keep, drop and `ok`; a topic's button, which turns the pane to
 * that topic's lines; m2b off or on for a folder, with its undo; and a curation run now, with its
 * undo.
 */
export type SessionActions = RowActions &
  CurateActions & {
    showTopic: (name: string) => Promise<void>
    switchFolder: (change: FolderSwitch, folder: string) => Promise<void>
    undoFolder: () => Promise<void>
  }

/** A line and what it is, by which it is drawn. */
type Line = { text: string; tone: Tone }

function line(text: string, tone: Tone = 'plain'): Line {
  return { text, tone }
}

function count(number: number, one: string, many: string): string {
  return `${number} ${number === 1 ? one : many}`
}

/**
 * How many things wait for an answer, as every surface counts them: each candidate and question,
 * each waiting proposal and the review one each. A row that was pressed counts until its write has
 * landed.
 */
export function waitCount(snapshot: BandSnapshot | null, proposals: BandProposals | null): number {
  return (snapshot?.candidates.length ?? 0) + (proposals?.waiting.length ?? 0) + (snapshot?.review ? 1 : 0)
}

function proposalsError(model: SessionModel): string | null {
  return errorBesideTasks(model.snapshot?.error ?? null, model.proposals)
}

/**
 * What stands in "Waits for you" before its rows: that m2b has not looked, what it could not read,
 * and what it said to a press that wrote nothing, which is said where it was pressed.
 */
function waitsNotes(model: SessionModel): Line[] {
  const { snapshot, rowNotice } = model
  const storeError = proposalsError(model)
  return [
    ...(snapshot === null ? [line(NOT_LOOKED, 'quiet')] : []),
    ...(snapshot?.error ? [line(plainLine(snapshot.error), 'trouble')] : []),
    ...(storeError === null ? [] : [line(couldNotLookLine(storeError), 'trouble')]),
    ...(rowNotice === null ? [] : [line(plainLine(rowNotice), 'trouble')]),
  ]
}

function waitsNothing(model: SessionModel): boolean {
  const { snapshot, proposals } = model
  return snapshot !== null && snapshot.error === null && proposalsError(model) === null && waitCount(snapshot, proposals) === 0
}

/**
 * Today's tasks first, then the overdue ones, the most recent first: a task left overdue for weeks
 * would otherwise stand above what is due today.
 */
export function dueFirst(due: BandDueTask[]): BandDueTask[] {
  return [...due.filter(task => !task.overdue), ...due.filter(task => task.overdue).reverse()]
}

export function dueLine(task: BandDueTask): string {
  return `${task.overdue ? 'overdue' : 'due today'}: ${plainLine(task.title)}`
}

/**
 * What "Today" says in place of tasks, or null where it lists them. The part is left out where
 * m2b has not looked or could not read the tasks: "Waits for you" says that once.
 */
function noDueLine(snapshot: BandSnapshot): string | null {
  if (snapshot.due === undefined) {
    return DUE_NOT_SHOWN
  }
  return snapshot.due.length === 0 ? NOTHING_DUE : null
}

function hasToday(snapshot: BandSnapshot | null): snapshot is BandSnapshot {
  return snapshot !== null && snapshot.error === null
}

/** `3 facts, 1 current`, or null where the topic's block was not counted or holds none of either. */
function topicCounts(topic: SessionTopic): string | null {
  const held = [
    ...(topic.facts === null || topic.facts === 0 ? [] : [count(topic.facts, 'fact', 'facts')]),
    ...(topic.current === null || topic.current === 0 ? [] : [`${topic.current} current`]),
  ]
  return held.length === 0 ? null : held.join(', ')
}

/** What "This session" says before its topics: that m2b could not look, or holds no note of the session. */
function givenNotes(given: BandSession): Line[] {
  if (given.error !== null) {
    return [line(`m2b could not look up what it gave this session: ${plainLine(given.error)}`, 'trouble')]
  }
  return given.known ? [] : [line(NOT_KNOWN, 'quiet')]
}

function printedLine(given: BandSession): string | null {
  if (given.atStart === null) {
    return null
  }
  return PRINTED.get(given.atStart) ?? `The distillate at the start: ${plainLine(given.atStart)}`
}

/**
 * Whether m2b is on in the session's folder, and the folder a press acts on: the session's own
 * where m2b is on, the one it is off under where it is off, which may lie above the session's.
 */
type FolderState = { isOn: boolean; folder: string }

/** Null where m2b could not look, or named no folder: a look that failed names neither. */
function folderState(given: BandSession): FolderState | null {
  const folder = given.offUnder ?? given.folder ?? null
  return folder === null ? null : { isOn: given.offUnder === null, folder }
}

/**
 * That the session gets no more topics, said only where m2b is off and knows what the session was
 * given: beside "holds no note of what it gave", "keeps what it was given" reads as its opposite.
 */
function keepsLine(given: BandSession): string | null {
  return given.offUnder !== null && given.error === null && given.known ? KEEPS : null
}

function notesLine(notes: number): string | null {
  return notes > 0 ? `${count(notes, 'note', 'notes')} written in this session` : null
}

/** What is wrong with m2b, each with its reason, then an older m2b in this session. */
function troubleLines(model: SessionModel): Line[] {
  const { health, versionLine } = model
  return [
    ...(health?.troubles ?? []).map(trouble => line(plainLine(trouble), 'trouble')),
    ...(versionLine === null ? [] : [line(plainLine(versionLine), 'waits')]),
  ]
}

/** Which machine runs curation, said on every other one: there is nothing to start here. */
function curatesElsewhere(model: SessionModel): Line[] {
  return model.health?.curates === false && model.curatingMachine !== null
    ? [line(`Curation runs on ${plainLine(model.curatingMachine)}.`, 'quiet')]
    : []
}

/** How m2b itself stands, as lines: what is wrong first, then the line about curation, which steps back, and where curation runs. */
function healthLines(model: SessionModel): Line[] {
  const { health } = model
  return [
    ...troubleLines(model),
    ...(health?.curation ? [line(plainLine(health.curation), 'quiet')] : []),
    ...curatesElsewhere(model),
  ]
}

function present<T>(value: T | null | false): value is T {
  return value !== null && value !== false
}

/**
 * The overview as lines of text, for a surface that cannot show the pane: the same parts in the
 * same order and words. What waits is named with the command that shows it, since a line has no
 * button.
 */
export function sessionLines(model: SessionModel): string[] {
  const { snapshot, proposals } = model
  const waiting = proposals?.waiting.length ?? 0
  const waits = [
    ...waitsNotes(model).map(one => one.text),
    ...(waiting > 0 ? [`${countLine(waiting)}: /m2b-proposals`] : []),
    ...(snapshot?.candidates ?? []).map(candidate => plainLine(candidate.title)),
    ...(snapshot?.review ? [`${[REVIEW, changesSummary(snapshot.review)].filter(present).join(', ')}: /m2b-review`] : []),
    ...(waitsNothing(model) ? [NOTHING_WAITS] : []),
  ]
  const instead = hasToday(snapshot) ? noDueLine(snapshot) : null
  const today = !hasToday(snapshot) ? null : instead === null ? dueFirst(snapshot.due ?? []).map(dueLine) : [instead]
  const health = healthLines(model).map(one => one.text)
  const parts: [string, string[] | null][] = [
    [WAITS_FOR_YOU, waits],
    [TODAY, today],
    [THIS_SESSION, sessionTexts(model)],
    [M2B_ITSELF, health.length === 0 ? null : health],
  ]
  return parts.flatMap(([title, lines]) => (lines === null ? [] : [title, ...lines.map(one => `  ${one}`)]))
}

/** The lines of "This session", null where the part is left out: m2b has looked at nothing yet, which the first part says, or has nothing to say of the session. */
function sessionTexts(model: SessionModel): string[] | null {
  const { given, snapshot } = model
  if (given === null) {
    return snapshot === null ? null : [NOT_LOOKED]
  }
  const folder = folderState(given)
  const lines = [
    ...givenNotes(given).map(one => one.text),
    ...given.topics.map(topic => [plainLine(topic.name), topicCounts(topic)].filter(present).join(': ')),
    printedLine(given),
    folder === null ? null : folder.isOn ? `${ON_HERE.slice(0, -1)}: ${wholePath(folder.folder)}` : `m2b is off under ${wholePath(folder.folder)}`,
    keepsLine(given),
    model.folderNotice === null ? null : plainLine(model.folderNotice),
    notesLine(model.notes),
  ].filter(present)
  // A session m2b knows and has nothing to say of: no part, as in the pane.
  return lines.length === 0 ? null : lines
}

function waitsGlance(model: SessionModel): string {
  const { snapshot, proposals } = model
  if (snapshot === null) {
    return NOT_LOOKED
  }
  if (snapshot.error !== null) {
    return TASKS_NOT_READ
  }
  const storeError = proposalsError(model)
  if (storeError !== null) {
    return couldNotLookLine(storeError)
  }
  const waits = waitCount(snapshot, proposals)
  return waits === 0 ? NOTHING_WAITS : waitForYou(waits)
}

function dueGlance(snapshot: BandSnapshot | null): string | null {
  const counts = dueCounts(snapshot?.due ?? []).map(one => one.text)
  return counts.length === 0 ? null : counts.join(', ')
}

function sessionGlance(given: BandSession | null, snapshot: BandSnapshot | null): string | null {
  if (given === null) {
    return snapshot === null ? null : NOT_LOOKED
  }
  if (given.error !== null) {
    return SESSION_NOT_READ
  }
  if (!given.known) {
    return NO_NOTE
  }
  return given.topics.length === 0 ? null : `${topicsCount(given.topics.length)} in this session`
}

/**
 * The pane as counts, for the small form the desktop app gives a minimized pane, in the order of
 * the overview: how many things wait, how many tasks are due, how many topics this session was
 * given. What could not be looked at is said in place of its count, and a count of none is not
 * said, except that nothing waits.
 */
export function glanceLines(model: SessionModel): string[] {
  return [waitsGlance(model), dueGlance(model.snapshot), sessionGlance(model.given, model.snapshot)].filter(present)
}

/** The small form's drawing: lines to read at a glance and no button, since a click may not reach it. */
export function glancePane($: EngineInterface, e: ResolveInput, model: SessionModel) {
  const ui = $.ui.resolve(e)
  const { Box } = ui
  return <Box flexDirection="column">{glanceLines(model).map(one => said(ui, one))}</Box>
}

function topicKey(index: number): string {
  return `topic:${index}`
}

/**
 * The key of the button of the topic `name`, null where the overview draws none for it. The
 * pane's other views draw no button under it.
 */
export function topicShowKey(model: SessionModel, name: string): string | null {
  const index = model.given === null || model.given.error !== null ? -1 : model.given.topics.findIndex(topic => topic.name === name)
  return index === -1 ? null : topicKey(index)
}

/** "Waits for you": the proposals as a count that names their tab, every candidate and question, and the review, each with its buttons. */
function waitsPart($: EngineInterface, e: ResolveInput, model: SessionModel, actions: SessionActions, columns: number) {
  const ui = $.ui.resolve(e)
  const { snapshot, proposals, presses } = model
  const waiting = proposals?.waiting.length ?? 0
  const review = snapshot?.review ?? null
  const waits = waitCount(snapshot, proposals)
  return part(ui, { key: 'waits', title: WAITS_FOR_YOU, waits: waits > 0, count: waits > 0 ? String(waits) : null, columns }, [
    ...waitsNotes(model).map(one => said(ui, one.text, one.tone)),
    waiting > 0 && row(ui, { key: 'row:proposals', text: countLine(waiting), buttons: [], detail: IN_PROPOSALS }),
    ...(snapshot?.candidates ?? []).map(candidate => candidateRow($, e, candidate, presses[candidate.id], actions)),
    review !== null && reviewRow($, e, review, presses[review.id], actions),
    review !== null && said(ui, WHOLE_REVIEW, 'quiet'),
    waitsNothing(model) && said(ui, NOTHING_WAITS, 'quiet'),
  ])
}

/** "Today": the tasks due, each with when it is due in its color, whatever the band shows of them. */
function todayPart($: EngineInterface, e: ResolveInput, snapshot: BandSnapshot | null, columns: number) {
  if (!hasToday(snapshot)) {
    return null
  }
  const ui = $.ui.resolve(e)
  const instead = noDueLine(snapshot)
  return part(
    ui,
    { key: 'today', title: TODAY, waits: false, columns },
    instead === null ? dueFirst(snapshot.due ?? []).map(task => taskLine(ui, task, 'wrap')) : [said(ui, instead, 'quiet')],
  )
}

/**
 * m2b in the session's folder: on or off, the folder a press acts on, drawn whole, and the button
 * that turns it off there or on again. Like keep and drop the press waits for undo, and while it
 * writes the row offers nothing. No row where m2b could not look, or named no folder.
 */
function folderRow(
  $: EngineInterface,
  e: ResolveInput,
  given: BandSession,
  pressed: BandPress | undefined,
  actions: SessionActions,
) {
  const state = folderState(given)
  if (state === null) {
    return null
  }
  const ui = $.ui.resolve(e)
  const { Box } = ui
  const { isOn, folder } = state
  const change: FolderSwitch = isOn ? 'off' : 'on'
  const doing = `turning m2b ${pressed?.action === 'on' ? 'on' : 'off'} here`
  return (
    <Box key="row:folder" flexDirection="column">
      {said(ui, isOn ? ON_HERE : OFF_HERE)}
      {/* The press hands the folder on as m2b named it, so every character of it is drawn. */}
      {pathLine(ui, folder)}
      {pressed === undefined &&
        button(ui, {
          key: `folder:${change}`,
          label: isOn ? 'turn off here' : 'turn on here',
          kind: isOn ? 'quiet' : 'default',
          onPress: () => actions.switchFolder(change, folder),
        })}
      {pressed?.phase === 'waiting' && pressLine(ui, [{ key: UNDO_FOLDER, label: 'undo', kind: 'default', onPress: actions.undoFolder }], doing)}
      {pressed?.phase === 'writing' && said(ui, `${doing}…`, 'quiet')}
    </Box>
  )
}

/** "This session": the topics m2b gave it, each a button to its lines, how its start printed the distillate, m2b in its folder, and its notes. */
function sessionPart($: EngineInterface, e: ResolveInput, model: SessionModel, actions: SessionActions, columns: number) {
  const { given, snapshot } = model
  const ui = $.ui.resolve(e)
  const { Box } = ui
  const spec = { key: 'session', title: THIS_SESSION, waits: false, columns }
  if (given === null) {
    return snapshot === null ? null : part(ui, spec, [said(ui, NOT_LOOKED, 'quiet')])
  }
  const printed = printedLine(given)
  const keeps = keepsLine(given)
  const notes = notesLine(model.notes)
  const body = [
    ...givenNotes(given).map(one => said(ui, one.text, one.tone)),
    ...given.topics.map((topic, index) => {
      const lead = { key: topicKey(index), label: topicLabel(topic.name), kind: 'default' as const, onPress: () => actions.showTopic(topic.name) }
      return pressLine(ui, [lead], topicCounts(topic), `row:topic:${index}`)
    }),
    printed !== null && said(ui, printed),
    folderRow($, e, given, model.presses[FOLDER_PRESS], actions),
    keeps !== null && said(ui, keeps, 'quiet'),
    model.folderNotice !== null && said(ui, plainLine(model.folderNotice), 'trouble'),
    notes !== null && said(ui, notes),
  ].filter(present)
  // A title with nothing below it says nothing: a session m2b knows and has nothing to say of gets no part.
  return body.length === 0 ? null : part(ui, spec, body)
}

/**
 * How curation stands, how many answers to proposals wait for a run, and on the machine that
 * curates the button that starts a run now. Like keep and drop the press waits for undo, and while
 * it starts the run the row offers nothing. No button while a run is under way, on a machine that
 * does not curate, or where m2b could not tell. A press that waits keeps its `undo` whatever a
 * look reads meanwhile: it can still be taken back. While a run is under way nothing is said of
 * the answers: the run files them.
 */
function curationLines($: EngineInterface, e: ResolveInput, model: SessionModel, health: BandHealth, actions: CurateActions) {
  const ui = $.ui.resolve(e)
  const { Box } = ui
  const pressed = model.presses[CURATE_PRESS]
  const standing = health.curation ? said(ui, plainLine(health.curation), 'quiet') : null
  const answered = health.isCurating ? 0 : (model.proposals?.answered ?? 0)
  const answers = answered > 0 ? said(ui, answeredLine(answered), 'quiet') : null
  if (pressed === undefined && (health.curates !== true || health.isCurating)) {
    return [standing, answers]
  }
  return [
    <Box key={CURATE_ROW} flexDirection="column">
      {standing}
      {answers}
      {curateButton($, e, pressed, actions)}
    </Box>,
  ]
}

/**
 * "m2b": what is wrong with m2b, each with its reason, why the last press started no run, and how
 * curation stands, with the button that starts a run on the machine that curates. Left out where
 * there is nothing to say.
 */
function healthPart($: EngineInterface, e: ResolveInput, model: SessionModel, actions: SessionActions, columns: number) {
  const { health, curateNotice } = model
  const ui = $.ui.resolve(e)
  const body = [
    ...troubleLines(model).map(one => said(ui, one.text, one.tone)),
    curateNotice !== null && said(ui, plainLine(curateNotice), 'trouble'),
    ...(health === null ? [] : curationLines($, e, model, health, actions)),
    ...curatesElsewhere(model).map(one => said(ui, one.text, one.tone)),
  ].filter(present)
  return body.length === 0 ? null : part(ui, { key: 'm2b', title: M2B_ITSELF, waits: false, columns }, body)
}

/** The overview's drawing. `columns` is the width of the pane's body: docked beside the chat it can be 24. */
export function sessionPane($: EngineInterface, e: ResolveInput, model: SessionModel, actions: SessionActions, columns: number) {
  const { Box } = $.ui.resolve(e)
  return (
    <Box flexDirection="column">
      {waitsPart($, e, model, actions, columns)}
      {todayPart($, e, model.snapshot, columns)}
      {sessionPart($, e, model, actions, columns)}
      {healthPart($, e, model, actions, columns)}
    </Box>
  )
}
