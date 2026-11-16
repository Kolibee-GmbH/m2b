import type { BandHealth, CurateRefusal } from '../types'
import { timeOrDay } from './moment'
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
    return { ...NOT_KNOWN, troubles: [COULD_NOT_LOOK_AT_ITSELF] }
  }
  return {
    curation: curationLine(answer, nowMs),
    troubles: troublesOf(answer).map(({ sentence, reason }) => (reason === null ? `${sentence}.` : `${sentence}: ${plainLine(reason)}`)),
    // Where the store does not name its curating machine, whether this one curates is not known.
    curates: curatingMachineOf(answer) === null ? null : answer['this_machine_curates'] === true,
    isCurating: isRunning(answer['run']),
  }
}

/** The machine that curates the store, as the status part names it; null where it names none. */
export function curatingMachineOf(answer: unknown): string | null {
  return isObject(answer) ? textOrNull(answer['curating_machine']) : null
}

/** How m2b stands where it gave no answer about itself: nothing is said, and nothing is known of curation. */
export const NOT_KNOWN: BandHealth = { curation: null, troubles: [], curates: null, isCurating: false }

const CURATING = 'curating'

function isRunning(run: unknown): boolean {
  return isObject(run) && run['state'] === 'running'
}

/**
 * How m2b stands right after it started a run: the run's record says so only a moment later, and
 * until the band has read it the part about m2b must not offer a second start.
 */
export function whileCurating(health: BandHealth): BandHealth {
  return { ...health, isCurating: true, curation: CURATING }
}

/** What a start of a run in the background came to: a run, or why none, with the command's own words where it failed. */
export type RunStart = { isStarted: true } | { isStarted: false; refusal: CurateRefusal; reason: string | null }

const REFUSALS: readonly CurateRefusal[] = ['running', 'not-curating', 'not-downloaded']

/** What `m2b curate --detach --json` answered; null for anything that is not that answer. */
export function parseRunStart(stdout: string): RunStart | null {
  let answer: unknown
  try {
    answer = JSON.parse(stdout)
  } catch {
    return null
  }
  if (!isObject(answer) || typeof answer['kind'] !== 'string') {
    return null
  }
  const kind = answer['kind']
  if (kind === 'started') {
    return { isStarted: true }
  }
  const refusal = REFUSALS.find(known => known === kind)
  // A kind this band does not know is told in the command's words, or by its name.
  return refusal === undefined
    ? { isStarted: false, refusal: 'failed', reason: textOrNull(answer['message']) ?? textOrNull(kind) }
    : { isStarted: false, refusal, reason: null }
}

const WHY_NO_RUN: Readonly<Record<Exclude<CurateRefusal, 'failed'>, string>> = {
  running: 'a curation run is already running on this machine',
  'not-curating': 'another machine curates the store',
  'not-downloaded': 'store.json is not downloaded on this machine',
}

/**
 * What the pane says of a press that started no run. The reasons m2b knows are said in words of
 * the band's own, which name no machine and no folder; `reason` is the command's own account of a
 * failure, which the caller keeps outside the session's state.
 */
export function noRunStarted(refusal: CurateRefusal, reason: string | null): string {
  const why = refusal === 'failed' ? (reason ?? 'm2b did not say why') : WHY_NO_RUN[refusal]
  return `No curation run started: ${why}`
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
  const parts = [
    ...(isRunning(run) ? [CURATING] : [...inboxCount(answer['inbox']), ...lastCurated(run, nowMs)]),
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
    return [`curated ${timeOrDay(succeededAt, nowMs)}`]
  }
  return run['state'] === 'none' ? ['not curated yet'] : []
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
