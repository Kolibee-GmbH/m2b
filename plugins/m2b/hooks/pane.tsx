import type { CommandSpec, EngineInterface, ResolveInput } from 'claude-code'

import type { BandPress, BandRun, BandSnapshot, PaneSearch, PaneView, SearchHit } from '../types'
import { runM2b } from './m2b'
import { CLOSED_BY_HAND } from './pane-seat'
import { untoldFindings } from './tasks'
import { plainLine, withoutHidden } from './plain-text'
import { NOTHING_WAITS, NOT_LOOKED, WAITS_FOR_YOU, inset, part, pathLine, said, styleOf, under } from './look'
import type { Tone } from './look'
import { timeOrDay } from './moment'
import { REVIEW, candidateRow, changesSummary, reviewRow } from './rows'
import type { RowActions } from './rows'

/*
 * The m2b pane's views of the last curation run, in full with every finding whole and every
 * candidate, and of the hits of a search, without asking the model. Both commands run at once,
 * also while a turn is working. The pane's own name and how it is opened are here too.
 */

export const PANE_ID = 'm2b'
export const PANE_TITLE = 'm2b'

export const REVIEW_COMMAND: CommandSpec = {
  name: 'm2b-review',
  description: 'Show the last curation run in a pane: every finding, candidate and question',
  immediate: true,
}

export const SEARCH_COMMAND: CommandSpec = {
  name: 'm2b-search',
  description: 'Search your second brain and show the hits in a pane, without asking the model',
  argumentHint: '[--word] <text>',
  immediate: true,
}

// `--word` in front of the text, then space: only whole words match. Anything else is the text.
const WORD_FLAG = /^--word(?:\s+|$)/

/** What `/m2b-search` was asked: the text, and whether only whole words match. */
export function searchRequest(args: string): { text: string; wholeWords: boolean } {
  const given = args.trim()
  return WORD_FLAG.test(given)
    ? { text: given.replace(WORD_FLAG, '').trim(), wholeWords: true }
    : { text: given, wholeWords: false }
}

const SEARCH_TIMEOUT_MS = 30_000
const HITS_SHOWN = 100
// Where the pane cannot be shown, its content goes into the conversation the model reads: kept short.
const FALLBACK_LINES = 20
const FALLBACK_LINE_LENGTH = 200

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function textOrNull(value: unknown): string | null {
  return typeof value === 'string' ? value : null
}

/** The run part of `m2b band --json`'s status; null when it is missing altogether. */
export function runOf(status: unknown): BandRun | null {
  const run = isObject(status) ? status['run'] : undefined
  if (isObject(run) && typeof run['error'] === 'string') {
    return { state: 'unreadable', startedAt: null, finishedAt: null, message: run['error'] }
  }
  if (!isObject(run) || typeof run['state'] !== 'string') {
    return null
  }
  return {
    state: run['state'],
    startedAt: textOrNull(run['started_at']),
    finishedAt: textOrNull(run['finished_at']),
    message: textOrNull(run['message']),
  }
}

export function isRun(value: unknown): value is BandRun {
  return (
    isObject(value) &&
    typeof value['state'] === 'string' &&
    ['startedAt', 'finishedAt', 'message'].every(field => value[field] === null || typeof value[field] === 'string')
  )
}

const LAST_RUN = 'Last curation run'
const RUN_NOT_READ = 'm2b could not read the last curation run'

/**
 * How the last curation run went, in one line: its state and when it ran, the time for a run of
 * today and the date for one before. A run m2b could not read, and one that failed or was
 * interrupted, is trouble; that none ran yet is no more than a note.
 */
export function runWords(run: BandRun | null, nowMs: number): { text: string; tone: Tone } {
  if (run === null) {
    return { text: `${RUN_NOT_READ}.`, tone: 'trouble' }
  }
  if (run.state === 'none') {
    return { text: 'No curation run yet.', tone: 'quiet' }
  }
  if (run.state === 'unreadable') {
    return { text: run.message ? `${RUN_NOT_READ}: ${plainLine(run.message)}` : `${RUN_NOT_READ}.`, tone: 'trouble' }
  }
  const tone = run.state === 'failed' || run.state === 'interrupted' ? 'trouble' : 'plain'
  return { text: `${plainLine(run.state)}${whenItRan(run, nowMs)}`, tone }
}

/** `, 18:00 to 18:04` for a run of today, `, 2026-03-13` for one before, `, started 18:00` for one under way; nothing where no start is known. */
function whenItRan(run: BandRun, nowMs: number): string {
  if (run.startedAt === null) {
    return ''
  }
  const started = timeOrDay(run.startedAt, nowMs)
  if (run.finishedAt === null) {
    return `, started ${started}`
  }
  const finished = timeOrDay(run.finishedAt, nowMs)
  return started === finished ? `, ${started}` : `, ${started} to ${finished}`
}

