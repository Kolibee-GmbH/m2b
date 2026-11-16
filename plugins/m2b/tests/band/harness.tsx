/** The band's test world: a fake `m2b` launcher answered from memory and a session started against it. */
import { expect, mock } from 'claude-code/testing'
import type { Engine, MockClock } from 'claude-code/testing'
import type { EngineResultOf, On, ProcessRunResult } from 'claude-code'

import { tabKey } from '../../hooks/pane-tabs'
import type { Shown, TabId } from '../../hooks/pane-tabs'
import type { BandShows } from '../../types'

export const HOME = '/home/alex'
export const NOW = Date.parse('2026-03-14T17:30:00Z')
export const SESSION_ID = '0f6a3c1e-5b7d-4e2a-9c48-1d2e3f4a5b6c'
/** A machine config in which the owner turned handing in on. */
export const HANDING_IN_ON = JSON.stringify({ version: 1, sessions: { propose: true } })

export const ENGINES_OWN_DRAWING = 'engine'

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

/** A proposal from the sessions as `m2b band --json` names it; `answer` once the person kept or dropped it. */
export type FakeProposal = {
  id: string
  kind: string
  text: string
  quote: string
  day: string
  topic: string | null
  due: string | null
  source?: string
  tool?: string | null
  by?: string | null
  answer?: 'keep' | 'drop'
}

/** A status with nothing wrong, which clears the status line. */
export const STATUS = {
  inbox: { count: 2, evicted: 0 },
  run: { state: 'succeeded', last_succeeded_at: '2026-03-14T18:02:00+01:00' },
  backends: { tasks: { state: 'reachable', detail: '' } },
}

/** A status with something wrong, and what the status line says to it: a line that was written, not cleared. */
export const TROUBLED_STATUS = { ...STATUS, backends: { tasks: { state: 'not reachable', detail: 'no grant' } } }
export const TROUBLE_LINE = 'tasks not reachable'

/** A topic whose facts the core gave a session, with what its block held then. */
export type FakeTopic = { name: string; facts: number | null; current: number | null }

/**
 * What the core noted of a session: its topics, how its start printed the distillate, and where the
 * distillate is off. `folder` is the session's folder as the core names it; a core from before the
 * pane's button names none.
 */
export type FakeGiven = { topics: FakeTopic[]; atStart: string | null; offUnder: string | null; folder?: string }

/** A topic's lines as `m2b distillate topic --json` answers them. */
export type FakeTopicLines = { facts: string[]; current: string[] }

/**
 * The `m2b` launcher, answered from memory; every call is recorded, the looks at what the session
 * was given apart from the rest, in `looks`.
 */
