import { describe, expect, test } from 'claude-code/testing'

import { COULD_NOT_LOOK, curationLine, statusLine } from '../../hooks/status-line'

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
  test('says nothing while nothing is wrong: notes in the inbox, an empty inbox, a run under way, no run yet, curation paused', () => {
    // Covers: B203
    expect(statusLine(answer({}))).toBeNull()
    expect(statusLine(answer({ inbox: { count: 0, evicted: 0 } }))).toBeNull()
    expect(statusLine(answer({ run: { state: 'running' } }))).toBeNull()
    expect(statusLine(answer({ inbox: { count: 0 }, run: { state: 'none' } }))).toBeNull()
    expect(statusLine(answer({ paused: true }))).toBeNull()
  })

  test('says the last curation run failed', () => {
    // Covers: B203
    expect(statusLine(answer({ run: { state: 'failed' } }))).toBe('last curation run failed')
  })

  test('says the last curation run was interrupted', () => {
    // Covers: B203
    expect(statusLine(answer({ run: { state: 'interrupted' } }))).toBe('last curation run interrupted')
  })

  test('names a backend that cannot be reached, during a run too', () => {
    // Covers: B203
    const backends = { ...REACHABLE, tasks: { state: 'not reachable', detail: 'no grant' } }
    expect(statusLine(answer({ backends }))).toBe('tasks not reachable')
    expect(statusLine(answer({ backends, run: { state: 'running' } }))).toBe('tasks not reachable')
  })

  test('says which part it could not read', () => {
    // Covers: B203
    expect(statusLine(answer({ run: { error: 'bad record' } }))).toBe('could not read the last curation run')
    expect(statusLine(answer({ run: undefined }))).toBe('could not read the last curation run')
    expect(statusLine(answer({ inbox: { error: 'gone' } }))).toBe('could not read the inbox')
    expect(statusLine(answer({ store_error: 'bad json' }))).toBe('could not read store.json')
  })

  test('joins everything that is wrong in one line, the run first', () => {
    // Covers: B203
    const backends = { ...REACHABLE, calendar: { state: 'not reachable', detail: 'timed out' } }
    const wrong = answer({ run: { state: 'failed' }, inbox: { error: 'gone' }, backends })
    expect(statusLine(wrong)).toBe('last curation run failed · could not read the inbox · calendar not reachable')
    expect(statusLine(answer({ store_error: 'bad json', backends }))).toBe('could not read store.json · calendar not reachable')
  })

  test('never names the inbox, the time of the last run or a pause beside what is wrong', () => {
    // Covers: B203
    expect(statusLine(answer({ run: { state: 'interrupted' }, paused: true, inbox: { count: 7, evicted: 0 } }))).toBe(
      'last curation run interrupted',
    )
  })

  test('is never 80 characters or longer', () => {
    // Covers: B203
    const backends = Object.fromEntries(
      ['store', 'tasks', 'calendar', 'mail', 'files'].map(name => [name, { state: 'not reachable' }]),
    )
    const line = statusLine(answer({ backends, store_error: 'x' })) ?? ''
    expect(line.length).toBeLessThan(80)
    expect(line.endsWith('…')).toBe(true)
  })

  test('could not look when the answer is not an object', () => {
    // Covers: B203
    expect(statusLine(null)).toBe(COULD_NOT_LOOK)
    expect(statusLine([])).toBe(COULD_NOT_LOOK)
  })
})

describe('the line that says how curation stands', () => {
  test('names the inbox and the time of the last run today', () => {
    // Covers: B203
    expect(curationLine(answer({}), NOW)).toBe('3 in inbox · curated 18:02')
  })

  test('says nothing of a last run that failed, never succeeded or could not be read', () => {
    // Covers: B203
    expect(curationLine(answer({ run: { state: 'failed' } }), NOW)).toBe('3 in inbox')
    expect(curationLine(answer({ run: { error: 'state.json: bad json' } }), NOW)).toBe('3 in inbox')
    expect(curationLine(answer({ run: { state: 'failed' }, inbox: { count: 0 } }), NOW)).toBeNull()
  })

  test('names no inbox that is empty', () => {
    // Covers: B203
    expect(curationLine(answer({ inbox: { count: 0, evicted: 0 } }), NOW)).toBe('curated 18:02')
  })

  test('names the day of a last run before today, read in its own offset', () => {
    // Covers: B203
    const run = { state: 'succeeded', last_succeeded_at: '2026-03-13T23:50:00+01:00' }
    expect(curationLine(answer({ run }), NOW)).toBe('3 in inbox · curated 2026-03-13')
  })

  test('says a run is in progress, and nothing of the inbox then', () => {
    // Covers: B203
    expect(curationLine(answer({ run: { state: 'running' } }), NOW)).toBe('curating')
  })

  test('says when nothing has been curated yet', () => {
    // Covers: B203
    expect(curationLine(answer({ run: { state: 'none' } }), NOW)).toBe('3 in inbox · not curated yet')
    expect(curationLine(answer({ inbox: { count: 0 }, run: { state: 'none' } }), NOW)).toBe('not curated yet')
  })

  test('says that curation is paused, after the rest', () => {
    // Covers: B203
    expect(curationLine(answer({ paused: true }), NOW)).toBe('3 in inbox · curated 18:02 · curation paused')
    expect(curationLine(answer({ paused: true, inbox: { count: 0 } }), NOW)).toBe('curated 18:02 · curation paused')
    expect(curationLine(answer({ paused: true, run: { state: 'running' } }), NOW)).toBe('curating · curation paused')
    expect(curationLine(answer({ paused: false }), NOW)).toBe('3 in inbox · curated 18:02')
  })

  test('names nothing that is wrong: no backend, no store.json', () => {
    // Covers: B203
    const backends = { ...REACHABLE, tasks: { state: 'not reachable', detail: 'no grant' } }
    expect(curationLine(answer({ backends, store_error: 'bad json' }), NOW)).toBe('3 in inbox · curated 18:02')
  })

  test('says nothing when the answer is not an object, which the status line says', () => {
    // Covers: B203
    expect(curationLine(null, NOW)).toBeNull()
    expect(curationLine([], NOW)).toBeNull()
  })
})
