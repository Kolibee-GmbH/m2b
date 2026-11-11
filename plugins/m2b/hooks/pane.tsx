import type { CommandSpec, EngineInterface, ResolveInput } from 'claude-code'

import type { BandPress, BandRun, BandSnapshot, PaneSearch, PaneView, SearchHit } from '../types'
import { runM2b } from './m2b'
import { plainLine } from './plain-text'
import { candidateRow, changesSummary, reviewRow } from './rows'
import type { RowActions } from './rows'

/*
 * The m2b pane: the last curation run in full, or the hits of a search. The band above the prompt
 * shows the first few findings and candidates; this shows all of them, each finding whole, and the
 * search without asking the model. Both commands run at once, also while a turn is working.
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

/** `2026-03-14 18:00` from a time m2b wrote with its offset: as written, in the offset of the machine that curated. */
export function minute(moment: string): string {
  return plainLine(moment.slice(0, 16).replace('T', ' '))
}

export function runLine(run: BandRun | null): string {
  if (run === null) {
    return 'Could not read the last curation run.'
  }
  if (run.state === 'none') {
    return 'No curation run yet.'
  }
  if (run.state === 'unreadable') {
    return 'Could not read the last curation run:'
  }
  const state = plainLine(run.state)
  if (run.startedAt === null) {
    return `Last curation run: ${state}`
  }
  const started = minute(run.startedAt)
  if (run.finishedAt === null) {
    return `Last curation run: ${state}, started ${started}`
  }
  const finished = minute(run.finishedAt)
  const end = finished.slice(0, 10) === started.slice(0, 10) ? finished.slice(11) : finished
  return `Last curation run: ${state}, ${started} to ${end}`
}

/** The review part as lines of text, for a surface that cannot show the pane. */
// After the file, what happened to more than a word or two: a line or a whole fact file gone.
const KIND_SHOWN: Record<string, string> = {
  removed: ', line removed',
  file_removed: ', file removed',
  file_emptied: ', file emptied',
}

/** Where the copy of the facts from before the run lies, and how many notes the run filed. */
function copyLine(copy: { path: string; captures: number }): string {
  const filed = copy.captures > 0 ? `; ${copy.captures} ${copy.captures === 1 ? 'note' : 'notes'} filed` : ''
  return `  facts before the run: ${plainLine(copy.path)}${filed}`
}

/** A changed line as text, the added words in [+ ] and the removed ones in [- ]. */
function changeText(parts: { text: string; change: string }[]): string {
  return parts
    .map(part => (part.change === 'same' ? part.text : `[${part.change === 'added' ? '+' : '-'}${part.text}]`))
    .map(plainLine)
    .join('')
}

