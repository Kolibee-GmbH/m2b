import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register, ResolveInput, Timer } from 'claude-code'

import type {
  BandCandidate,
  BandDueTask,
  BandHealth,
  BandPress,
  BandProposal,
  BandProposals,
  BandReview,
  BandRun,
  BandSession,
  BandSettle,
  BandShows,
  BandSnapshot,
  CurateRefusal,
  FolderSwitch,
  PaneView,
} from '../types'
import { bandLine, bandRow, belowPrompt, hintRow, standsBelow, topicsGiven } from './band'
import type { BandModel } from './band'
import { tabRow } from './look'
import { launcherPath, m2bHome, machineConfigPath, runM2b } from './m2b'
import { timeOrDay } from './moment'
import { NOTE_COMMAND, note } from './note'
import { isInOwnWords, isOwnPrompt, withPrompt } from './own-words'
import {
  AS_A_DIALOG,
  PANE_ID,
  PANE_TITLE,
  REVIEW_COMMAND,
  SEARCH_COMMAND,
  isRun,
  reviewLines,
  reviewPane,
  runOf,
  searchLines,
  searchPane,
  searchPlaced,
  searchStore,
  searchRequest,
  searchSummary,
  showPane,
} from './pane'
import { CLOSED_BY_HAND, closeAnswer, docksFor, staysBesideChat } from './pane-seat'
import { focusKeyAfterTab, paneTabs, tabKeyAfterTurn } from './pane-tabs'
import type { TabId } from './pane-tabs'
import { plainLine, wholePath } from './plain-text'
import {
  askCoreAgain,
  beginLook,
  countNote,
  forgetSession,
  givenTo,
  lookAtSession,
  lookFailed,
  notesOf,
  sessionIdOf,
} from './session'
import {
  CURATE_PRESS,
  FOLDER_PRESS,
  UNDO_CURATE,
  SESSION_COMMAND,
  UNDO_FOLDER,
  SESSION_PLACED,
  glancePane,
  sessionLines,
  sessionPane,
} from './session-view'
import type { SessionActions, SessionModel } from './session-view'
import {
  KEEP_ALL,
  PROPOSALS_COMMAND,
  PROPOSALS_PLACED,
  UNDO_ALL,
  isProposals,
  refusedLine,
  parseProposals,
  pressKey,
  proposalLines,
  proposalsPane,
} from './proposals'
import type { ProposalActions } from './proposals'
import { REVIEW, undoKey } from './rows'
import type { RowActions } from './rows'
import { shared } from './shared-cache'
import { COULD_NOT_LOOK, NOT_KNOWN, curatingMachineOf, healthOf, noRunStarted, parseRunStart, statusLine, whileCurating } from './status-line'
import type { RunStart } from './status-line'
import { parseBandShows, parseBandTasks } from './tasks'
import {
  SETTINGS_COMMAND,
  SETTINGS_IN_A_TERMINAL,
  SETTINGS_PLACED,
  SETTINGS_UNDO,
  askSettings,
  beginChange,
  beginSettings,
  dropWaitingChange,
  endChange,
  fillSettings,
  foldedTitle,
  forgetSettingsUnless,
  heldSettings,
  openSettings,
  readSettings,
  restKey,
  settingsPane,
  startWriting,
  undoChange,
  waits,
} from './settings'
import type { SettingsActions } from './settings'
import { beginTopic, fillTopic, forgetTopicUnless, heldTopic, readTopic, topicPane } from './topic'
import {
  NOTE_COMMAND_LINE,
  NOTE_TOOL,
  NOTE_TOOL_NAME,
  NOT_HANDED_IN,
  ONLY_THE_MAIN_CONVERSATION,
  PROPOSE_COMMAND_LINE,
  PROPOSE_TOOL,
  PROPOSE_TOOL_NAME,
  SEARCH_TOOL,
  SEARCH_TOOL_NAME,
  isHandingInOn,
  noteTextOf,
  noteTool,
  proposeTool,
  searchCommandLineOf,
  searchTool,
  verdictFor,
} from './tools'

const snapshotAtom = atom({ plugin: 'm2b', key: 'bandSnapshot' } as const, null)
const noticeAtom = atom({ plugin: 'm2b', key: 'bandNotice' } as const, null)
const rowNoticeAtom = atom({ plugin: 'm2b', key: 'rowNotice' } as const, null)
const healthAtom = atom({ plugin: 'm2b', key: 'bandHealth' } as const, null)
const pressesAtom = atom({ plugin: 'm2b', key: 'bandPresses' } as const, {})
const versionNoticeAtom = atom({ plugin: 'm2b', key: 'bandVersionNotice' } as const, null)
const runAtom = atom({ plugin: 'm2b', key: 'bandRun' } as const, null)
const proposalsAtom = atom({ plugin: 'm2b', key: 'bandProposals' } as const, null)
// Apart from the band's notice, which is about tasks: the proposals pane draws this one alone.
const proposalsNoticeAtom = atom({ plugin: 'm2b', key: 'bandProposalsNotice' } as const, null)
const paneViewAtom = atom({ plugin: 'm2b', key: 'paneView' } as const, null)
const toastedRunAtom = atom({ plugin: 'm2b', key: 'bandToastedRun' } as const, null)
const ownPromptsAtom = atom({ plugin: 'm2b', key: 'ownPrompts' } as const, [])
// `session.ts` names the same two values and writes them too: a module's reads and writes are
// listed from its own source, so each module that touches a value names it itself.
const sessionAtom = atom({ plugin: 'm2b', key: 'bandSession' } as const, null)
const notesAtom = atom({ plugin: 'm2b', key: 'sessionNotes' } as const, null)
const sessionNoticeAtom = atom({ plugin: 'm2b', key: 'sessionNotice' } as const, null)
const curateNoticeAtom = atom({ plugin: 'm2b', key: 'curateNotice' } as const, null)
// The command's own account of a start that failed. Its words can name a folder or a machine: they
// are drawn, and never put into the session's state, which holds only that the start failed.
let curateFailure: string | null = null

/** Forgets why the last press on `curate now` started no run. */
async function forgetCurateNotice($: EngineInterface): Promise<void> {
  curateFailure = null
  await update($, curateNoticeAtom, () => null)
}

const REFRESH_EVERY_MS = 60_000
// `m2b band` reaches and reads the task list (two Apple Reminders calls, 20 seconds each by
// default) and, at most every five minutes, probes the calendar within 10 seconds.
const BAND_TIMEOUT_MS = 90_000
// A drop on Apple Reminders is three calls (find, edit the notes, complete), 20 seconds each by default.
const WRITE_TIMEOUT_MS = 90_000
// A press is written only once this is over, so undo takes it back without touching the task list.
const UNDO_WINDOW_MS = 5_000
// m2b's own hooks give a session its topics: before a prompt, and at the start that follows a
// compaction. This long after either, the pane asks what the session holds now, so a topic that
// came in with a prompt shows while the turn still works.
const LOOK_AFTER_GIVING_MS = 3_000
// A session not known right at its start is looked at once more: its start may still be noting.
const SECOND_LOOK_MS = 5_000
// After `/clear` or a resume the session goes on under another id. The pane asks this long after
// the end, and while the session still answers with the ended id, this many times more.
const LOOK_AFTER_NEW_ID_MS = 1_000
const NEW_ID_TRIES = 5
// How long `/m2b-pane` waits for a fresh look before it shows what it holds.
const COMMAND_WAITS_MS = 2_000
// Read by `m2b doctor`: the core cannot see whether Claude Code loaded this module.
const SEEN_FILE = '.local/state/m2b/band-seen.json'
const MANIFEST = '.claude-plugin/plugin.json'

const BAND_ANSWER = ['band', '--json'] as const
// The name the sessions share that answer under. A band from before the one row shares its own
// under `view`, where the status is a line about the inbox and a task due is one to list: neither
// takes the other's answer, while a session still runs the older band.
const SHARED_ANSWER = 'answer'
// The second look before a keep or drop needs the tasks alone, not the status and its probes.
const TASKS_ANSWER = ['band', '--json', '--tasks-only'] as const

/**
 * What one answer of `m2b band --json` draws: the band's rows, the status line, and the version of
 * the installed core, which is the version the launcher runs.
 */
type BandView = {
  snapshot: BandSnapshot
  /** What is wrong with m2b, for the status line; null while nothing is, which clears the line. */
  status: string | null
  version: string | null
  run?: BandRun | null
  proposals?: BandProposals
  /** How m2b itself stands, for the pane; absent where m2b gave no answer to read it from. */
  health?: BandHealth
  /** The machine that curates the store; absent or null where the answer names none. */
  curatingMachine?: string | null
}

// The machine that curates the store, from the last answer. A setting's value: it is drawn, and
// never put into the session's state, which every plugin can read.
let curatingMachine: string | null = null

/** Runs jobs one after another, in the order they were queued. */
function serialQueue(): <T>(job: () => Promise<T>) => Promise<T> {
  let tail: Promise<unknown> = Promise.resolve()
  return job => {
    const run = tail.then(job)
    tail = run.catch(() => undefined)
    return run
  }
}

// Where m2b gave no answer, the pane's part about m2b says nothing: what failed is said once, as the task list's error.
const NO_HEALTH: BandHealth = NOT_KNOWN

