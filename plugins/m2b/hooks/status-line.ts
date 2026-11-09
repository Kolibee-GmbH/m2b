export const COULD_NOT_LOOK = 'brain: could not look'

const MAX_LENGTH = 79
const NOT_REACHABLE = 'not reachable'

type JsonObject = Record<string, unknown>

function isObject(value: unknown): value is JsonObject {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/** The status line for one `m2b status --json` answer: one line, shorter than 80 characters. */
export function statusLine(answer: unknown, nowMs: number): string {
  if (!isObject(answer)) {
    return COULD_NOT_LOOK
  }
  const parts = [runPart(answer, nowMs), ...problemParts(answer)]
  return fit(`brain: ${parts.join(' · ')}`)
}

function runPart(answer: JsonObject, nowMs: number): string {
  const run = answer['run']
  if (!isObject(run) || 'error' in run) {
    return 'could not read the last run'
  }
  switch (run['state']) {
    case 'running':
      return 'curating'
    case 'failed':
      return 'last run failed, see review'
    case 'interrupted':
      return 'last run interrupted'
    default:
      return `${inboxPart(answer['inbox'])} · ${curatedPart(run, nowMs)}`
  }
}

function inboxPart(inbox: unknown): string {
  if (!isObject(inbox) || typeof inbox['count'] !== 'number') {
    return 'could not read the inbox'
  }
  return `${inbox['count']} in inbox`
}

function curatedPart(run: JsonObject, nowMs: number): string {
  const succeededAt = run['last_succeeded_at']
  if (typeof succeededAt !== 'string') {
    return 'not curated yet'
  }
  return `curated ${localTimeOrDay(succeededAt, nowMs)}`
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
