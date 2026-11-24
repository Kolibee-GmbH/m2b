import type { CommandSpec, EngineInterface } from 'claude-code'

import { CAPTURED_BUT_TASK_UNCONFIRMED, notices, parseCapture } from './capture'
import { runM2b } from './m2b'
import { dayInWords, ownersOffsetAt } from './moment'
import { plainLine } from './plain-text'

/**
 * `/m2b-note <text>` writes the text into the inbox through `m2b capture`, without a model turn;
 * `/m2b-note --due <day> <text>` also makes a task due that day, as `m2b capture --follow-up` does.
 * `immediate`: Claude Code runs it at once, also while a turn is working, instead of queueing it.
 */
export const NOTE_COMMAND: CommandSpec = {
  name: 'm2b-note',
  description: 'Note the text into your second brain at once, without asking the model',
  argumentHint: '[--due today|tomorrow|YYYY-MM-DD] <text>',
  immediate: true,
}

// A capture writes one file, after waiting up to 20 s for an evicted store.json. Killed after the
// write, the line says "not noted" though the note is there, and typing it again doubles it.
const CAPTURE_TIMEOUT_MS = 30_000
// A follow-up also asks the task list, as the note tool does.
const FOLLOW_UP_TIMEOUT_MS = 45_000
const DAY_MS = 86_400_000
// `--due` alone, `--due tomorrow …` or `--due=tomorrow …`; `--duel` is text.
const DUE = /^\s*--due(?:=(\S*)|\s+(\S+)|\s*$)\s*([\s\S]*)$/
const DAY_FORMS = 'nothing noted: --due takes today, tomorrow or YYYY-MM-DD'
const SHOWN_LENGTH = 50

/** What a run of the command did: the one line it answers with, and whether a capture was written. */
export type NoteOutcome = { line: string; isWritten: boolean }

/** Notes what was typed after the command; `isSetUp` is asked before anything is called. */
export async function note($: EngineInterface, typed: string, isSetUp: () => Promise<boolean>): Promise<NoteOutcome> {
  const due = DUE.exec(typed)
  if (due !== null) {
    const [, joined, spaced, text = ''] = due
    return noteWithDay($, joined ?? spaced, text, isSetUp)
  }
  const text = typed
  if (plainLine(text).trim() === '') {
    const line = `nothing noted: write the text after the command, as in /${NOTE_COMMAND.name} Sam brings the plywood`
    return { line, isWritten: false }
  }
  const notReady = await notSetUp(isSetUp)
  if (notReady !== undefined) {
    return notReady
  }
  // On standard input, so quotes, dollar signs and a leading dash arrive as written.
  const outcome = await runM2b($, ['capture', '--source', 'claude', '-'], CAPTURE_TIMEOUT_MS, text)
  if (!outcome.ok) {
    return { line: `not noted: ${plainLine(outcome.error)}`, isWritten: false }
  }
  return { line: `noted: ${beginning(plainLine(text).trim())}`, isWritten: true }
}

/** Why nothing can be noted before m2b is set up, or undefined where it is. */
async function notSetUp(isSetUp: () => Promise<boolean>): Promise<NoteOutcome | undefined> {
  let isReady: boolean
  try {
    isReady = await isSetUp()
  } catch (error) {
    return { line: `not noted: could not look whether m2b is set up: ${plainLine(String(error))}`, isWritten: false }
  }
  return isReady ? undefined : { line: 'not noted: m2b is not set up on this machine; /m2b:m2b sets it up', isWritten: false }
}

async function noteWithDay(
  $: EngineInterface,
  given: string | undefined,
  text: string,
  isSetUp: () => Promise<boolean>,
): Promise<NoteOutcome> {
  if (given === undefined || given === '') {
    return { line: `${DAY_FORMS}, before the text`, isWritten: false }
  }
  const nowMs = await $.clock.now()
  const day = dayOf(given, nowMs)
  if (day === undefined) {
    return { line: `${DAY_FORMS}, not ${plainLine(given)}`, isWritten: false }
  }
  if (plainLine(text).trim() === '') {
    const line = `nothing noted: write the text after the day, as in /${NOTE_COMMAND.name} --due tomorrow Call Sam`
    return { line, isWritten: false }
  }
  const notReady = await notSetUp(isSetUp)
  if (notReady !== undefined) {
    return notReady
  }
  const args = ['capture', '--source', 'claude', '--json', '--follow-up', day, '-']
  const outcome = await runM2b($, args, FOLLOW_UP_TIMEOUT_MS, text)
  const noted = `noted: ${beginning(plainLine(text).trim())}`
  if (!outcome.ok) {
    const reason = plainLine(outcome.error)
    // The note is in the inbox; typing it again would note it twice.
    if (reason.includes(CAPTURED_BUT_TASK_UNCONFIRMED)) {
      return { line: `${noted}; ${reason}`, isWritten: true }
    }
    return { line: `not noted: ${reason}`, isWritten: false }
  }
  const saved = parseCapture(outcome.stdout)
  if (typeof saved?.taskId === 'string') {
    return { line: `${noted}; a task is due ${dayInWords(day, nowMs)}`, isWritten: true }
  }
  // The core says on standard error why the task waits for the next curation run.
  const [said] = notices(outcome.stderr, plainLine)
  return { line: `${noted}; ${said ?? 'look at the task list for its task'}`, isWritten: true }
}

/**
 * The day `given` names on the owner's clock at `nowMs`, as YYYY-MM-DD, or undefined for no day.
 * `offsetAt` is the owner's offset from UTC, in minutes, at a moment.
 */
export function dayOf(given: string, nowMs: number, offsetAt: (ms: number) => number = ownersOffsetAt): string | undefined {
  const today = nowMs + offsetAt(nowMs) * 60_000
  if (given === 'today' || given === 'tomorrow') {
    return new Date(today + (given === 'tomorrow' ? DAY_MS : 0)).toISOString().slice(0, 10)
  }
  if (!/^\d{4}-\d{2}-\d{2}$/.test(given)) {
    return undefined
  }
  // 2026-02-30 would roll over to 2 March.
  const parsed = new Date(`${given}T00:00:00Z`)
  return !Number.isNaN(parsed.getTime()) && parsed.toISOString().startsWith(given) ? given : undefined
}

/** The first characters, counted as characters a person sees, so an emoji is never cut in half. */
function beginning(text: string): string {
  const characters = Array.from(text)
  return characters.length <= SHOWN_LENGTH ? text : `${characters.slice(0, SHOWN_LENGTH).join('').trimEnd()}…`
}
