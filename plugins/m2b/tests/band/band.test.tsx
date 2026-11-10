import { expect, mock, test } from 'claude-code/testing'
import type { Engine, MockClock } from 'claude-code/testing'
import type { On, ProcessRunResult } from 'claude-code'

const LAUNCHER = '/home/alex/.local/bin/m2b'
const MACHINE_CONFIG = '/home/alex/.config/m2b/config.json'
const NOW = Date.parse('2026-03-14T17:30:00Z')

const BAND = {
  plugin: 'm2b',
  component: 'AbovePrompt',
  requestId: 'above-prompt',
  props: {
    hasSurvey: false,
    isWorking: false,
    maxRows: 20,
    bodyColumns: 100,
    scroll: { offset: 0, bodyRows: 19 },
    view: {},
  },
} as const

type FakeTask = {
  id: string
  title: string
  notes: string
  completed: boolean
  dropped: boolean
  marker: string
}

const STATUS = {
  inbox: { count: 2, evicted: 0 },
  run: { state: 'succeeded', last_succeeded_at: '2026-03-14T18:02:00+01:00' },
  backends: { tasks: { state: 'reachable', detail: '' } },
}

/** The `m2b` launcher, answered from memory; every call is recorded. */
class FakeM2b {
  readonly calls: string[][] = []
  tasks: FakeTask[] = []
  status: unknown = STATUS
  failure: string | null = null
  statusFails = false
  /** Whether m2b is set up on this machine: its machine config exists, else every command answers "not set up". */
  isSetUp = true
  /** Set up, but the store has no store.json yet, as on a machine whose synced store has not arrived. */
  isStoreMissing = false
  /** The launcher the core writes at its first session start after setup. */
  hasLauncher = true
  /** How long the answer to a call takes on the test clock; it is read when the call starts. */
  delayMs: (args: readonly string[]) => number = () => 0
  /** Runs before the band's answer is made, as another session would act meanwhile. */
  beforeCandidateList: (() => void) | null = null

  candidate(id: string, title: string): this {
    this.tasks.push({ id, title, notes: 'm2b:candidate', completed: false, dropped: false, marker: 'candidate' })
    return this
  }

  question(id: string, title: string): this {
    this.tasks.push({ id, title, notes: 'm2b:current 1a2b3c4d5e6f', completed: false, dropped: false, marker: 'current' })
    return this
  }

  review(id: string, findings: string[]): this {
    const notes = ['m2b:review\nCuration run of 2026-03-14 18:02', ...findings].join('\n\n')
    this.tasks.push({ id, title: 'm2b: review', notes, completed: false, dropped: false, marker: 'review' })
    return this
  }

  handle(argv: readonly string[]): ProcessRunResult {
    expect(argv[0]).toBe(LAUNCHER)
    const args = argv.slice(1)
    this.calls.push(args)
    if (!this.isSetUp) {
      return fail('not set up: no machine config at /home/alex/.config/m2b/config.json')
    }
    if (args[0] === 'band') {
      return this.bandAnswer()
    }
    if (this.failure !== null) {
      return fail(this.failure)
    }
    const [, verb, ...rest] = args
    const task = this.tasks.find(open => open.id === rest[0])
    if (task === undefined) {
      return fail(`no task with id ${rest[0]}`)
    }
    task.completed = true
    task.dropped = verb === 'drop'
    return ok('')
  }

  /** As `m2b band --json` answers: the open curator tasks by marker, or the error, and the status. */
  bandAnswer(): ProcessRunResult {
    if (this.statusFails) {
      return fail('could not read the machine config')
    }
    if (this.beforeCandidateList !== null) {
      this.beforeCandidateList()
      this.beforeCandidateList = null
    }
    const open = (marker: string): FakeTask[] => this.tasks.filter(task => task.marker === marker && !task.completed)
    const error = this.isStoreMissing
      ? 'not set up: no store.json in the store /home/alex/Notes. Run /m2b:m2b setup in Claude Code.'
      : this.failure
    const tasks =
      error === null
        ? { candidates: open('candidate'), questions: open('current'), reviews: open('review') }
        : { error }
    return ok(JSON.stringify({ tasks, status: this.status }))
  }

