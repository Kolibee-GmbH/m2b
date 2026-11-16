import { plainLine } from './plain-text'

/*
 * The one way a moment is said to a person: the time of day when it lies on today's date, else
 * the date.
 */

/**
 * `18:02` for a moment of today, `2026-03-14` for one before; a text that is no moment as m2b
 * writes it comes back as one plain line, since it is drawn like any other text from outside.
 *
 * m2b writes local times with their offset, so "today" is read in that offset; the mod has no time
 * zone of its own to trust.
 */
export function timeOrDay(moment: string, nowMs: number): string {
  const match = /^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})(?::\d{2}(?:\.\d+)?)?(Z|[+-]\d{2}:\d{2})$/.exec(moment)
  if (match === null) {
    return plainLine(moment)
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
