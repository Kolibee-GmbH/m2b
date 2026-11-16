import type { BandHealth } from '../types'
import { plainLine } from './plain-text'

export const COULD_NOT_LOOK = 'could not look'
// The same in the pane, where a line is a sentence: the band's answer came without a part about m2b itself.
const COULD_NOT_LOOK_AT_ITSELF = 'm2b could not look at how it stands.'

const MAX_LENGTH = 79
const NOT_REACHABLE = 'not reachable'

type JsonObject = Record<string, unknown>

function isObject(value: unknown): value is JsonObject {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/**
 * The status line for one `m2b status --json` answer: what is wrong with m2b, in one line shorter
 * than 80 characters, or null while nothing is. Claude Code draws a plugin's status line as a
 * warning, with its sign and in the warning color, so a line while all is well would warn all day:
 * when m2b last curated and what waits in the inbox are said by `curationLine`, for the pane.
 * What waits for an answer is the band's.
 */
export function statusLine(answer: unknown): string | null {
  if (!isObject(answer)) {
    return COULD_NOT_LOOK
  }
  const parts = troublesOf(answer).map(trouble => trouble.status)
  return parts.length === 0 ? null : fit(parts.join(' · '))
}

/**
 * How m2b stands, for the pane's part about m2b itself: `curationLine`, and each thing that is
 * wrong as a sentence with its reason, where the answer names one. The status line has room for
 * what is wrong alone; why stands here.
 */
export function healthOf(answer: unknown, nowMs: number): BandHealth {
  if (!isObject(answer)) {
    return { curation: null, troubles: [COULD_NOT_LOOK_AT_ITSELF] }
  }
  return {
    curation: curationLine(answer, nowMs),
    troubles: troublesOf(answer).map(({ sentence, reason }) => (reason === null ? `${sentence}.` : `${sentence}: ${plainLine(reason)}`)),
  }
}

/**
 * How curation stands while nothing is wrong, in one line: a run under way, or how many notes
 * wait in the inbox, where any do, and when m2b last curated; then that this machine starts no
 * run by itself. A count of none is not said, and nothing of a last run that failed or could not be
 * read, which `statusLine` says: null where that leaves nothing.
 */
export function curationLine(answer: unknown, nowMs: number): string | null {
  if (!isObject(answer)) {
    return null
  }
  const run = answer['run']
  const isRunning = isObject(run) && run['state'] === 'running'
  const parts = [
    ...(isRunning ? ['curating'] : [...inboxCount(answer['inbox']), ...lastCurated(run, nowMs)]),
    ...(answer['paused'] === true ? ['curation paused'] : []),
  ]
  return parts.length === 0 ? null : fit(parts.join(' · '))
}

/** One thing wrong with m2b: in the status line's few words, as a sentence of the pane, and why, where the answer says. */
type Trouble = { status: string; sentence: string; reason: string | null }

function textOrNull(value: unknown): string | null {
  return typeof value === 'string' && value !== '' ? value : null
}

function troublesOf(answer: JsonObject): Trouble[] {
  return [...runTrouble(answer['run']), ...inboxTrouble(answer['inbox']), ...storeTrouble(answer), ...backendTroubles(answer)]
}

function runTrouble(run: unknown): Trouble[] {
  if (!isObject(run) || 'error' in run) {
    const reason = isObject(run) ? textOrNull(run['error']) : null
    return [{ status: 'could not read the last curation run', sentence: 'm2b could not read the last curation run', reason }]
  }
  if (run['state'] === 'failed') {
    return [{ status: 'last curation run failed', sentence: 'The last curation run failed', reason: textOrNull(run['message']) }]
  }
  return run['state'] === 'interrupted'
    ? [{ status: 'last curation run interrupted', sentence: 'The last curation run was interrupted', reason: textOrNull(run['message']) }]
    : []
}

function inboxTrouble(inbox: unknown): Trouble[] {
  if (isObject(inbox) && typeof inbox['count'] === 'number') {
    return []
  }
  const reason = isObject(inbox) ? textOrNull(inbox['error']) : null
  return [{ status: 'could not read the inbox', sentence: 'm2b could not read the inbox', reason }]
}

function inboxCount(inbox: unknown): string[] {
  return isObject(inbox) && typeof inbox['count'] === 'number' && inbox['count'] > 0 ? [`${inbox['count']} in inbox`] : []
}

/** When a run last succeeded, or that none ever ran; nothing for a run that could not be read or never succeeded. */
function lastCurated(run: unknown, nowMs: number): string[] {
  if (!isObject(run) || 'error' in run) {
    return []
  }
  const succeededAt = run['last_succeeded_at']
  if (typeof succeededAt === 'string') {
    return [`curated ${localTimeOrDay(succeededAt, nowMs)}`]
  }
  return run['state'] === 'none' ? ['not curated yet'] : []
}

/**
 * The time of day when the moment lies on today's date, else the date.
 *
 * m2b writes local times with their offset, so "today" is read in that offset; the module has no
 * time zone of its own to trust.
 */
function localTimeOrDay(moment: string, nowMs: number): string {
  const match = /^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})(?::\d{2}(?:\.\d+)?)?(Z|[+-]\d{2}:\d{2})$/.exec(moment)
  if (match === null) {
    return moment
  }
  const [, day, time, offset] = match as unknown as [string, string, string, string]
  const today = new Date(nowMs + offsetMinutes(offset) * 60_000).toISOString().slice(0, 10)
  return day === today ? time : day
}

function offsetMinutes(offset: string): number {
  if (offset === 'Z') {
    return 0
  }
  const sign = offset.startsWith('-') ? -1 : 1
  const [hours = 0, minutes = 0] = offset.slice(1).split(':').map(Number)
  return sign * (hours * 60 + minutes)
}

function storeTrouble(answer: JsonObject): Trouble[] {
  const reason = answer['store_error']
  return typeof reason === 'string'
    ? [{ status: 'could not read store.json', sentence: 'm2b could not read store.json', reason: textOrNull(reason) }]
    : []
}

function backendTroubles(answer: JsonObject): Trouble[] {
  const backends = answer['backends']
  if (!isObject(backends)) {
    return []
  }
  return Object.entries(backends).flatMap(([name, check]) =>
    isObject(check) && check['state'] === NOT_REACHABLE
      ? [{ status: `${name} not reachable`, sentence: `m2b could not reach the ${plainLine(name)}`, reason: textOrNull(check['detail']) }]
      : [],
  )
}

function fit(line: string): string {
  return line.length <= MAX_LENGTH ? line : `${line.slice(0, MAX_LENGTH - 1)}…`
}
