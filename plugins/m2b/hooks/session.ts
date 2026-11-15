import { atom, update } from 'claude-code'
import type { EngineInterface } from 'claude-code'

import type { BandSession, SessionNotes, SessionTopic } from '../types'
import { runM2b } from './m2b'

/*
 * What m2b gave this session, and the notes the session wrote. Every session asks for itself, with
 * `m2b band --json --session <id> --session-only`, and keeps the answer in its own state: the
 * band's other answer is one the open sessions share, and what one session was given is no other
 * session's to show. The question reads one small file of the machine state and the machine
 * config, no task list and no store, so asking it per session costs little.
 */

const sessionAtom = atom({ plugin: 'm2b', key: 'bandSession' } as const, null)
const notesAtom = atom({ plugin: 'm2b', key: 'sessionNotes' } as const, null)

const LOOK_TIMEOUT_MS = 20_000
// The exit of the core's command line for a call it cannot take, and what it says to an option it does not know.
const EXIT_USAGE = 2
const UNKNOWN_OPTION = /unrecognized arguments/
const OTHER_SHAPE = 'm2b answered something other than what a session was given'
const OLDER_CORE = 'the installed m2b is older than this band; update m2b, then run /reload-plugins'
const NO_ID = 'this session cannot name itself'

// A core from before the question refuses it on every call, so it is asked once per session start.
let doesCoreAnswer = true
// Looks overlap: one after a prompt, one when the turn ends, one for the command. A slow one may
// answer after a later one, so only the look started last writes. The count is this module's: a
// look of an earlier load of the mod that is still under way can write once more, for the same
// session and a few seconds older, until the next look replaces it.
let lookCount = 0

/** Begins a look and answers its number, which the look hands back when it writes. */
export function beginLook(): number {
  lookCount += 1
  return lookCount
}

/** At session start: the installed core may be another one than at the last start. */
export function askCoreAgain(): void {
  doesCoreAnswer = true
}

/** The id Claude Code gives this session, or null where it cannot say. */
export async function sessionIdOf($: EngineInterface): Promise<string | null> {
  try {
    const id: unknown = await $.session.id()
    return typeof id === 'string' && id !== '' ? id : null
  } catch {
    return null
  }
}

/**
 * Asks m2b what it gave this session and keeps the answer, also one that says it could not look.
 * The answer is kept with the id it was asked for: after `/clear` or a resume the session goes on
 * under another id, and what the ended conversation was given is not the new one's.
 */
export async function lookAtSession($: EngineInterface, look: number): Promise<BandSession> {
  const given = await askM2b($)
  if (look === lookCount) {
    await update($, sessionAtom, () => given)
  }
  return given
}

/** Keeps that a look could not even be started, so the pane says so instead of waiting for one. */
export async function lookFailed($: EngineInterface, look: number, reason: string): Promise<BandSession> {
  const given = couldNotLook(await sessionIdOf($), reason)
  if (look === lookCount) {
    await update($, sessionAtom, () => given)
  }
  return given
}

/** Forgets what was kept, and with it the answer of any look still under way. */
export async function forgetSession($: EngineInterface): Promise<void> {
  lookCount += 1
  await update($, sessionAtom, () => null)
}

/** What is kept, when it is about the session with this id; else null, as before any look. */
export function givenTo(given: BandSession | null, session: string | null): BandSession | null {
  return given !== null && given.id === session ? given : null
}

/**
 * The child gets no folder of its own: `$.process.run` then runs it in the session's working
 * directory, and that is the folder the answer says the distillate is off under.
 */
async function askM2b($: EngineInterface): Promise<BandSession> {
  const id = await sessionIdOf($)
  if (!doesCoreAnswer) {
    return couldNotLook(id, OLDER_CORE)
  }
  if (id === null) {
    return couldNotLook(id, NO_ID)
  }
  const outcome = await runM2b($, ['band', '--json', '--session', id, '--session-only'], LOOK_TIMEOUT_MS)
  if (!outcome.ok) {
    if (outcome.exitCode === EXIT_USAGE && UNKNOWN_OPTION.test(outcome.stderr ?? '')) {
      doesCoreAnswer = false
      return couldNotLook(id, OLDER_CORE)
    }
    return couldNotLook(id, outcome.error)
  }
  try {
    const answer: unknown = JSON.parse(outcome.stdout)
    return parseSession(isObject(answer) ? answer['session'] : undefined, id)
  } catch {
    return couldNotLook(id, 'm2b band answered something that is not JSON')
  }
}

function couldNotLook(id: string | null, error: string): BandSession {
  return { id, known: false, topics: [], atStart: null, offUnder: null, error }
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isTextOrNull(value: unknown): value is string | null {
  return value === null || typeof value === 'string'
}

function isCountOrNull(value: unknown): value is number | null {
  return value === null || (typeof value === 'number' && Number.isInteger(value) && value >= 0)
}

function isTopic(value: unknown): value is SessionTopic {
  return isObject(value) && typeof value['name'] === 'string' && isCountOrNull(value['facts']) && isCountOrNull(value['current'])
}

/**
 * The session part of the answer, for the session with the id that was asked; a part of any other
 * shape is could not look, never "given nothing".
 */
export function parseSession(part: unknown, id: string | null): BandSession {
  if (isObject(part) && typeof part['error'] === 'string') {
    return couldNotLook(id, part['error'])
  }
  const distillate = isObject(part) ? part['distillate'] : undefined
  if (
    !isObject(part) ||
    typeof part['known'] !== 'boolean' ||
    !Array.isArray(part['topics']) ||
    !part['topics'].every(isTopic) ||
    !isObject(distillate) ||
    !isTextOrNull(distillate['at_start']) ||
    !isTextOrNull(distillate['off_under'])
  ) {
    return couldNotLook(id, OTHER_SHAPE)
  }
  return {
    id,
    known: part['known'],
    // Kept in the session's state, which every plugin can read: only what the pane draws.
    topics: part['topics'].map(({ name, facts, current }) => ({ name, facts, current })),
    atStart: distillate['at_start'],
    offUnder: distillate['off_under'],
    error: null,
  }
}

/**
 * Counts a note this session wrote through the mod's command or tool. The count is kept with the
 * session's id, so one that the state carried over from another session starts again.
 */
export async function countNote($: EngineInterface): Promise<void> {
  const session = await sessionIdOf($)
  await update($, notesAtom, notes => ({ session, count: notes !== null && notes.session === session ? notes.count + 1 : 1 }))
}

/** How many notes the session with this id wrote through the mod. */
export function notesOf(notes: SessionNotes | null, session: string | null): number {
  return notes !== null && notes.session === session ? notes.count : 0
}
