import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register, Timer } from 'claude-code'

import type {
  BandCandidate,
  BandDueTask,
  BandPress,
  BandProposal,
  BandProposals,
  BandReview,
  BandRun,
  BandSession,
  BandSettle,
  BandSnapshot,
  FolderSwitch,
  PaneView,
} from '../types'
import { bandRows, lineBesidePane, lineRow, topicsGiven } from './band'
import type { BandActions, BandModel } from './band'
import { launcherPath, m2bHome, machineConfigPath, runM2b } from './m2b'
import { NOTE_COMMAND, note } from './note'
import { isInOwnWords, isOwnPrompt, withPrompt } from './own-words'
import {
  AS_A_DIALOG,
  PANE_ID,
  PANE_TITLE,
  REVIEW_COMMAND,
  SEARCH_COMMAND,
  isRun,
  minute,
  paneTree,
  reviewLines,
  runOf,
  searchLines,
  searchStore,
  searchRequest,
  searchSummary,
  showPane,
} from './pane'
import { CLOSED_BY_HAND, closeAnswer, docksFor, paneSight, staysBesideChat } from './pane-seat'
import type { PaneSight } from './pane-seat'
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
  FOLDER_PRESS,
  SESSION_COMMAND,
  SESSION_PLACED,
  backRow,
  glancePane,
  sessionLines,
  sessionPane,
} from './session-view'
import type { SessionActions, SessionModel } from './session-view'
import {
  KEEP_ALL,
  PROPOSALS_COMMAND,
  PROPOSALS_PLACED,
  isProposals,
  refusedLine,
  parseProposals,
  pressKey,
  proposalLines,
  proposalsPane,
} from './proposals'
import type { ProposalActions } from './proposals'
import type { RowActions } from './rows'
import { shared } from './shared-cache'
import { COULD_NOT_LOOK, statusLine } from './status-line'
import { parseBandTasks } from './tasks'
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
  SEARCH_COMMAND_LINE,
  SEARCH_TOOL,
  SEARCH_TOOL_NAME,
  isHandingInOn,
  noteTextOf,
  noteTool,
  proposeTool,
  searchTool,
  verdictFor,
} from './tools'

const snapshotAtom = atom({ plugin: 'm2b', key: 'bandSnapshot' } as const, null)
const noticeAtom = atom({ plugin: 'm2b', key: 'bandNotice' } as const, null)
const pressesAtom = atom({ plugin: 'm2b', key: 'bandPresses' } as const, {})
const versionNoticeAtom = atom({ plugin: 'm2b', key: 'bandVersionNotice' } as const, null)
const runAtom = atom({ plugin: 'm2b', key: 'bandRun' } as const, null)
const proposalsAtom = atom({ plugin: 'm2b', key: 'bandProposals' } as const, null)
// Apart from the band's notice, which is about tasks: the proposals pane draws this one alone.
const proposalsNoticeAtom = atom({ plugin: 'm2b', key: 'bandProposalsNotice' } as const, null)
const paneViewAtom = atom({ plugin: 'm2b', key: 'paneView' } as const, null)
const paneSeatsAtom = atom({ plugin: 'm2b', key: 'paneSeats' } as const, {})
const toastedRunAtom = atom({ plugin: 'm2b', key: 'bandToastedRun' } as const, null)
const ownPromptsAtom = atom({ plugin: 'm2b', key: 'ownPrompts' } as const, [])
// `session.ts` names the same two values and writes them too: a module's reads and writes are
// listed from its own source, so each module that touches a value names it itself.
const sessionAtom = atom({ plugin: 'm2b', key: 'bandSession' } as const, null)
const notesAtom = atom({ plugin: 'm2b', key: 'sessionNotes' } as const, null)
const sessionNoticeAtom = atom({ plugin: 'm2b', key: 'sessionNotice' } as const, null)

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
// How long `/m2b` waits for a fresh look before it shows what it holds.
const COMMAND_WAITS_MS = 2_000
// Read by `m2b doctor`: the core cannot see whether Claude Code loaded this module.
const SEEN_FILE = '.local/state/m2b/band-seen.json'
const MANIFEST = '.claude-plugin/plugin.json'