/** One call for everything the band, the pane and the status line show; whatever fails, it answers a view. */
async function loadView($: EngineInterface, answer: readonly string[] = BAND_ANSWER): Promise<BandView> {
  const outcome = await runM2b($, answer, BAND_TIMEOUT_MS)
  if (!outcome.ok) {
    return { snapshot: failed(`m2b could not read the tasks: ${outcome.error}`), status: COULD_NOT_LOOK, version: null, health: NO_HEALTH }
  }
  let parsed: unknown
  try {
    parsed = JSON.parse(outcome.stdout)
  } catch {
    return { snapshot: failed('m2b band answered something that is not JSON'), status: COULD_NOT_LOOK, version: null, health: NO_HEALTH }
  }
  const fields = isObject(parsed) ? parsed : {}
  return {
    snapshot: snapshotOf(fields['tasks'], parseBandShows(fields['band'])),
    status: statusLine(fields['status']),
    version: typeof fields['version'] === 'string' ? fields['version'] : null,
    run: runOf(fields['status']),
    proposals: parseProposals(fields['proposals']),
    health: healthOf(fields['status'], await $.clock.now()),
    curatingMachine: curatingMachineOf(fields['status']),
  }
}

function snapshotOf(part: unknown, shows: BandShows | undefined): BandSnapshot {
  try {
    const tasks = parseBandTasks(part)
    if (typeof tasks === 'string') {
      // The settings were answered all the same, and where the band stands decides where this is said.
      return { ...failed(`m2b could not read the tasks: ${tasks}`), ...(shows === undefined ? {} : { shows }) }
    }
    return {
      candidates: tasks.candidates,
      review: tasks.review,
      error: null,
      ...(tasks.due === undefined ? {} : { due: tasks.due }),
      ...(shows === undefined ? {} : { shows }),
    }
  } catch (error) {
    return failed(String((error as Error).message))
  }
}

// Everything that reads or writes the band's rows goes through one queue, so a reload that read
// the tasks before a keep or drop can never land after it. A reload asked for while one waits to
// start is that same reload, forced if any of the requests was; asked for while one runs, it
// queues one more, which reads after the request. However many turns end while m2b is slow, at
// most one reload waits.
const bandJobs = serialQueue()
type WaitingReload = { isForced: boolean; done: Promise<void> }
let waitingReload: WaitingReload | null = null

/** With `isForced` (after this session's own turn or write), the band reads itself, never another session's answer. */
function reload($: EngineInterface, isForced = false): Promise<void> {
  if (waitingReload !== null) {
    waitingReload.isForced ||= isForced
    return waitingReload.done
  }
  const waiting: WaitingReload = { isForced, done: Promise.resolve() }
  waiting.done = bandJobs(() => {
    waitingReload = null
    return loadNow($, waiting.isForced)
  })
  waitingReload = waiting
  return waiting.done
}

/**
 * Puts a snapshot in place of the one held. The machine's settings are not the tasks' state: a
 * snapshot that names none (m2b did not answer, a look at the tasks alone, a write that failed)
 * keeps the ones held, so the band stays where it stands and says its error there.
 */
async function holdSnapshot($: EngineInterface, next: BandSnapshot): Promise<void> {
  await update($, snapshotAtom, held => (next.shows === undefined && held?.shows !== undefined ? { ...next, shows: held.shows } : next))
}

async function loadNow($: EngineInterface, isForced: boolean): Promise<void> {
  const view = await shared($, SHARED_ANSWER, () => loadView($), isView, isForced, hasReadTheTasks)
  // m2b can stop being set up while the call ran; its answer must not draw the band back.
  if (!(await isSetUp($))) {
    await clearBand($)
    return
  }
  await holdSnapshot($, view.snapshot)
  await update($, versionNoticeAtom, () => versionNotice(view.version))
  // An answer a session without the pane stored has no run; it leaves the run line as it was.
  await update($, runAtom, current => (view.run === undefined ? current : view.run))
  // Nor has an answer a session without proposals stored, or one m2b could not give, a word on them.
  await update($, proposalsAtom, current => view.proposals ?? current)
  await update($, healthAtom, current => view.health ?? current)
  curatingMachine = view.health === undefined ? curatingMachine : (view.curatingMachine ?? null)
  $.ui.status(view.status === null ? undefined : plainLine(view.status))
  await toastFailedRun($, view.run ?? null)
}

/**
 * One line when a curation run failed, once per session and run: the run's start is kept in the
 * session's state, which a reload of the mod keeps too. A run that succeeded says nothing.
 */
async function toastFailedRun($: EngineInterface, run: BandRun | null): Promise<void> {
  if (run?.state !== 'failed' || run.startedAt === null) {
    return
  }
  const startedAt = run.startedAt
  let isNew = false
  await update($, toastedRunAtom, shown => {
    isNew = shown !== startedAt
    return isNew ? startedAt : shown
  })
  if (!isNew) {
    return
  }
  try {
    const started = plainLine(timeOrDay(startedAt, await $.clock.now()))
    $.ui.toast(`m2b: the curation run of ${started} failed; its review task says why, and /m2b-review shows it`, {
      timeoutMs: 10_000,
    })
  } catch {
    // The status line says the run failed all the same.
  }
}

// The version in the manifest of the plugin this module was loaded from, read at session start.
let loadedVersion: string | null = null

async function readLoadedVersion($: EngineInterface): Promise<string | null> {
  try {
    const manifest: unknown = JSON.parse(await $.fs.read(`${$.plugin.root}/${MANIFEST}`))
    if (isObject(manifest) && typeof manifest['version'] === 'string') {
      return manifest['version']
    }
  } catch {
    // Without its own version the band cannot compare, and says nothing about it.
  }
  return null
}

/**
 * A session keeps the band it loaded, also after m2b was updated, while the launcher always runs
 * the installed core. Claude Code loads the installed band with `/reload-plugins` or a new session.
 * A band newer than the installed core comes from a checkout or a project's own install, which a
 * reload would not change, so only an older band says something.
 */
function versionNotice(installed: string | null): string | null {
  if (installed === null || loadedVersion === null || !isOlder(loadedVersion, installed)) {
    return null
  }
  return `This session runs m2b ${loadedVersion} and m2b ${installed} is installed: run /reload-plugins.`
}

/** Whether release `a` comes before release `b`, by `MAJOR.MINOR.PATCH`; anything else compares as not older. */
function isOlder(a: string, b: string): boolean {
  const [left, right] = [releaseNumbers(a), releaseNumbers(b)]
  if (left === null || right === null) {
    return false
  }
  const differing = left.findIndex((part, index) => part !== right[index])
  return differing !== -1 && (left[differing] ?? 0) < (right[differing] ?? 0)
}

