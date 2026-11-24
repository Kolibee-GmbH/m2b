import type { ElementTable, EngineInterface, ResolveInput } from 'claude-code'

import type { PaneView } from '../types'
import type { Evidence } from './facts-tab'
import { isObject, isOlderCore, notReadError, strings, textOrNull } from './facts-tab'
import { nameLine, part, pathLine, pressLine, said, topicLabel } from './look'
import { runM2b } from './m2b'
import { OLDER_CORE } from './session'
import { plainLine } from './plain-text'

/*
 * What a fact rests on, one press below its fact file: an evidence entry's row turns the pane to
 * that source under a tab of its own, read with `m2b source --json --viewer`. A note shows the
 * words as they were captured and what the curation run added; a picture or a document what it is,
 * the outline of what stands on which page, and `open the file` where `m2b store open` would open
 * it in the system's viewer, else the path and why not.
 *
 * As the fact file, all of it is this module's alone, for the press that opened it, and dropped
 * the moment the pane turns away: a note holds the owner's own words.
 */

export type SourceKind = 'note' | 'picture' | 'document'

export type SourceLook =
  | { state: 'reading' }
  | {
      state: 'read'
      kind: SourceKind
      day: string | null
      captured: string[]
      added: string[]
      originalName: string | null
      outline: string[]
      // The file's name in the archive, which `m2b store open` takes; null for a note.
      original: string | null
      opens: boolean
      notOpened: string | null
      file: string | null
    }
  | { state: 'failed'; error: string }

/** A press on `open the file`: not made, under way, done, or refused with why. */
export type Opening = { state: 'none' } | { state: 'opening' } | { state: 'opened' } | { state: 'failed'; error: string }

// `from` and `index` are the fact file and its evidence row the source was opened from, null for
// a note opened from a current item, which has no fact file above it. Such a note is named by its
// file alone, so its tab says what it is only once it is read (`isLabelOfTheLook`).
type Held = {
  press: string
  from: string | null
  index: number | null
  label: string
  isLabelOfTheLook: boolean
  look: SourceLook
  opening: Opening
}

let held: Held | null = null

/**
 * Keeps, for the opening `press`, the source the evidence row `index` of the fact file opened as
 * `from` names; the tab's label comes from the row, so it stands while the source is read.
 */
export function beginSource(press: string, from: string, index: number, evidence: Evidence): void {
  held = {
    press,
    from,
    index,
    label: sourceTabLabel(evidence),
    isLabelOfTheLook: false,
    look: { state: 'reading' },
    opening: { state: 'none' },
  }
}

const A_NOTE = 'note'

/**
 * Keeps, for the opening `press`, a note a current item names. Its tab reads `note` while it is
 * read and then what a fact file's row would have said of it: its day, or a document's name.
 */
export function beginNote(press: string): void {
  held = { press, from: null, index: null, label: A_NOTE, isLabelOfTheLook: true, look: { state: 'reading' }, opening: { state: 'none' } }
}

export function fillSource(press: string, look: SourceLook): boolean {
  if (held === null || held.press !== press) {
    return false
  }
  const label = held.isLabelOfTheLook && look.state === 'read' ? sourceTabLabel(look) : held.label
  held = { ...held, look, label }
  return true
}

/** Notes how a press on `open the file` stands; false where the opening is no longer shown. */
export function noteOpening(press: string, opening: Opening): boolean {
  if (held === null || held.press !== press) {
    return false
  }
  held = { ...held, opening }
  return true
}

export function sourceOf(press: string): SourceLook {
  return held !== null && held.press === press ? held.look : { state: 'reading' }
}

export function openingOf(press: string): Opening {
  return held !== null && held.press === press ? held.opening : { state: 'none' }
}

/** The label of the tab the source stands under; empty where nothing is kept for it, as after a reload of the mod. */
export function sourceLabelOf(press: string): string {
  return held !== null && held.press === press ? held.label : ''
}

/** Which evidence row of the fact file opened the source, for the focus on the way back; null where nothing is kept. */
export function evidenceIndexOf(press: string): number | null {
  return held !== null && held.press === press ? held.index : null
}

/** Whether anything is kept at all. Nothing outside the module can read what it keeps, so its tests ask this. */
export function holdsSource(): boolean {
  return held !== null
}

/** Drops what is kept unless `view` is the opening it was read for. */
export function forgetSourceUnless(view: PaneView | null): void {
  if (held !== null && !(view?.kind === 'source' && view.press === held.press)) {
    held = null
  }
}

const READ_TIMEOUT_MS = 20_000
// `m2b store open` waits up to five seconds for the viewer to hand over.
const OPEN_TIMEOUT_MS = 20_000
const OTHER_SHAPE = 'm2b answered something other than a note'
const READING = 'm2b is reading it…'
const KINDS: readonly SourceKind[] = ['note', 'picture', 'document']
// The line the core writes into the note of every picture or document it takes in ("A pdf file,
// captured as 20261116T165634Z-cli-7198.pdf."): the view says what the file is in its own words.
const CAPTURED_AS = /^An? \S+ file, captured as \S+\.$/
const KIND_IN_WORDS: Readonly<Record<SourceKind, string>> = { note: 'A note', picture: 'A picture', document: 'A document' }
export const OPEN_THE_FILE = 'open the file'
export const OPEN_KEY = 'source:open'
export const WHAT_IT_IS = 'What it is'
export const OUTLINE = 'What stands on which page'
export const ADDED = 'What the curation run added'