const BAND_ANSWER = ['band', '--json'] as const
// The second look before a keep or drop needs the tasks alone, not the status and its probes.
const TASKS_ANSWER = ['band', '--json', '--tasks-only'] as const

/**
 * What one answer of `m2b band --json` draws: the band's rows, the status line, and the version of
 * the installed core, which is the version the launcher runs.
 */
type BandView = {
  snapshot: BandSnapshot
  status: string
  version: string | null
  run?: BandRun | null
  proposals?: BandProposals
}

/** Runs jobs one after another, in the order they were queued. */
function serialQueue(): <T>(job: () => Promise<T>) => Promise<T> {
  let tail: Promise<unknown> = Promise.resolve()
  return job => {
    const run = tail.then(job)
    tail = run.catch(() => undefined)
    return run
  }
}

/** One call for everything the band and the status line show; whatever fails, it answers a view. */
async function loadView($: EngineInterface, answer: readonly string[] = BAND_ANSWER): Promise<BandView> {
  const outcome = await runM2b($, answer, BAND_TIMEOUT_MS)
  if (!outcome.ok) {
    return {
      snapshot: failed(`m2b could not read the tasks: ${outcome.error}`),
      status: COULD_NOT_LOOK,
      version: null,
    }
  }
  let parsed: unknown
  try {
    parsed = JSON.parse(outcome.stdout)
  } catch {
    return { snapshot: failed('m2b band answered something that is not JSON'), status: COULD_NOT_LOOK, version: null }
  }
  const fields = isObject(parsed) ? parsed : {}
  return {
    snapshot: snapshotOf(fields['tasks']),
    status: statusLine(fields['status'], await $.clock.now()),
    version: typeof fields['version'] === 'string' ? fields['version'] : null,
    run: runOf(fields['status']),
    proposals: parseProposals(fields['proposals']),
  }
}

