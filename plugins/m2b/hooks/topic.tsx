import type { EngineInterface, ResolveInput } from 'claude-code'

import type { PaneView } from '../types'
import { part, said } from './look'
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

/**
 * A look at one topic of the distillate, as `m2b distillate topic` answers at the press: its facts
 * and current items, that the distillate holds no topic of the name, or why m2b could not read it.
 */
export type TopicLook =
  | { state: 'reading' }
  | { state: 'read'; facts: string[]; current: string[] }
  | { state: 'missing' }
  | { state: 'failed'; error: string }

// The look the pane shows, with the press that asked for it. The module's own: the session's
// state is one every plugin can read, and it stays over a reload of the mod, while this starts
// over with the module and is gone the moment the pane turns to anything else.
let held: { press: string; look: TopicLook } | null = null

/** Begins a look for a press, in place of whatever was kept before: m2b reads. */
export function beginTopic(press: string): void {
  held = { press, look: { state: 'reading' } }
}

/**
 * Puts m2b's answer in the place of "reading" for the press that asked. False, and nothing kept,
 * once the pane turned away from that press: an answer that comes late is dropped here.
 */
export function fillTopic(press: string, look: TopicLook): boolean {
  if (held === null || held.press !== press) {
    return false
  }
  held = { press, look }
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

/** Drops what is kept unless `view` is the topic view it was read for. */
export function forgetTopicUnless(view: PaneView | null): void {
  if (held !== null && !(view !== null && view.kind === 'topic' && view.press === held.press)) {
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
  const { found, facts, current } = answer as Record<string, unknown>
  if (typeof found !== 'boolean' || !isLines(facts) || !isLines(current)) {
    return { state: 'failed', error: OTHER_SHAPE }
  }
  return found ? { state: 'read', facts, current } : { state: 'missing' }
}

/** The topic's view, one part under the topic's name, whole. `columns` is the width of the pane's body. */
export function topicPane($: EngineInterface, e: ResolveInput, name: string, look: TopicLook, columns: number) {
  const ui = $.ui.resolve(e)
  const isEmpty = look.state === 'read' && look.facts.length === 0 && look.current.length === 0
  return part(ui, { key: 'topic', title: plainLine(name), waits: false, columns }, [
    said(ui, AS_IT_IS_NOW, 'quiet'),
    look.state === 'reading' && said(ui, READING, 'quiet'),
    look.state === 'missing' && said(ui, NO_TOPIC, 'quiet'),
    look.state === 'failed' && said(ui, `m2b could not read the topic: ${plainLine(look.error)}`, 'trouble'),
    isEmpty && said(ui, NO_LINES, 'quiet'),
    ...(look.state === 'read' ? look.facts.map(fact => said(ui, plainLine(fact))) : []),
    look.state === 'read' && look.current.length > 0 && said(ui, CURRENT, 'strong'),
    ...(look.state === 'read' ? look.current.map(item => said(ui, plainLine(item))) : []),
  ])
}