  writes(): string[][] {
    return this.calls.filter(call => call[0] === 'tasks')
  }
}

function ok(stdout: string): ProcessRunResult {
  return { exitCode: 0, stdout, stderr: '', isStdoutTruncated: false, isStderrTruncated: false }
}

function fail(message: string): ProcessRunResult {
  return { exitCode: 1, stdout: '', stderr: `m2b: ${message}\n`, isStdoutTruncated: false, isStderrTruncated: false }
}

type World = { clock: MockClock; statuses: (string | undefined)[] }

/** Files under the home folder, shared by the sessions of one test: what `$.fs` reads and writes. */
type Files = Map<string, string>

async function start(
  $: Engine,
  on: On,
  fake: FakeM2b,
  env: Record<string, string> = {},
  files?: Files,
): Promise<World> {
  const clock = mock.clock(on, { now: NOW })
  mock.env(on, { HOME: '/home/alex', ...env })
  on('fs.exists', (_, e) => ({
    value: (e.path === LAUNCHER && fake.hasLauncher) || (e.path === MACHINE_CONFIG && fake.isSetUp),
  }))
  if (files !== undefined) {
    on('fs.read', (_, e) => {
      const text = files.get(e.path)
      if (text === undefined) {
        throw new Error(`ENOENT: ${e.path}`)
      }
      return { value: text }
    })
    on('fs.write', (_, e) => {
      files.set(e.path, e.text)
      return { value: undefined }
    })
  }
  const statuses: (string | undefined)[] = []
  on('process.run', async (_, e) => {
    const value = fake.handle(e.argv)
    const delay = fake.delayMs(e.argv.slice(1))
    if (delay > 0) {
      await clock.sleep(delay)
    }
    return { value }
  })
  on('ui.status', (_, e) => {
    statuses.push(e.text)
    return { value: undefined }
  })
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('turn.complete', (_, e) => ({ text: e.answer }))
  // Stands for the engine's own drawing, which is what the band leaves to when it has nothing to show.
  on('ui.render', ($, e) => {
    const { Text } = $.ui.resolve(e)
    return <Text>engine</Text>
  })
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await clock.advance(1)
  return { clock, statuses }
}

async function texts(ui: { findAll: (q: { type: string }) => Promise<{ text: string }[]> }): Promise<string[]> {
  return (await ui.findAll({ type: 'Text' })).map(found => found.text.trim()).filter(text => text !== '')
}

test('the band shows candidates and the review, capped with "and N more"', async ($, on) => {
  // Covers: B31
  const fake = new FakeM2b()
  for (const n of [1, 2, 3, 4, 5]) {
    fake.candidate(`c${n}`, `Remember? Dana prefers tea ${n}`)
  }
  fake.review('r1', ['lint: broken link in a.md', 'lint: broken link in b.md', 'ingest: x', 'ingest: y'])
  await start($, on, fake)

  for (const surface of ['terminal', 'desktop'] as const) {
    const ui = await $.ui.mount({ ...BAND, surface })
    const shown = await texts(ui)
    expect(shown).toContain('Remember? Dana prefers tea 3')
    expect(shown).not.toContain('Remember? Dana prefers tea 4')
    expect(shown).toContain('and 2 more candidates')
    expect(shown).toContain('m2b: review')
    expect(shown).toContain('lint: broken link in a.md')
    expect(shown).not.toContain('ingest: y')
    expect(shown).toContain('and 1 more findings')
    expect(await ui.findAll({ type: 'Button' })).toHaveLength(6)
    await ui.unmount()
  }
})

test('nothing to show draws nothing of its own', async ($, on) => {
  await start($, on, new FakeM2b())
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await texts(ui)).toEqual(['engine'])
  await ui.unmount()
})