function releaseNumbers(version: string): number[] | null {
  const match = /^(\d+)\.(\d+)\.(\d+)$/.exec(version)
  return match === null ? null : match.slice(1).map(Number)
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

/** A look that could not read the tasks says something about the session that looked, not about the tasks. */
function hasReadTheTasks(view: BandView): boolean {
  return view.snapshot.error === null
}

function isView(value: unknown): value is BandView {
  return (
    isObject(value) &&
    isSnapshot(value['snapshot']) &&
    (value['status'] === null || typeof value['status'] === 'string') &&
    (value['version'] === null || typeof value['version'] === 'string') &&
    // Absent in an answer a session without the pane stored: no run to show, like null.
    (value['run'] === undefined || value['run'] === null || isRun(value['run'])) &&
    (value['proposals'] === undefined || isProposals(value['proposals'])) &&
    (value['health'] === undefined || isHealth(value['health'])) &&
    (value['curatingMachine'] === undefined || value['curatingMachine'] === null || typeof value['curatingMachine'] === 'string')
  )
}

function isHealth(value: unknown): value is BandHealth {
  return (
    isObject(value) &&
    (value['curation'] === null || typeof value['curation'] === 'string') &&
    Array.isArray(value['troubles']) &&
    value['troubles'].every(trouble => typeof trouble === 'string') &&
    // A band from before the button shared its answer without these: it is not taken, and m2b is asked.
    (value['curates'] === null || typeof value['curates'] === 'boolean') &&
    typeof value['isCurating'] === 'boolean'
  )
}

/** The whole shape: a session of another m2b version may have written the shared answer. */
function isSnapshot(value: unknown): value is BandSnapshot {
  return (
    isObject(value) &&
    Array.isArray(value['candidates']) &&
    value['candidates'].every(isCandidate) &&
    (value['review'] === null || isReview(value['review'])) &&
    (value['error'] === null || typeof value['error'] === 'string') &&
    (value['due'] === undefined || (Array.isArray(value['due']) && value['due'].every(isDueTask))) &&
    // An answer that read the tasks names the machine's settings; one that failed may name none.
    (value['shows'] === undefined ? value['error'] !== null : isShows(value['shows']))
  )
}

/**
 * A band from before the band's place shared its answer without one, or without any settings:
 * that answer is not taken, and m2b is asked, so a band never moves to another place because an
 * older session answered last. An answer that could not read the tasks is no other session's to
 * take, whatever settings it names (`hasReadTheTasks`): a band says its own error where it stands
 * (`holdSnapshot`).
 */
function isShows(value: unknown): value is BandShows {
  return (
    isObject(value) &&
    (value['place'] === 'above' || value['place'] === 'below' || value['place'] === 'waiting') &&
    (value['dueTasks'] === 'off' || value['dueTasks'] === 'count' || value['dueTasks'] === 'list') &&
    typeof value['topics'] === 'boolean'
  )
}

function isDueTask(value: unknown): value is BandDueTask {
  return isObject(value) && typeof value['id'] === 'string' && typeof value['title'] === 'string' && typeof value['overdue'] === 'boolean'
}

function isCandidate(value: unknown): value is BandCandidate {
  return isObject(value) && typeof value['id'] === 'string' && typeof value['title'] === 'string'
}

function isReview(value: unknown): value is BandReview {
  return (
    isObject(value) &&
    typeof value['id'] === 'string' &&
    typeof value['title'] === 'string' &&
    Array.isArray(value['findings']) &&
    value['findings'].every(finding => typeof finding === 'string') &&
    (value['changes'] === undefined || (Array.isArray(value['changes']) && value['changes'].every(isFactChange))) &&
    (value['told'] === undefined || (Array.isArray(value['told']) && value['told'].every(told => typeof told === 'string'))) &&
    (value['copies'] === undefined ||
      (Array.isArray(value['copies']) &&
        value['copies'].every(copy => isObject(copy) && typeof copy['path'] === 'string' && typeof copy['captures'] === 'number')))
  )
}

function isFactChange(value: unknown): boolean {
  return (
    isObject(value) &&
    typeof value['topic'] === 'string' &&
    typeof value['file'] === 'string' &&
    Array.isArray(value['parts']) &&
    value['parts'].every(part => isObject(part) && typeof part['text'] === 'string' && typeof part['change'] === 'string')
  )
}

async function clearBand($: EngineInterface): Promise<void> {
  await update($, snapshotAtom, () => null)
  await update($, noticeAtom, () => null)
  await update($, rowNoticeAtom, () => null)
  await update($, versionNoticeAtom, () => null)
  await update($, healthAtom, () => null)
  curatingMachine = null
  await update($, runAtom, () => null)
  await update($, proposalsAtom, () => null)
  await update($, proposalsNoticeAtom, () => null)
  await turnTo($, null)
  await update($, sessionAtom, () => null)
  await update($, sessionNoticeAtom, () => null)
  await forgetCurateNotice($)
  $.ui.status(undefined)
}

/**
 * Reloads band and status line with one `m2b band` call. Before m2b is set up on this machine (no
 * machine config) or before the core wrote its launcher, it clears both and calls nothing; when m2b
 * cannot say, the status line says it could not look. The minute's refresh takes another session's
 * fresh answer; `isForced`, after this session's own turn, does not.
 */
async function refresh($: EngineInterface, isForced = false): Promise<void> {
  if (!(await isSetUp($))) {
    await clearBand($)
    return
  }
  await reload($, isForced)
}

/**
 * Asks what m2b gave this session, where m2b is set up and this is no curation run. It answers
 * what was said, or null where nothing was asked. Whatever fails, the pane says it could not look.
 */
async function look($: EngineInterface): Promise<BandSession | null> {
  const number = beginLook()
  try {
    return (await isCurationRun($)) || !(await isSetUp($)) ? null : await lookAtSession($, number)
  } catch (error) {
    try {
      return await lookFailed($, number, plainLine(String(error)))
    } catch {
      return null
    }
  }
}

// The looks that wait for their moment; a session start cancels them with the module's other timers.
const lookTimers = new Set<Timer>()

/** A look once `afterMs` are over; `isStart` for the look of a session's start, which may look twice. */
function lookLater($: EngineInterface, afterMs: number, isStart = false): void {
  const timer = $.clock.after(afterMs, () => {
    lookTimers.delete(timer)
    const looked: Promise<unknown> = isStart ? lookAtStart($) : look($)
    looked.catch(() => undefined)
  })
  lookTimers.add(timer)
}

/** The look at a session's start, and one more a little later for a session the first one did not know. */
async function lookAtStart($: EngineInterface): Promise<void> {
  const given = await look($)
  if (given !== null && !given.known && given.error === null) {
    lookLater($, SECOND_LOOK_MS)
  }
}

/**
 * The look after a session ended with `/clear` or a resume. Asked while the session still answers
 * with the ended id, m2b would say what the ended conversation was given, so the look waits for
 * the new id; after the last wait it looks all the same, for a resume into the same session.
 */
function lookUnderNewId($: EngineInterface, ended: string, triesLeft: number): void {
  const timer = $.clock.after(LOOK_AFTER_NEW_ID_MS, () => {
    lookTimers.delete(timer)
    lookUnlessEnded($, ended, triesLeft).catch(() => undefined)
  })
  lookTimers.add(timer)
}

async function lookUnlessEnded($: EngineInterface, ended: string, triesLeft: number): Promise<void> {
  if (triesLeft > 0 && (await sessionIdOf($)) === ended) {
    lookUnderNewId($, ended, triesLeft - 1)
    return
  }
  await lookAtStart($)
}

/**
 * A fresh look, waited for no longer than `limitMs`: a command answers with what is true now, and
 * still answers. False when the look did not come back in time, and what is kept may be older.
 */
async function lookWithin($: EngineInterface, limitMs: number): Promise<boolean> {
  let timer: Timer | undefined
  const limit = new Promise<false>(resolve => {
    try {
      timer = $.clock.after(limitMs, () => resolve(false))
    } catch {
      resolve(false)
    }
  })
  const isFresh = await Promise.race([look($).then(() => true), limit])
  timer?.cancel()
  return isFresh
}

/**
 * Everything the pane's start view draws, as this session holds it now. What was kept for another
 * session id, the one before a `/clear`, counts as not looked at.
 */
async function sessionModel($: EngineInterface): Promise<SessionModel> {
  const session = await sessionIdOf($)
  return {
    given: givenTo(await read($, sessionAtom), session),
    notes: notesOf(await read($, notesAtom), session),
    rowNotice: await read($, rowNoticeAtom),
    folderNotice: await read($, sessionNoticeAtom),
    curateNotice: curateNoticeOf(await read($, curateNoticeAtom)),
    health: await read($, healthAtom),
    curatingMachine,
    versionLine: await read($, versionNoticeAtom),
    snapshot: await read($, snapshotAtom),
    proposals: await read($, proposalsAtom),
    presses: await read($, pressesAtom),
  }
}

/**
 * A press on a tab: the pane turns to that tab's view, and the focus goes to the tab that leads
 * back to the view that is left, which that view did not draw. Left at its place in the row of
 * buttons, the focus could stand on a button of the new view that writes. Escape leads to the
 * start view without it: it hands the keyboard back to the prompt.
 */
async function turnByTab($: EngineInterface, to: TabId): Promise<void> {
  const focusKey = await focusKeyAfterPress($, to)
  if (to === 'overview') {
    await backToStart($)
    await focusInPane($, focusKey)
    return
  }
  if (to === 'settings') {
    await showSettings($, focusKey)
    return
  }
  await asDialog($, { kind: to })
  const focusMoved = focusInPane($, focusKey)
  $.clock.after(0, inBackground($, () => refresh($, true)))
  await focusMoved
}

/** Where the focus goes after a press on the tab `to`, null where what the pane shows cannot be read. */
async function focusKeyAfterPress($: EngineInterface, to: TabId): Promise<string | null> {
  try {
    return focusKeyAfterTab(await read($, paneViewAtom), to, await sessionModel($))
  } catch {
    // The pane turns all the same.
    return null
  }
}

/**
 * Turns the open pane to another of its views, as a dialog. A pane that opened by itself does not
 * close on Escape; opened anew it does, and Escape on the view leads back to the one the pane
 * starts in.
 */
async function asDialog($: EngineInterface, view: PaneView): Promise<void> {
  await turnTo($, view)
  try {
    await $.ui.open(AS_A_DIALOG)
  } catch {
    // The view is turned all the same; the tabs above it lead on.
  }
}

/**
 * The one way the pane's view changes, null for the view it starts in: whatever turns the pane
 * away from a topic drops that topic's lines with it, and away from the settings their values, so
 * no way out of either view can keep them.
 */
async function turnTo($: EngineInterface, view: PaneView | null): Promise<void> {
  forgetTopicUnless(view)
  forgetSettingsUnless(view)
  await update($, paneViewAtom, () => view)
}

/**
 * Turns the pane to one topic and reads its lines from the distillate as it is now. The lines are
 * kept by the module that draws them, never in the session's state, and only for the press that
 * asked: after a tab, a close, another view or a press on another topic nothing is kept for this
 * one, and an answer that arrives then is dropped. The focus goes to the tab that leads back.
 */
async function showTopic($: EngineInterface, name: string): Promise<void> {
  const press = await newPressToken($)
  beginTopic(press)
  await asDialog($, { kind: 'topic', name, press, isRead: false })
  // The read does not wait for the focus.
  const focusMoved = focusInPane($, tabKeyAfterTurn('overview', 'aside'))
  if (fillTopic(press, await readTopic($, name))) {
    // The lines are the module's; this write is what draws the pane again.
    await update($, paneViewAtom, view => (view !== null && view.kind === 'topic' && view.press === press ? { ...view, isRead: true } : view))
  }
  await focusMoved
}

type SettingsView = Extract<PaneView, { kind: 'settings' }>

/** Changes the settings view of the opening `press` names, which draws the pane again; any other view stays. */
async function turnSettings($: EngineInterface, press: string, change: (view: SettingsView) => SettingsView): Promise<void> {
  await update($, paneViewAtom, view => (view !== null && view.kind === 'settings' && view.press === press ? change(view) : view))
}

/**
 * Draws the settings again after what their module holds changed. A view turned to a group the
 * list no longer has is turned back to the choices, so the tabs name what is drawn below them.
 */
function drawSettings($: EngineInterface, press: string): Promise<void> {
  return turnSettings($, press, view => {
    const isGone = view.aside !== null && foldedTitle(press, view.aside.name) === null
    return { ...view, aside: isGone ? null : view.aside, drawn: view.drawn + 1 }
  })
}

/** Reads the list of the settings for an opening of the view; an answer for a view that was left is dropped. */
async function loadSettings($: EngineInterface, press: string): Promise<void> {
  const asked = askSettings(press)
  if (asked !== null && fillSettings(press, await readSettings($), asked)) {
    await drawSettings($, press)
  }
}

/**
 * Turns the pane to the settings and reads their list, with the focus on the button under
 * `focusKey`. The values are kept by the module that draws them, never in the session's state, and
 * only for this opening of the view.
 */
async function showSettings($: EngineInterface, focusKey: string | null): Promise<void> {
  const press = await newPressToken($)
  beginSettings(press)
  await asDialog($, { kind: 'settings', press, aside: null, drawn: 0 })
  // The read does not wait for the focus.
  const focusMoved = focusInPane($, focusKey)
  await loadSettings($, press)
  await focusMoved
}

// What the core is told of where a change comes from: it refuses to turn handing in on wherever
// Claude Code started the command, and it knows that by this variable. The mod names it itself,
// so that refusal does not rest on what the child happens to inherit.
const FROM_A_SESSION = { CLAUDECODE: '1' } as const
// What the core is told for the one press that turns handing in on, on its value: an empty value,
// which the core reads as a terminal of the owner's own, set over whatever the mod inherited. No
// other call of the mod carries it.
const BY_THE_PERSONS_PRESS = { CLAUDECODE: '' } as const

/**
 * Writes a press on a switch once its undo window is over, with the core's own command, which
 * refuses whatever is no switch. Then the list is read again for the view that is open now, so it
 * shows what is true, whatever the command said. The band is not waited for; after a change that
 * was written it is read behind the list, because a switch can be about what the band shows.
 */
async function settleSetting($: EngineInterface, token: string): Promise<void> {
  const stillWaited = waits(token)
  const write = startWriting(token)
  if (write === null) {
    // Taken back, or dropped because the list no longer offers the value: the view says what is true.
    await drawOpenSettings($)
    if (stillWaited) {
      // Dropped: `undo` is gone from under the focus, and the values stand again where it stood.
      await focusOffTheValues($)
    }
    return
  }
  let refused: string | null = 'the change could not be started'
  let focusMoved: Promise<void> = Promise.resolve()
  try {
    await drawOpenSettings($)
    // `undo` is gone from under the focus: it goes to a button that sets nothing, never to a value that comes back.
    // The write does not wait for it.
    focusMoved = focusOffTheValues($)
    // `--`: a key and a value are handed on as the core named them, whatever they begin with.
    const from = write.isTurningHandingInOn ? BY_THE_PERSONS_PRESS : FROM_A_SESSION
    const outcome = await runM2b($, ['settings', 'set', '--', write.key, write.argument], WRITE_TIMEOUT_MS, undefined, from)
    refused = outcome.ok ? null : outcome.error
  } catch (error) {
    refused = plainLine(String(error))
  } finally {
    // Whatever went wrong, the change ends: one left as being written would lock every switch.
    endChange(token, refused)
  }
  await focusMoved
  // The change is over at once in the view; the list follows when it is read. The values are
  // buttons again, which moves every button below them: the focus is asked for once more, and
  // the read does not wait for it.
  await drawOpenSettings($)
  const rests = focusOffTheValues($)
  const open = openSettings()
  if (open !== null) {
    await loadSettings($, open)
  }
  if (refused === null) {
    $.clock.after(0, inBackground($, () => refresh($, true)))
  }
  await rests
}

/** Draws the settings again for the opening the pane shows now, if it shows them. */
async function drawOpenSettings($: EngineInterface): Promise<void> {
  const open = openSettings()
  if (open !== null) {
    await drawSettings($, open)
  }
}

/**
 * Asks Claude Code for the focus of the pane on the button drawn under `key`. Claude Code keeps
 * the focus at its place in the row of buttons when a view is drawn anew, not on its button: left
 * alone, Enter pressed again would land on whatever stands at that place of the new drawing. So
 * where a press turns the pane to another view or changes which buttons the settings draw, the
 * mod says where the focus goes. Where the pane does not hold the
 * keyboard, as after Escape, Claude Code refuses, and the view is as drawn. Never throws.
 */
async function focusInPane($: EngineInterface, key: string | null): Promise<void> {
  if (key === null) {
    return
  }
  try {
    await $.ui.focus({ requestId: PANE_ID, key })
  } catch {
    // The view is drawn all the same.
  }
}

/**
 * Asks for the focus on a button that sets nothing, near the setting that was pressed, where the
 * pane shows the settings to choose; nothing where it shows another view or a group under its own
 * tab, which draws none of those buttons: Claude Code would wait for a key that is not drawn.
 * Never throws: a press is written whatever becomes of the focus.
 */
async function focusOffTheValues($: EngineInterface): Promise<void> {
  try {
    const view = await read($, paneViewAtom)
    if (view?.kind === 'settings' && view.aside === null) {
      await focusInPane($, restKey())
    }
  } catch {
    // The view is drawn all the same.
  }
}

function settingsActions($: EngineInterface, press: string): SettingsActions {
  return {
    showGroup: async name => {
      const title = foldedTitle(press, name)
      if (title === null) {
        return
      }
      // Leaving the values takes back a press that still waits on one: from the group's view nobody could.
      undoChange(press)
      await turnSettings($, press, view => ({ ...view, aside: { name, title }, drawn: view.drawn + 1 }))
      // The group stands under a tab of its own, which holds no button: the focus goes to the tab that leads back.
      await focusInPane($, tabKeyAfterTurn('settings', 'aside'))
    },
    choose: async (at, place, surface) => {
      const token = await newPressToken($)
      if (beginChange(press, at, place, token, surface)) {
        // A press taken back, or a view that was left, finds nothing to write when this fires.
        $.clock.after(
          UNDO_WINDOW_MS,
          inBackground($, () => settleSetting($, token)),
        )
        await drawSettings($, press)
        // The one button that takes the press back: Enter once more is undo.
        await focusInPane($, SETTINGS_UNDO)
      }
    },
    undo: async () => {
      if (undoChange(press)) {
        await drawSettings($, press)
        await focusOffTheValues($)
      }
    },
  }
}

/**
 * What the pane draws below its tabs: the view it is turned to, null for the one it starts in.
 * `bodyColumns` is the width of the pane's body.
 */
async function viewOfPane(
  $: EngineInterface,
  e: ResolveInput,
  view: PaneView | null,
  proposals: BandProposals | null,
  bodyColumns: number,
) {
  if (view === null) {
    return sessionPane($, e, await sessionModel($), sessionActions($), bodyColumns)
  }
  const presses = await read($, pressesAtom)
  switch (view.kind) {
    case 'settings':
      return settingsPane($, e, view, heldSettings(view.press), settingsActions($, view.press), bodyColumns)
    case 'proposals':
      return proposalsPane($, e, proposals, presses, await read($, proposalsNoticeAtom), proposalActions($), bodyColumns)
    case 'topic':
      return topicPane($, e, view.name, heldTopic(view.press), bodyColumns)
    case 'search':
      return searchPane($, e, view.search, bodyColumns)
    case 'review': {
      const model = {
        snapshot: await read($, snapshotAtom),
        run: await read($, runAtom),
        presses,
        notice: await read($, rowNoticeAtom),
        nowMs: await $.clock.now(),
      }
      return reviewPane($, e, model, rowActions($), bodyColumns)
    }
  }
}

// Where the pane's last drawing sat on each surface, as that surface said. The module's own: after
// a reload of the mod the pane is drawn anew before the person can act on it.
const paneSeats = new Map<string, string>()

/**
 * After a close of the pane has settled. Gone, it sits nowhere. A hook beneath may have kept it
 * open: then its seats stand. Where Claude Code cannot say, the seats go.
 */
async function seatsAfterClose($: EngineInterface): Promise<void> {
  let isStillOpen = false
  try {
    isStillOpen = (await $.ui.panes()).some(pane => pane.id === PANE_ID)
  } catch {
    // Counted as closed.
  }
  if (!isStillOpen) {
    paneSeats.clear()
  }
}

/**
 * Shows the pane as `showPane` does, and sees to a pane it could not show. `showPane` closes that
 * pane itself, and Claude Code leaves a plugin's hooks out of a close the plugin's own code made:
 * what the close hook does for the person's close is done here for the mod's own. The pane starts
 * in its start view when it opens next, and its seats go.
 */
async function showInPane(
  $: EngineInterface,
  placedLine: string,
  lines: () => string[],
  staysOpen = false,
): Promise<string> {
  const answer = await showPane($, placedLine, lines, staysOpen)
  if (answer !== placedLine) {
    await turnTo($, null)
    await seatsAfterClose($)
  }
  return answer
}

/** What the band draws from. How many topics the session was given is looked up only where the band shows it. */
async function bandModel($: EngineInterface): Promise<BandModel> {
  const snapshot = await read($, snapshotAtom)
  return {
    snapshot,
    proposals: await read($, proposalsAtom),
    notice: await read($, noticeAtom),
    topics: snapshot?.shows?.topics === true ? topicsGiven(givenTo(await read($, sessionAtom), await sessionIdOf($))) : 0,
  }
}

// When the person's close last led back to the start view. A second close this soon after it is
// the same key pressed twice.
let wentBackAtMs: number | null = null
const SAME_KEY_TWICE_MS = 500

/**
 * Back to the view the pane starts in, for Escape and the tab `Overview`. Beside the
 * chat the pane is opened once more, without the manners of a dialog: each open sets them anew, and
 * a pane that stays must not close on an Escape at the empty prompt. That comes before the view is
 * turned, so a close that arrives meanwhile still meets the other view and leads back as well.
 * Above the prompt the pane stays the dialog it was, so the next Escape closes the block.
 */
async function backToStart($: EngineInterface): Promise<void> {
  if (staysBesideChat(paneSeats.values())) {
    try {
      await $.ui.open({ id: PANE_ID, title: PANE_TITLE })
    } catch {
      // The pane shows its start view all the same.
    }
  }
  await turnTo($, null)
  lookLater($, 0)
  $.clock.after(0, inBackground($, () => refresh($, true)))
}

// Whether the pane may still open by itself: once per session, and once more after `/clear` or a
// resume, which go on as another session without a session start. The try is spent when it
// starts: one that fails is not made again in the session, and `/m2b-pane` opens the pane. A reload of
// the mod starts the module anew and tries once more, which opens nothing while the pane is open
// or was closed by hand.
let isOpeningDue = true
// A terminal's drawing said it runs under the fullscreen layout, which is fixed for a session.
let isTerminalFullscreen = false

/** Spends this session's try to open the pane by itself, a moment later: no state is written while a drawing is made. */
function openSoon($: EngineInterface): void {
  isOpeningDue = false
  try {
    $.clock.after(0, () => {
      openByItself($).catch(() => undefined)
    })
  } catch {
    // The band draws all the same; /m2b-pane opens the pane.
  }
}

/**
 * Opens the pane beside the chat without being asked, where m2b is set up and this is no curation
 * run: in the view it starts in, without the keyboard, and not closing on Escape. A pane the
 * terminal is too narrow to draw stays open and appears once it is wider. Not after the person
 * closed it by hand, until they open it again; and a pane that is open is left as it is, since
 * opening it anew would take the manners of a dialog from it.
 */
async function openByItself($: EngineInterface): Promise<void> {
  if ((await isCurationRun($)) || !(await isSetUp($))) {
    return
  }
  if ((await $.store.get(CLOSED_BY_HAND)) === true) {
    return
  }
  if ((await $.ui.panes()).some(pane => pane.id === PANE_ID)) {
    return
  }
  // A pane that closed left its start view behind, so there is no view to turn here. A command
  // that opens the pane in this very moment is retitled without its Escape; its tabs still lead out.
  await $.ui.open({ id: PANE_ID, title: PANE_TITLE })
}

function sessionActions($: EngineInterface): SessionActions {
  return {
    ...rowActions($),
    showTopic: name => showTopic($, name),
    switchFolder: async (change, folder) => {
      // What the last press could not write is no longer what the button is about.
      await update($, sessionNoticeAtom, () => null)
      await press($, FOLDER_PRESS, change, folderWrite($, change, folder), UNDO_FOLDER)
    },
    undoFolder: () => undo($, FOLDER_PRESS),
    curateNow: async () => {
      // Why the last press started no run is no longer what the button is about.
      await forgetCurateNotice($)
      await press($, CURATE_PRESS, 'curate', curateWrite($), UNDO_CURATE)
    },
    undoCurate: () => undo($, CURATE_PRESS),
  }
}

// How long after a start the run's record is read: by then the run has written that it is under way.
const RUN_SHOWS_AFTER_MS = 3_000

/**
 * Starts one curation run in the background with the core's own command, which answers at once
 * whether a run started: it runs also while curation is paused, and starts none while a run is
 * under way or on a machine that does not curate. A run that started is said at once, before its
 * record says so, and the band is read again a moment later; a press that started none says why,
 * in the command's words.
 */
function curateWrite($: EngineInterface): PressWrite {
  return async () => {
    const start = await startedRun($)
    if (start.isStarted) {
      await update($, healthAtom, health => (health === null ? health : whileCurating(health)))
      $.clock.after(
        RUN_SHOWS_AFTER_MS,
        inBackground($, () => refresh($, true)),
      )
      return false
    }
    curateFailure = start.reason
    await update($, curateNoticeAtom, () => start.refusal)
    // Most often a run is under way that this session had not read of yet: the look says so, and the button goes.
    $.clock.after(
      0,
      inBackground($, () => refresh($, true)),
    )
    return false
  }
}

/** Asks the core for one run in the background. A command that failed, threw or answered something else started none. */
async function startedRun($: EngineInterface): Promise<RunStart> {
  const failed = (reason: string): RunStart => ({ isStarted: false, refusal: 'failed', reason })
  try {
    const outcome = await runM2b($, ['curate', '--force', '--detach', '--json'], WRITE_TIMEOUT_MS)
    if (!outcome.ok) {
      return failed(outcome.error)
    }
    return parseRunStart(outcome.stdout) ?? failed('m2b answered something that is not the start of a run')
  } catch (error) {
    return failed(String(error))
  }
}

/** What the pane says of the last press that started no run, null where there is none. */
function curateNoticeOf(refusal: CurateRefusal | null): string | null {
  return refusal === null ? null : noRunStarted(refusal, curateFailure)
}

/**
 * Turns the distillate off or on for `folder`, which is handed to m2b as m2b named it: the
 * command's own default is the folder its process runs in, and that need not be the one the pane's
 * answer was about. Whatever the command said, the session is asked again, so the view shows what
 * is true now. The band holds nothing this changes and is not read again.
 */
function folderWrite($: EngineInterface, change: FolderSwitch, folder: string): PressWrite {
  return async () => {
    const failed = (reason: string): string =>
      change === 'off'
        ? `m2b could not be turned off in ${wholePath(folder)}: ${reason}`
        : `m2b could not be turned on under ${wholePath(folder)}: ${reason}`
    try {
      // `--`: a folder is handed on as it is named, whatever it begins with.
      const outcome = await runM2b($, ['distillate', change, '--', folder], WRITE_TIMEOUT_MS)
      await update($, sessionNoticeAtom, () => (outcome.ok ? null : failed(outcome.error)))
      await look($)
    } catch (error) {
      await update($, sessionNoticeAtom, () => failed(String(error)))
    }
    return false
  }
}

/**
 * For timers: the work runs unawaited, so anything it throws ends here, and the status line says
 * the band could not look instead of keeping a state it no longer knows.
 */
function inBackground($: EngineInterface, work: () => Promise<void>): () => void {
  return () => {
    work().catch(() => {
      try {
        $.ui.status(COULD_NOT_LOOK)
      } catch {
        // Nothing left to tell; the next refresh tries again.
      }
    })
  }
}

/**
 * Set up means the machine config exists, as the core reads it, and the core has written its
 * launcher, which it does at its first session start after setup. A store that is set up but
 * cannot be read is not "not set up": the band shows the error.
 */
async function isSetUp($: EngineInterface): Promise<boolean> {
  const [launcher, config] = [await launcherPath($), await machineConfigPath($)]
  return (
    launcher !== undefined && config !== undefined && (await $.fs.exists(config)) && (await $.fs.exists(launcher))
  )
}

/** The line a command answers when it cannot run yet, or null when m2b is set up here. */
async function notSetUpLine($: EngineInterface, what: string): Promise<string | null> {
  try {
    return (await isSetUp($)) ? null : `${what}: m2b is not set up on this machine; /m2b:m2b sets it up`
  } catch (error) {
    return `${what}: could not look whether m2b is set up: ${plainLine(String(error))}`
  }
}

/** Notes that this session runs the band, which `m2b doctor` reports; a failed write changes nothing. */
async function noteSeen($: EngineInterface): Promise<void> {
  const home = await m2bHome($)
  if (home === undefined) {
    return
  }
  try {
    await $.fs.write(`${home}/${SEEN_FILE}`, JSON.stringify({ seenAt: new Date(await $.clock.now()).toISOString() }))
  } catch {
    // The band runs all the same; doctor then says it has not seen it.
  }
}

/** A fenced model step of a curation run loads this plugin too; the band stays out of it. */
async function isCurationRun($: EngineInterface): Promise<boolean> {
  return (await $.env.get('M2B_CURATION_RUN')) === '1'
}

// This module's timers. A reload of the mod cancels them; session start, which runs again then, starts them anew.
let minuteTimer: Timer | null = null
const undoTimers = new Map<string, Timer>()
const lockTimers = new Map<string, Timer>()

// The longest a write holds its row: the write and the reload after it, each to its time limit.
const WRITE_LOCK_MS = WRITE_TIMEOUT_MS + BAND_TIMEOUT_MS

// Tells this module's presses apart from those of an earlier load of the mod, which share `$.state`.
let pressCount = 0

async function newPressToken($: EngineInterface): Promise<string> {
  pressCount += 1
  return `${await $.clock.now()}-${pressCount}`
}

/** The presses without `id`'s, when it is still the press `token` names; a later press on the row stays. */
function withoutPress(presses: Record<string, BandPress>, id: string, token: string): Record<string, BandPress> {
  return presses[id]?.token === token
    ? Object.fromEntries(Object.entries(presses).filter(([pressed]) => pressed !== id))
    : presses
}

/** Releases the row of a press still writing at its deadline, so a write that never returns cannot lock it for good. */
function releaseAtDeadline($: EngineInterface, id: string, pressed: BandPress, nowMs: number): void {
  const remainingMs = Math.max(0, (pressed.deadlineMs ?? nowMs) - nowMs)
  lockTimers.get(id)?.cancel()
  lockTimers.set(
    id,
    $.clock.after(
      remainingMs,
      inBackground($, async () => {
        await update($, pressesAtom, presses => withoutPress(presses, id, pressed.token))
      }),
    ),
  )
}

/**
 * At session start, which also runs when the mod is loaded again: a press still in its undo window
 * is forgotten, since its timer went with the old module and nothing was written. A press already
 * writing keeps its row locked until that write ends or its deadline passes: the old module's write
 * may still be under way, and a second press on the row would not queue behind it.
 */
async function carryPressesOver($: EngineInterface): Promise<void> {
  const nowMs = await $.clock.now()
  let writing: [string, BandPress][] = []
  await update($, pressesAtom, presses => {
    writing = Object.entries(presses).filter(
      ([, pressed]) => pressed.phase === 'writing' && (pressed.deadlineMs ?? 0) > nowMs,
    )
    return Object.fromEntries(writing)
  })
  for (const [id, pressed] of writing) {
    releaseAtDeadline($, id, pressed, nowMs)
  }
}

/** What a press writes once its undo window is over. It never rejects, and answers whether the band reads again. */
type PressWrite = () => Promise<boolean>

/**
 * A press on keep or drop writes nothing yet: the row offers undo for a few seconds, and only then
 * is the task completed or dropped, or the proposal answered. Taking a press back is forgetting it,
 * so a crash, a closed session or a reload of the mod during those seconds leaves everything as it
 * was, and an item another session settles meanwhile is caught when the write comes. `ids` are the
 * proposals a press on keep all stands for.
 *
 * The focus goes to the row's `undo`, drawn under `undoKey` once the press waits: Enter pressed
 * again takes the press back. Left at its place in the row of buttons, it would stand on `undo`
 * after keep and, after drop, on keep of the row below, since the pressed row draws one button
 * where it drew two.
 */
async function press(
  $: EngineInterface,
  id: string,
  action: BandPress['action'],
  write: PressWrite,
  undoKey: string,
  ids?: string[],
): Promise<void> {
  const token = await newPressToken($)
  const pressed: BandPress = { action, phase: 'waiting', token, ...(ids === undefined ? {} : { ids }) }
  let isClaimed = false
  await update($, pressesAtom, presses => {
    isClaimed = presses[id] === undefined
    return isClaimed ? { ...presses, [id]: pressed } : presses
  })
  if (isClaimed) {
    undoTimers.set(
      id,
      $.clock.after(
        UNDO_WINDOW_MS,
        inBackground($, () => settle($, id, token, write)),
      ),
    )
    await focusInPane($, undoKey)
  }
}

async function undo($: EngineInterface, id: string): Promise<void> {
  let isUndone = false
  await update($, pressesAtom, presses => {
    const pressed = presses[id]
    isUndone = pressed?.phase === 'waiting'
    return pressed !== undefined && isUndone ? withoutPress(presses, id, pressed.token) : presses
  })
  if (isUndone) {
    undoTimers.get(id)?.cancel()
    undoTimers.delete(id)
  }
}

/**
 * Writes a press once its undo window is over. The row stays locked until the reload after the
 * write has landed, so a second press cannot meet the old row.
 */
async function settle($: EngineInterface, id: string, token: string, write: PressWrite): Promise<void> {
  undoTimers.delete(id)
  const deadlineMs = (await $.clock.now()) + WRITE_LOCK_MS
  let isStillPressed = false
  await update($, pressesAtom, presses => {
    const pressed = presses[id]
    isStillPressed = pressed?.token === token && pressed.phase === 'waiting'
    return pressed !== undefined && isStillPressed
      ? { ...presses, [id]: { ...pressed, phase: 'writing', deadlineMs } satisfies BandPress }
      : presses
  })
  if (!isStillPressed) {
    return
  }
  try {
    // Written: whatever the reload does, the band no longer says the write failed.
    if (await bandJobs(write)) {
      await reload($, true)
    }
  } finally {
    await update($, pressesAtom, presses => withoutPress(presses, id, token))
  }
}

/**
 * Completes or drops a candidate after reading the list again: a candidate another session settled
 * meanwhile is left alone, and the band says so.
 */
function taskWrite($: EngineInterface, candidate: BandCandidate, action: BandSettle): PressWrite {
  return async () => {
    try {
      return await settleNow($, candidate, action)
    } catch (error) {
      await holdSnapshot($, failed(`m2b could not ${verbOf(action)} "${nameOf(candidate)}": ${String(error)}`))
      return false
    }
  }
}

async function settleNow($: EngineInterface, candidate: BandCandidate, action: BandSettle): Promise<boolean> {
  // What the last press could not write is not cleared here: it stands until the next press, and
  // a write may land seconds after a refusal that no press has followed.
  const { snapshot } = await loadView($, TASKS_ANSWER)
  if (snapshot.error !== null) {
    await holdSnapshot($, snapshot)
    return false
  }
  const current = snapshot.candidates
  const fresh = snapshot.review
  // `ok` on the review closes it the way keep closes a candidate.
  if (!current.some(open => open.id === candidate.id) && fresh?.id !== candidate.id) {
    await update($, rowNoticeAtom, () => `Already settled in another session, nothing written: ${nameOf(candidate)}`)
    await update($, snapshotAtom, old => (old === null ? old : { ...old, candidates: current, review: fresh }))
    return false
  }
  // A run that ended since the review was drawn rewrote it under the same id: what was pressed on
  // is not what would be closed.
  if (fresh !== null && fresh.id === candidate.id && isOtherReview(candidate, fresh)) {
    await update($, rowNoticeAtom, () => `The review changed since it was drawn, nothing written: ${nameOf(candidate)}`)
    await update($, snapshotAtom, old => (old === null ? old : { ...old, candidates: current, review: fresh }))
    return false
  }
  // `--`: with the markdown backend a task id is a file name, and it may start with a dash.
  const outcome = await runM2b($, ['tasks', action, '--', candidate.id], WRITE_TIMEOUT_MS)
  if (!outcome.ok) {
    await holdSnapshot($, failed(`m2b could not ${verbOf(action)} "${nameOf(candidate)}": ${outcome.error}`))
    return false
  }
  return true
}

/** What a pressed row is called in what m2b says of it: the review as the pane calls it, a candidate or a question by its title. */
function nameOf(pressed: BandCandidate): string {
  return Array.isArray((pressed as Partial<BandReview>).findings) ? REVIEW : pressed.title
}

/** Whether the review pressed on holds other findings than the one read now; unknown counts as the same. */
function isOtherReview(pressed: BandCandidate, fresh: BandReview): boolean {
  const findings = (pressed as Partial<BandReview>).findings
  return Array.isArray(findings) && findings.join('\n\n') !== fresh.findings.join('\n\n')
}

function rowActions($: EngineInterface): RowActions {
  return {
    press: async (candidate, action) => {
      // What the last press could not write is said until the next press there.
      await update($, rowNoticeAtom, () => null)
      await press($, candidate.id, action, taskWrite($, candidate, action), undoKey(candidate.id))
    },
    undo: id => undo($, id),
  }
}

/**
 * Answers proposals with `m2b proposals keep` or `drop`, which adds the answers and leaves the
 * filing to the next curation run. No second look comes first: the command itself refuses an
 * answer where another one stands, from another session or machine, and what it says to that stays
 * as the notice. Whatever it answered, the band reads again, so the rows are those that still wait.
 */
function proposalWrite($: EngineInterface, proposals: BandProposal[], action: BandSettle): PressWrite {
  return async () => {
    const verb = verbOf(action)
    try {
      const ids = proposals.map(proposal => proposal.id)
      const outcome = await runM2b($, ['proposals', verb, ...ids], WRITE_TIMEOUT_MS)
      if (!outcome.ok) {
        await update($, proposalsNoticeAtom, () => refusedLine(proposals, verb, outcome.error))
      }
    } catch (error) {
      await update($, proposalsNoticeAtom, () => refusedLine(proposals, verb, String(error)))
    }
    return true
  }
}

function proposalActions($: EngineInterface): ProposalActions {
  return {
    answer: async (proposal, action) => {
      // What the last answer could not write is said until the next press there.
      await update($, proposalsNoticeAtom, () => null)
      await press($, pressKey(proposal.id), action, proposalWrite($, [proposal], action), undoKey(proposal.id))
    },
    keepAll: async proposals => {
      await update($, proposalsNoticeAtom, () => null)
      await press(
        $,
        KEEP_ALL,
        'complete',
        proposalWrite($, proposals, 'complete'),
        UNDO_ALL,
        proposals.map(proposal => proposal.id),
      )
    },
    undo: key => undo($, key),
  }
}

/** Turns the pane to the proposals and opens it; where it cannot be shown, the answer holds them as text. */
async function showProposals($: EngineInterface): Promise<string> {
  await turnTo($, { kind: 'proposals' })
  // Opens with what the band holds and reads the proposals again behind it.
  $.clock.after(0, inBackground($, () => refresh($, true)))
  const proposals = await read($, proposalsAtom)
  return showInPane($, PROPOSALS_PLACED, () => proposalLines(proposals))
}

/**
 * `open` on the band's row: the pane opens in the view it starts in, as the person's own open, so
 * it is placed at any width, and asks again what the session was given.
 * `staysOpen` where the band is drawn under the fullscreen layout at a width that docks a pane.
 * A button has no answer to put the lines in, so where no pane can be shown the band names the
 * command that answers with them.
 */
async function openFromBand($: EngineInterface, staysOpen: boolean): Promise<void> {
  await turnTo($, null)
  $.clock.after(0, inBackground($, () => refresh($, true)))
  lookLater($, 0)
  const answer = await placedOrWhyNot($, staysOpen)
  if (answer !== SESSION_PLACED) {
    await update($, noticeAtom, () => `${answer}; /${SESSION_COMMAND.name} answers with the lines`)
  }
}

/** Opens the pane for the band's row; an open Claude Code refuses is said like a pane that cannot be shown. */
async function placedOrWhyNot($: EngineInterface, staysOpen: boolean): Promise<string> {
  try {
    const [answer] = (await showInPane($, SESSION_PLACED, () => [], staysOpen)).split('\n')
    return answer ?? SESSION_PLACED
  } catch (error) {
    return `the m2b pane could not be opened: ${plainLine(String(error))}`
  }
}

function verbOf(action: BandSettle): string {
  return action === 'complete' ? 'keep' : 'drop'
}

/** The texts that say something, as one. */
function joined(texts: readonly string[], separator: string): string {
  return texts.filter(text => text !== '').join(separator)
}

function failed(error: string): BandSnapshot {
  return { candidates: [], review: null, error }
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    const result = await next(e)
    if (await isCurationRun($)) {
      return result
    }
    // A reload of the mod runs this again and cancels the old module's timers.
    minuteTimer?.cancel()
    for (const timer of [...undoTimers.values(), ...lockTimers.values(), ...lookTimers]) {
      timer.cancel()
    }
    undoTimers.clear()
    lockTimers.clear()
    lookTimers.clear()
    isOpeningDue = true
    await carryPressesOver($)
    // A reload of the mod took the lines of a topic, and the values of the settings, with the old
    // module: the pane starts over.
    if (['topic', 'settings'].includes((await read($, paneViewAtom))?.kind ?? '')) {
      await turnTo($, null)
    }
    loadedVersion = await readLoadedVersion($)
    askCoreAgain()
    for (const command of [SESSION_COMMAND, NOTE_COMMAND, REVIEW_COMMAND, SEARCH_COMMAND, PROPOSALS_COMMAND, SETTINGS_COMMAND]) {
      try {
        await $.command.register(command)
      } catch {
        // Without the command the band still runs; the skills note and search the same way.
      }
    }
    const tools = [NOTE_TOOL, SEARCH_TOOL, ...((await isHandingInOn($)) ? [PROPOSE_TOOL] : [])]
    for (const tool of tools) {
      try {
        await $.tool.register(tool)
      } catch {
        // Without the tool the model runs the skill's command, as where no mod runs.
      }
    }
    minuteTimer = $.clock.every(REFRESH_EVERY_MS, inBackground($, () => refresh($)))
    $.clock.after(0, inBackground($, () => refresh($)))
    lookLater($, 0, true)
    void noteSeen($)
    return result
  })

  on('turn.complete', async ($, e, next) => {
    const result = await next(e)
    if (e.agentId === undefined && !(await isCurationRun($))) {
      $.clock.after(0, inBackground($, () => refresh($, true)))
      lookLater($, 0)
    }
    return result
  })

  // `/clear` and a resume end the conversation while the process goes on under a new session id,
  // and no session start follows: what the pane holds is about the conversation that ended.
  on('session.end', async ($, e, next) => {
    const result = await next(e)
    if ((e.reason === 'clear' || e.reason === 'resume') && !(await isCurationRun($))) {
      isOpeningDue = true
      // The band reads nothing that `/clear` changes, so its next drawing may be a minute away.
      if (isTerminalFullscreen) {
        openSoon($)
      }
      await forgetSession($)
      // A topic's lines were opened from the list of the conversation that ended.
      if ((await read($, paneViewAtom))?.kind === 'topic') {
        await turnTo($, null)
      }
      lookUnderNewId($, e.sessionId, NEW_ID_TRIES)
    }
    return result
  })

  // A compaction begins the list of what the session was given again, at the start that follows it.
  on('session.compact', async ($, e, next) => {
    const result = await next(e)
    // Not what a precompute prepares, and not a compaction that was skipped.
    if (e.agentId === undefined && e.trigger !== 'precompute' && !('skip' in result)) {
      lookLater($, LOOK_AFTER_GIVING_MS)
    }
    return result
  })

  on('command.run', { command: SESSION_COMMAND.name }, async ($, e, next) => {
    if (await isCurationRun($)) {
      return next(e)
    }
    const notReady = await notSetUpLine($, 'not shown')
    if (notReady !== null) {
      return { text: notReady }
    }
    await turnTo($, null)
    // Opens with what the band holds and reads it again behind the pane. What the session was
    // given is asked first: where no pane can be shown, the lines go into the conversation.
    $.clock.after(0, inBackground($, () => refresh($, true)))
    const isFresh = await lookWithin($, COMMAND_WAITS_MS)
    const model = await sessionModel($)
    // The pane draws the answer when it comes. The text is given once, so without a fresh answer
    // it says that m2b has not looked, never what an earlier look said.
    const lines = (): string[] => sessionLines(isFresh ? model : { ...model, given: null })
    // Beside the chat the start view stays; above the prompt it is a dialog that Escape closes.
    return { text: await showInPane($, SESSION_PLACED, lines, docksFor(e.presentation)) }
  })

  on('command.run', { command: NOTE_COMMAND.name }, async ($, e, next) => {
    // Registered only outside a curation run, where nothing would type it; the band stays out of it.
    if (await isCurationRun($)) {
      return next(e)
    }
    const outcome = await note($, e.args, () => isSetUp($))
    if (outcome.isWritten) {
      await countNote($)
      // The status line counts the new capture without waiting for the minute.
      $.clock.after(0, inBackground($, () => refresh($, true)))
    }
    return { text: outcome.line }
  })

  on('command.run', { command: REVIEW_COMMAND.name }, async ($, e, next) => {
    if (await isCurationRun($)) {
      return next(e)
    }
    const notReady = await notSetUpLine($, 'not shown')
    if (notReady !== null) {
      return { text: notReady }
    }
    await turnTo($, { kind: 'review' })
    // Opens with what the band holds and reads the run again behind it.
    $.clock.after(0, inBackground($, () => refresh($, true)))
    const [snapshot, run] = [await read($, snapshotAtom), await read($, runAtom)]
    const nowMs = await $.clock.now()
    const text = await showInPane($, 'the last curation run is in the m2b pane', () => reviewLines(snapshot, run, nowMs))
    return { text }
  })

  on('command.run', { command: PROPOSALS_COMMAND.name }, async ($, e, next) => {
    if (await isCurationRun($)) {
      return next(e)
    }
    const notReady = await notSetUpLine($, 'not shown')
    return { text: notReady ?? (await showProposals($)) }
  })

  // The command opens the view and no more: it takes no value, whoever ran it and whatever
  // follows its name. Its answer is one line without a value, because an answer reaches the model.
  on('command.run', { command: SETTINGS_COMMAND.name }, async ($, e, next) => {
    if (await isCurationRun($)) {
      return next(e)
    }
    const notReady = await notSetUpLine($, 'not shown')
    if (notReady !== null) {
      return { text: notReady }
    }
    const press = await newPressToken($)
    beginSettings(press)
    await turnTo($, { kind: 'settings', press, aside: null, drawn: 0 })
    const [answer] = (await showInPane($, SETTINGS_PLACED, () => [])).split('\n')
    if (answer !== SETTINGS_PLACED) {
      // No pane: nothing is read, and the list is where a terminal shows it.
      return { text: `${answer}; ${SETTINGS_IN_A_TERMINAL}` }
    }
    $.clock.after(0, inBackground($, () => loadSettings($, press)))
    return { text: SETTINGS_PLACED }
  })

  on('command.run', { command: SEARCH_COMMAND.name }, async ($, e, next) => {
    if (await isCurationRun($)) {
      return next(e)
    }
    const request = searchRequest(e.args)
    if (plainLine(request.text).trim() === '') {
      return { text: `nothing searched: write what to look for after the command, as in /${SEARCH_COMMAND.name} plywood` }
    }
    const notReady = await notSetUpLine($, 'not searched')
    if (notReady !== null) {
      return { text: notReady }
    }
    const outcome = await searchStore($, request.text, request.wholeWords)
    if ('line' in outcome) {
      return { text: outcome.line }
    }
    const { search } = outcome
    const summary = searchSummary(search)
    if (search.total === 0) {
      return { text: summary }
    }
    await turnTo($, { kind: 'search', search })
    return { text: await showInPane($, searchPlaced(search), () => [summary, ...searchLines(search)]) }
  })

  // Registered only outside a curation run; a call there is not this mod's to answer.
  on('tool.call', { tool: NOTE_TOOL_NAME }, async ($, e, next) => {
    if (await isCurationRun($)) {
      return next(e)
    }
    const notReady = await notSetUpLine($, 'not noted')
    const answer = notReady === null ? await noteTool($, e) : { error: notReady }
    if ('error' in answer) {
      return { deny: answer.error }
    }
    await countNote($)
    // The status line counts the new capture without waiting for the minute.
    $.clock.after(0, inBackground($, () => refresh($, true)))
    return { result: answer.text }
  })

  on('tool.call', { tool: SEARCH_TOOL_NAME }, async ($, e, next) => {
    if (await isCurationRun($)) {
      return next(e)
    }
    const notReady = await notSetUpLine($, 'could not search')
    const answer = notReady === null ? await searchTool($, e) : { error: notReady }
    return 'error' in answer ? { deny: answer.error } : { result: answer.text }
  })

  // Offered only where the owner turned handing in on. A session that started before they turned
  // it off still has the tool, and the command refuses.
  on('tool.call', { tool: PROPOSE_TOOL_NAME }, async ($, e, next) => {
    if (await isCurationRun($)) {
      return next(e)
    }
    const refusal = e.agentId === undefined ? await notSetUpLine($, NOT_HANDED_IN) : ONLY_THE_MAIN_CONVERSATION
    const answer = refusal === null ? await proposeTool($, e) : { error: refusal }
    return 'error' in answer ? { deny: answer.error } : { result: answer.text }
  })

  on('tool.check', { tool: NOTE_TOOL_NAME }, async ($, e, next) => {
    const verdict = await next(e)
    const isOwn = isInOwnWords(noteTextOf(e.input), await read($, ownPromptsAtom))
    return verdictFor($, e, verdict, NOTE_COMMAND_LINE, isOwn)
  })
  on('tool.check', { tool: SEARCH_TOOL_NAME }, async ($, e, next) =>
    verdictFor($, e, await next(e), searchCommandLineOf(e.input)),
  )
  on('tool.check', { tool: PROPOSE_TOOL_NAME }, async ($, e, next) =>
    verdictFor($, e, await next(e), PROPOSE_COMMAND_LINE),
  )

  // The person's close on the review, a search or the proposals leads back to the view the pane
  // starts in: answered here without `next`, the pane stays open. On the start view it closes, and
  // beside the chat that is kept, so the pane does not open by itself until they open it again.
  // When this throws, the pane closes as it was asked to: a pane that cannot be closed is worse
  // than one that closes a view too early. The mod's own close is not this hook's: Claude Code
  // leaves a plugin's hooks out of a close its own code made, and `showInPane` sees to it.
  on('ui.close', { id: PANE_ID }, async ($, e, next) => {
    if (e.origin.kind === 'plugin') {
      // Another plugin's close: the pane starts in its start view when it opens next, a topic's
      // lines and the settings' values go, and a press that still waits is taken back, since
      // nobody could do that any more.
      dropWaitingChange()
      await turnTo($, null)
      return next(e)
    }
    const nowMs = await $.clock.now()
    const view = await read($, paneViewAtom)
    const isOnStartView = view === null
    const isRightAfterBack = wentBackAtMs !== null && nowMs - wentBackAtMs < SAME_KEY_TWICE_MS
    const answer = closeAnswer(e.origin.kind, isOnStartView, staysBesideChat(paneSeats.values()), isRightAfterBack)
    if (answer === 'back') {
      if (!isOnStartView) {
        wentBackAtMs = nowMs
      }
      // Not awaited: the way back opens the pane anew, and from inside the pane's own close that
      // open could wait for this hook to end.
      $.clock.after(0, () => {
        backToStart($).catch(() => undefined)
      })
      return { value: undefined }
    }
    if (answer === 'by hand') {
      try {
        await $.store.set(CLOSED_BY_HAND, true)
      } catch {
        // The pane closes all the same; it then opens by itself again in the next session.
      }
    }
    // Whoever closes it, the pane starts in its start view when it opens next.
    await turnTo($, null)
    const result = await next(e)
    // Once the close has settled, the seats go. Not awaited:
    // asked from inside the pane's own close, Claude Code may still list the pane.
    $.clock.after(0, () => {
      seatsAfterClose($).catch(() => undefined)
    })
    return result
  }).catch(async (_, e, next) => {
    // The pane closes without its view being turned: a topic's lines and the settings' values go
    // all the same, and so do the seats, which the pane's next drawing notes anew.
    forgetTopicUnless(null)
    forgetSettingsUnless(null)
    paneSeats.clear()
    return next(e)
  })

  on('ui.render', { component: 'Pane', requestId: PANE_ID }, async ($, e) => {
    paneSeats.set(e.surface, e.props.placement)
    // The small form of the desktop app is read at a glance, whatever view the pane was turned to.
    if (e.props.placement === 'widget') {
      return glancePane($, e, await sessionModel($))
    }
    const view = await read($, paneViewAtom)
    const proposals = await read($, proposalsAtom)
    const ui = $.ui.resolve(e)
    const { Box } = ui
    return (
      <Box flexDirection="column">
        <Box marginBottom={1}>{tabRow(ui, paneTabs(view, proposals?.waiting.length ?? 0, to => turnByTab($, to)))}</Box>
        {await viewOfPane($, e, view, proposals, e.props.bodyColumns)}
      </Box>
    )
  })

  // The band clears its notice here and keeps the words of the person's own prompt for the note
  // tool; when that throws or overruns, the prompt still enters as typed, through the catch instead
  // of an engine report naming m2b as the failed hook. A prompt not kept only makes a note ask.
  on('prompt.submit', async ($, e, next) => {
    await update($, noticeAtom, () => null)
    await update($, rowNoticeAtom, () => null)
    await update($, proposalsNoticeAtom, () => null)
    await update($, sessionNoticeAtom, () => null)
    await forgetCurateNotice($)
    if (isOwnPrompt(e)) {
      await update($, ownPromptsAtom, prompts => withPrompt(prompts ?? [], e.text))
    }
    lookLater($, LOOK_AFTER_GIVING_MS)
    return next(e)
  }).catch(($, e, next) => next(e))

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    // A session start says nothing of the layout; every drawing does. So the pane opens by itself
    // with the band's first drawing on a terminal under the fullscreen layout, where it sits beside
    // the chat. On the main screen it would be a block above the prompt in every session, and never
    // opens unasked. Another surface's drawing opens nothing: the pane is one for the session, and
    // a terminal on the main screen would seat it above the prompt.
    if (e.surface === 'terminal' && e.viewport?.isFullscreen === true) {
      isTerminalFullscreen = true
      if (isOpeningDue) {
        openSoon($)
      }
    }
    if (e.props.hasSurvey) {
      return next(e)
    }
    const model = await bandModel($)
    const line = standsBelow(model) ? null : bandLine(model)
    if (line === null) {
      return next(e)
    }
    const staysOpen = docksFor({ isFullscreen: e.viewport?.isFullscreen === true, columns: e.viewport?.columns ?? 0 })
    return bandRow($, e, line, () => openFromBand($, staysOpen))
  })

  // With the band below the prompt, the hint line there ends in it: as a row m2b draws after the
  // engine's text where the line has room for it, else as words the engine adds to its own line.
  on('ui.render', { component: 'PromptHint' }, async ($, e, next) => {
    const model = await bandModel($)
    const line = standsBelow(model) ? bandLine(model) : null
    if (line === null) {
      return next(e)
    }
    // What another plugin added to the line stays: before m2b's words, and in the row as the engine's text.
    const added = e.props.tail ?? ''
    const below = belowPrompt(line, joined([e.props.hint, added], ' '), e.viewport?.columns ?? null, SESSION_COMMAND.name)
    if (below.kind === 'tail') {
      return next({ ...e, props: { ...e.props, tail: joined([added, below.text], ' · ') } })
    }
    // On a terminal a click presses a button below the prompt under the fullscreen layout alone.
    const isFullscreen = e.viewport?.isFullscreen === true
    const staysOpen = docksFor({ isFullscreen, columns: e.viewport?.columns ?? 0 })
    const onOpen = isFullscreen ? () => openFromBand($, staysOpen) : null
    return hintRow($, e, joined([e.props.hint, added], ' '), below.line, onOpen, SESSION_COMMAND.name)
  }).catch(($, e, next) => next(e))
}
