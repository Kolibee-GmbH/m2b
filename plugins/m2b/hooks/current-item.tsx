import type { EngineInterface, ResolveInput } from 'claude-code'

import { pressLine, said } from './look'
import type { ButtonSpec } from './look'
import { plainLine } from './plain-text'

/*
 * A current item of the distillate, as the tab `Facts` and a topic's view draw it. The curation
 * run writes such an item as its words, the notes of the archive it rests on as links
 * (`[[20261117T104540Z-cli-a1b2.md]]`, for a document or a picture with its own ending) and since
 * when it holds. A file's name says nothing to the person reading, so the row is the words and
 * since when, and each note is a button that opens it in the view a fact file's sources open in.
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

export function currentItemOf(line: string): CurrentItem {
  const notes = [...line.matchAll(NOTE_LINK)].map(found => found[1] ?? '')
  return { words: line.replace(NOTE_LINK_WITH_SPACE, '').trim(), notes }
}

/** The key of the button of the note `note` of the current item drawn at `item`. */
export function currentNoteKey(item: number, note: number): string {
  return `current-note:${item}:${note}`
}

/**
 * One current item as a row: its words, and below them a button for each note it names, `show`
 * for one and `show 1`, `show 2` for several. An item that names no note is its words alone.
 */
export function currentItemRow($: EngineInterface, e: ResolveInput, index: number, line: string, onShow: (note: string) => Promise<void>) {
  const ui = $.ui.resolve(e)
  const { Box } = ui
  const { words, notes } = currentItemOf(line)
  const buttons: ButtonSpec[] = notes.map((note, at) => ({
    key: currentNoteKey(index, at),
    label: notes.length === 1 ? 'show' : `show ${at + 1}`,
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
