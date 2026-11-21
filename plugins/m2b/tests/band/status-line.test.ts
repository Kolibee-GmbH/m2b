import { describe, expect, test } from 'claude-code/testing'

import {
  COULD_NOT_LOOK,
  NOT_KNOWN,
  curatingMachineOf,
  curationLine,
  healthOf,
  isLessonStanding,
  lessonLine,
  noRunStarted,
  parseRunStart,
  statusLine,
  whileCurating,
} from '../../hooks/status-line'

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
    expect(statusLine(answer({ lessons: { error: 'memory/lessons is not downloaded to this machine' } }))).toBe(
      'could not read the lessons',
    )
    expect(statusLine(answer({ lessons: { in_every_session: 0, kept_at_source: [], each: [] } }))).toBeNull()
    expect(statusLine(answer({ lessons: undefined }))).toBeNull()
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
    // Covers: B203, B209
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
    // Covers: B203, B209
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

/** What the health of `answer` says of curation: this machine curates, and no run is under way. */
const CURATES_HERE = { curates: true, isCurating: false }

describe('how m2b stands, for the part of the pane about m2b itself', () => {
  test('while nothing is wrong it names no trouble, and the line about curation is the one that says how curation stands', () => {
    // Covers: B206
    expect(healthOf(answer({}), NOW)).toEqual({ curation: '3 in inbox · curated 18:02', troubles: [], ...CURATES_HERE })
    expect(healthOf(answer({ paused: true, run: { state: 'running' } }), NOW)).toEqual({
      curation: 'curating · curation paused',
      troubles: [],
      ...CURATES_HERE,
      isCurating: true,
    })
    // Nothing in the inbox and no time of a run that succeeded: nothing to say.
    expect(healthOf(answer({ inbox: { count: 0 }, run: { state: 'succeeded' } }), NOW)).toEqual({ curation: null, troubles: [], ...CURATES_HERE })
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

  test('lessons m2b could not read are a sentence with the error, never no lessons', () => {
    // Covers: B206
    const lessons = { error: 'memory/lessons is not downloaded to this machine; run: m2b store fetch memory/lessons' }
    expect(healthOf(answer({ lessons }), NOW).troubles).toEqual([`m2b could not read the lessons: ${lessons.error}`])
  })

  test('an answer without a part about m2b is one trouble, where the status line says that it could not look', () => {
    // Covers: B206
    for (const noAnswer of [undefined, null, 'ok', 7]) {
      expect(healthOf(noAnswer, NOW)).toEqual({
        curation: null,
        troubles: ['m2b could not look at how it stands.'],
        curates: null,
        isCurating: false,
      })
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
      ...CURATES_HERE,
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
    expect(healthOf(answer({ run: { state: 'failed' } }), NOW)).toEqual({
      curation: '3 in inbox',
      troubles: ['The last curation run failed.'],
      ...CURATES_HERE,
    })
  })

  test('a reason is one plain line, whatever the answer holds', () => {
    // Covers: B206
    const run = { state: 'failed', message: 'the ingest step\nfailed\u001b[2J' }
    expect(healthOf(answer({ run }), NOW).troubles).toEqual(['The last curation run failed: the ingest step failed'])
  })
})

describe('what m2b knows of curation on this machine, for the button that starts a run', () => {
  test('whether this machine curates and which one does come from the answer, and where it names no curating machine neither is known', () => {
    // Covers: B216
    expect(healthOf(answer({}), NOW).curates).toBe(true)
    expect(curatingMachineOf(answer({}))).toBe('alex-laptop')
    const elsewhere = answer({ curating_machine: 'tower-2', this_machine_curates: false })
    expect(healthOf(elsewhere, NOW).curates).toBe(false)
    expect(curatingMachineOf(elsewhere)).toBe('tower-2')
    // Only `true` says that this machine curates.
    for (const said of [undefined, null, 'true', 1]) {
      expect(healthOf(answer({ curating_machine: 'tower-2', this_machine_curates: said }), NOW).curates).toBe(false)
    }
    // No machine named: not known, whatever the answer says of this one.
    for (const machine of [undefined, null, '', 7, ['tower-2']]) {
      for (const curates of [true, false]) {
        const unnamed = answer({ curating_machine: machine, this_machine_curates: curates })
        expect(healthOf(unnamed, NOW).curates).toBeNull()
        expect(curatingMachineOf(unnamed)).toBeNull()
      }
    }
    for (const noAnswer of [undefined, null, 'tower-2', 7, ['tower-2']]) {
      expect(curatingMachineOf(noAnswer)).toBeNull()
    }
  })

  test('how m2b stands never names the machine that curates: the name is a value of a setting, read apart', () => {
    // Covers: B216, B197
    for (const status of [answer({}), answer({ curating_machine: 'tower-2', this_machine_curates: false }), answer({ run: { state: 'running' } })]) {
      const health = healthOf(status, NOW)
      expect(Object.keys(health).sort()).toEqual(['curates', 'curation', 'isCurating', 'troubles'])
      expect(JSON.stringify(health)).not.toContain('alex-laptop')
      expect(JSON.stringify(health)).not.toContain('tower-2')
      expect(JSON.stringify(whileCurating(health))).not.toContain('alex-laptop')
    }
  })

  test('a run is under way where the answer says its state is running, and nowhere else', () => {
    // Covers: B216
    expect(healthOf(answer({ run: { state: 'running' } }), NOW).isCurating).toBe(true)
    for (const run of [{ state: 'succeeded' }, { state: 'failed' }, { state: 'none' }, { state: 'Running' }, { error: 'state.json: bad json' }, {}, undefined, null, 'running']) {
      expect(healthOf(answer({ run }), NOW).isCurating).toBe(false)
    }
    // Beside a trouble too: the store that cannot be read does not hide the run.
    expect(healthOf(answer({ run: { state: 'running' }, store_error: 'bad json', curating_machine: null }), NOW)).toEqual({
      curation: 'curating',
      troubles: ['m2b could not read store.json: bad json'],
      curates: null,
      isCurating: true,
    })
  })

  test('the lessons are read with their counts, a lesson not in the form left out, and none where there are none', () => {
    // Covers: B282
    const each = [
      { name: 'proof.md', kind: 'action', kept: '2026-11-20', corrected_again: 2, fired: 3, calls: 40 },
      { name: 'once.md', kind: 'knowledge', kept: '2026-11-20', corrected_again: null },
      { name: 'odd.md', kind: 'action', kept: '2026-11-20', corrected_again: -1 },
      { name: 7, kind: 'action', kept: '2026-11-20', corrected_again: 0 },
    ]

    expect(healthOf(answer({ lessons: { each } }), NOW).lessons).toEqual([
      { name: 'proof.md', kind: 'action', kept: '2026-11-20', correctedAgain: 2, fired: 3, calls: 40 },
      { name: 'once.md', kind: 'knowledge', kept: '2026-11-20', correctedAgain: null },
    ])
    expect('lessons' in healthOf(answer({ lessons: { each: [] } }), NOW)).toBe(false)
    // A share that ends in a half is rounded to the even number, as `m2b status` rounds it.
    const action = { name: 'proof.md', kind: 'action', kept: '2026-11-20', correctedAgain: 0 }
    expect(lessonLine({ ...action, fired: 1, calls: 40 })).toContain('in 40 Bash calls (2%)')
    expect(lessonLine({ ...action, fired: 3, calls: 40 })).toContain('in 40 Bash calls (8%)')
    expect(isLessonStanding({ ...action, fired: 'x', calls: 'y' })).toBe(false)
    expect(isLessonStanding({ ...action, fired: 1, calls: 40 })).toBe(true)
    expect(lessonLine({ name: 'a\u001b[2Jb.md', kind: 'knowledge', kept: '2026-11-20', correctedAgain: 0 })).toBe(
      'lesson ab.md (knowledge, kept 2026-11-20): corrected again 0 times',
    )
  })

  test('a lesson kept as a fix is read and said with its counts like any other', () => {
    // Covers: B289
    const each = [{ name: 'fix-3f9c2a71b0de', kind: 'fix', kept: '2026-11-20', corrected_again: 1 }]

    const [lesson] = healthOf(answer({ lessons: { each } }), NOW).lessons ?? []

    expect(lesson).toEqual({ name: 'fix-3f9c2a71b0de', kind: 'fix', kept: '2026-11-20', correctedAgain: 1 })
    expect(lessonLine(lesson!)).toBe('lesson fix-3f9c2a71b0de (fix, kept 2026-11-20): corrected again 1 time: not working')
  })

  test('where m2b gave no answer about itself nothing is known of curation and nothing is said', () => {
    // Covers: B216
    expect(NOT_KNOWN).toEqual({ curation: null, troubles: [], curates: null, isCurating: false })
    expect(healthOf(undefined, NOW)).toEqual({ ...NOT_KNOWN, troubles: ['m2b could not look at how it stands.'] })
  })

  test('right after a start m2b stands as with a run under way: the line says curating, and the rest is as it was', () => {
    // Covers: B216
    const before = healthOf(answer({ run: { state: 'failed', message: 'the ingest step failed' } }), NOW)
    const kept = structuredClone(before)

    expect(whileCurating(before)).toEqual({ ...before, isCurating: true, curation: 'curating' })
    expect(whileCurating(before).troubles).toEqual(['The last curation run failed: the ingest step failed'])
    // What it was handed is not changed.
    expect(before).toEqual(kept)
    expect(whileCurating(NOT_KNOWN)).toEqual({ ...NOT_KNOWN, isCurating: true, curation: 'curating' })
    expect(NOT_KNOWN.isCurating).toBe(false)
    // As the line reads once m2b's status says that a run is under way.
    expect(whileCurating(before).curation).toBe(healthOf(answer({ run: { state: 'running' } }), NOW).curation)
  })

  test('the answer of the command that starts a run: a run where its kind says started; a refusal the band knows by its kind alone; any other kind as a failure in the command\'s words; anything else is no such answer', () => {
    // Covers: B216
    const started = 'a curation run started in the background (process 4711); m2b status shows how it goes'
    expect(parseRunStart(JSON.stringify({ kind: 'started', message: started }))).toEqual({ isStarted: true })
    expect(parseRunStart(`${JSON.stringify({ kind: 'started', message: started })}\n`)).toEqual({ isStarted: true })
    // More than the two fields, or the kind alone, is read all the same.
    expect(parseRunStart(JSON.stringify({ kind: 'started', message: started, pid: 4711 }))).toEqual({ isStarted: true })
    expect(parseRunStart(JSON.stringify({ kind: 'started' }))).toEqual({ isStarted: true })

    // The three reasons the band has words for: the command's sentence, which can name a machine or a folder, is left out.
    const sentences = ['tower-2 curates this store', 'run: m2b fetch /home/alex/Notes/store.json', '', undefined, null, 7]
    for (const refusal of ['running', 'not-curating', 'not-downloaded'] as const) {
      for (const message of sentences) {
        expect(parseRunStart(JSON.stringify({ kind: refusal, message }))).toEqual({ isStarted: false, refusal, reason: null })
      }
    }

    // Any other kind is a failure told in the command's words, or by the kind's name where it has none.
    for (const kind of ['paused', 'not-due', 'queued', 'Started', 'started ', 'failed', 'RUNNING']) {
      expect(parseRunStart(JSON.stringify({ kind, message: 'why' }))).toEqual({ isStarted: false, refusal: 'failed', reason: 'why' })
      for (const message of [undefined, null, '', 7, ['a sentence']]) {
        expect(parseRunStart(JSON.stringify({ kind, message }))).toEqual({ isStarted: false, refusal: 'failed', reason: kind })
      }
    }
    expect(parseRunStart(JSON.stringify({ kind: '', message: 'why' }))).toEqual({ isStarted: false, refusal: 'failed', reason: 'why' })

    const noSuchAnswer = [
      '',
      started,
      '{"kind":"started"',
      'null',
      '7',
      '"started"',
      '["started"]',
      JSON.stringify({ message: started }),
      JSON.stringify({ kind: true, message: started }),
      JSON.stringify({ kind: null, message: started }),
    ]
    for (const stdout of noSuchAnswer) {
      expect(parseRunStart(stdout)).toBeNull()
    }
  })

  test('what the pane says of a press that started no run: the band\'s own words for the reasons it knows, which name no machine and no folder, and the reason it was handed for a failure', () => {
    // Covers: B216
    const reason = 'tower-2 curates the store in /home/alex/Notes'
    expect(noRunStarted('running', null)).toBe('No curation run started: a curation run is already running on this machine')
    expect(noRunStarted('not-curating', null)).toBe('No curation run started: another machine curates the store')
    expect(noRunStarted('not-downloaded', null)).toBe('No curation run started: store.json is not downloaded on this machine')
    // A reason handed beside a refusal the band knows is not said: its own words stand.
    for (const refusal of ['running', 'not-curating', 'not-downloaded'] as const) {
      expect(noRunStarted(refusal, reason)).toBe(noRunStarted(refusal, null))
      expect(noRunStarted(refusal, reason)).not.toContain('tower-2')
    }
    expect(noRunStarted('failed', reason)).toBe(`No curation run started: ${reason}`)
    // The reason is gone where the mod was loaded again since: the state still says that the start failed.
    expect(noRunStarted('failed', null)).toBe('No curation run started: m2b did not say why')
  })
})
