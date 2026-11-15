import type { CommandSpec, EngineInterface, ResolveInput } from 'claude-code'

import type { BandDueTask, BandPress, BandProposals, BandSession, BandSnapshot, SessionTopic } from '../types'
import { plainLine } from './plain-text'
import { couldNotLookLine, countLine, errorBesideTasks, proposalsRow } from './proposals'
import { candidateRow, reviewRow } from './rows'
import type { RowActions } from './rows'

/*
 * The view the m2b pane starts in, in three parts: what m2b gave this session, so the owner sees
 * which topic's facts it holds without scrolling to its start; what waits for an answer, with the
 * buttons the band has; and the tasks due today. The review, a search and the proposals are the
 * pane's other views.
 */

export const SESSION_COMMAND: CommandSpec = {
  name: 'm2b',
  description: 'Show in a pane what m2b gave this session, what waits for you and what is due today',
  immediate: true,
}

export const SESSION_PLACED = 'this session and what waits for you are in the m2b pane'

const IN_THIS_SESSION = 'In this session'
const WAITS_FOR_YOU = 'Waits for you'
const TODAY = 'Today'
const NOT_LOOKED = 'm2b has not looked yet.'
// Not known is a session this machine holds no note of: started under an earlier m2b, or without m2b's hooks.
const NOT_KNOWN = 'm2b holds no note of what it gave this session; that does not say it gave nothing.'
const NO_TOPIC = 'No topic was given.'
const NOTHING_WAITS = 'Nothing waits for you.'
const NOTHING_DUE = 'Nothing due today.'
const TASKS_NOT_READ = 'The task list could not be read.'
// With `band.due_tasks` off, and in an answer a session with an earlier band shared.
const DUE_NOT_SHOWN = 'Tasks due are not shown.'
const WHOLE_REVIEW = 'the whole review'

// How the session's start printed the distillate, as the core names it.
const PRINTED = new Map([
  ['whole', 'The distillate was printed whole at the start.'],
  ['cut', 'The distillate was printed at the start, cut to fit.'],
  ['none', 'There was no distillate to print at the start.'],
])

/** Everything the start view draws. `notes` are the notes this session wrote through the mod. */
export type SessionModel = {
  given: BandSession | null
  notes: number
  snapshot: BandSnapshot | null
  proposals: BandProposals | null
  presses: Record<string, BandPress>
}

/** What the start view's buttons do: keep, drop and `ok` as in the band, and `show`, which turns the pane. */
export type SessionActions = RowActions & {
  showProposals: () => Promise<void>
  showReview: () => Promise<void>
}

function count(number: number, one: string, many: string): string {
  return `${number} ${number === 1 ? one : many}`
}

/** `Northwind: 3 facts, 1 current`, or the name alone where its block's lines were not noted. */
function topicLine(topic: SessionTopic): string {
  const held = [
    ...(topic.facts === null ? [] : [count(topic.facts, 'fact', 'facts')]),
    ...(topic.current === null || topic.current === 0 ? [] : [`${topic.current} current`]),
  ]
  const name = plainLine(topic.name)
  return held.length === 0 ? name : `${name}: ${held.join(', ')}`
}

/** A line of the first part and how it is drawn: as it is, dim for what is not known, or as an error. */
export type GivenLine = { text: string; tone: 'plain' | 'quiet' | 'error' }

function plain(text: string): GivenLine {
  return { text, tone: 'plain' }
}

