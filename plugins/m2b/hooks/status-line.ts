export const COULD_NOT_LOOK = 'could not look'

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
  const parts = [...runTrouble(answer['run']), ...inboxTrouble(answer['inbox']), ...problemParts(answer)]
  return parts.length === 0 ? null : fit(parts.join(' · '))
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

function runTrouble(run: unknown): string[] {
  if (!isObject(run) || 'error' in run) {
    return ['could not read the last curation run']
  }
  if (run['state'] === 'failed') {
    return ['last curation run failed']
  }
  return run['state'] === 'interrupted' ? ['last curation run interrupted'] : []
}

function inboxTrouble(inbox: unknown): string[] {
  return isObject(inbox) && typeof inbox['count'] === 'number' ? [] : ['could not read the inbox']
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

function problemParts(answer: JsonObject): string[] {
  const parts: string[] = []
  if (typeof answer['store_error'] === 'string') {
    parts.push('could not read store.json')
  }
  const backends = answer['backends']
  if (isObject(backends)) {
    for (const [name, check] of Object.entries(backends)) {
      if (isObject(check) && check['state'] === NOT_REACHABLE) {
        parts.push(`${name} not reachable`)
      }
    }
  }
  return parts
}

function fit(line: string): string {
  return line.length <= MAX_LENGTH ? line : `${line.slice(0, MAX_LENGTH - 1)}…`
}
