/** The band's test world: a fake `m2b` launcher answered from memory and a session started against it. */
import { expect, mock } from 'claude-code/testing'
import type { Engine, MockClock } from 'claude-code/testing'
import type { EngineResultOf, On, ProcessRunResult } from 'claude-code'

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
  /** What `m2b capture` reports on standard error beside a saved note, as a follow-up that waits for the next run. */
  captureNotice: string | null = null
  /** What `m2b capture` was called with besides the text, one entry per call. */
  readonly captureArgs: string[][] = []
  /** The exit code of a failing `m2b capture`. */
  captureExit = 1
  /** The verdict Claude Code's own permission decision reaches for a call of a tool of the mod. */
  coreVerdict: EngineResultOf['tool.check'] = { decision: 'ask' }
  /** Its verdict for the skill's Bash command, which the mod asks about. */
  shellVerdict: EngineResultOf['tool.check'] = { decision: 'ask' }
  /** The Bash commands the mod asked Claude Code's verdict on. */
  readonly shellQuestions: string[] = []
  /** What `m2b search --json` answers: its hits, and the files it could not read. */
  searchHits: { path: string; line: number; text: string }[] = []
  searchEvicted: string[] = []
  searchUnreadable: { path: string; reason: string }[] = []
  /** When set, the surface leaves a pane undrawn, with this as the reason. */
  paneWaits: string | null = null
  /** Set, `m2b search`'s answer is cut as `$.process.run` cuts one past 4 MiB. */
  searchCut = false
  /** When set, `m2b search` fails with this as its message. */
  searchFails: string | null = null
  /** The tasks due today or overdue as `m2b band --json` answers them; null when `band.due_tasks` is off. */
  dueTasks: { id: string; title: string; due: string; overdue: boolean }[] | null = []
  /** Set, a toast is refused, as while the session closes. */
  toastFails = false
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
    if (args[0] === 'search') {
      if (this.searchFails !== null) {
        return fail(this.searchFails)
      }
      const evicted = this.searchEvicted.map(path => ({ path, fetch: `m2b fetch ${path}` }))
      const answer = JSON.stringify({ terms: [args.at(-1)], hits: this.searchHits, evicted, unreadable: this.searchUnreadable })
      return this.searchCut ? { ...ok(answer.slice(0, 40)), isStdoutTruncated: true } : ok(answer)
    }
    if (args[0] === 'capture') {
      if (this.captureFails !== null) {
        return { ...fail(this.captureFails), exitCode: this.captureExit }
      }
      this.captured.push(stdin ?? '')
      this.captureArgs.push(args)
      const path = 'inbox/20260314-173000-claude-ab12.md'
      const dayAt = args.indexOf('--follow-up')
      const followUp = dayAt === -1 ? null : (args[dayAt + 1] ?? null)
      const stdout = args.includes('--json')
        ? // As the core answers: `follow_up` only for a follow-up that waits, once its task is made only `task_id`.
          JSON.stringify(
            followUp === null
              ? { path, task_id: null, follow_up: null }
              : this.captureNotice === null
                ? { path, task_id: 'T-7', follow_up: null }
                : { path, task_id: null, follow_up: followUp },
          )
        : `/home/alex/Notes/${path}`
      const result = ok(`${stdout}\n`)
      return this.captureNotice === null ? result : { ...result, stderr: `m2b: ${this.captureNotice}\n` }
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
        ? {
            candidates: open('candidate'),
            questions: open('current'),
            reviews: open('review'),
            ...(this.dueTasks === null ? {} : { due: this.dueTasks.map(task => ({ ...task, notes: '', completed: false, dropped: false, marker: null })) }),
          }
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

/** A tool the mod registered for the model, as `$.tool.register` was handed it. */
export type RegisteredTool = { name: string; description: string; inputSchema: Record<string, unknown>; isDeferred?: boolean }

/** A pane the mod asked to open, and whether the surface placed it. */
export type Opened = { id: string; title?: string }

export type World = {
  toasts: string[]
  clock: MockClock
  statuses: (string | undefined)[]
  commands: Registered[]
  tools: RegisteredTool[]
  opened: Opened[]
}

/** The pane as Claude Code hands it to the render hook, at a width the test chooses. */
export function pane(id: string, bodyColumns = 80) {
  return {
    plugin: 'm2b',
    component: 'Pane',
    requestId: id,
    props: {
      title: id,
      isFocused: false,
      bodyColumns,
      placement: 'dock',
      scroll: { offset: 0, bodyRows: 40 },
      view: {},
    },
  } as const
}

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
  const opened: Opened[] = []
  on('ui.close', () => ({ value: undefined }))
  const toasts: string[] = []
  on('ui.toast', (_, e) => {
    if (fake.toastFails) {
      return { deny: 'the session is closing' }
    }
    toasts.push(e.text)
    return { value: undefined }
  })
  on('ui.open', (_, e) => {
    opened.push(e)
    return fake.paneWaits === null
      ? { value: { isPlaced: true } }
      : { value: { isPlaced: false, reason: fake.paneWaits } }
  })
  on('command.register', (_, e) => {
    commands.push(e)
    return { value: { command: e.name } }
  })
  const tools: RegisteredTool[] = []
  on('tool.register', (_, e) => {
    tools.push(e)
    return { value: { tool: `mcp__m2b__${e.name}` } }
  })
  // Stands for Claude Code's own permission decision, which the kit does not have.
  on('tool.check', (_, e) => {
    if (e.tool !== 'Bash') {
      return fake.coreVerdict
    }
    fake.shellQuestions.push(String((e.input as { command?: unknown }).command))
    return fake.shellVerdict
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
  return { clock, statuses, commands, tools, opened, toasts }
}

export async function texts(ui: { findAll: (q: { type: string }) => Promise<{ text: string }[]> }): Promise<string[]> {
  return (await ui.findAll({ type: 'Text' })).map(found => found.text.trim()).filter(text => text !== '')
}