/** Reads one source with `m2b source --json --viewer`; a source not on this machine or not readable is could not read. */
export async function readSource($: EngineInterface, name: string): Promise<SourceLook> {
  // `--`: the name is a fact file's text, and it may start with a dash.
  const outcome = await runM2b($, ['source', '--json', '--viewer', '--', name], READ_TIMEOUT_MS)
  if (!outcome.ok) {
    return { state: 'failed', error: isOlderCore(outcome) ? OLDER_CORE : outcome.error }
  }
  return parseSource(outcome.stdout)
}

function lastPart(path: string): string {
  return path.slice(path.lastIndexOf('/') + 1)
}

/** The answer of `m2b source --json --viewer` for a note; a fact file or any other shape is could not read. */
export function parseSource(text: string): SourceLook {
  let answer: unknown
  try {
    answer = JSON.parse(text)
  } catch {
    return { state: 'failed', error: OTHER_SHAPE }
  }
  if (!isObject(answer)) {
    return { state: 'failed', error: OTHER_SHAPE }
  }
  const notRead = notReadError(answer)
  if (notRead !== null) {
    return { state: 'failed', error: notRead }
  }
  const kind = KINDS.find(one => one === answer['kind'])
  const added = strings(answer['added'])
  const outline = strings(answer['outline'])
  if (kind === undefined || typeof answer['captured'] !== 'string' || added === null || outline === null) {
    return { state: 'failed', error: OTHER_SHAPE }
  }
  const original = textOrNull(answer['original'])
  return {
    state: 'read',
    kind,
    day: textOrNull(answer['day']),
    captured: answer['captured'].split('\n').filter(line => line.trim() !== '' && !(kind !== 'note' && CAPTURED_AS.test(line.trim()))),
    added,
    originalName: textOrNull(answer['original_name']),
    outline,
    original: original === null ? null : lastPart(original),
    // Only an answer of `true` offers the button: a field missing or of another shape offers nothing.
    opens: answer['opens'] === true && original !== null,
    notOpened: textOrNull(answer['not_opened']),
    file: textOrNull(answer['file']),
  }
}

/** Runs `m2b store open` on the file; what became of it, never a rejection. */
export async function openFile($: EngineInterface, original: string): Promise<Opening> {
  const outcome = await runM2b($, ['store', 'open', '--', original], OPEN_TIMEOUT_MS)
  if (outcome.ok) {
    return { state: 'opened' }
  }
  return { state: 'failed', error: isOlderCore(outcome) ? OLDER_CORE : outcome.error }
}

/** The label of the tab a source stands under: a document's or picture's original name, else what it is and its day. */
export function sourceTabLabel(evidence: Pick<Evidence, 'originalName' | 'kind' | 'day'>): string {
  if (evidence.originalName !== null) {
    return topicLabel(evidence.originalName)
  }
  const what = evidence.kind === 'picture' ? 'picture' : evidence.kind === 'document' ? 'document' : 'note'
  return topicLabel(evidence.day === null ? what : `${what} ${evidence.day}`)
}

export type SourceActions = { open: (original: string) => Promise<void> }

type Ui = Pick<ElementTable, 'Box' | 'Button' | 'Text'>

function openingLine(ui: Ui, opening: Opening) {
  switch (opening.state) {
    case 'none':
      return null
    case 'opening':
      return said(ui, 'm2b is opening it…', 'quiet')
    case 'opened':
      return said(ui, 'Opened in the system’s viewer.', 'done')
    case 'failed':
      return said(ui, `m2b could not open it: ${plainLine(opening.error)}`, 'trouble')
  }
}

/** Where the file is and why it does not open here, or `open the file` and how the last press stands. */
function fileLines(ui: Ui, press: string, look: Extract<SourceLook, { state: 'read' }>, actions: SourceActions) {
  if (look.original === null) {
    return []
  }
  if (look.opens) {
    const original = look.original
    return [
      pressLine(ui, [{ key: OPEN_KEY, label: OPEN_THE_FILE, kind: 'default', onPress: () => actions.open(original) }], null, 'source:open-row'),
      openingLine(ui, openingOf(press)),
    ]
  }
  return [
    look.file !== null && pathLine(ui, look.file),
    look.notOpened !== null && said(ui, plainLine(look.notOpened), 'quiet'),
  ]
}

/** The source under its own tab: for a note its words and what the run added; for a file what it is, its outline and the file. */
export function sourcePane($: EngineInterface, e: ResolveInput, press: string, actions: SourceActions, columns: number) {
  const ui = $.ui.resolve(e)
  const look = sourceOf(press)
  if (look.state !== 'read') {
    const line = look.state === 'reading' ? said(ui, READING, 'quiet') : said(ui, `m2b could not read it: ${plainLine(look.error)}`, 'trouble')
    return part(ui, { key: 'source', title: WHAT_IT_IS, waits: false, columns }, [line])
  }
  const day = look.day === null ? '' : `, captured on ${plainLine(look.day)}`
  const head = [
    said(ui, `${KIND_IN_WORDS[look.kind]}${day}`, 'quiet'),
    // Whole in the tab above, a name would only repeat it; cut there, the view gives it whole.
    look.originalName !== null && sourceLabelOf(press) !== plainLine(look.originalName) && nameLine(ui, look.originalName, 'strong'),
  ]
  const words = look.captured.map(line => said(ui, plainLine(line)))
  const parts = [part(ui, { key: 'source', title: WHAT_IT_IS, waits: false, columns }, [...head, ...words, ...fileLines(ui, press, look, actions)])]
  if (look.outline.length > 0) {
    parts.push(part(ui, { key: 'source:outline', title: OUTLINE, waits: false, columns }, look.outline.map(line => said(ui, plainLine(line)))))
  }
  if (look.added.length > 0) {
    parts.push(part(ui, { key: 'source:added', title: ADDED, waits: false, columns }, look.added.map(line => said(ui, plainLine(line), 'quiet'))))
  }
  return parts
}
