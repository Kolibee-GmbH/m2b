/** The band's test world: a fake `m2b` launcher answered from memory and a session started against it. */
import { expect, mock } from 'claude-code/testing'
import type { Engine, MockClock } from 'claude-code/testing'
import type { On, ProcessRunResult } from 'claude-code'

export const HOME = '/home/alex'
export const NOW = Date.parse('2026-03-14T17:30:00Z')

export const BAND = {
  plugin: 'm2b',
  component: 'AbovePrompt',
  requestId: 'above-prompt',
  props: {
    hasSurvey: false,
    isCollapsed: false,
    isWorking: false,
    maxRows: 20,
    bodyColumns: 100,
    scroll: { offset: 0, bodyRows: 19 },
    view: {},
  },
} as const

export type FakeTask = {
  id: string
  title: string
  notes: string
  completed: boolean
  dropped: boolean
  marker: string
}

export const STATUS = {
  inbox: { count: 2, evicted: 0 },
  run: { state: 'succeeded', last_succeeded_at: '2026-03-14T18:02:00+01:00' },
  backends: { tasks: { state: 'reachable', detail: '' } },
}

/** The `m2b` launcher, answered from memory; every call is recorded. */
export class FakeM2b {
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
  /** The folder the core puts its machine paths under, as it resolves `M2B_HOME`. */
  home = HOME
  /** When set, starting the launcher rejects with this, as a timeout or a launcher that cannot run does. */
  runFails: string | null = null
  /** When set, `$.fs.exists` rejects, as it does for a folder on a network location that does not answer. */
  existsFails = false
  /** What `m2b capture` was handed on standard input, one entry per call. */
  readonly captured: string[] = []
  /** When set, `m2b capture` fails with this as its message. */
  captureFails: string | null = null
  /** The installed core's version, as `m2b band --json` answers it. */
  version = '0.3.0'
  /** The version in the manifest of the plugin the band was loaded from; null when it cannot be read. */
  bandVersion: string | null = '0.3.0'

  get launcher(): string {
    return `${this.home}/.local/bin/m2b`
  }

  get machineConfig(): string {
    return `${this.home}/.config/m2b/config.json`
  }

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

  handle(argv: readonly string[], stdin?: string): ProcessRunResult {
    expect(argv[0]).toBe(this.launcher)
    const args = argv.slice(1)
    this.calls.push(args)
    if (!this.isSetUp) {
      return fail('not set up: no machine config at /home/alex/.config/m2b/config.json')
    }
    if (args[0] === 'band') {
      return this.bandAnswer()
    }
    if (args[0] === 'capture') {
      if (this.captureFails !== null) {
        return fail(this.captureFails)
      }
      this.captured.push(stdin ?? '')
      return ok('/home/alex/Notes/inbox/20260314-173000-claude-ab12.md\n')
    }
    if (this.failure !== null) {
      return fail(this.failure)
    }
    const [, verb, ...rest] = args
    const id = rest[0] === '--' ? rest[1] : rest[0]
    const task = this.tasks.find(open => open.id === id)
    if (task === undefined) {
      return fail(`no task with id ${id}`)
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
    return ok(JSON.stringify({ version: this.version, tasks, status: this.status }))
  }

  writes(): string[][] {
    return this.calls.filter(call => call[0] === 'tasks')
  }
}

export function ok(stdout: string): ProcessRunResult {
  return { exitCode: 0, stdout, stderr: '', isStdoutTruncated: false, isStderrTruncated: false }
}

export function fail(message: string): ProcessRunResult {
  return { exitCode: 1, stdout: '', stderr: `m2b: ${message}\n`, isStdoutTruncated: false, isStderrTruncated: false }
}

/** A slash command the mod registered, as `$.command.register` was handed it. */
export type Registered = { name: string; immediate?: true }

export type World = { clock: MockClock; statuses: (string | undefined)[]; commands: Registered[] }

/** Files under the home folder, shared by the sessions of one test: what `$.fs` reads and writes. */
export type Files = Map<string, string>

export async function start(
  $: Engine,
  on: On,
  fake: FakeM2b,
  env: Record<string, string> = {},
  files?: Files,
): Promise<World> {
  const clock = mock.clock(on, { now: NOW })
  mock.env(on, { HOME, ...env })
  on('fs.exists', (_, e) => {
    if (fake.existsFails) {
      return { deny: `ETIMEDOUT: ${e.path}` }
    }
    return { value: (e.path === fake.launcher && fake.hasLauncher) || (e.path === fake.machineConfig && fake.isSetUp) }
  })
  on('fs.read', (_, e) => {
    if (e.path.endsWith('/.claude-plugin/plugin.json') && fake.bandVersion !== null) {
      return { value: JSON.stringify({ name: 'm2b', version: fake.bandVersion }) }
    }
    const text = files?.get(e.path)
    if (text === undefined) {
      throw new Error(`ENOENT: ${e.path}`)
    }
    return { value: text }
  })
  if (files !== undefined) {
    on('fs.write', (_, e) => {
      files.set(e.path, e.text)
      return { value: undefined }
    })
  }
  const statuses: (string | undefined)[] = []
  const commands: Registered[] = []
  on('command.register', (_, e) => {
    commands.push(e)
    return { value: { command: e.name } }
  })
  on('process.run', async (_, e) => {
    if (fake.runFails !== null) {
      return { deny: fake.runFails }
    }
    const value = fake.handle(e.argv, e.init?.stdin)
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
  return { clock, statuses, commands }
}

export async function texts(ui: { findAll: (q: { type: string }) => Promise<{ text: string }[]> }): Promise<string[]> {
  return (await ui.findAll({ type: 'Text' })).map(found => found.text.trim()).filter(text => text !== '')
}
