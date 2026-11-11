import type { CommandSpec, EngineInterface } from 'claude-code'

import { runM2b } from './m2b'
import { plainLine } from './plain-text'

/**
 * `/m2b-note <text>` writes the text into the inbox through `m2b capture`, without a model turn.
 * `immediate`: Claude Code runs it at once, also while a turn is working, instead of queueing it.
 */
export const NOTE_COMMAND: CommandSpec = {
  name: 'm2b-note',
  description: 'Note the text into your second brain at once, without asking the model',
  argumentHint: '<text>',
  immediate: true,
}

// A capture writes one file, after waiting up to 20 s for an evicted store.json. Killed after the
// write, the line says "not noted" though the note is there, and typing it again doubles it.
const CAPTURE_TIMEOUT_MS = 30_000
const SHOWN_LENGTH = 50

/** What a run of the command did: the one line it answers with, and whether a capture was written. */
export type NoteOutcome = { line: string; isWritten: boolean }

/** Notes `text`; `isSetUp` is asked before anything is called. */
export async function note($: EngineInterface, text: string, isSetUp: () => Promise<boolean>): Promise<NoteOutcome> {
  if (plainLine(text).trim() === '') {
    const line = `nothing noted: write the text after the command, as in /${NOTE_COMMAND.name} Sam brings the plywood`
    return { line, isWritten: false }
  }
  let isReady: boolean
  try {
    isReady = await isSetUp()
  } catch (error) {
    return { line: `not noted: could not look whether m2b is set up: ${plainLine(String(error))}`, isWritten: false }
  }
  if (!isReady) {
    return { line: 'not noted: m2b is not set up on this machine; /m2b:m2b sets it up', isWritten: false }
  }
  // On standard input, so quotes, dollar signs and a leading dash arrive as written.
  const outcome = await runM2b($, ['capture', '--source', 'claude', '-'], CAPTURE_TIMEOUT_MS, text)
  if (!outcome.ok) {
    return { line: `not noted: ${plainLine(outcome.error)}`, isWritten: false }
  }
  return { line: `noted: ${beginning(plainLine(text).trim())}`, isWritten: true }
}

/** The first characters, counted as characters a person sees, so an emoji is never cut in half. */
function beginning(text: string): string {
  const characters = Array.from(text)
  return characters.length <= SHOWN_LENGTH ? text : `${characters.slice(0, SHOWN_LENGTH).join('').trimEnd()}…`
}
