import { describe, expect, test } from 'claude-code/testing'

import { COULD_NOT_LOOK, statusLine } from '../../hooks/status-line'

const NOW = Date.parse('2026-03-14T17:30:00Z')

const REACHABLE = {
  store: { state: 'reachable', detail: '' },
  tasks: { state: 'reachable', detail: '' },
  calendar: { state: 'not configured', detail: '' },
}

function answer(fields: Record<string, unknown>): Record<string, unknown> {
  return {
    machine_id: 'alex-laptop',
    curating_machine: 'alex-laptop',
    this_machine_curates: true,
    inbox: { count: 3, evicted: 0 },
    run: {
      state: 'succeeded',
      machine_id: 'alex-laptop',
      started_at: '2026-03-14T18:01:00+01:00',
      finished_at: '2026-03-14T18:02:00+01:00',
      last_succeeded_at: '2026-03-14T18:02:00+01:00',
    },
    due: { due: false, reason: 'curated 0 h ago' },
    backends: REACHABLE,
    backends_checked_at: '2026-03-14T18:29:00+01:00',
    ...fields,
  }
}

describe('the status line', () => {
  test('names the inbox and the time of the last run today', () => {
    expect(statusLine(answer({}), NOW)).toBe('3 in inbox · curated 18:02')
  })

  test('names the day of a last run before today, read in its own offset', () => {
    const run = { state: 'succeeded', last_succeeded_at: '2026-03-13T23:50:00+01:00' }
    expect(statusLine(answer({ run }), NOW)).toBe('3 in inbox · curated 2026-03-13')
  })

  test('says a run is in progress', () => {
    expect(statusLine(answer({ run: { state: 'running' } }), NOW)).toBe('curating')
  })

  test('says the last run failed', () => {
    expect(statusLine(answer({ run: { state: 'failed' } }), NOW)).toBe('last run failed, see review')
  })

  test('says the last run was interrupted', () => {
    expect(statusLine(answer({ run: { state: 'interrupted' } }), NOW)).toBe('last run interrupted')
  })

  test('says when nothing has been curated yet', () => {
    expect(statusLine(answer({ inbox: { count: 0 }, run: { state: 'none' } }), NOW)).toBe(
      '0 in inbox · not curated yet',
    )
  })

  test('names a backend that cannot be reached', () => {
    const backends = { ...REACHABLE, tasks: { state: 'not reachable', detail: 'no grant' } }
    expect(statusLine(answer({ backends, run: { state: 'running' } }), NOW)).toBe(
      'curating · tasks not reachable',
    )
  })

  test('says which part it could not read', () => {
    expect(statusLine(answer({ run: { error: 'bad record' } }), NOW)).toBe('could not read the last run')
    expect(statusLine(answer({ inbox: { error: 'gone' } }), NOW)).toBe(
      'could not read the inbox · curated 18:02',
    )
    expect(statusLine(answer({ store_error: 'bad json' }), NOW)).toBe(
      '3 in inbox · curated 18:02 · could not read store.json',
    )
  })

  test('is never 80 characters or longer', () => {
    const backends = Object.fromEntries(
      ['store', 'tasks', 'calendar', 'mail', 'files'].map(name => [name, { state: 'not reachable' }]),
    )
    const line = statusLine(answer({ backends, store_error: 'x' }), NOW)
    expect(line.length).toBeLessThan(80)
    expect(line.endsWith('…')).toBe(true)
  })

  test('could not look when the answer is not an object', () => {
    expect(statusLine(null, NOW)).toBe(COULD_NOT_LOOK)
    expect(statusLine([], NOW)).toBe(COULD_NOT_LOOK)
  })
})