test('the band runs without any switch once m2b is set up', async ($, on) => {
  // Covers: B91
  const fake = new FakeM2b().candidate('c1', 'Remember? Acme moved')
  const { statuses } = await start($, on, fake)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await ui.findAll({ type: 'Button' })).toHaveLength(2)
  await ui.unmount()
  expect(statuses.at(-1)).toBe('2 in inbox · curated 18:02')
  expect(fake.calls.some(call => call[0] === 'addons')).toBe(false)
})

test('before m2b is set up the band draws nothing, says nothing and asks m2b nothing', async ($, on) => {
  // Covers: B91
  const fake = new FakeM2b().candidate('c1', 'Remember? Acme moved')
  fake.isSetUp = false
  const { clock, statuses } = await start($, on, fake)
  await clock.advance(60_000)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await texts(ui)).toEqual(['engine'])
  await ui.unmount()
  expect(statuses.length).toBeGreaterThan(0)
  expect(statuses.every(text => text === undefined)).toBe(true)
  expect(fake.calls).toEqual([])
})

test('a machine config that goes away clears what the band showed', async ($, on) => {
  const fake = new FakeM2b().candidate('c1', 'Remember? Acme moved')
  const { clock, statuses } = await start($, on, fake)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await ui.findAll({ type: 'Button' })).toHaveLength(2)

  fake.isSetUp = false
  await clock.advance(60_000)
  expect(await texts(ui)).toEqual(['engine'])
  expect(statuses.at(-1)).toBeUndefined()
  await ui.unmount()
})

test('a store without store.json shows the error line instead of an empty band', async ($, on) => {
  const fake = new FakeM2b().candidate('c1', 'Remember? Acme moved')
  fake.isStoreMissing = true
  await start($, on, fake)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect((await texts(ui)).join('\n')).toContain('m2b could not read the tasks: not set up: no store.json')
  await ui.unmount()
})

test('a session start whose note cannot be written still starts the band', async ($, on) => {
  on('fs.write', () => {
    throw new Error('EACCES: permission denied')
  })
  const fake = new FakeM2b().candidate('c1', 'Remember? Acme moved')
  await start($, on, fake)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await ui.findAll({ type: 'Button' })).toHaveLength(2)
  await ui.unmount()
})

test('a session start notes that the band ran, for m2b doctor', async ($, on) => {
  // Covers: B92
  const files: Files = new Map()
  await start($, on, new FakeM2b(), {}, files)
  expect(JSON.parse(files.get('/home/alex/.local/state/m2b/band-seen.json') ?? '{}')).toEqual({
    seenAt: '2026-03-14T17:30:00.000Z',
  })
})

test('before the core wrote its launcher the band starts nothing and says nothing', async ($, on) => {
  const fake = new FakeM2b().candidate('c1', 'Remember? Acme moved')
  fake.hasLauncher = false
  const { clock, statuses } = await start($, on, fake)
  await clock.advance(60_000)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await texts(ui)).toEqual(['engine'])
  await ui.unmount()
  expect(fake.calls).toEqual([])
  expect(statuses.every(text => text === undefined)).toBe(true)
})

test('inside a fenced curation step the band asks m2b nothing', async ($, on) => {
  const fake = new FakeM2b().candidate('c1', 'Remember? Acme moved')
  const { clock } = await start($, on, fake, { M2B_CURATION_RUN: '1' })
  await clock.advance(60_000)
  await $.turn.complete({ answer: 'done', durationMs: 5, isAborted: false, turnId: 't1', reason: 'answer' })
  await clock.advance(1)
  expect(fake.calls).toEqual([])
})