function snapshotOf(part: unknown): BandSnapshot {
  try {
    const tasks = parseBandTasks(part)
    return typeof tasks === 'string'
      ? failed(`m2b could not read the tasks: ${tasks}`)
      : { candidates: tasks.candidates, review: tasks.review, error: null, ...(tasks.due === undefined ? {} : { due: tasks.due }) }
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

async function loadNow($: EngineInterface, isForced: boolean): Promise<void> {
  const view = await shared($, 'view', () => loadView($), isView, isForced)
  // m2b can stop being set up while the call ran; its answer must not draw the band back.
  if (!(await isSetUp($))) {
    await clearBand($)
    return
  }
  await update($, snapshotAtom, () => view.snapshot)
  await update($, versionNoticeAtom, () => versionNotice(view.version))
  // An answer a session without the pane stored has no run; it leaves the run line as it was.
  await update($, runAtom, current => (view.run === undefined ? current : view.run))
  // Nor has an answer a session without proposals stored, or one m2b could not give, a word on them.
  await update($, proposalsAtom, current => view.proposals ?? current)
  $.ui.status(plainLine(view.status))
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
    $.ui.toast(`m2b: the curation run of ${minute(startedAt)} failed; its review task says why, and /m2b-review shows it`, {
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
  return `this session runs the band of m2b ${loadedVersion} while m2b ${installed} is installed: run /reload-plugins`
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

function isView(value: unknown): value is BandView {
  return (
    isObject(value) &&
    isSnapshot(value['snapshot']) &&
    typeof value['status'] === 'string' &&
    (value['version'] === null || typeof value['version'] === 'string') &&
    // Absent in an answer a session without the pane stored: no run to show, like null.
    (value['run'] === undefined || value['run'] === null || isRun(value['run'])) &&
    (value['proposals'] === undefined || isProposals(value['proposals']))
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
    (value['due'] === undefined || (Array.isArray(value['due']) && value['due'].every(isDueTask)))
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
  await update($, versionNoticeAtom, () => null)
  await update($, runAtom, () => null)
  await update($, proposalsAtom, () => null)
  await update($, proposalsNoticeAtom, () => null)
  await turnTo($, null)
  await update($, sessionAtom, () => null)
  await update($, sessionNoticeAtom, () => null)
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
    notice: await read($, sessionNoticeAtom),
    snapshot: await read($, snapshotAtom),
    proposals: await read($, proposalsAtom),
    presses: await read($, pressesAtom),
  }
}

/**
 * Turns the open pane to another of its views, as a dialog, and reads the band again behind it. A
 * pane that opened by itself does not close on Escape; opened anew it does, and Escape on the view
 * leads back to the one the pane starts in.
 */
async function turnPane($: EngineInterface, view: PaneView): Promise<void> {
  await asDialog($, view)
  $.clock.after(0, inBackground($, () => refresh($, true)))
}

async function asDialog($: EngineInterface, view: PaneView): Promise<void> {
  await turnTo($, view)
  try {
    await $.ui.open(AS_A_DIALOG)
  } catch {
    // The view is turned all the same; the button above it leads back.
  }
}

/**
 * The one way the pane's view changes, null for the view it starts in: whatever turns the pane
 * away from a topic drops that topic's lines with it, so no way out of the view can keep them.
 */
async function turnTo($: EngineInterface, view: PaneView | null): Promise<void> {
  forgetTopicUnless(view)
  await update($, paneViewAtom, () => view)
}

/**
 * Turns the pane to one topic and reads its lines from the distillate as it is now. The lines are
 * kept by the module that draws them, never in the session's state, and only for the press that
 * asked: after `back`, a close, another view or a press on another topic nothing is kept for this
 * one, and an answer that arrives then is dropped.
 */
async function showTopic($: EngineInterface, name: string): Promise<void> {
  const press = await newPressToken($)
  beginTopic(press)
  await asDialog($, { kind: 'topic', name, press, isRead: false })
  if (fillTopic(press, await readTopic($, name))) {
    // The lines are the module's; this write is what draws the pane again.
    await update($, paneViewAtom, view => (view !== null && view.kind === 'topic' && view.press === press ? { ...view, isRead: true } : view))
  }
}

// Where the pane's last drawing sat on each surface, as that surface said. The module's own: after
// a reload of the mod the pane is drawn anew before the person can act on it. The band draws by
// the copy in the session's state, which draws it again when a seat changes.
const paneSeats = new Map<string, string>()
// How often the map changed, and the change the session's state is known to hold. They differ
// while a write is under way or after one failed; of two writes that overlap, the later may fail
// while the earlier lands, so each write counts for the change it started from.
let seatsNoted = 0
let seatsShared = 0

/**
 * Keeps where the pane was just drawn on a surface, and hands a new seat to the band a moment
 * later: no state is written while a drawing is made. A write that failed is made again with the
 * pane's next drawing, so the band does not keep a seat the pane has left.
 */
function noteSeat($: EngineInterface, surface: string, placement: string): void {
  if (paneSeats.get(surface) !== placement) {
    paneSeats.set(surface, placement)
    seatsNoted += 1
  } else if (seatsShared === seatsNoted) {
    return
  }
  try {
    $.clock.after(0, () => {
      shareSeats($).catch(() => undefined)
    })
  } catch {
    // The pane's next drawing tries again.
  }
}

async function shareSeats($: EngineInterface): Promise<void> {
  const noted = seatsNoted
  await update($, paneSeatsAtom, () => Object.fromEntries(paneSeats))
  seatsShared = Math.max(seatsShared, noted)
}

/** The pane is gone: the seat of an earlier drawing no longer says where it sits. */
async function forgetSeats($: EngineInterface): Promise<void> {
  paneSeats.clear()
  seatsNoted += 1
  await shareSeats($)
}

/**
 * After a close of the pane has settled. Gone, it sits nowhere. A hook beneath may have kept it
 * open: then its seats stand. Either way the state is written, which draws the band again, and the
 * band asks Claude Code itself what is open. Where Claude Code cannot say, the seats go: the band
 * then draws all it has.
 */
async function seatsAfterClose($: EngineInterface): Promise<void> {
  let isStillOpen = false
  try {
    isStillOpen = (await $.ui.panes()).some(pane => pane.id === PANE_ID)
  } catch {
    // Counted as closed.
  }
  await (isStillOpen ? shareSeats($) : forgetSeats($))
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

/**
 * Where the pane stands for the band of `surface`. Claude Code is asked only where the pane was
 * drawn on that surface and has not closed since, which is where the band may step back: the seat
 * says where the pane sat, Claude Code whether it is drawn and shown now, and the pane's view
 * whether it holds the band's rows. A call that fails counts as not in view.
 */
async function sightOn($: EngineInterface, surface: string): Promise<PaneSight> {
  const seat = (await read($, paneSeatsAtom))[surface]
  if (seat === undefined) {
    return 'away'
  }
  const isOnStartView = (await read($, paneViewAtom)) === null
  try {
    return paneSight(
      seat,
      (await $.ui.panes()).find(pane => pane.id === PANE_ID),
      isOnStartView,
    )
  } catch {
    return 'away'
  }
}

/**
 * What the band draws from. How many topics the session was given is looked up only where the
 * pane is not in view, which is where the band has a row for it.
 */
async function bandModel($: EngineInterface, sight: PaneSight): Promise<BandModel> {
  return {
    snapshot: await read($, snapshotAtom),
    proposals: await read($, proposalsAtom),
    notice: await read($, noticeAtom),
    proposalsNotice: await read($, proposalsNoticeAtom),
    versionLine: await read($, versionNoticeAtom),
    presses: await read($, pressesAtom),
    topics: sight === 'away' ? topicsGiven(givenTo(await read($, sessionAtom), await sessionIdOf($))) : 0,
  }
}

// When the person's close last led back to the start view. A second close this soon after it is
// the same key pressed twice.
let wentBackAtMs: number | null = null
const SAME_KEY_TWICE_MS = 500

/**
 * Back to the view the pane starts in, for Escape and the button above the other views. Beside the
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
// starts: one that fails is not made again in the session, and `/m2b` opens the pane. A reload of
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
    // The band draws all the same; /m2b opens the pane.
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
  // that opens the pane in this very moment is retitled without its Escape; `back` still leads out.
  await $.ui.open({ id: PANE_ID, title: PANE_TITLE })
}

function sessionActions($: EngineInterface): SessionActions {
  return {
    ...rowActions($),
    showProposals: () => turnPane($, { kind: 'proposals' }),
    showReview: () => turnPane($, { kind: 'review' }),
    showTopic: name => showTopic($, name),
    switchFolder: async (change, folder) => {
      // What the last press could not write is no longer what the button is about.
      await update($, sessionNoticeAtom, () => null)
      await press($, FOLDER_PRESS, change, folderWrite($, change, folder))
    },
    undoFolder: () => undo($, FOLDER_PRESS),
  }
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
        ? `m2b could not leave itself out of ${wholePath(folder)}: ${reason}`
        : `m2b could not turn the distillate on under ${wholePath(folder)}: ${reason}`
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
 */
async function press(
  $: EngineInterface,
  id: string,
  action: BandPress['action'],
  write: PressWrite,
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
      await update($, snapshotAtom, () => failed(`m2b could not ${verbOf(action)} "${candidate.title}": ${String(error)}`))
      return false
    }
  }
}

async function settleNow($: EngineInterface, candidate: BandCandidate, action: BandSettle): Promise<boolean> {
  await update($, noticeAtom, () => null)
  const { snapshot } = await loadView($, TASKS_ANSWER)
  if (snapshot.error !== null) {
    await update($, snapshotAtom, () => snapshot)
    return false
  }
  const current = snapshot.candidates
  const fresh = snapshot.review
  // `ok` on the review closes it the way keep closes a candidate.
  if (!current.some(open => open.id === candidate.id) && fresh?.id !== candidate.id) {
    await update($, noticeAtom, () => `Already settled in another session, nothing written: ${candidate.title}`)
    await update($, snapshotAtom, old => (old === null ? old : { ...old, candidates: current, review: fresh }))
    return false
  }
  // A run that ended since the review was drawn rewrote it under the same id: what was pressed on
  // is not what would be closed.
  if (fresh !== null && fresh.id === candidate.id && isOtherReview(candidate, fresh)) {
    await update($, noticeAtom, () => `The review changed since it was drawn, nothing written: ${candidate.title}`)
    await update($, snapshotAtom, old => (old === null ? old : { ...old, candidates: current, review: fresh }))
    return false
  }
  // `--`: with the markdown backend a task id is a file name, and it may start with a dash.
  const outcome = await runM2b($, ['tasks', action, '--', candidate.id], WRITE_TIMEOUT_MS)
  if (!outcome.ok) {
    await update($, snapshotAtom, () => failed(`m2b could not ${verbOf(action)} "${candidate.title}": ${outcome.error}`))
    return false
  }
  return true
}

/** Whether the review pressed on holds other findings than the one read now; unknown counts as the same. */
function isOtherReview(pressed: BandCandidate, fresh: BandReview): boolean {
  const findings = (pressed as Partial<BandReview>).findings
  return Array.isArray(findings) && findings.join('\n\n') !== fresh.findings.join('\n\n')
}

function rowActions($: EngineInterface): RowActions {
  return {
    press: (candidate, action) => press($, candidate.id, action, taskWrite($, candidate, action)),
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
    answer: (proposal, action) => press($, pressKey(proposal.id), action, proposalWrite($, [proposal], action)),
    keepAll: proposals =>
      press(
        $,
        KEEP_ALL,
        'complete',
        proposalWrite($, proposals, 'complete'),
        proposals.map(proposal => proposal.id),
      ),
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

/** `show` in the band: a button has no answer to put the proposals in, so the band says where they are listed. */
async function showFromBand($: EngineInterface): Promise<void> {
  const [answer] = (await showProposals($)).split('\n')
  if (answer !== undefined && answer !== PROPOSALS_PLACED) {
    await update($, noticeAtom, () => `${answer}; m2b proposals lists them in a shell`)
  }
}

/**
 * `show` on the band's row for this session: the pane opens in the view it starts in, as the
 * person's own open, so it is placed at any width, and asks again what the session was given.
 * `staysOpen` where the band is drawn under the fullscreen layout at a width that docks a pane.
 * A button has no answer to put the lines in, so where no pane can be shown the band names the
 * command that answers with them.
 */
async function showSessionFromBand($: EngineInterface, staysOpen: boolean): Promise<void> {
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

function bandActions($: EngineInterface, staysOpen: boolean): BandActions {
  return {
    ...rowActions($),
    showProposals: () => showFromBand($),
    showSession: () => showSessionFromBand($, staysOpen),
  }
}

function verbOf(action: BandSettle): string {
  return action === 'complete' ? 'keep' : 'drop'
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
    // A reload starts this module over while the pane stays up: the seats in the session's state
    // stand until the pane is drawn again, and the band asks Claude Code before it goes by one.
    // Seats this module holds, of drawings before this start, are handed over once more.
    if (paneSeats.size > 0) {
      try {
        await shareSeats($)
      } catch {
        // The session starts all the same, and the pane's next drawing tries again.
      }
    }
    await carryPressesOver($)
    // A reload of the mod took the lines of a topic with the old module: the pane starts over.
    if ((await read($, paneViewAtom))?.kind === 'topic') {
      await turnTo($, null)
    }
    loadedVersion = await readLoadedVersion($)
    askCoreAgain()
    for (const command of [SESSION_COMMAND, NOTE_COMMAND, REVIEW_COMMAND, SEARCH_COMMAND, PROPOSALS_COMMAND]) {
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
    const text = await showInPane($, 'the last curation run is in the m2b pane', () => reviewLines(snapshot, run))
    return { text }
  })

  on('command.run', { command: PROPOSALS_COMMAND.name }, async ($, e, next) => {
    if (await isCurationRun($)) {
      return next(e)
    }
    const notReady = await notSetUpLine($, 'not shown')
    return { text: notReady ?? (await showProposals($)) }
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
    return { text: await showInPane($, `${summary} in the m2b pane`, () => [summary, ...searchLines(search)]) }
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
    verdictFor($, e, await next(e), SEARCH_COMMAND_LINE),
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
      return next(e)
    }
    const nowMs = await $.clock.now()
    const isOnStartView = (await read($, paneViewAtom)) === null
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
    // Once the close has settled, the seats go and the band draws its rows again. Not awaited:
    // asked from inside the pane's own close, Claude Code may still list the pane.
    $.clock.after(0, () => {
      seatsAfterClose($).catch(() => undefined)
    })
    return result
  }).catch(async ($, e, next) => {
    // The pane closes without its view being turned: a topic's lines go all the same, and so do
    // the seats, which the pane's next drawing notes anew.
    forgetTopicUnless(null)
    await forgetSeats($).catch(() => undefined)
    return next(e)
  })

  on('ui.render', { component: 'Pane', requestId: PANE_ID }, async ($, e) => {
    noteSeat($, e.surface, e.props.placement)
    // The small form of the desktop app is read at a glance, whatever view the pane was turned to.
    if (e.props.placement === 'widget') {
      return glancePane($, e, await sessionModel($))
    }
    const view = await read($, paneViewAtom)
    const presses = await read($, pressesAtom)
    if (view === null) {
      return sessionPane($, e, await sessionModel($), sessionActions($))
    }
    const { Box } = $.ui.resolve(e)
    const snapshot = await read($, snapshotAtom)
    const run = await read($, runAtom)
    return (
      <Box flexDirection="column">
        {backRow($, e, () => backToStart($))}
        {view.kind === 'proposals'
          ? proposalsPane($, e, await read($, proposalsAtom), presses, await read($, proposalsNoticeAtom), proposalActions($))
          : view.kind === 'topic'
            ? topicPane($, e, view.name, heldTopic(view.press))
            : paneTree($, e, view, snapshot, run, presses, rowActions($))}
      </Box>
    )
  })

  // The band clears its notice here and keeps the words of the person's own prompt for the note
  // tool; when that throws or overruns, the prompt still enters as typed, through the catch instead
  // of an engine report naming m2b as the failed hook. A prompt not kept only makes a note ask.
  on('prompt.submit', async ($, e, next) => {
    await update($, noticeAtom, () => null)
    await update($, proposalsNoticeAtom, () => null)
    await update($, sessionNoticeAtom, () => null)
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
    // Beside the pane, which holds every row with its buttons, the band is one line at most. Where
    // the pane is not in view, it draws all it has and a row for what this session was given.
    const sight = await sightOn($, e.surface)
    const model = await bandModel($, sight)
    if (sight === 'beside') {
      const line = lineBesidePane(model)
      return line === null ? next(e) : lineRow($, e, line)
    }
    const staysOpen = docksFor({ isFullscreen: e.viewport?.isFullscreen === true, columns: e.viewport?.columns ?? 0 })
    return bandRows($, e, model, bandActions($, staysOpen)) ?? next(e)
  })
}