/** Before the band's first answer neither the run nor the list was read: not known, which is not "could not read". */
function isUnread(snapshot: BandSnapshot | null, run: BandRun | null): boolean {
  return snapshot === null && run === null
}

/** What a run said beside its state, where it is no part of the run's line already. */
function runMessage(run: BandRun | null): string | null {
  return run !== null && run.state !== 'unreadable' && run.message ? plainLine(run.message) : null
}

/** The run's line for a text, which has no part's title above it. */
function runTextLine(run: BandRun | null, nowMs: number): string {
  const { text: words } = runWords(run, nowMs)
  return run === null || run.state === 'none' || run.state === 'unreadable' ? words : `${LAST_RUN}: ${words}`
}

/** How many rows of the run wait for an answer: its candidates and questions, and the review. */
function runWaits(snapshot: BandSnapshot | null): number {
  return (snapshot?.candidates.length ?? 0) + (snapshot?.review ? 1 : 0)
}

/**
 * Whether the view says that nothing waits: where m2b could read the list and it holds no row.
 * Not before any run: "no run yet" says it all.
 */
function saysNothingWaits(snapshot: BandSnapshot | null, run: BandRun | null): boolean {
  return snapshot !== null && !snapshot.error && runWaits(snapshot) === 0 && run?.state !== 'none'
}

// What happened to more than a word or two: a line or a whole fact file gone.
const KIND_SHOWN: Record<string, string> = {
  removed: 'line removed',
  file_removed: 'file removed',
  file_emptied: 'file emptied',
}

/**
 * What stands in brackets beside what a changed fact is about: its fact file and what happened to
 * it. The file is named once: where a whole file went, the change is about the file itself, and
 * the core names it as the topic. Null where that leaves nothing.
 */
function changedWhere(change: { topic: string; file: string; kind: string }): string | null {
  const file = plainLine(change.file)
  const pieces = [...(file === plainLine(change.topic) ? [] : [file]), ...(KIND_SHOWN[change.kind] ? [KIND_SHOWN[change.kind]] : [])]
  return pieces.length === 0 ? null : pieces.join(', ')
}

/** Where the copy of the facts from before the run lies, and how many notes the run filed. */
function copyLine(copy: { path: string; captures: number }): string {
  return `${BEFORE_THE_RUN}: ${plainLine(copy.path)}${notesFiled(copy.captures)}`
}

const BEFORE_THE_RUN = 'facts before the run'

/** `; 2 notes filed`, or nothing where the run filed none. */
function notesFiled(captures: number): string {
  return captures > 0 ? `; ${captures} ${captures === 1 ? 'note' : 'notes'} filed` : ''
}

/** A changed line as text, the added words in [+ ] and the removed ones in [- ]. */
function changeText(parts: { text: string; change: string }[]): string {
  return parts
    .map(part => (part.change === 'same' ? part.text : `[${part.change === 'added' ? '+' : '-'}${part.text}]`))
    .map(plainLine)
    .join('')
}

/** The review part as lines of text, for a surface that cannot show the pane. */

export function reviewLines(snapshot: BandSnapshot | null, run: BandRun | null, nowMs: number): string[] {
  if (isUnread(snapshot, run)) {
    return [NOT_LOOKED]
  }
  const message = runMessage(run)
  const lines = [runTextLine(run, nowMs), ...(message === null ? [] : [message])]
  if (snapshot?.error) {
    lines.push(plainLine(snapshot.error))
  }
  const review = snapshot?.review ?? null
  if (review !== null) {
    const changed = changesSummary(review)
    lines.push(changed === null ? REVIEW : `${REVIEW}, ${changed}`)
    for (const change of review.changes ?? []) {
      const where = changedWhere(change)
      const head = `  ${plainLine(change.topic)}${where === null ? '' : ` (${where})`}`
      // A file that went holds no line to show.
      lines.push(change.parts.length === 0 ? head : `${head}: ${changeText(change.parts)}`)
    }
    lines.push(...(review.copies ?? []).map(copy => `  ${copyLine(copy)}`))
    lines.push(...untoldFindings(review).map(finding => `  ${plainLine(finding)}`))
  }
  lines.push(...(snapshot?.candidates ?? []).map(candidate => `- ${plainLine(candidate.title)}`))
  if (saysNothingWaits(snapshot, run)) {
    lines.push(NOTHING_WAITS)
  }
  return lines
}

/** What `/m2b-search` answers: the search, or the one line that says why there is none. */
export type SearchOutcome = { search: PaneSearch } | { line: string }