test('an answer another session stored within 55 seconds is used without starting m2b', async ($, on) => {
  const cache = '/home/alex/.local/state/m2b'
  const files: Files = new Map([
    [
      `${cache}/band-view.json`,
      JSON.stringify({
        writtenAtMs: NOW - 10_000,
        value: {
          snapshot: { candidates: [{ id: 'c9', title: 'Remember? From the other session' }], review: null, error: null },
          status: '7 in inbox',
        },
      }),
    ],
  ])
  const fake = new FakeM2b()
  const { clock, statuses } = await start($, on, fake, {}, files)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await texts(ui)).toContain('Remember? From the other session')
  expect(statuses.at(-1)).toBe('7 in inbox')
  expect(fake.calls).toEqual([])

  fake.candidate('c1', 'Remember? Acme moved')
  await clock.advance(60_000)
  expect(await texts(ui)).toContain('Remember? Acme moved')
  expect(fake.calls.map(call => call[0])).toContain('band')
  expect(JSON.parse(files.get(`${cache}/band-view.json`) ?? '{}').value.snapshot.candidates[0].id).toBe('c1')
  await ui.unmount()
})

test('after its own turn a session reads again, whatever another session stored', async ($, on) => {
  const files: Files = new Map()
  const fake = new FakeM2b()
  const { clock } = await start($, on, fake, {}, files)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await ui.findAll({ type: 'Button' })).toHaveLength(0)

  fake.candidate('c1', 'Remember? Acme moved')
  await clock.advance(10_000)
  await $.turn.complete({ answer: 'done', durationMs: 5, isAborted: false, turnId: 't1', reason: 'answer' })
  await clock.advance(1)
  expect(await ui.findAll({ type: 'Button' })).toHaveLength(2)
  await ui.unmount()
})

test('a slow load never replaces an answer another session started later', async ($, on) => {
  const cache = '/home/alex/.local/state/m2b/band-view.json'
  const files: Files = new Map()
  const fake = new FakeM2b().candidate('c1', 'Remember? Acme moved')
  fake.delayMs = args => (args[0] === 'band' ? 30_000 : 0)
  const { clock } = await start($, on, fake, {}, files)
  const snapshot = { candidates: [], review: null, error: null }
  const newer = { writtenAtMs: NOW + 5_000, value: { snapshot, status: '0 in inbox' } }
  files.set(cache, JSON.stringify(newer))
  await clock.advance(31_000)
  expect(JSON.parse(files.get(cache) ?? '{}')).toEqual(newer)
})

test('keep completes the candidate and drop drops it', async ($, on) => {
  const fake = new FakeM2b().candidate('c1', 'Remember? Alex runs on Tuesdays').candidate('c2', 'Remember? Acme moved')
  await start($, on, fake)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })

  const before = fake.calls.length
  await ui.press({ key: 'keep:c1' })
  await ui.press({ key: 'drop:c2' })

  expect(fake.writes()).toEqual([
    ['tasks', 'complete', 'c1'],
    ['tasks', 'drop', 'c2'],
  ])
  // The look before each write reads the tasks alone, without the status and its probes.
  expect(fake.calls.slice(before)[0]).toEqual(['band', '--json', '--tasks-only'])
  expect(await ui.findAll({ type: 'Button' })).toHaveLength(0)
  await ui.unmount()
})

test('a question whether a current item still holds is shown and settled like a candidate', async ($, on) => {
  const fake = new FakeM2b().candidate('c1', 'Remember? Acme moved').question('q1', 'Still current? Planning the trip')
  await start($, on, fake)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await ui.findAll({ type: 'Button' })).toHaveLength(4)

  await ui.press({ key: 'drop:q1' })

  expect(fake.writes()).toEqual([['tasks', 'drop', 'q1']])
  expect(await ui.findAll({ type: 'Button' })).toHaveLength(2)
  await ui.unmount()
})

