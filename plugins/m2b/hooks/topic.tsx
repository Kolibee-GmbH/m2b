import type { EngineInterface, ResolveInput } from 'claude-code'

import type { PaneView } from '../types'
import { currentItemRow } from './current-item'
import type { TabId } from './pane-tabs'
import { opensRow, part, said } from './look'
import { runM2b } from './m2b'
import { plainLine } from './plain-text'
import { OLDER_CORE } from './session'

/*
 * The lines of one topic the session was given, shown on a press in the pane's start view. m2b
 * keeps the names and counts of what it gave a session, never the lines, so they are read from the
 * distillate as it is at the press, and the view says so. They are the owner's facts, often about
 * a customer: this module hands them to the pane's drawing alone. No command of the band answers
 * with them, and nothing here writes them to a file, into the session's state or into a text for
 * the conversation.
 */

/** A fact of a topic: what it states, and the fact file its line names, or null. */
export type TopicFact = { statement: string; file: string | null }

/**
 * A look at one topic of the distillate, as `m2b distillate topic` answers at the press: its facts
 * and current items, that the distillate holds no topic of the name, or why m2b could not read it.
 */
export type TopicLook =
  | { state: 'reading' }
  | { state: 'read'; facts: TopicFact[]; current: string[] }
  | { state: 'missing' }
  | { state: 'failed'; error: string }

// The look the pane shows, with the press that asked for it. The module's own: the session's
// state is one every plugin can read, and it stays over a reload of the mod, while this starts
// over with the module and is gone the moment the pane turns to anything else.
// The topic's name too: opened from the tab Facts it can be one this session was never given, a
// customer's among them, and the view in the session's state names only the press.
// `origin` is the tab the topic was opened from, which leads back from it and from a note opened here.
let held: { press: string; name: string; origin: TabId; look: TopicLook } | null = null

/** Begins a look for a press, in place of whatever was kept before: m2b reads. */
export function beginTopic(press: string, name: string, origin: TabId = 'overview'): void {
  held = { press, name, origin, look: { state: 'reading' } }
}

/** The tab the press opened the topic from; the overview where nothing is kept for it. */
export function topicOriginOf(press: string): TabId {
  return held !== null && held.press === press ? held.origin : 'overview'
}

/** The name of the topic the press opened; empty where nothing is kept for it, as after a reload of the mod. */
export function topicNameOf(press: string): string {
  return held !== null && held.press === press ? held.name : ''
}

/**
 * Puts m2b's answer in the place of "reading" for the press that asked. False, and nothing kept,
 * once the pane turned away from that press: an answer that comes late is dropped here.
 */
export function fillTopic(press: string, look: TopicLook): boolean {
  if (held === null || held.press !== press) {
    return false
  }
  held = { ...held, look }
  return true
}

/** The look kept for this press. Where none is kept, as after a reload of the mod, m2b counts as still reading. */
export function heldTopic(press: string): TopicLook {
  return held !== null && held.press === press ? held.look : { state: 'reading' }
}

/** Whether a look is kept at all. Nothing outside the module can read what it keeps, so its tests ask this. */
export function holdsTopic(): boolean {
  return held !== null
}

/**
 * Drops what is kept unless `view` is the topic view it was read for, or `behind` names that
 * topic's press: a view that leads back to the topic, a fact file opened from it.
 */
export function forgetTopicUnless(view: PaneView | null, behind: string | null = null): void {
  const isShown = view !== null && view.kind === 'topic' && view.press === held?.press
  if (held !== null && !isShown && behind !== held.press) {
    held = null
  }
}

const READ_TIMEOUT_MS = 20_000
// The exit of the core's command line for a call it cannot take, and what it says to an action it does not know.
const EXIT_USAGE = 2
const UNKNOWN_ACTION = /invalid choice|unrecognized arguments/
const OTHER_SHAPE = 'm2b answered something other than a topic'
const AS_IT_IS_NOW = 'As the distillate holds it now, which may differ from what this session was given.'
const READING = 'm2b is reading the topic…'
const NO_TOPIC = 'The distillate holds no topic of this name now.'
const NO_LINES = 'The topic holds no lines now.'
const CURRENT = 'Current'

/** Reads one topic from the distillate as it is now; whatever fails, the look says why. */
export async function readTopic($: EngineInterface, name: string): Promise<TopicLook> {
  // `--`: a name is the distillate's own text, and it may start with a dash.
  const outcome = await runM2b($, ['distillate', 'topic', '--json', '--', name], READ_TIMEOUT_MS)
  if (outcome.ok) {
    return parseTopic(outcome.stdout)
  }
  const isOlderCore = outcome.exitCode === EXIT_USAGE && UNKNOWN_ACTION.test(outcome.stderr ?? '')
  return { state: 'failed', error: isOlderCore ? OLDER_CORE : outcome.error }
}