export class FakeM2b {
  readonly calls: string[][] = []
  /** The calls that asked what the session was given, which every session makes for itself. */
  readonly looks: string[][] = []
  /** The folder each of those calls was started in, as the mod named it; undefined where it named none. */
  readonly lookFolders: (string | undefined)[] = []
  /** The project folder each of those calls was handed in `CLAUDE_PROJECT_DIR`; undefined where it was handed none. */
  readonly lookProjects: (string | undefined)[] = []
  /** The session's project root, as the engine names it; null when it cannot say. */
  root: string | null = '/home/alex/code/lumen'
  /** What the core noted of the session that asks; null as for a session it holds no note of. */
  given: FakeGiven | null = { topics: [], atStart: 'whole', offUnder: null }
  /** When set, the session part of the answer is this instead, whatever its shape. */
  sessionPart: unknown = undefined
  /** When set, the look at what the session was given fails with this as its message. */
  lookFails: string | null = null
  /** Unset, the installed core is one from before sessions: it refuses the options as an unknown argument. */
  knowsSessions = true
  /** When set, `m2b distillate off` and `on` fail with this as their message, and nothing is turned. */
  distillateFails: string | null = null
  /** The topics the distillate holds now, by name, as `m2b distillate topic` reads them. */
  topicLines: Record<string, FakeTopicLines> = {}
  /** When set, `m2b distillate topic` ends as for a store it cannot read, with this as its message. */
  topicFails: string | null = null
  /** Unset, the installed core is one from before `distillate topic`: it refuses the action. */
  knowsTopics = true
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
  /** Set, another plugin's pane is the one the surface shows, and m2b's is a tab behind it. */
  isPaneBehind = false
  /** When set, Claude Code cannot list the open panes, with this as the reason. */
  panesFail: string | null = null
  /** When set, Claude Code refuses to open a pane, with this as the reason. */
  openFails: string | null = null
  /** Set, a hook beneath the mod keeps the pane open when it is asked to close. */
  isCloseHeld = false
  /** Set, `m2b search`'s answer is cut as `$.process.run` cuts one past 4 MiB. */
  searchCut = false
  /** When set, `m2b search` fails with this as its message. */
  searchFails: string | null = null
  /**
   * The machine's `band` settings as `m2b band --json` names them: how the band shows the tasks
   * due, and whether it counts the topics. Null as a core before these settings answers: no `band`
   * part, and the tasks due under `due` alone.
   */
  shows: BandShows | null = { dueTasks: 'count', topics: false }
  /**
   * The tasks due today or overdue. `m2b band --json` names them under `due_by_today` whatever the
   * band shows, and under `due` too while it lists them. Null where the answer names none under
   * either key, as a core before the `band` settings answers with `band.due_tasks` off.
   */
  dueTasks: { id: string; title: string; due: string; overdue: boolean }[] | null = []
  /** The changes of the facts `m2b band --json` names for an open review; null as a core before 0.3.3 answers. */
  reviewDetails: { changes: unknown[]; copies: unknown[]; paragraphs: string[] } | null = null
  /** Set, a toast is refused, as while the session closes. */
  toastFails = false
  /** What a reading of the sessions proposed; null as a core that does not know proposals answers. */
  proposals: FakeProposal[] | null = []
  /** When set, the proposals part of the band's answer is this error, as with answers that are not downloaded. */
  proposalsError: string | null = null
  /** When set, the proposals part is this instead, whatever its shape. */
  proposalsPart: unknown = undefined
  /** When set, starting `m2b proposals keep` or `drop` fails with this, before anything is answered. */
  answerFails: string | null = null
  /** What the machine config holds, as `$.fs.read` gives it; null as a file that cannot be read. */
  machineConfigText: string | null = null
  /** The id of this session, as the engine names it; null when it cannot say. */
  sessionId: string | null = SESSION_ID
  /** The mod's own store, which outlives a session: what an earlier one kept, and what this one keeps. */
  stored: Record<string, unknown> = {}
  /** What `m2b proposals add` was handed on standard input, one entry per call. */
  readonly handedIn: string[] = []
  /** How `m2b proposals add` ends. */
  handInAnswer: ProcessRunResult = ok('handed in; go on with the task\n')
  /**
   * How `m2b settings` and `m2b settings set` end, by the words after `settings` and the variables
   * the call was handed. Unset, the
   * installed core is one from before the command: it refuses it as an unknown choice.
   */
  onSettings: ((args: readonly string[], env?: Record<string, string>) => ProcessRunResult) | null = null
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

  proposal(id: string, text: string, quote = text, fields: Partial<FakeProposal> = {}): this {
    const proposed = { id, kind: 'person', text, quote, day: '2026-03-12', topic: null, due: null, ...fields }
    this.proposals = [...(this.proposals ?? []), proposed]
    return this
  }