export async function searchStore($: EngineInterface, text: string, wholeWords = false): Promise<SearchOutcome> {
  // `--`: a text that starts with a dash is what to look for, not an option.
  const args = ['search', '--json', ...(wholeWords ? ['--word'] : []), '--', text]
  const outcome = await runM2b($, args, SEARCH_TIMEOUT_MS)
  if (!outcome.ok) {
    return { line: `could not search: ${plainLine(outcome.error)}` }
  }
  if (outcome.isCut) {
    return { line: `too many hits for ${plainLine(text)} to show; search for something narrower` }
  }
  let answer: unknown
  try {
    answer = JSON.parse(outcome.stdout)
  } catch {
    return { line: 'could not search: m2b search answered something that is not JSON' }
  }
  if (!isObject(answer) || !Array.isArray(answer['hits'])) {
    return { line: 'could not search: m2b search answered without hits' }
  }
  const hits = answer['hits'].filter(isHit)
  return {
    search: {
      query: text,
      // Kept in the session's state, which every plugin can read: only what the pane draws.
      hits: hits.slice(0, HITS_SHOWN),
      total: hits.length,
      evicted: Array.isArray(answer['evicted']) ? answer['evicted'].length : 0,
      unreadable: Array.isArray(answer['unreadable']) ? answer['unreadable'].length : 0,
      ...(wholeWords ? { wholeWords: true } : {}),
    },
  }
}

function isHit(value: unknown): value is SearchHit {
  return (
    isObject(value) &&
    typeof value['path'] === 'string' &&
    typeof value['line'] === 'number' &&
    typeof value['text'] === 'string'
  )
}

/** The search in words: `3 hits for plywood`, `no hits for Velo, whole words only`. */
export function searchSummary(search: PaneSearch): string {
  const query = `${plainLine(search.query)}${search.wholeWords === true ? ', whole words only' : ''}`
  const count = search.total
  return count === 0 ? `no hits for ${query}` : `${count} ${count === 1 ? 'hit' : 'hits'} for ${query}`
}

/** That the hits are in the pane, for the command's answer. */
export function searchPlaced(search: PaneSearch): string {
  // The comma closes "whole words only", which stands between commas.
  return `${searchSummary(search)}${search.wholeWords === true ? ',' : ''} in the m2b pane`
}

function hitPlace(hit: SearchHit): string {
  return `${plainLine(hit.path)}:${hit.line}`
}

function noHits(search: PaneSearch): string {
  return `No hits for ${plainLine(search.query)}.`
}

/** What a search says after its hits: how many more there are, and which files it could not search. */
function searchNotes(search: PaneSearch): string[] {
  return [
    ...(search.total > search.hits.length ? [`and ${search.total - search.hits.length} more hits`] : []),
    ...(search.evicted > 0 ? [`${search.evicted} ${search.evicted === 1 ? 'file' : 'files'} not downloaded, not searched`] : []),
    ...(search.unreadable > 0 ? [`${search.unreadable} ${search.unreadable === 1 ? 'file' : 'files'} could not be read`] : []),
  ]
}

/** The search as lines: each hit's place on one line, its text on the next. */
export function searchLines(search: PaneSearch): string[] {
  const hits = search.hits.slice(0, HITS_SHOWN).flatMap(hit => [hitPlace(hit), `  ${plainLine(hit.text)}`])
  return [...(search.hits.length === 0 ? [noHits(search)] : hits), ...searchNotes(search)]
}

/** The pane as a dialog: it asks for the keyboard, and Escape closes it as the person's close mark does. */
export const AS_A_DIALOG = { id: PANE_ID, title: PANE_TITLE, closeOnEscape: true, focus: true } as const

/**
 * Opens the pane and says where to look. A surface that cannot show it (no pane there, or none
 * attached) gets the content as the command's own lines instead. `staysOpen` is for the start view
 * where it sits beside the chat: Escape hands the keyboard back there and the pane stays.
 */
export async function showPane(
  $: EngineInterface,
  placedLine: string,
  lines: () => string[],
  staysOpen = false,
): Promise<string> {
  // `focus` is a request: the pane takes the keyboard, so the arrows scroll it, only over an empty prompt.
  const opened = await $.ui.open(staysOpen ? { id: PANE_ID, title: PANE_TITLE, focus: true } : AS_A_DIALOG)
  if (opened.isPlaced) {
    await openedByThePerson($)
    return placedLine
  }
  // Undrawn, it would stay open and appear once a surface that places panes attaches.
  await $.ui.close({ id: PANE_ID })
  return [`the m2b pane cannot be shown here: ${withoutHidden(plainLine(opened.reason))}`, ...fallback(lines())].join('\n')
}

/**
 * The person opened the pane, with a command or a press: it opens by itself again from the next
 * session on, also after they once closed it by hand.
 */
async function openedByThePerson($: EngineInterface): Promise<void> {
  try {
    await $.store.delete(CLOSED_BY_HAND)
  } catch {
    // The pane is shown all the same; it then stays one that does not open by itself.
  }
}

