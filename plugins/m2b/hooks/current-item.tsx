import type { EngineInterface, ResolveInput } from 'claude-code'

import { opensRow, pressLine, said } from './look'
import type { ButtonSpec } from './look'
import { MONTHS, ownersOffsetAt } from './moment'
import { plainLine } from './plain-text'

/*
 * A current item of the distillate, as the tab `Facts` and a topic's view draw it. The curation
 * run writes such an item as its words, the notes of the archive it rests on as links
 * (`[[20261117T104540Z-cli-a1b2.md]]`, for a document or a picture with its own ending) and since
 * when it holds. A file's name says nothing to the person reading, so the row is the words and
 * since when; an item with one note is itself the button that opens it, and one with several has a
 * button for each, bearing the day the note was captured. A note opens in the view a fact file's
 * sources open in.
 */

/** What a current item says, without its links, and the notes it names, in the order it names them. */
export type CurrentItem = { words: string; notes: string[] }

// The name m2b gives a capture, as the core takes it: a time, where it came from, four signs and
// the file's ending, `.md` for a note and its own for a document or a picture. A link of any
// other form names nothing this view could open, and stays in the words as written.
const NOTE_NAME = String.raw`\d{8}T\d{6}Z-[a-z][a-z0-9-]*-[0-9a-f]{4}\.[A-Za-z0-9]+`
const NOTE_LINK = new RegExp(String.raw`\[\[(${NOTE_NAME})\]\]`, 'g')
// The link with the space before it: taken out together, so the words on both sides meet as
// they were written and nothing else of the line is touched.
const NOTE_LINK_WITH_SPACE = new RegExp(String.raw`[ \t]*\[\[${NOTE_NAME}\]\]`, 'g')
// The moment a note's name begins with, in UTC, as the core writes it.
const CAPTURED = /^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z/

export function currentItemOf(line: string): CurrentItem {
  const notes = [...line.matchAll(NOTE_LINK)].map(found => found[1] ?? '')
  return { words: line.replace(NOTE_LINK_WITH_SPACE, '').trim(), notes }
}

/** The key of the button of the note `note` of the current item drawn at `item`; an item with one note is that button itself. */
export function currentNoteKey(item: number, note: number): string {
  return `current-note:${item}:${note}`
}

/** The moment a note was captured, as its name says it; null for a name that says no moment that can be. */
function capturedAt(note: string): number | null {
  const parts = CAPTURED.exec(note)
  if (parts === null) {
    return null
  }
  const [year, month, day, hours, minutes, seconds] = parts.slice(1).map(Number) as [number, number, number, number, number, number]
  const ms = Date.UTC(year, month - 1, day, hours, minutes, seconds)
  // `Date.UTC` rolls a 31 November over into December: such a name says no moment.
  return new Date(ms).getUTCDate() === day && new Date(ms).getUTCMonth() === month - 1 ? ms : null
}

/** A moment as the owner's clock shows it: its year, the day (`17 Nov`), the time (`10:45`) and the time with its seconds. */
function onTheOwnersClock(ms: number, offsetAt: (ms: number) => number): { year: number; day: string; time: string; seconds: string } {
  const local = new Date(ms + offsetAt(ms) * 60_000)
  const pad = (value: number) => String(value).padStart(2, '0')
  return {
    year: local.getUTCFullYear(),
    day: `${local.getUTCDate()} ${MONTHS[local.getUTCMonth()] ?? ''}`,
    time: `${pad(local.getUTCHours())}:${pad(local.getUTCMinutes())}`,
    seconds: `${pad(local.getUTCHours())}:${pad(local.getUTCMinutes())}:${pad(local.getUTCSeconds())}`,
  }
}

/**
 * The labels of the buttons of an item's notes, in their order: the day each was captured in the
 * owner's time zone (`17 Nov`, `1 Dec 2025` for a day of another year than `nowMs`'s), and the
 * time after it where two of them fall on one day (`17 Nov 10:45`), with its seconds where two
 * fall in one minute (`17 Nov 10:45:40`), so each button tells its note. A name that says no moment is
 * labelled by its place, `note 2`. `offsetAt` is the owner's offset from UTC, in minutes, at a moment.
 */
export function noteLabels(notes: string[], nowMs: number, offsetAt: (ms: number) => number = ownersOffsetAt): string[] {
  const thisYear = onTheOwnersClock(nowMs, offsetAt).year
  const moments = notes.map(note => {
    const ms = capturedAt(note)
    if (ms === null) {
      return null
    }
    const seen = onTheOwnersClock(ms, offsetAt)
    return { ...seen, day: seen.year === thisYear ? seen.day : `${seen.day} ${seen.year}` }
  })
  const count = (same: (other: { day: string; time: string }) => boolean) => moments.filter(other => other !== null && same(other)).length
  return moments.map((moment, at) => {
    if (moment === null) {
      return `note ${at + 1}`
    }
    if (count(other => other.day === moment.day) === 1) {
      return moment.day
    }
    const isSameMinute = count(other => other.day === moment.day && other.time === moment.time) > 1
    return `${moment.day} ${isSameMinute ? moment.seconds : moment.time}`
  })
}

/**
 * One current item as a row: an item that names one note is its own button, its words with `›`,
 * that opens the note; one that names several is its words with a button for each note below them,
 * bearing the note's day (`noteLabels`); one that names none is its words alone. `nowMs` is the
 * moment the year of a day is said against.
 */
export function currentItemRow(
  $: EngineInterface,
  e: ResolveInput,
  index: number,
  line: string,
  onShow: (note: string) => Promise<void>,
  nowMs: number,
) {
  const ui = $.ui.resolve(e)
  const { Box } = ui
  const { words, notes } = currentItemOf(line)
  const [only] = notes
  if (notes.length === 1 && only !== undefined) {
    return (
      <Box key={`current:${index}`} flexDirection="column">
        {opensRow(ui, { key: currentNoteKey(index, 0), text: plainLine(words), onPress: () => onShow(only) })}
      </Box>
    )
  }
  const labels = noteLabels(notes, nowMs)
  const buttons: ButtonSpec[] = notes.map((note, at) => ({
    key: currentNoteKey(index, at),
    label: labels[at] ?? `note ${at + 1}`,
    kind: 'quiet',
    onPress: () => onShow(note),
  }))
  return (
    <Box key={`current:${index}`} flexDirection="column">
      {said(ui, plainLine(words))}
      {buttons.length > 0 && pressLine(ui, buttons, null)}
    </Box>
  )
}
