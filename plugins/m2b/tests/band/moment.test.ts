import { expect, test } from 'claude-code/testing'

import { timeOrDay } from '../../hooks/moment'

/** Half past six in the evening of 14 March where the clock is an hour ahead of UTC. */
const NOW = Date.parse('2026-03-14T17:30:00Z')

test('a moment of today is said as its time of day, to the minute', () => {
  // Covers: B209
  expect(timeOrDay('2026-03-14T18:02:00+01:00', NOW)).toBe('18:02')
  // Seconds and their fraction are not said, and a moment written without them reads the same.
  expect(timeOrDay('2026-03-14T18:02:59.750+01:00', NOW)).toBe('18:02')
  expect(timeOrDay('2026-03-14T18:02+01:00', NOW)).toBe('18:02')
  // Today from its first minute to its last, whether the moment is past or still to come.
  expect(timeOrDay('2026-03-14T00:00:00+01:00', NOW)).toBe('00:00')
  expect(timeOrDay('2026-03-14T23:59:00+01:00', NOW)).toBe('23:59')
})

test('a moment of a day before is said as its date, without a time', () => {
  // Covers: B209
  expect(timeOrDay('2026-03-13T18:02:00+01:00', NOW)).toBe('2026-03-13')
  expect(timeOrDay('2026-03-13T23:59:59+01:00', NOW)).toBe('2026-03-13')
  expect(timeOrDay('2025-12-31T09:00:00+01:00', NOW)).toBe('2025-12-31')
  // The same moment is of today until midnight where it was written, and of a day before from then on.
  const written = '2026-03-14T18:02:00+01:00'
  expect(timeOrDay(written, Date.parse('2026-03-14T22:59:59Z'))).toBe('18:02')
  expect(timeOrDay(written, Date.parse('2026-03-14T23:00:00Z'))).toBe('2026-03-14')
})

test('today is read in the offset the moment was written with, whatever the offset', () => {
  // Covers: B209
  // Ten hours ahead it is already the 15th, at half past three in the morning.
  expect(timeOrDay('2026-03-15T03:10:00+10:00', NOW)).toBe('03:10')
  expect(timeOrDay('2026-03-14T23:50:00+10:00', NOW)).toBe('2026-03-14')
  // Eight hours behind it is half past nine in the morning of the 14th.
  expect(timeOrDay('2026-03-14T08:00:00-08:00', NOW)).toBe('08:00')
  expect(timeOrDay('2026-03-13T23:00:00-08:00', NOW)).toBe('2026-03-13')
  // An offset of half an hour, and UTC written as Z.
  expect(timeOrDay('2026-03-14T22:45:00+05:30', NOW)).toBe('22:45')
  expect(timeOrDay('2026-03-14T09:00:00Z', NOW)).toBe('09:00')
  expect(timeOrDay('2026-03-13T23:30:00Z', NOW)).toBe('2026-03-13')
})

test('a text that is no moment as m2b writes it comes back as it is', () => {
  // Covers: B209
  for (const text of ['', 'yesterday', '2026-03-14', '18:02', '2026-03-14T18:02:00', '2026-03-14 18:02:00+01:00', '2026-03-14T18:02:00+0100']) {
    expect(timeOrDay(text, NOW)).toBe(text)
  }
})

test('a text that is no moment comes back as one plain line: no escape sequence and no line break reaches a drawing', () => {
  // Covers: B209
  const escape = String.fromCharCode(27)
  const dirty = timeOrDay(`18:02${escape}[31m red\nnext line`, NOW)

  expect(dirty).not.toContain(escape)
  expect(dirty).not.toContain('\n')
  expect(dirty).toContain('18:02')
  expect(dirty).toContain('next line')
})