export function reviewLines(snapshot: BandSnapshot | null, run: BandRun | null): string[] {
  const lines = [runLine(run)]
  if (run?.message) {
    lines.push(plainLine(run.message))
  }
  if (snapshot?.error) {
    lines.push(plainLine(snapshot.error))
  }
  const review = snapshot?.review ?? null
  if (review !== null) {
    lines.push(`${plainLine(review.title)}${changesSummary(review)}`)
    for (const change of review.changes ?? []) {
      lines.push(`  ${plainLine(change.topic)} (${plainLine(change.file)}): ${changeText(change.parts)}`)
    }
    if (review.copy) {
      lines.push(copyLine(review.copy))
    }
    lines.push(...review.findings.map(finding => `  ${plainLine(finding)}`))
  }
  const candidates = snapshot?.candidates ?? []
  lines.push(
    ...(candidates.length === 0
      ? ['Nothing to keep or drop.']
      : candidates.map(candidate => `- ${plainLine(candidate.title)}`)),
  )
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

export function searchSummary(search: PaneSearch): string {
  const query = `${plainLine(search.query)}${search.wholeWords === true ? ', whole words only,' : ''}`
  const count = search.total
  return count === 0 ? `no hits for ${query}` : `${count} ${count === 1 ? 'hit' : 'hits'} for ${query}`
}

/** The search as lines: each hit's place on one line, its text on the next. */
export function searchLines(search: PaneSearch): string[] {
  const lines =
    search.hits.length === 0
      ? [`No hits for ${plainLine(search.query)}.`]
      : search.hits.slice(0, HITS_SHOWN).flatMap(hit => [`${plainLine(hit.path)}:${hit.line}`, `  ${plainLine(hit.text)}`])
  if (search.total > search.hits.length) {
    lines.push(`and ${search.total - search.hits.length} more hits`)
  }
  if (search.evicted > 0) {
    lines.push(`${search.evicted} ${search.evicted === 1 ? 'file' : 'files'} not downloaded, not searched`)
  }
  if (search.unreadable > 0) {
    lines.push(`${search.unreadable} ${search.unreadable === 1 ? 'file' : 'files'} could not be read`)
  }
  return lines
}

/**
 * Opens the pane and says where to look. A surface that cannot show it (no pane there, or none
 * attached) gets the content as the command's own lines instead.
 */
export async function showPane($: EngineInterface, placedLine: string, lines: () => string[]): Promise<string> {
  // `focus` is a request: the pane takes the keyboard, so the arrows scroll it, only over an empty prompt.
  const opened = await $.ui.open({ id: PANE_ID, title: PANE_TITLE, closeOnEscape: true, focus: true })
  if (opened.isPlaced) {
    return placedLine
  }
  // Undrawn, it would stay open and appear once a surface that places panes attaches.
  await $.ui.close({ id: PANE_ID })
  return [`the m2b pane cannot be shown here: ${plainLine(opened.reason)}`, ...fallback(lines())].join('\n')
}

function fallback(lines: string[]): string[] {
  const cut = lines
    .slice(0, FALLBACK_LINES)
    .map(line => (line.length <= FALLBACK_LINE_LENGTH ? line : `${Array.from(line).slice(0, FALLBACK_LINE_LENGTH).join('')}…`))
  return lines.length > FALLBACK_LINES ? [...cut, `and ${lines.length - FALLBACK_LINES} more lines`] : cut
}

/** The pane's drawing: the search, or the run with its findings whole and every row to keep or drop. */
export function paneTree(
  $: EngineInterface,
  e: ResolveInput,
  view: PaneView | null,
  snapshot: BandSnapshot | null,
  run: BandRun | null,
  presses: Record<string, BandPress>,
  actions: RowActions,
) {
  const { Box, Text } = $.ui.resolve(e)
  if (view?.kind === 'search') {
    return (
      <Box flexDirection="column">
        {searchLines(view.search).map(line => (
          <Text wrap="wrap">{line}</Text>
        ))}
      </Box>
    )
  }
  const review = snapshot?.review ?? null
  const candidates = snapshot?.candidates ?? []
  return (
    <Box flexDirection="column">
      <Text weight="semibold" wrap="wrap">
        {runLine(run)}
      </Text>
      {run?.message ? <Text wrap="wrap">{plainLine(run.message)}</Text> : null}
      {snapshot?.error ? (
        <Text color="error" wrap="wrap">
          {plainLine(snapshot.error)}
        </Text>
      ) : null}
      {review !== null && reviewRow($, e, review, presses[review.id], actions, 'wrap')}
      {(review?.changes ?? []).map(change => (
        <Box flexDirection="column">
          <Text wrap="wrap">
            <Text weight="semibold">{`  ${plainLine(change.topic)}`}</Text>
            <Text dimColor>{` (${plainLine(change.file)}${KIND_SHOWN[change.kind] ?? ''})`}</Text>
          </Text>
          <Text wrap="wrap">
            {'    '}
            {change.parts.map(part =>
              part.change === 'same' ? (
                <Text>{plainLine(part.text)}</Text>
              ) : (
                <Text color={part.change === 'added' ? 'success' : 'error'} strikethrough={part.change === 'removed'}>
                  {plainLine(part.text)}
                </Text>
              ),
            )}
          </Text>
        </Box>
      ))}
      {review?.copy ? <Text dimColor wrap="wrap">{copyLine(review.copy)}</Text> : null}
      {(review?.findings ?? []).map(finding => (
        <Text wrap="wrap">
          {'  '}
          {plainLine(finding)}
        </Text>
      ))}
      {candidates.length === 0 ? (
        <Text dimColor>Nothing to keep or drop.</Text>
      ) : (
        candidates.map(candidate => candidateRow($, e, candidate, presses[candidate.id], actions, 'wrap'))
      )}
    </Box>
  )
}
