import type { EngineInterface, ResolveInput } from 'claude-code'

import type { BandPress, NoteDay } from '../types'
import { pressLine, said, valueRow } from './look'
import type { NoteOutcome } from './note'
import { daysFromToday } from './note'
import { plainLine } from './plain-text'

/*
 * The overview's field `note`: a text typed there and Enter keep it as a capture after the five
 * seconds of `undo` every press that writes has, with a task due the day chosen below it.
 *
 * What is typed is held by the field and by this module alone, never in the session's state,
 * which other plugins can read: the draft while it is typed, the text while its press waits, and
 * the line said after the write, which begins with it. The press in the state names no text. The
 * day chosen is no secret and stands in the state, so a press on a day draws the field again.
 */

/** The key of the box the field, its day and what it says stand in. */
export const NOTE_BOX = 'note'
/** The key of the field. */
export const NOTE_FIELD = 'note:field'
/** The press of the field's Enter, in the session's presses. */
export const NOTE_PRESS = 'note:keep'
/** The key of `undo` while the press waits. */
export const UNDO_NOTE = 'undo:note'

// Below this width of the pane's body the label would break after `note` and leave the text a few
// characters; the placeholder alone says what the field is.
const LABEL_FROM_COLUMNS = 36

const DAYS: readonly { day: NoteDay; label: string; inDays: number | null }[] = [
  { day: 'none', label: 'no day', inDays: null },
  { day: 'today', label: 'today', inDays: 0 },
  { day: 'tomorrow', label: 'tomorrow', inDays: 1 },
  { day: 'week', label: 'in a week', inDays: 7 },
]

/** A note Enter took out of the field: its text as typed and the day chosen for its task. */
export type TakenNote = { text: string; day: NoteDay }

/** What the field holds between draws: the draft as typed, the note whose press waits, and what the last write said. */
type Held = { draft: string; waiting: TakenNote | null; said: NoteOutcome | null }

const held: Held = { draft: '', waiting: null, said: null }

/** What the field's presses do; `keep` starts, with the text Enter gave, the press that writes after its undo window. */
export type NoteFieldActions = {
  keep: (value: string) => Promise<void>
  undo: () => Promise<void>
  chooseDay: (day: NoteDay) => Promise<void>
}

/** Every change of the text, kept so the field draws it again after the pane closed or was read again. */
export function typedNote(value: string): void {
  held.draft = value
}

/**
 * Enter: takes the text out of the field for its press, or null for a text of blanks alone, which
 * writes nothing. A note whose press still waits is not replaced.
 */
export function takeNote(value: string, day: NoteDay): TakenNote | null {
  if (plainLine(value).trim() === '' || held.waiting !== null) {
    return null
  }
  held.waiting = { text: value, day }
  held.draft = ''
  held.said = null
  return held.waiting
}

/** Undo: the text goes back into the field. Answers the day it was to be due, to be chosen again. */
export function giveNoteBack(): NoteDay | null {
  const waiting = held.waiting
  if (waiting === null) {
    return null
  }
  held.waiting = null
  held.draft = waiting.text
  return waiting.day
}

/**
 * What the write of `taken` said. A note that was written leaves the field empty; one that was not
 * goes back into it, unless something was typed meanwhile, so no text is lost. A field emptied
 * since, by `/clear`, keeps nothing of it.
 */
export function noteWritten(taken: TakenNote, outcome: NoteOutcome): void {
  if (held.waiting !== taken) {
    return
  }
  held.waiting = null
  held.said = outcome
  if (!outcome.isWritten && held.draft === '') {
    held.draft = taken.text
  }
}

/** The day `day` names on the owner's clock at `nowMs`, as YYYY-MM-DD, or null for no day. */
export function dueOf(day: NoteDay, nowMs: number): string | null {
  const inDays = DAYS.find(one => one.day === day)?.inDays ?? null
  return inDays === null ? null : daysFromToday(inDays, nowMs)
}

/** Forgets everything held: a session that starts, and the conversation after `/clear` or a resume, start with an empty field. */
export function forgetNoteField(): void {
  held.draft = ''
  held.waiting = null
  held.said = null
}

/**
 * The field above the overview's parts: while its press waits `undo` and the text it keeps, else
 * the field with the draft, the day as values side by side, and what the last write said.
 */
export function noteField(
  $: EngineInterface,
  e: ResolveInput,
  day: NoteDay,
  pressed: BandPress | undefined,
  actions: NoteFieldActions,
  columns: number,
) {
  const ui = $.ui.resolve(e)
  const { Box, Input } = ui
  const waiting = held.waiting
  if (pressed !== undefined && waiting !== null) {
    const label = DAYS.find(one => one.day === waiting.day)?.label ?? ''
    const doing = waiting.day === 'none' ? 'keeping' : `keeping, with a task due ${label}`
    return (
      <Box key={NOTE_BOX} flexDirection="column" marginBottom={1}>
        {pressed.phase === 'waiting'
          ? pressLine(ui, [{ key: UNDO_NOTE, label: 'undo', kind: 'default', onPress: () => void actions.undo() }], doing)
          : said(ui, `${doing}…`, 'quiet')}
        {said(ui, plainLine(waiting.text))}
      </Box>
    )
  }
  const isWide = columns >= LABEL_FROM_COLUMNS
  const values = DAYS.map(one => ({
    label: one.label,
    isInForce: one.day === day,
    set: { key: `note:day:${one.day}`, onPress: () => void actions.chooseDay(one.day) },
  }))
  return (
    <Box key={NOTE_BOX} flexDirection="column" marginBottom={1}>
      <Input
        key={NOTE_FIELD}
        {...(isWide ? { label: 'note', placeholder: 'what to keep' } : { placeholder: 'note' })}
        // Drawn as a plain line: a control character in a drawn text makes the engine refuse the pane.
        value={plainLine(held.draft)}
        submitLabel="keep"
        onInput={value => typedNote(value)}
        onSubmit={value => void actions.keep(value)}
      />
      {valueRow(ui, values)}
      {held.said !== null && said(ui, held.said.line, held.said.isWritten ? 'quiet' : 'trouble')}
    </Box>
  )
}