test('after keep the band reads the tasks itself, not the answer it stored a moment before', async ($, on) => {
  const cache = '/home/alex/.local/state/m2b'
  const fake = new FakeM2b().candidate('c1', 'Remember? Acme moved')
  const files: Files = new Map([
    [
      `${cache}/band-view.json`,
      JSON.stringify({
        writtenAtMs: NOW,
        value: {
          snapshot: { candidates: [{ id: 'c1', title: 'Remember? Acme moved' }], review: null, error: null },
          status: '2 in inbox',
        },
      }),
    ],
  ])
  await start($, on, fake, {}, files)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await ui.findAll({ type: 'Button' })).toHaveLength(2)

  await ui.press({ key: 'keep:c1' })

  expect(fake.writes()).toEqual([['tasks', 'complete', 'c1']])
  expect(await ui.findAll({ type: 'Button' })).toHaveLength(0)
  expect(JSON.parse(files.get(`${cache}/band-view.json`) ?? '{}').value.snapshot.candidates).toEqual([])
  await ui.unmount()
})

test('a candidate settled in another session is not written and the band says so', async ($, on) => {
  // Covers: B30
  const fake = new FakeM2b().candidate('c1', 'Remember? Alex runs on Tuesdays')
  await start($, on, fake)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  fake.beforeCandidateList = () => {
    const task = fake.tasks[0]
    if (task !== undefined) {
      task.completed = true
    }
  }

  await ui.press({ key: 'drop:c1' })

  expect(fake.writes()).toEqual([])
  expect(await texts(ui)).toContain(
    'Already settled in another session, nothing written: Remember? Alex runs on Tuesdays',
  )
  expect(await ui.findAll({ type: 'Button' })).toHaveLength(0)
  await ui.unmount()
})

test('a failing command shows one error line', async ($, on) => {
  // Covers: X11
  const fake = new FakeM2b().candidate('c1', 'Remember? Alex runs on Tuesdays')
  fake.failure = 'reminders did not answer within 20 seconds'
  await start($, on, fake)

  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await texts(ui)).toEqual([
    'm2b could not read the tasks: reminders did not answer within 20 seconds',
  ])
  await ui.unmount()
})

test('the band reloads every 60 seconds and after each turn', async ($, on) => {
  // Covers: B31
  const fake = new FakeM2b()
  const { clock } = await start($, on, fake)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await ui.findAll({ type: 'Button' })).toHaveLength(0)

  fake.candidate('c1', 'Remember? Acme moved')
  await clock.advance(60_000)
  expect(await ui.findAll({ type: 'Button' })).toHaveLength(2)

  fake.candidate('c2', 'Remember? Dana likes tea')
  await $.turn.complete({ answer: 'done', durationMs: 5, isAborted: false, turnId: 't1', reason: 'answer' })
  await clock.advance(1)
  expect(await ui.findAll({ type: 'Button' })).toHaveLength(4)
  await ui.unmount()
})

test('the status line follows m2b status, and says when it could not look', async ($, on) => {
  const fake = new FakeM2b()
  const { clock, statuses } = await start($, on, fake)
  expect(statuses.at(-1)).toBe('2 in inbox · curated 18:02')

  fake.status = { ...STATUS, run: { state: 'running' } }
  await clock.advance(60_000)
  expect(statuses.at(-1)).toBe('curating')

  fake.statusFails = true
  await clock.advance(60_000)
  expect(statuses.at(-1)).toBe('could not look')
})

test('a subagent finishing its turn does not reload the band', async ($, on) => {
  const fake = new FakeM2b()
  const { clock } = await start($, on, fake)
  const before = fake.calls.length

  await $.turn.complete({
    answer: 'done',
    durationMs: 5,
    isAborted: false,
    turnId: 't2',
    agentId: 'a1',
    reason: 'answer',
  })
  await clock.advance(1)

  expect(fake.calls.length).toBe(before)
})

test('a write that fails shows one error line and the candidate comes back on the next reload', async ($, on) => {
  // Covers: X11
  const fake = new FakeM2b().candidate('c1', 'Remember? Alex runs on Tuesdays')
  const { clock } = await start($, on, fake)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  const handle = fake.handle.bind(fake)
  fake.handle = argv => (argv[2] === 'complete' ? fail('the task list is read-only') : handle(argv))

  await ui.press({ key: 'keep:c1' })
  expect(await texts(ui)).toEqual(['m2b could not keep "Remember? Alex runs on Tuesdays": the task list is read-only'])

  fake.handle = handle
  await clock.advance(60_000)
  expect(await ui.findAll({ type: 'Button' })).toHaveLength(2)
  await ui.unmount()
})