/** What m2b gave this session, as lines: its topics, the distillate at its start and now, its notes. */
export function givenLines(given: BandSession | null, notes: number): GivenLine[] {
  const written = notes > 0 ? [plain(`${count(notes, 'note', 'notes')} written in this session`)] : []
  if (given === null) {
    return [{ text: NOT_LOOKED, tone: 'quiet' }, ...written]
  }
  if (given.error !== null) {
    return [{ text: `m2b could not look up what it gave this session: ${plainLine(given.error)}`, tone: 'error' }, ...written]
  }
  const printed = given.atStart === null ? undefined : (PRINTED.get(given.atStart) ?? `The distillate at the start: ${plainLine(given.atStart)}`)
  return [
    ...(given.known ? (given.topics.length === 0 ? [plain(NO_TOPIC)] : []) : [{ text: NOT_KNOWN, tone: 'quiet' } as const]),
    ...given.topics.map(topic => plain(topicLine(topic))),
    ...(printed === undefined ? [] : [plain(printed)]),
    ...(given.offUnder === null
      ? []
      : [plain(`The distillate is off under ${plainLine(given.offUnder)}: a session that starts there gets none.`)]),
    ...written,
  ]
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

function proposalsError(model: SessionModel): string | null {
  return errorBesideTasks(model.snapshot?.error ?? null, model.proposals)
}

function waitsNothing(model: SessionModel): boolean {
  const { snapshot, proposals } = model
  return (
    snapshot !== null &&
    snapshot.error === null &&
    snapshot.candidates.length === 0 &&
    snapshot.review === null &&
    (proposals?.waiting.length ?? 0) === 0 &&
    proposalsError(model) === null
  )
}

/** What the third part says in place of tasks, or null where it lists them. */
function noDueLine(snapshot: BandSnapshot | null): string | null {
  if (snapshot === null) {
    return NOT_LOOKED
  }
  if (snapshot.error !== null) {
    return TASKS_NOT_READ
  }
  if (snapshot.due === undefined) {
    return DUE_NOT_SHOWN
  }
  return snapshot.due.length === 0 ? NOTHING_DUE : null
}

/**
 * The start view as lines of text, for a surface that cannot show the pane: what waits is named
 * with the command that shows it, since a line has no button.
 */
export function sessionLines(model: SessionModel): string[] {
  const { snapshot, proposals } = model
  const waiting = proposals?.waiting.length ?? 0
  const storeError = proposalsError(model)
  const waits = [
    ...(snapshot === null ? [NOT_LOOKED] : []),
    ...(snapshot?.error ? [plainLine(snapshot.error)] : []),
    ...(storeError === null ? [] : [couldNotLookLine(storeError)]),
    ...(waiting > 0 ? [`${countLine(waiting)}: /m2b-proposals`] : []),
    ...(snapshot?.candidates ?? []).map(candidate => plainLine(candidate.title)),
    ...(snapshot?.review ? [`${plainLine(snapshot.review.title)}: /m2b-review`] : []),
    ...(waitsNothing(model) ? [NOTHING_WAITS] : []),
  ]
  const nothingDue = noDueLine(snapshot)
  const due = nothingDue === null ? dueFirst(snapshot?.due ?? []).map(dueLine) : [nothingDue]
  const indented = (lines: string[]): string[] => lines.map(line => `  ${line}`)
  return [
    IN_THIS_SESSION,
    ...indented(givenLines(model.given, model.notes).map(line => line.text)),
    WAITS_FOR_YOU,
    ...indented(waits),
    TODAY,
    ...indented(due),
  ]
}

/**
 * The way back to the start view, drawn above the pane's other views. Escape goes the same way
 * there; the button is for a pointer, and for a pane that does not hold the keyboard.
 */
export function backRow($: EngineInterface, e: ResolveInput, back: () => Promise<void>) {
  const { Button } = $.ui.resolve(e)
  return <Button key="back" label="back" onPress={back} />
}

/** The start view's drawing. Every line wraps: docked beside the chat, the pane can be 24 columns wide. */
export function sessionPane($: EngineInterface, e: ResolveInput, model: SessionModel, actions: SessionActions) {
  const { Box, Button, Text } = $.ui.resolve(e)
  const { given, snapshot, proposals, presses } = model
  const heading = (text: string) => (
    <Text weight="semibold" wrap="wrap">
      {text}
    </Text>
  )
  const quiet = (text: string) => (
    <Text dimColor wrap="wrap">
      {text}
    </Text>
  )
  const failure = (text: string) => (
    <Text color="error" wrap="wrap">
      {text}
    </Text>
  )
  const review = snapshot?.review ?? null
  const waiting = proposals?.waiting.length ?? 0
  const storeError = proposalsError(model)
  const nothingDue = noDueLine(snapshot)
  return (
    <Box flexDirection="column">
      {heading(IN_THIS_SESSION)}
      {givenLines(given, model.notes).map(({ text, tone }) =>
        tone === 'error' ? failure(text) : tone === 'quiet' ? quiet(text) : <Text wrap="wrap">{text}</Text>,
      )}
      {heading(WAITS_FOR_YOU)}
      {snapshot === null && quiet(NOT_LOOKED)}
      {snapshot?.error ? failure(plainLine(snapshot.error)) : null}
      {storeError !== null && failure(couldNotLookLine(storeError))}
      {waiting > 0 && proposalsRow($, e, waiting, actions.showProposals, 'wrap')}
      {(snapshot?.candidates ?? []).map(candidate => candidateRow($, e, candidate, presses[candidate.id], actions, 'wrap'))}
      {review !== null && reviewRow($, e, review, presses[review.id], actions, 'wrap')}
      {review !== null && (
        <Box key="row:whole-review" flexDirection="row">
          <Button key="show:review" label="show" onPress={actions.showReview} />
          <Text dimColor wrap="wrap">
            {' '}
            {WHOLE_REVIEW}
          </Text>
        </Box>
      )}
      {waitsNothing(model) && quiet(NOTHING_WAITS)}
      {heading(TODAY)}
      {nothingDue === null
        ? dueFirst(snapshot?.due ?? []).map(task => <Text wrap="wrap">{dueLine(task)}</Text>)
        : quiet(nothingDue)}
    </Box>
  )
}
