import { plainLine } from './plain-text'

/*
 * The one way a moment is said to a person: the time of day when it lies on today's date, else
 * the date. And the owner's time zone, for a moment written in UTC.
 */

/** The months as a day is said to a person: `20 Nov`. */
export const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'] as const

/**
 * How many minutes the owner's clock is ahead of UTC at the moment `ms`. The mod runs on the
 * owner's machine, in the time zone the core says its local times in, and the offset is asked for
 * that moment, so a day in summer time is said in summer time.
 */
export function ownersOffsetAt(ms: number): number {
  return -new Date(ms).getTimezoneOffset()
}

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

/**
 * A day as m2b writes it (`2026-11-24`) in words: `24 Nov`, with the year where it is not the year
 * of `nowMs` on the owner's clock (`1 Dec 2025`). A text that is no day comes back as one plain line.
 */
export function dayInWords(day: string, nowMs: number): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(day)
  const month = match === null ? undefined : MONTHS[Number(match[2]) - 1]
  if (match === null || month === undefined) {
    return plainLine(day)
  }
  const thisYear = new Date(nowMs + ownersOffsetAt(nowMs) * 60_000).getUTCFullYear()
  return `${Number(match[3])} ${month}${Number(match[1]) === thisYear ? '' : ` ${match[1]}`}`
}
