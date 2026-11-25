import type { EngineInterface, ResolveInput } from 'claude-code'

import type { BandPress } from '../types'

import type { WaitingCorrection } from './facts-tab'
import { pressLine, said } from './look'
import type { ButtonSpec } from './look'
import { runM2b } from './m2b'
import { plainLine } from './plain-text'
import type { AnswersCuration } from './proposals'
import { curateButton } from './rows'

/*
 * `correct` in a fact file's view: a press draws the field `what is right`; a text typed there and
 * Enter keep it, after the five seconds of `undo` every press that writes has, as a capture about
 * that fact file, which the next curation run applies to it.
 *
 * What is typed is held by the field and by this module alone, never in the session's state,
 * which other plugins can read, and neither is the fact file's name: each file's draft, the
 * correction whose press waits and the line said after a failed write. A draft stays for its fact
 * file while the pane shows another view, since Escape in this view turns the pane to the overview
 * at once, and is drawn again when that file's view is opened again.
 */

/** The key of the box `correct`, the field or the press that waits stand in. */
export const CORRECTING = 'fact:correcting'
/** The key of the button `correct`. */
export const CORRECT = 'fact:correct'
/** The key of the field. */
export const CORRECT_FIELD = 'fact:correct:field'
/** The press of the field's Enter, in the session's presses. */
export const CORRECT_PRESS = 'fact:correct'
/** The key of `undo` while the press waits. */
export const UNDO_CORRECT = 'undo:correct'
/** The key of the lines that name the corrections and the kept edits that wait, with what starts a run beside them. */
export const WAITING_CORRECTIONS = 'fact:corrections'

// Below this width of the pane's body the label would leave the text a few characters.
const LABEL_FROM_COLUMNS = 36
// A capture writes one file, after waiting up to 20 s for an evicted store.json, as `/m2b-note` does.
const CAPTURE_TIMEOUT_MS = 30_000

/** A correction Enter took out of the field: the fact file it is about and its text as typed. */
export type TakenCorrection = { file: string; text: string }

/** The field of one fact file while it is open: its draft, and why the last write wrote nothing. */
type Field = { draft: string; failed: string | null }

/**
 * What is held between draws: the field of each fact file it was opened for, by the file's name,
 * so a draft for one file is never another's, and the correction whose press waits.
 */
const held: { fields: Map<string, Field>; waiting: TakenCorrection | null } = { fields: new Map(), waiting: null }

/** What the presses of a fact file's view on its correction do. */
export type CorrectActions = {
  open: () => Promise<void>
  keep: (value: string) => Promise<void>
  undo: () => Promise<void>
}

/** A press on `correct`: the field opens for `file`, with the draft it had where it was open. */
export function openCorrection(file: string): void {
  if (!held.fields.has(file)) {
    held.fields.set(file, { draft: '', failed: null })
  }
}

/** Every change of the text in `file`'s field, kept so the field draws it again after the view was left. */
export function typedCorrection(file: string, value: string): void {
  const field = held.fields.get(file)
  if (field !== undefined) {
    field.draft = value
  }
}

/**
 * Enter in `file`'s field: takes the text out of it for its press, or null for a text of blanks
 * alone, which writes nothing, and while another correction's press has not landed.
 */
export function takeCorrection(file: string, value: string): TakenCorrection | null {
  const field = held.fields.get(file)
  if (field === undefined || held.waiting !== null) {
    return null
  }
  if (plainLine(value).trim() === '') {
    field.draft = ''
    return null
  }
  held.waiting = { file, text: value }
  field.draft = ''
  field.failed = null
  return held.waiting
}

/** Undo: the text goes back into its own fact file's field. */
export function giveCorrectionBack(): void {
  const waiting = held.waiting
  if (waiting === null) {
    return
  }
  held.waiting = null
  held.fields.set(waiting.file, { draft: waiting.text, failed: null })
}

/**
 * What the write of `taken` did, to its own fact file's field alone: written, the field closes and
 * the view names the correction from the core; refused, the text goes back into the field with
 * why, unless something was typed there meanwhile. A field emptied since, by `/clear`, keeps
 * nothing of it.
 */
export function correctionWritten(taken: TakenCorrection, refused: string | null): void {
  if (held.waiting !== taken) {
    return
  }
  held.waiting = null
  const field = held.fields.get(taken.file)
  if (refused === null) {
    if (field !== undefined && field.draft === '') {
      held.fields.delete(taken.file)
    }
    return
  }
  held.fields.set(taken.file, { draft: field !== undefined && field.draft !== '' ? field.draft : taken.text, failed: refused })
}

