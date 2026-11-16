import { describe, expect, test } from 'claude-code/testing'

import { COULD_NOT_LOOK, curationLine, healthOf, statusLine } from '../../hooks/status-line'

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

describe('how m2b stands, for the part of the pane about m2b itself', () => {
  test('while nothing is wrong it names no trouble, and the line about curation is the one that says how curation stands', () => {
    // Covers: B206
    expect(healthOf(answer({}), NOW)).toEqual({ curation: '3 in inbox · curated 18:02', troubles: [] })
    expect(healthOf(answer({ paused: true, run: { state: 'running' } }), NOW)).toEqual({ curation: 'curating · curation paused', troubles: [] })
    // Nothing in the inbox and no time of a run that succeeded: nothing to say.
    expect(healthOf(answer({ inbox: { count: 0 }, run: { state: 'succeeded' } }), NOW)).toEqual({ curation: null, troubles: [] })
  })

  test('a last curation run that failed is a sentence with what the run said, and one that ends with a full stop where it said nothing', () => {
    // Covers: B206
    const failed = { state: 'failed', message: 'the ingest step failed' }
    expect(healthOf(answer({ run: failed }), NOW).troubles).toEqual(['The last curation run failed: the ingest step failed'])
    expect(healthOf(answer({ run: { state: 'failed' } }), NOW).troubles).toEqual(['The last curation run failed.'])
    expect(healthOf(answer({ run: { state: 'failed', message: '' } }), NOW).troubles).toEqual(['The last curation run failed.'])
  })

  test('a last curation run that was interrupted is a sentence, with what the run said where it said something', () => {
    // Covers: B206
    const interrupted = { state: 'interrupted', message: 'the machine went to sleep' }
    expect(healthOf(answer({ run: interrupted }), NOW).troubles).toEqual(['The last curation run was interrupted: the machine went to sleep'])
    expect(healthOf(answer({ run: { state: 'interrupted' } }), NOW).troubles).toEqual(['The last curation run was interrupted.'])
  })

  test('a last curation run m2b could not read is a sentence, with the error where the answer names one', () => {
    // Covers: B206
    expect(healthOf(answer({ run: { error: 'state.json: bad json' } }), NOW).troubles).toEqual([
      'm2b could not read the last curation run: state.json: bad json',
    ])
    expect(healthOf(answer({ run: undefined }), NOW).troubles).toEqual(['m2b could not read the last curation run.'])
  })

  test('an inbox m2b could not read is a sentence, with the error where the answer names one', () => {
    // Covers: B206
    expect(healthOf(answer({ inbox: { error: 'the folder is gone' } }), NOW).troubles).toEqual(['m2b could not read the inbox: the folder is gone'])
    expect(healthOf(answer({ inbox: undefined }), NOW).troubles).toEqual(['m2b could not read the inbox.'])
  })

  test('an answer without a part about m2b is one trouble, where the status line says that it could not look', () => {
    // Covers: B206
    for (const noAnswer of [undefined, null, 'ok', 7]) {
      expect(healthOf(noAnswer, NOW)).toEqual({ curation: null, troubles: ['m2b could not look at how it stands.'] })
      expect(statusLine(noAnswer)).toBe(COULD_NOT_LOOK)
    }
  })

  test('a store.json m2b could not read is a sentence, with the error where it is not empty', () => {
    // Covers: B206
    expect(healthOf(answer({ store_error: 'bad json in line 3' }), NOW).troubles).toEqual(['m2b could not read store.json: bad json in line 3'])
    expect(healthOf(answer({ store_error: '' }), NOW).troubles).toEqual(['m2b could not read store.json.'])
  })

  test('a backend m2b could not reach is a sentence that names it, with the detail where the check gave one', () => {
    // Covers: B206
    const timedOut = { ...REACHABLE, calendar: { state: 'not reachable', detail: 'timed out after 20 seconds' } }
    expect(healthOf(answer({ backends: timedOut }), NOW).troubles).toEqual(['m2b could not reach the calendar: timed out after 20 seconds'])
    const silent = { ...REACHABLE, tasks: { state: 'not reachable', detail: '' } }
    expect(healthOf(answer({ backends: silent }), NOW).troubles).toEqual(['m2b could not reach the tasks.'])
    expect(healthOf(answer({ backends: { ...REACHABLE, tasks: { state: 'not reachable' } } }), NOW).troubles).toEqual([
      'm2b could not reach the tasks.',
    ])
  })

  test('everything that is wrong is named, each a sentence of its own, in the order of the status line, beside the line about curation', () => {
    // Covers: B206
    const backends = { ...REACHABLE, calendar: { state: 'not reachable', detail: 'timed out' } }
    const wrong = answer({ run: { state: 'failed', message: 'the ingest step failed' }, inbox: { error: 'gone' }, store_error: 'bad json', backends })

    expect(healthOf(wrong, NOW)).toEqual({
      curation: null,
      troubles: [
        'The last curation run failed: the ingest step failed',
        'm2b could not read the inbox: gone',
        'm2b could not read store.json: bad json',
        'm2b could not reach the calendar: timed out',
      ],
    })
    // The status line names the same things in the same order, in its few words and without a reason.
    const { store_error: _, ...withoutStore } = wrong
    expect(statusLine(withoutStore)).toBe('last curation run failed · could not read the inbox · calendar not reachable')
    expect(healthOf(withoutStore, NOW).troubles).toEqual([
      'The last curation run failed: the ingest step failed',
      'm2b could not read the inbox: gone',
      'm2b could not reach the calendar: timed out',
    ])
    // What still can be said of curation stays: the inbox beside a run that failed.
    expect(healthOf(answer({ run: { state: 'failed' } }), NOW)).toEqual({ curation: '3 in inbox', troubles: ['The last curation run failed.'] })
  })

  test('a reason is one plain line, whatever the answer holds', () => {
    // Covers: B206
    const run = { state: 'failed', message: 'the ingest step\nfailed\u001b[2J' }
    expect(healthOf(answer({ run }), NOW).troubles).toEqual(['The last curation run failed: the ingest step failed'])
  })
})