/** Delays the first band answer after `armed()` is called: a reload that read before the click. */
function slowFirstCandidateList(fake: FakeM2b): () => void {
  let isArmed = false
  fake.delayMs = args => {
    if (isArmed && args[0] === 'band') {
      isArmed = false
      return 5_000
    }
    return 0
  }
  return () => {
    isArmed = true
  }
}

test('a reload that read before keep was pressed does not bring the candidate back', async ($, on) => {
  const fake = new FakeM2b().candidate('c1', 'Remember? Acme moved')
  const arm = slowFirstCandidateList(fake)
  const { clock } = await start($, on, fake)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  arm()
  await clock.advance(60_000)

  const pressing = ui.press({ key: 'keep:c1' })
  await clock.advance(5_000)
  await pressing

  expect(fake.writes()).toEqual([['tasks', 'complete', 'c1']])
  expect(await ui.findAll({ type: 'Button' })).toHaveLength(0)
  await ui.unmount()
})

test('a reload that read before a failed write does not hide the error', async ($, on) => {
  // Covers: X11
  const fake = new FakeM2b().candidate('c1', 'Remember? Acme moved')
  const arm = slowFirstCandidateList(fake)
  const { clock } = await start($, on, fake)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  const handle = fake.handle.bind(fake)
  fake.handle = argv => (argv[2] === 'complete' ? fail('the task list is read-only') : handle(argv))
  arm()
  await clock.advance(60_000)

  const pressing = ui.press({ key: 'keep:c1' })
  await clock.advance(5_000)
  await pressing

  expect(await texts(ui)).toEqual(['m2b could not keep "Remember? Acme moved": the task list is read-only'])
  await ui.unmount()
})

test('a reload starts exactly one m2b process for the band and the status line', async ($, on) => {
  // Covers: B93
  const fake = new FakeM2b().candidate('c1', 'Remember? Acme moved').question('q1', 'Still current? Porto')
  fake.review('r1', ['lint: broken link in a.md'])
  const { clock, statuses } = await start($, on, fake)
  const before = fake.calls.length

  await clock.advance(60_000)

  expect(fake.calls.slice(before)).toEqual([['band', '--json']])
  expect(statuses.at(-1)).toBe('2 in inbox · curated 18:02')
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await ui.findAll({ type: 'Button' })).toHaveLength(4)
  expect(await texts(ui)).toContain('lint: broken link in a.md')
  await ui.unmount()
})

test('two quick presses on the same candidate write once', async ($, on) => {
  const fake = new FakeM2b().candidate('c1', 'Remember? Acme moved')
  await start($, on, fake)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })

  await Promise.all([ui.press({ key: 'keep:c1' }), ui.press({ key: 'drop:c1' })])

  expect(fake.writes()).toEqual([['tasks', 'complete', 'c1']])
  await ui.unmount()
})

test('a prompt enters as typed and clears the band notice', async ($, on) => {
  on('prompt.submit', (_, e) => ({ text: e.text, context: e.context }))
  const fake = new FakeM2b().candidate('c1', 'Remember? Alex runs on Tuesdays')
  await start($, on, fake)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  fake.beforeCandidateList = () => {
    const task = fake.tasks[0]
    if (task !== undefined) {
      task.completed = true
    }
  }
  await ui.press({ key: 'drop:c1' })
  const notice = 'Already settled in another session, nothing written: Remember? Alex runs on Tuesdays'
  expect(await texts(ui)).toContain(notice)

  const entered = await $.prompt.submit({ text: 'what is on today?', context: ['from another plugin'] })

  expect(entered).toEqual({ text: 'what is on today?', context: ['from another plugin'] })
  expect(await texts(ui)).not.toContain(notice)
  await ui.unmount()
})