  /** As `m2b proposals keep` and `drop`: an unknown id answers nothing, another answer than the one that stands ends with exit 1. */
  answer(verb: string | undefined, ids: string[]): ProcessRunResult {
    if (this.answerFails !== null) {
      return fail(this.answerFails)
    }
    const known = this.proposals ?? []
    const unknown = ids.filter(id => !known.some(proposed => proposed.id === id))
    if ((verb !== 'keep' && verb !== 'drop') || unknown.length > 0) {
      return fail(`no proposal has the id ${unknown.join(', ')}; m2b proposals lists those that wait`)
    }
    const standing: string[] = []
    for (const proposed of known.filter(one => ids.includes(one.id))) {
      if (proposed.answer !== undefined && proposed.answer !== verb) {
        standing.push(`m2b: ${proposed.id} is answered with ${proposed.answer} already; that answer stands`)
      }
      proposed.answer ??= verb
    }
    return standing.length === 0 ? ok('') : { ...fail(''), stderr: `${standing.join('\n')}\n` }
  }

  handle(argv: readonly string[], stdin?: string, cwd?: string, env?: Record<string, string>): ProcessRunResult {
    expect(argv[0]).toBe(this.launcher)
    const args = argv.slice(1)
    if (args[0] === 'band' && args.includes('--session-only')) {
      this.looks.push(args)
      this.lookFolders.push(cwd)
      this.lookProjects.push(env?.['CLAUDE_PROJECT_DIR'])
      return this.isSetUp ? this.sessionAnswer(args) : fail(NOT_SET_UP)
    }
    this.calls.push(args)
    if (!this.isSetUp) {
      return fail(NOT_SET_UP)
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
    if (args[0] === 'proposals' && args[1] === 'add') {
      this.handedIn.push(stdin ?? '')
      return this.handInAnswer
    }
    if (args[0] === 'proposals') {
      return this.answer(args[1], args.slice(2))
    }
    if (args[0] === 'distillate' && args[1] === 'topic') {
      return this.topicAnswer(args.at(-1) ?? '')
    }
    if (args[0] === 'settings') {
      const stderr = "usage: m2b [-h] [--version]\nm2b: error: argument command: invalid choice: 'settings'\n"
      return this.onSettings === null ? { ...fail(''), exitCode: 2, stderr } : this.onSettings(args.slice(1), env)
    }
    if (args[0] === 'distillate') {
      if (this.distillateFails !== null) {
        return fail(this.distillateFails)
      }
      // As the core: off under the folder it was handed, on again for that folder.
      this.given = this.given === null ? null : { ...this.given, offUnder: args[1] === 'off' ? (args.at(-1) ?? null) : null }
      return ok('')
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

  /** As `m2b distillate topic --json -- <name>` answers: the topic's lines, or that the distillate holds none of the name. */
  topicAnswer(name: string): ProcessRunResult {
    if (!this.knowsTopics) {
      const stderr = "usage: m2b distillate [-h] {off,on} ...\nm2b distillate: error: argument action: invalid choice: 'topic'\n"
      return { ...fail(''), exitCode: 2, stderr }
    }
    if (this.topicFails !== null) {
      return { ...fail(this.topicFails), exitCode: 3 }
    }
    const held = this.topicLines[name]
    return ok(JSON.stringify({ name, found: held !== undefined, facts: held?.facts ?? [], current: held?.current ?? [] }))
  }

  /** The calls that turned the distillate off or on for a folder. */
  folderCalls(): string[][] {
    return this.calls.filter(call => call[0] === 'distillate' && call[1] !== 'topic')
  }

  /** The calls that read a topic's lines. */
  topicCalls(): string[][] {
    return this.calls.filter(call => call[0] === 'distillate' && call[1] === 'topic')
  }

  /** As `m2b band --json --session <id> --session-only` answers: the version and what the session was given. */
  sessionAnswer(args: readonly string[]): ProcessRunResult {
    if (!this.knowsSessions) {
      // As argparse refuses: its usage first, the reason on the line below.
      const stderr = 'usage: m2b [-h] [--version]\nm2b: error: unrecognized arguments: --session-only\n'
      return { ...fail(''), exitCode: 2, stderr }
    }
    if (this.lookFails !== null) {
      return fail(this.lookFails)
    }
    const id = args[args.indexOf('--session') + 1]
    const noted = this.given
    const session = this.sessionPart ?? {
      id,
      known: noted !== null,
      topics: noted?.topics ?? [],
      distillate: {
        at_start: noted?.atStart ?? null,
        off_under: noted?.offUnder ?? null,
        ...(noted?.folder === undefined ? {} : { folder: noted.folder }),
      },
    }
    return ok(JSON.stringify({ version: this.version, session }))
  }

  /** The tasks due as the tasks part names them: by the key of the core that answers, and by what the band shows. */
  duePart(): Record<string, unknown> {
    if (this.dueTasks === null) {
      return {}
    }
    const due = this.dueTasks.map(task => ({ ...task, notes: '', completed: false, dropped: false, marker: null }))
    if (this.shows === null) {
      return { due }
    }
    return { due_by_today: due, ...(this.shows.dueTasks === 'list' ? { due } : {}) }
  }

  /** As `m2b band --json` answers: the band's settings, the open curator tasks by marker, or the error, and the status. */
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
      ? 'not set up: no store.json in the store /home/alex/Notes. Run /m2b:m2b setup in Claude Code; without Claude Code, m2b setup apply (https://github.com/Kolibee-GmbH/m2b/blob/main/docs/getting-started.md).'
      : this.failure
    const tasks =
      error === null
        ? {
            candidates: open('candidate'),
            questions: open('current'),
            reviews: open('review'),
            ...this.duePart(),
            ...(this.reviewDetails !== null && open('review').length > 0 ? { review: this.reviewDetails } : {}),
          }
        : { error }
    const proposals = this.proposalsPart ?? this.waitingProposals()
    const band = this.shows === null ? {} : { band: { due_tasks: this.shows.dueTasks, topics: this.shows.topics } }
    return ok(JSON.stringify({ version: this.version, ...band, tasks, ...(proposals === null ? {} : { proposals }), status: this.status }))
  }

  waitingProposals(): unknown {
    if (this.proposalsError !== null) {
      return { error: this.proposalsError }
    }
    if (this.proposals === null) {
      return null
    }
    const waiting = this.proposals.filter(proposed => proposed.answer === undefined)
    return {
      proposals: waiting.map(({ answer: _, ...fields }) => fields),
      answered: this.proposals.length - waiting.length,
    }
  }

  /** The calls that listed the settings or changed one. */
  settingCalls(): string[][] {
    return this.calls.filter(call => call[0] === 'settings')
  }

  /** The calls that answered proposals. */
  answers(): string[][] {
    return this.calls.filter(call => call[0] === 'proposals' && call[1] !== 'add')
  }

  writes(): string[][] {
    return this.calls.filter(call => call[0] === 'tasks')
  }
}

const NOT_SET_UP = 'not set up: no machine config at /home/alex/.config/m2b/config.json'

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

/** A pane the mod asked to open, with the manners it asked for. */
export type Opened = { id: string; title?: string; focus?: true; closeOnEscape?: true }

export type World = {
  toasts: string[]
  clock: MockClock
  statuses: (string | undefined)[]
  commands: Registered[]
  tools: RegisteredTool[]
  opened: Opened[]
  /** The ids of the panes that are open now: opened, and not closed since. */
  openPanes: Set<string>
}

/** The pane as Claude Code hands it to the render hook, at a width and in a seat the test chooses. */
export function pane(id: string, bodyColumns = 80, placement: 'dock' | 'inline' | 'widget' = 'dock') {
  return {
    plugin: 'm2b',
    component: 'Pane',
    requestId: id,
    props: {
      title: id,
      isFocused: false,
      bodyColumns,
      placement,
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
  on('store.get', (_, e) => ({ value: fake.stored[e.key] }))
  on('store.set', (_, e) => {
    fake.stored[e.key] = e.value
    return { value: undefined }
  })
  on('store.delete', (_, e) => {
    delete fake.stored[e.key]
    return { value: undefined }
  })
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
    if (e.path === fake.machineConfig && fake.machineConfigText !== null) {
      return { value: fake.machineConfigText }
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
  const openPanes = new Set<string>()
  // Reached only by a close no hook of the mod answered for: the pane is gone then.
  on('ui.close', (_, e) => {
    if (!fake.isCloseHeld) {
      openPanes.delete(e.id)
    }
    return { value: undefined }
  })
  on('ui.panes', () => {
    if (fake.panesFail !== null) {
      return { deny: fake.panesFail }
    }
    return {
      value: [...openPanes].map(id => ({
        id,
        title: id,
        isShown: !fake.isPaneBehind,
        isFocused: false,
        isPlaced: fake.paneWaits === null,
      })),
    }
  })
  const toasts: string[] = []
  on('ui.toast', (_, e) => {
    if (fake.toastFails) {
      return { deny: 'the session is closing' }
    }
    toasts.push(e.text)
    return { value: undefined }
  })
  on('ui.open', (_, e) => {
    if (fake.openFails !== null) {
      return { deny: fake.openFails }
    }
    opened.push(e)
    openPanes.add(e.id)
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
    const value = fake.handle(e.argv, e.init?.stdin, e.init?.cwd, e.init?.env)
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
  on('session.id', () => (fake.sessionId === null ? { deny: 'the session has no id yet' } : { value: fake.sessionId }))
  on('session.root', () => (fake.root === null ? { deny: 'the session has no root' } : { value: fake.root }))
  on('turn.complete', (_, e) => ({ text: e.answer }))
  on('session.end', (_, e) => ({ sessionId: e.sessionId }))
  // A compaction asked to `skip` is one a hook blocked: the conversation stays as it is.
  on('session.compact', (_, e) => (e.instructions === 'skip' ? { skip: 'a hook blocked it' } : { messages: e.messages }))
  // Stands for the engine's own drawing, which is what the band leaves to when it has nothing to show.
  on('ui.render', ($, e) => {
    const { Text } = $.ui.resolve(e)
    return <Text>{ENGINES_OWN_DRAWING}</Text>
  })
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await clock.advance(1)
  return { clock, statuses, commands, tools, opened, toasts, openPanes }
}

/** An element inside a drawing, as the kit hands it on: its tag, its props and what it holds. */
type Element = { type: string; props: Record<string, unknown>; children?: unknown[] }

/** An element a drawing was asked for: its tag, its key, its props, the text it shows and what it holds. */
type Found = { type: string; key: string | undefined; props: Record<string, unknown>; text: string; children: unknown[] }

/** A drawing of the band or of the pane, as far as these helpers read it. */
type Drawn = {
  find: (q: { key: string }) => Promise<Found | undefined>
  findAll: (q: { type?: string; text?: string }) => Promise<Found[]>
}

function isElement(value: unknown): value is Element {
  return typeof value === 'object' && value !== null && 'type' in value && 'props' in value
}

function elementsIn(children: unknown[] | undefined, type?: string): Element[] {
  return (children ?? []).filter(isElement).filter(child => type === undefined || child.type === type)
}

/** The text an element shows: its own strings and those of the texts inside it, in the order drawn. */
function shownText(element: Element): string {
  return (element.children ?? []).map(child => (isElement(child) ? shownText(child) : String(child))).join('')
}

/** The key of the band's row, of the tasks listed below it, and of its one button. */
const BAND_ROW = 'row:m2b'
const BAND_TASKS = 'tasks'
export const OPEN = 'open'

/** The line of the band's row: the one text that is cut where the row is too narrow, with its pieces inside. */
async function bandLineOf(ui: Drawn): Promise<{ texts: Element[]; line: Element | undefined } | null> {
  const row = await ui.find({ key: BAND_ROW })
  if (row === undefined) {
    return null
  }
  const texts = elementsIn(row.children, 'Text')
  return { texts, line: texts.find(text => text.props['wrap'] === 'truncate-end') }
}

/**
 * The band as m2b drew it. `isNamed`: `m2b` stands before the row as a text of its own. `says`:
 * the row's pieces as the one line they are drawn in. `below`: the lines under the row, a task as
 * its word and its title. `buttons`: the keys of every button of the band.
 */
export type ShownBand = { isNamed: boolean; says: string; below: string[]; buttons: (string | undefined)[] }

/** The band's row and what stands below it; null where m2b drew no band. */
export async function shownBand(ui: Drawn): Promise<ShownBand | null> {
  const row = await bandLineOf(ui)
  if (row === null) {
    return null
  }
  const below = elementsIn((await ui.find({ key: BAND_TASKS }))?.children)
  return {
    isNamed: row.texts.some(text => text !== row.line && shownText(text) === 'm2b'),
    says: row.line === undefined ? '' : shownText(row.line),
    below: below.map(under =>
      under.type === 'Box'
        ? elementsIn(under.children, 'Text')
            .map(text => shownText(text).trim())
            .join(' ')
        : shownText(under),
    ),
    buttons: (await ui.findAll({ type: 'Button' })).map(button => button.key),
  }
}

/** A band of one row: what it says after `m2b`, and `open`. */
export function rowSaying(says: string): ShownBand {
  return { isNamed: true, says, below: [], buttons: [OPEN] }
}

/** A band whose row is a sentence that names m2b itself, so no `m2b` stands before it. */
export function sentenceOfM2b(says: string): ShownBand {
  return { isNamed: false, says, below: [], buttons: [OPEN] }
}

/** A piece of text in the band with the props it is drawn by. */
export type BandPiece = { text: string; color: unknown; dimColor: unknown }

function pieceOf(text: Element): BandPiece {
  return { text: shownText(text), color: text.props['color'], dimColor: text.props['dimColor'] }
}

/** The pieces of the band's row in the order drawn, each with its color and whether it is dimmed. */
export async function bandPieces(ui: Drawn): Promise<BandPiece[]> {
  return elementsIn((await bandLineOf(ui))?.line?.children, 'Text').map(pieceOf)
}

/** The two texts of a task listed below the band's row: when it is due, as wide as drawn, and its title. */
export async function listedTask(ui: Drawn, id: string): Promise<{ due: BandPiece; title: BandPiece & { wrap: unknown } } | null> {
  const [due, title] = elementsIn((await ui.find({ key: `task:${id}` }))?.children, 'Text')
  return due === undefined || title === undefined ? null : { due: pieceOf(due), title: { ...pieceOf(title), wrap: title.props['wrap'] } }
}

/** The view the pane starts in, drawn beside the chat: every row that is answered stands there with its buttons. */
export function startView($: Engine, surface: 'terminal' | 'desktop' = 'terminal') {
  return $.ui.mount({ ...pane('m2b'), surface })
}

const ANSWERS = /^(keep|drop|undo|ok):/

/** The keys of the buttons that answer a row: keep, drop, ok and undo, without those that turn the pane. */
export async function answerKeys(ui: { findAll: (q: { type: string }) => Promise<{ key?: string | undefined }[]> }): Promise<string[]> {
  return (await ui.findAll({ type: 'Button' })).map(button => button.key ?? '').filter(key => ANSWERS.test(key))
}

/** The key of the box that holds the pane's row of tabs. */
const TABS = 'tabs'
const TAB_IDS: readonly TabId[] = ['overview', 'proposals', 'review', 'settings']

/**
 * A tab of the pane's row as drawn: its label, and the key of its button; `key` is null for the
 * tab whose view is shown, which is a text and no button.
 */
export type ShownTab = { label: string; key: string | null }

/** The pane's row of tabs in the order drawn; empty where the pane draws none. */
export async function shownTabs(ui: Drawn): Promise<ShownTab[]> {
  return elementsIn((await ui.find({ key: TABS }))?.children).map(tab => {
    if (tab.type === 'Button') {
      return { label: String(tab.props['label']), key: String(tab.props['key']) }
    }
    if (tab.type !== 'Text') {
      throw new Error(`the row of tabs holds a ${tab.type}`)
    }
    return { label: shownText(tab), key: null }
  })
}

/** Which tab the row marks as the one shown: one of the four by its place, or the fifth beside them. */
export async function shownTab(ui: Drawn): Promise<Shown> {
  const at = (await shownTabs(ui)).findIndex(tab => tab.key === null)
  if (at === -1) {
    throw new Error('the pane marks no tab as the one shown')
  }
  return TAB_IDS[at] ?? 'aside'
}

/** Presses the tab that turns the pane to `to`, under the key it has above the view drawn now. */
export async function pressTab(ui: Drawn & { press: (target: { key: string }) => Promise<unknown> }, to: TabId): Promise<void> {
  await ui.press({ key: tabKey(to, await shownTab(ui)) })
}

/**
 * What the pane's view draws of the given tags, in the order drawn: everything but the row of
 * tabs above it. The row is the first thing the pane draws, which is checked here.
 */
export async function inView(ui: Drawn, ...types: string[]): Promise<Found[]> {
  const drawn = (await ui.findAll({})).filter(found => types.includes(found.type))
  const inRow = elementsIn((await ui.find({ key: TABS }))?.children).filter(tab => types.includes(tab.type))
  expect(drawn.slice(0, inRow.length).map(found => found.key ?? found.text)).toEqual(
    inRow.map(tab => (tab.type === 'Button' ? String(tab.props['key']) : shownText(tab))),
  )
  return drawn.slice(inRow.length)
}

/** The keys of the buttons of the pane's view, without the tabs above it. */
export async function viewButtons(ui: Drawn): Promise<string[]> {
  return (await inView(ui, 'Button')).map(button => button.key ?? '')
}

/**
 * The texts m2b drew, without the engine's own drawing and without the pane's row of tabs, which
 * `shownTabs` reads. Whether the engine draws beside a band that shows something depends on the
 * Claude Code version: up to 2.1.322 the band stands in its place, from 2.1.323 the engine draws
 * below it.
 */
export async function texts(ui: Drawn): Promise<string[]> {
  return (await inView(ui, 'Text')).map(found => found.text.trim()).filter(text => text !== '' && text !== ENGINES_OWN_DRAWING)
}

/** Every text on the surface, the engine's own drawing included: `[ENGINES_OWN_DRAWING]` when m2b drew nothing. */
export async function everyText(ui: Drawn): Promise<string[]> {
  return (await ui.findAll({ type: 'Text' })).map(found => found.text.trim()).filter(text => text !== '')
}

/**
 * What an element draws, as the lines it stands on: a text is a line, a button its label in
 * brackets, a row its pieces side by side, a column the lines of what it holds. A text padded to a
 * column of its own is read without the padding.
 */
function linesOf(element: Element): string[] {
  if (element.type === 'Text') {
    return [shownText(element).trim()]
  }
  if (element.type === 'Button') {
    return [`[${String(element.props['label'])}]`]
  }
  const inside = elementsIn(element.children).flatMap(linesOf)
  if (element.props['flexDirection'] !== 'row') {
    return inside
  }
  return [inside.join(Number(element.props['columnGap'] ?? 0) > 0 ? ' ' : '')]
}

/** Every element of a tag under an element, itself included, in the order drawn. */
function allIn(element: Element, type: string): Element[] {
  const inside = elementsIn(element.children).flatMap(child => allIn(child, type))
  return element.type === type ? [element, ...inside] : inside
}

/** The lines of the element drawn under `key`, read as `linesOf` reads them; null where the drawing holds none. */
export async function linesAt(ui: Drawn, key: string): Promise<string[] | null> {
  const found = await ui.find({ key })
  return found === undefined ? null : linesOf(found)
}

/** The title of each part of the overview, by the key the part is drawn under. */
export const PARTS = { waits: 'Waits for you', today: 'Today', session: 'This session', m2b: 'm2b' } as const
export type PartKey = keyof typeof PARTS

const PART_KEY = /^part:/

/**
 * A part of the overview as drawn: its key without `part:`, its title, the count at the end of the
 * title's line, null where there is none, and the lines below.
 */
export type ShownPart = { key: string; title: string; count: string | null; lines: string[] }

function shownPart(part: Found): ShownPart {
  const [heading, ...body] = elementsIn(part.children)
  const [title, count] = elementsIn(heading?.children, 'Text')
  return {
    key: (part.key ?? '').replace(PART_KEY, ''),
    title: title === undefined ? '' : shownText(title),
    count: count === undefined ? null : shownText(count),
    lines: body.flatMap(linesOf),
  }
}

/** The parts of the overview in the order drawn; empty where the pane shows another view. */
export async function shownParts(ui: Drawn): Promise<ShownPart[]> {
  return (await ui.findAll({ type: 'Box' })).filter(box => PART_KEY.test(box.key ?? '')).map(shownPart)
}

/** The lines of one part of the overview, below its title; null where the part is left out. */
export async function partLines(ui: Drawn, key: PartKey): Promise<string[] | null> {
  const part = await ui.find({ key: `part:${key}` })
  return part === undefined ? null : shownPart(part).lines
}

/**
 * How a part is framed and headed: the style, color and padding of its frame, the color and weight
 * of its title, and the color of its count, undefined where it has none.
 */
export type PartLook = {
  borderStyle: unknown
  borderColor: unknown
  paddingX: unknown
  titleColor: unknown
  titleWeight: unknown
  countColor: unknown
}

export async function partLook(ui: Drawn, key: PartKey): Promise<PartLook | null> {
  const part = await ui.find({ key: `part:${key}` })
  if (part === undefined) {
    return null
  }
  const [heading] = elementsIn(part.children)
  const [title, count] = elementsIn(heading?.children, 'Text')
  return {
    borderStyle: part.props['borderStyle'],
    borderColor: part.props['borderColor'],
    paddingX: part.props['paddingX'],
    titleColor: title?.props['color'],
    titleWeight: title?.props['weight'],
    countColor: count?.props['color'],
  }
}

/** How a text is drawn: its color, whether it is dimmed, and how it wraps. */
export type TextLook = { color: unknown; dimColor: unknown; wrap: unknown }

/** How the text that reads exactly `text` is drawn, the first where several do; null where none does. */
export async function lookOf(ui: Drawn, text: string): Promise<TextLook | null> {
  const found = (await ui.findAll({ type: 'Text', text })).find(one => one.text.trim() === text)
  return found === undefined ? null : { color: found.props['color'], dimColor: found.props['dimColor'], wrap: found.props['wrap'] }
}

/** A button as drawn: its key, its label, and what marks it as the one accent of its row or as one beside the point. */
export type ShownButton = { key: string; label: string; variant: unknown; dimColor: unknown }

/** The buttons of the element drawn under `key`, in the order drawn; empty where the drawing holds none. */
export async function buttonsAt(ui: Drawn, key: string): Promise<ShownButton[]> {
  const found = await ui.find({ key })
  return (found === undefined ? [] : allIn(found, 'Button')).map(button => ({
    key: String(button.props['key']),
    label: String(button.props['label']),
    variant: button.props['variant'],
    dimColor: button.props['dimColor'],
  }))
}

/**
 * The pieces of the path drawn inside the element under `key`, in the order drawn: the path is a
 * row that breaks between its pieces and nowhere else.
 */
export async function pathPieces(ui: Drawn, key: string): Promise<string[]> {
  const found = await ui.find({ key })
  const path = found === undefined ? undefined : allIn(found, 'Box').find(box => box.props['flexWrap'] === 'wrap')
  return elementsIn(path?.children, 'Text').map(shownText)
}