/** The lines as a model gets them: no character that draws nothing, and no more than a few lines of a few words. */
function fallback(lines: string[]): string[] {
  const cut = lines
    .slice(0, FALLBACK_LINES)
    .map(withoutHidden)
    .map(line => (line.length <= FALLBACK_LINE_LENGTH ? line : `${Array.from(line).slice(0, FALLBACK_LINE_LENGTH).join('')}…`))
  return lines.length > FALLBACK_LINES ? [...cut, `and ${lines.length - FALLBACK_LINES} more lines`] : cut
}

/**
 * A search's view, one part under the search in words: each hit's place, and its text below it,
 * indented whole. A search without hits opens no pane, so the part always holds some.
 */
export function searchPane($: EngineInterface, e: ResolveInput, search: PaneSearch, columns: number) {
  const ui = $.ui.resolve(e)
  const summary = searchSummary(search)
  const title = `${summary.charAt(0).toUpperCase()}${summary.slice(1)}`
  return part(ui, { key: 'search', title, waits: false, columns }, [
    ...search.hits.slice(0, HITS_SHOWN).flatMap(hit => [said(ui, hitPlace(hit), 'quiet'), under(ui, plainLine(hit.text), 'plain')]),
    ...searchNotes(search).map(note => said(ui, note, 'quiet')),
  ])
}

/**
 * What the review's view draws from. `notice` is what m2b said to the last press on a row that
 * wrote nothing, `nowMs` the moment the run's times are said against.
 */
export type ReviewModel = {
  snapshot: BandSnapshot | null
  run: BandRun | null
  presses: Record<string, BandPress>
  notice: string | null
  nowMs: number
}

/**
 * The review's view, two parts: the last curation run, how it went and what it changed, with
 * every finding whole; and what of it waits for an answer, the review with `ok` and every
 * candidate and question with keep and drop. `columns` is the width of the pane's body.
 */
export function reviewPane($: EngineInterface, e: ResolveInput, model: ReviewModel, actions: RowActions, columns: number) {
  const ui = $.ui.resolve(e)
  const { Box, Text } = ui
  const { snapshot, run, presses, notice } = model
  const words = runWords(run, model.nowMs)
  const message = runMessage(run)
  const review = snapshot?.review ?? null
  const waits = runWaits(snapshot)
  const nothingWaits = saysNothingWaits(snapshot, run)
  if (isUnread(snapshot, run)) {
    return part(ui, { key: 'run', title: LAST_RUN, waits: false, columns }, [said(ui, NOT_LOOKED, 'quiet')])
  }
  // Before any run, with nothing to answer, the first part says all there is.
  const hasWaitsPart = waits > 0 || nothingWaits || snapshot === null || Boolean(snapshot.error) || notice !== null
  return (
    <Box flexDirection="column">
      {part(ui, { key: 'run', title: LAST_RUN, waits: false, columns }, [
        said(ui, words.text, words.tone),
        message !== null && said(ui, message, words.tone),
        ...(review?.changes ?? []).map(change => {
          const where = changedWhere(change)
          return (
            <Box flexDirection="column">
              <Text wrap="wrap">
                <Text {...styleOf('strong')}>{plainLine(change.topic)}</Text>
                {where !== null && <Text {...styleOf('quiet')}>{` (${where})`}</Text>}
              </Text>
              {/* A file that went holds no line to show. */}
              {change.parts.length > 0 &&
                inset(
                  ui,
                  <Text wrap="wrap">
                    {change.parts.map(piece => (
                      <Text {...styleOf(piece.change === 'same' ? 'plain' : piece.change === 'added' ? 'added' : 'removed')}>{plainLine(piece.text)}</Text>
                    ))}
                  </Text>,
                )}
            </Box>
          )
        }),
        ...(review?.copies ?? []).flatMap(copy => [said(ui, `${BEFORE_THE_RUN}${notesFiled(copy.captures)}:`, 'quiet'), pathLine(ui, copy.path)]),
        ...(review === null ? [] : untoldFindings(review)).map(finding => under(ui, plainLine(finding), 'plain')),
      ])}
      {hasWaitsPart &&
        part(ui, { key: 'waits', title: WAITS_FOR_YOU, waits: waits > 0, count: waits > 0 ? String(waits) : null, columns }, [
          snapshot === null && said(ui, NOT_LOOKED, 'quiet'),
          snapshot?.error ? said(ui, plainLine(snapshot.error), 'trouble') : null,
          notice !== null && said(ui, plainLine(notice), 'trouble'),
          review !== null && reviewRow($, e, review, presses[review.id], actions),
          ...(snapshot?.candidates ?? []).map(candidate => candidateRow($, e, candidate, presses[candidate.id], actions)),
          nothingWaits && said(ui, NOTHING_WAITS, 'quiet'),
        ])}
    </Box>
  )
}
