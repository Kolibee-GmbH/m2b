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
  BandSettle,
  BandSnapshot,
  PaneView,
} from '../types'
import { launcherPath, m2bHome, machineConfigPath, runM2b } from './m2b'
import { NOTE_COMMAND, note } from './note'
import { isInOwnWords, isOwnPrompt, withPrompt } from './own-words'
import {
  PANE_ID,
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
import { plainLine } from './plain-text'
import {
  KEEP_ALL,
  PROPOSALS_COMMAND,
  PROPOSALS_PLACED,
  couldNotLookLine,
  isProposals,
  refusedLine,
  parseProposals,
  pressKey,
  proposalLines,
  proposalsPane,
  proposalsRow,
} from './proposals'
import type { ProposalActions } from './proposals'
import { candidateRow, reviewRow } from './rows'
import type { RowActions } from './rows'
import { shared } from './shared-cache'
import { COULD_NOT_LOOK, statusLine } from './status-line'
import { parseBandTasks, untoldFindings } from './tasks'
import {
  NOTE_COMMAND_LINE,
  NOTE_TOOL,
  NOTE_TOOL_NAME,
  SEARCH_COMMAND_LINE,
  SEARCH_TOOL,
  SEARCH_TOOL_NAME,
  noteTextOf,
  noteTool,
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
const toastedRunAtom = atom({ plugin: 'm2b', key: 'bandToastedRun' } as const, null)
const ownPromptsAtom = atom({ plugin: 'm2b', key: 'ownPrompts' } as const, [])

const REFRESH_EVERY_MS = 60_000
// `m2b band` reaches and reads the task list (two Apple Reminders calls, 20 seconds each by
// default) and, at most every five minutes, probes the calendar within 10 seconds.
const BAND_TIMEOUT_MS = 90_000
// A drop on Apple Reminders is three calls (find, edit the notes, complete), 20 seconds each by default.
const WRITE_TIMEOUT_MS = 90_000
// A press is written only once this is over, so undo takes it back without touching the task list.
const UNDO_WINDOW_MS = 5_000
// Read by `m2b doctor`: the core cannot see whether Claude Code loaded this module.
const SEEN_FILE = '.local/state/m2b/band-seen.json'
const MANIFEST = '.claude-plugin/plugin.json'
const CANDIDATES_SHOWN = 3
const FINDINGS_SHOWN = 3
const DUE_SHOWN = 3

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
      : { candidates: tasks.candidates, review: tasks.review, error: null, due: tasks.due }
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
  await update($, paneViewAtom, () => null)
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
  action: BandSettle,
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
  await update($, paneViewAtom, (): PaneView => ({ kind: 'proposals' }))
  // Opens with what the band holds and reads the proposals again behind it.
  $.clock.after(0, inBackground($, () => refresh($, true)))
  const proposals = await read($, proposalsAtom)
  return showPane($, PROPOSALS_PLACED, () => proposalLines(proposals))
}

/** `show` in the band: a button has no answer to put the proposals in, so the band says where they are listed. */
async function showFromBand($: EngineInterface): Promise<void> {
  const [answer] = (await showProposals($)).split('\n')
  if (answer !== undefined && answer !== PROPOSALS_PLACED) {
    await update($, noticeAtom, () => `${answer}; m2b proposals lists them in a shell`)
  }
}

function verbOf(action: BandSettle): string {
  return action === 'complete' ? 'keep' : 'drop'
}

function failed(error: string): BandSnapshot {
  return { candidates: [], review: null, error }
}

/**
 * Today's tasks first, then the overdue ones, the most recent first: a task left overdue for weeks
 * would otherwise fill the three rows every day.
 */
function dueFirst(due: BandDueTask[]): BandDueTask[] {
  return [...due.filter(task => !task.overdue), ...due.filter(task => task.overdue).reverse()]
}

function andMore(hidden: number, what: string): string | null {
  return hidden > 0 ? `and ${hidden} more ${what}` : null
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    const result = await next(e)
    if (await isCurationRun($)) {
      return result
    }
    // A reload of the mod runs this again and cancels the old module's timers.
    minuteTimer?.cancel()
    for (const timer of [...undoTimers.values(), ...lockTimers.values()]) {
      timer.cancel()
    }
    undoTimers.clear()
    lockTimers.clear()
    await carryPressesOver($)
    loadedVersion = await readLoadedVersion($)
    for (const command of [NOTE_COMMAND, REVIEW_COMMAND, SEARCH_COMMAND, PROPOSALS_COMMAND]) {
      try {
        await $.command.register(command)
      } catch {
        // Without the command the band still runs; the skills note and search the same way.
      }
    }
    for (const tool of [NOTE_TOOL, SEARCH_TOOL]) {
      try {
        await $.tool.register(tool)
      } catch {
        // Without the tool the model runs the skill's command, as where no mod runs.
      }
    }
    minuteTimer = $.clock.every(REFRESH_EVERY_MS, inBackground($, () => refresh($)))
    $.clock.after(0, inBackground($, () => refresh($)))
    void noteSeen($)
    return result
  })

  on('turn.complete', async ($, e, next) => {
    const result = await next(e)
    if (e.agentId === undefined && !(await isCurationRun($))) {
      $.clock.after(0, inBackground($, () => refresh($, true)))
    }
    return result
  })

  on('command.run', { command: NOTE_COMMAND.name }, async ($, e, next) => {
    // Registered only outside a curation run, where nothing would type it; the band stays out of it.
    if (await isCurationRun($)) {
      return next(e)
    }
    const outcome = await note($, e.args, () => isSetUp($))
    if (outcome.isWritten) {
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
    await update($, paneViewAtom, (): PaneView => ({ kind: 'review' }))
    // Opens with what the band holds and reads the run again behind it.
    $.clock.after(0, inBackground($, () => refresh($, true)))
    const [snapshot, run] = [await read($, snapshotAtom), await read($, runAtom)]
    const text = await showPane($, 'the last curation run is in the m2b pane', () => reviewLines(snapshot, run))
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
    await update($, paneViewAtom, (): PaneView => ({ kind: 'search', search }))
    return { text: await showPane($, `${summary} in the m2b pane`, () => [summary, ...searchLines(search)]) }
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

  on('tool.check', { tool: NOTE_TOOL_NAME }, async ($, e, next) => {
    const verdict = await next(e)
    const isOwn = isInOwnWords(noteTextOf(e.input), await read($, ownPromptsAtom))
    return verdictFor($, e, verdict, NOTE_COMMAND_LINE, isOwn)
  })
  on('tool.check', { tool: SEARCH_TOOL_NAME }, async ($, e, next) =>
    verdictFor($, e, await next(e), SEARCH_COMMAND_LINE),
  )

  on('ui.render', { component: 'Pane', requestId: PANE_ID }, async ($, e) => {
    const view = await read($, paneViewAtom)
    const presses = await read($, pressesAtom)
    if (view?.kind === 'proposals') {
      const [proposals, notice] = [await read($, proposalsAtom), await read($, proposalsNoticeAtom)]
      return proposalsPane($, e, proposals, presses, notice, proposalActions($))
    }
    const snapshot = await read($, snapshotAtom)
    const run = await read($, runAtom)
    return paneTree($, e, view, snapshot, run, presses, rowActions($))
  })

  // The band clears its notice here and keeps the words of the person's own prompt for the note
  // tool; when that throws or overruns, the prompt still enters as typed, through the catch instead
  // of an engine report naming m2b as the failed hook. A prompt not kept only makes a note ask.
  on('prompt.submit', async ($, e, next) => {
    await update($, noticeAtom, () => null)
    await update($, proposalsNoticeAtom, () => null)
    if (isOwnPrompt(e)) {
      await update($, ownPromptsAtom, prompts => withPrompt(prompts ?? [], e.text))
    }
    return next(e)
  }).catch(($, e, next) => next(e))

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    if (e.props.hasSurvey) {
      return next(e)
    }
    const snapshot = await read($, snapshotAtom)
    const notice = await read($, noticeAtom)
    const versionLine = await read($, versionNoticeAtom)
    const proposalsNotice = await read($, proposalsNoticeAtom)
    const presses = await read($, pressesAtom)
    const candidates = snapshot?.candidates ?? []
    const review = snapshot?.review ?? null
    const error = snapshot?.error ?? null
    const due = snapshot?.due ?? []
    const proposals = await read($, proposalsAtom)
    const waiting = proposals?.waiting.length ?? 0
    // Beside a task list that could not be read, the store is most often the same reason: one line.
    const proposalsError = error === null ? (proposals?.error ?? null) : null
    const isEmpty =
      candidates.length === 0 && due.length === 0 && review === null && error === null && waiting === 0 && proposalsError === null
    if (isEmpty && notice === null && proposalsNotice === null && versionLine === null) {
      return next(e)
    }

    const { Box, Text } = $.ui.resolve(e)
    const moreCandidates = andMore(candidates.length - CANDIDATES_SHOWN, 'candidates')
    const moreDue = andMore(due.length - DUE_SHOWN, 'due')
    const findings = review === null ? [] : untoldFindings(review)
    const moreFindings = andMore(findings.length - FINDINGS_SHOWN, 'findings')
    const isWriting = Object.values(presses).some(pressed => pressed.phase === 'writing')

    const actions = rowActions($)
    const row = (candidate: BandCandidate) => candidateRow($, e, candidate, presses[candidate.id], actions)

    return (
      <Box flexDirection="column">
        {error !== null && (
          <Text color="error" wrap="truncate-end">
            {plainLine(error)}
          </Text>
        )}
        {candidates.slice(0, CANDIDATES_SHOWN).map(row)}
        {moreCandidates !== null && <Text dimColor>{moreCandidates}</Text>}
        {waiting > 0 && proposalsRow($, e, waiting, () => showFromBand($))}
        {proposalsError !== null && (
          <Text color="error" wrap="truncate-end">
            {couldNotLookLine(proposalsError)}
          </Text>
        )}
        {dueFirst(due).slice(0, DUE_SHOWN).map(task => (
          <Text dimColor wrap="truncate-end">
            {`${task.overdue ? 'overdue' : 'due today'}: ${plainLine(task.title)}`}
          </Text>
        ))}
        {moreDue !== null && <Text dimColor>{moreDue}</Text>}
        {review !== null && reviewRow($, e, review, presses[review.id], actions)}
        {findings.slice(0, FINDINGS_SHOWN).map(finding => (
          <Text wrap="truncate-end">
            {'  '}
            {plainLine(finding)}
          </Text>
        ))}
        {moreFindings !== null && <Text dimColor>{`  ${moreFindings}`}</Text>}
        {(review?.changes?.length ?? 0) > 0 && <Text dimColor>  the whole review: /m2b-review</Text>}
        {isWriting && <Text dimColor>working…</Text>}
        {notice !== null && (
          <Text color="warning" wrap="truncate-end">
            {plainLine(notice)}
          </Text>
        )}
        {proposalsNotice !== null && (
          <Text color="warning" wrap="truncate-end">
            {plainLine(proposalsNotice)}
          </Text>
        )}
        {versionLine !== null && (
          <Text color="warning" wrap="truncate-end">
            {plainLine(versionLine)}
          </Text>
        )}
      </Box>
    )
  })
}