function isLines(value: unknown): value is string[] {
  return Array.isArray(value) && value.every(line => typeof line === 'string')
}

function isTopicFact(value: unknown): value is TopicFact {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    return false
  }
  const { statement, file } = value as Record<string, unknown>
  return typeof statement === 'string' && (file === null || typeof file === 'string')
}

/**
 * Each fact with its fact file. A core from before `facts_with_files` names no file: its facts are
 * drawn as text. A key that does not name the same facts as `facts` is null, another shape.
 */
function factsOf(facts: string[], withFiles: unknown): TopicFact[] | null {
  if (withFiles === undefined) {
    return facts.map(statement => ({ statement, file: null }))
  }
  const isSame = Array.isArray(withFiles) && withFiles.length === facts.length && withFiles.every((fact, at) => isTopicFact(fact) && fact.statement === facts[at])
  return isSame ? withFiles.map(fact => ({ statement: fact.statement, file: fact.file })) : null
}

/** The answer of `m2b distillate topic --json`; one of any other shape is could not read, never a topic without lines. */
export function parseTopic(text: string): TopicLook {
  let answer: unknown
  try {
    answer = JSON.parse(text)
  } catch {
    return { state: 'failed', error: OTHER_SHAPE }
  }
  if (typeof answer !== 'object' || answer === null) {
    return { state: 'failed', error: OTHER_SHAPE }
  }
  const { found, facts, current, facts_with_files: withFiles } = answer as Record<string, unknown>
  if (typeof found !== 'boolean' || !isLines(facts) || !isLines(current)) {
    return { state: 'failed', error: OTHER_SHAPE }
  }
  const topicFacts = factsOf(facts, withFiles)
  if (topicFacts === null) {
    return { state: 'failed', error: OTHER_SHAPE }
  }
  return found ? { state: 'read', facts: topicFacts, current } : { state: 'missing' }
}

/** The key of the row of the topic's fact drawn at `index`, which opens its file. */
export function topicFactKey(index: number): string {
  return `topic-fact:${index}`
}

/**
 * What a press in a topic's view does: a fact's row opens its file, `index` the place of the fact
 * the way back leads to; a note's button opens the note.
 */
export type TopicActions = {
  details: (index: number, file: string) => Promise<void>
  showNote: (note: string) => Promise<void>
}

/**
 * The topic's view, one part under the topic's name, whole: its facts, each that names a fact file
 * a row that opens it, then its current items, each with its way to the notes it names
 * (`current-item.tsx`). `columns` is the width of the pane's body, `nowMs` the moment a note's day
 * is said against.
 */
export function topicPane(
  $: EngineInterface,
  e: ResolveInput,
  name: string,
  look: TopicLook,
  actions: TopicActions,
  columns: number,
  nowMs: number,
) {
  const ui = $.ui.resolve(e)
  const isEmpty = look.state === 'read' && look.facts.length === 0 && look.current.length === 0
  return part(ui, { key: 'topic', title: plainLine(name), waits: false, columns }, [
    said(ui, AS_IT_IS_NOW, 'quiet'),
    look.state === 'reading' && said(ui, READING, 'quiet'),
    look.state === 'missing' && said(ui, NO_TOPIC, 'quiet'),
    look.state === 'failed' && said(ui, `m2b could not read the topic: ${plainLine(look.error)}`, 'trouble'),
    isEmpty && said(ui, NO_LINES, 'quiet'),
    ...(look.state === 'read' ? look.facts.map((fact, index) => factRow(ui, fact, index, actions)) : []),
    look.state === 'read' && look.current.length > 0 && said(ui, CURRENT, 'strong'),
    ...(look.state === 'read' ? look.current.map((item, index) => currentItemRow($, e, index, item, actions.showNote, nowMs)) : []),
  ])
}

/** A fact of the topic: a row that opens its fact file, or its words alone where its line names none. */
function factRow(ui: ReturnType<EngineInterface['ui']['resolve']>, fact: TopicFact, index: number, actions: TopicActions) {
  const { Box } = ui
  const file = fact.file
  return (
    <Box key={`topic-fact-row:${index}`} flexDirection="column">
      {file === null
        ? said(ui, plainLine(fact.statement))
        : opensRow(ui, { key: topicFactKey(index), text: plainLine(fact.statement), onPress: () => actions.details(index, file) })}
    </Box>
  )
}