/** Forgets everything held: a session that starts, and the conversation after `/clear` or a resume, start without a correction typed. */
export function forgetCorrection(): void {
  held.fields.clear()
  held.waiting = null
}

/**
 * Writes `taken` as a capture about its fact file (`m2b capture --about`), on standard input so the
 * text arrives as typed. Answers null where it was written, else why not, cleaned.
 */
export async function writeCorrection($: EngineInterface, taken: TakenCorrection): Promise<string | null> {
  // `--about` takes the fact file's name as the distillate names it; the core refuses any other.
  const args = ['capture', '--source', 'claude', '--about', taken.file, '-']
  const outcome = await runM2b($, args, CAPTURE_TIMEOUT_MS, taken.text)
  return outcome.ok ? null : plainLine(outcome.error)
}

/**
 * Under a fact file's title: `correct`, with `beside` after it; once pressed, the field `what is
 * right`, with `beside` below it; while its press waits, `undo` and the text it keeps; while it
 * writes, that alone.
 */
export function correctionRow(
  $: EngineInterface,
  e: ResolveInput,
  file: string,
  pressed: BandPress | undefined,
  actions: CorrectActions,
  beside: readonly ButtonSpec[],
  columns: number,
) {
  const ui = $.ui.resolve(e)
  const { Box, Input } = ui
  const waiting = held.waiting
  if (pressed !== undefined && waiting !== null && waiting.file === file) {
    return (
      <Box key={CORRECTING} flexDirection="column">
        {pressed.phase === 'waiting'
          ? pressLine(ui, [{ key: UNDO_CORRECT, label: 'undo', kind: 'default', onPress: () => void actions.undo() }], 'correcting')
          : said(ui, 'correcting…', 'quiet')}
        {said(ui, plainLine(waiting.text))}
      </Box>
    )
  }
  const field = held.fields.get(file)
  if (field === undefined) {
    return (
      <Box key={CORRECTING} flexDirection="column">
        {pressLine(ui, [{ key: CORRECT, label: 'correct', kind: 'default', onPress: () => void actions.open() }, ...beside])}
      </Box>
    )
  }
  const isWide = columns >= LABEL_FROM_COLUMNS
  return (
    <Box key={CORRECTING} flexDirection="column">
      <Input
        key={CORRECT_FIELD}
        {...(isWide ? { label: 'what is right', placeholder: 'the fact as it should read' } : { placeholder: 'what is right' })}
        // Drawn as a plain line: a control character in a drawn text makes the engine refuse the pane.
        value={plainLine(field.draft)}
        submitLabel="keep"
        onInput={value => typedCorrection(file, value)}
        onSubmit={value => void actions.keep(value)}
      />
      {field.failed !== null && said(ui, `not kept: ${field.failed}`, 'trouble')}
      {/* The field stays open, empty too, until a correction is written: what stands beside it stays reachable. */}
      {beside.length > 0 && pressLine(ui, beside)}
    </Box>
  )
}

/**
 * What waits in the inbox for the next curation run to change this fact file, as the core named it
 * with the file: the corrections, each by its first line, and the edits kept. On the machine that
 * curates one `curate now` below them, on another each line names the machine that curates, and
 * while a run is under way it says so. Nothing where nothing waits.
 */
export function waitingForTheRun(
  $: EngineInterface,
  e: ResolveInput,
  corrections: readonly WaitingCorrection[],
  keptEdits: number,
  curation: AnswersCuration,
) {
  if (corrections.length === 0 && keptEdits === 0) {
    return null
  }
  const ui = $.ui.resolve(e)
  const { Box } = ui
  const { health, curatingMachine, notice, pressed, actions } = curation
  const count = corrections.length === 1 ? '1 correction waits' : `${corrections.length} corrections wait`
  const edits = keptEdits === 1 ? 'your edit waits' : `${keptEdits} of your edits wait`
  const elsewhere = pressed === undefined && health?.curates === false && curatingMachine !== null ? ` on ${plainLine(curatingMachine)}` : ''
  const canStart = pressed !== undefined || (health?.curates === true && health.isCurating !== true)
  return (
    <Box key={WAITING_CORRECTIONS} flexDirection="column">
      {corrections.length > 0 && said(ui, `${count} for the next curation run${elsewhere}:`, 'waits')}
      {corrections.map(correction => said(ui, `“${plainLine(correction.firstLine)}”`, 'quiet'))}
      {keptEdits > 0 && said(ui, `${edits} for the next curation run${elsewhere}`, 'waits')}
      {health?.isCurating === true && pressed === undefined && said(ui, 'A curation run is under way.', 'quiet')}
      {canStart && notice !== null && said(ui, plainLine(notice), 'trouble')}
      {canStart && curateButton($, e, pressed, actions)}
    </Box>
  )
}
