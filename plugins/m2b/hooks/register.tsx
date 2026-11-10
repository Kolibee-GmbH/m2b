import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { BandCandidate, BandSnapshot } from '../types'
import { launcherPath, m2bHome, machineConfigPath, runM2b } from './m2b'
import { shared } from './shared-cache'
import { COULD_NOT_LOOK, statusLine } from './status-line'
import { parseBandTasks } from './tasks'

const snapshotAtom = atom({ plugin: 'm2b', key: 'bandSnapshot' } as const, null)
const noticeAtom = atom({ plugin: 'm2b', key: 'bandNotice' } as const, null)
const busyAtom = atom({ plugin: 'm2b', key: 'bandIsBusy' } as const, false)

const REFRESH_EVERY_MS = 60_000
// `m2b band` reaches and reads the task list (two Apple Reminders calls, 20 seconds each by
// default) and, at most every five minutes, probes the calendar within 10 seconds.
const BAND_TIMEOUT_MS = 90_000
// A drop on Apple Reminders is three calls (find, edit the notes, complete), 20 seconds each by default.
const WRITE_TIMEOUT_MS = 90_000
// Read by `m2b doctor`: the core cannot see whether Claude Code loaded this module.
const SEEN_FILE = '.local/state/m2b/band-seen.json'
const CANDIDATES_SHOWN = 3
const FINDINGS_SHOWN = 3

const BAND_ANSWER = ['band', '--json'] as const
// The second look before a keep or drop needs the tasks alone, not the status and its probes.
const TASKS_ANSWER = ['band', '--json', '--tasks-only'] as const

/** What one answer of `m2b band --json` draws: the band's rows and the status line. */
type BandView = { snapshot: BandSnapshot; status: string }

type Settle = 'complete' | 'drop'

type Job = () => Promise<void>

/** Runs jobs one after another, in the order they were queued. */
function serialQueue(): (job: Job) => Promise<void> {
  let tail: Promise<void> = Promise.resolve()
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
    return { snapshot: failed(`m2b could not read the tasks: ${outcome.error}`), status: COULD_NOT_LOOK }
  }
  let parsed: unknown
  try {
    parsed = JSON.parse(outcome.stdout)
  } catch {
    return { snapshot: failed('m2b band answered something that is not JSON'), status: COULD_NOT_LOOK }
  }
  const fields = typeof parsed === 'object' && parsed !== null ? (parsed as Record<string, unknown>) : {}
  return { snapshot: snapshotOf(fields['tasks']), status: statusLine(fields['status'], await $.clock.now()) }
}

function snapshotOf(part: unknown): BandSnapshot {
  try {
    const tasks = parseBandTasks(part)
    return typeof tasks === 'string'
      ? failed(`m2b could not read the tasks: ${tasks}`)
      : { candidates: tasks.candidates, review: tasks.review, error: null }
  } catch (error) {
    return failed(String((error as Error).message))
  }
}

// Everything that reads or writes the band's rows goes through one queue, so a reload that read
// the tasks before a keep or drop can never land after it. A reload asked for while one waits to
// start is that same reload; asked for while one runs, it queues another, read after the request.
const bandJobs = serialQueue()
let reloadWaiting: Promise<void> | null = null

/** With `isForced` (after this session wrote), the band reads itself, never another session's answer. */
function reload($: EngineInterface, isForced = false): Promise<void> {
  if (isForced) {
    return bandJobs(() => loadNow($, true))
  }
  reloadWaiting ??= bandJobs(() => loadNow($, false))
  return reloadWaiting
}

async function loadNow($: EngineInterface, isForced: boolean): Promise<void> {
  if (!isForced) {
    reloadWaiting = null
  }
  const view = await shared($, 'view', () => loadView($), isView, isForced)
  await update($, snapshotAtom, () => view.snapshot)
  $.ui.status(view.status)
}

function isView(value: unknown): value is BandView {
  return (
    typeof value === 'object' &&
    value !== null &&
    'snapshot' in value &&
    isSnapshot(value.snapshot) &&
    'status' in value &&
    typeof value.status === 'string'
  )
}

function isSnapshot(value: unknown): value is BandSnapshot {
  return (
    typeof value === 'object' &&
    value !== null &&
    'candidates' in value &&
    Array.isArray(value.candidates) &&
    'review' in value &&
    (value.review === null || (typeof value.review === 'object' && 'findings' in value.review)) &&
    'error' in value &&
    (value.error === null || typeof value.error === 'string')
  )
}

async function clearBand($: EngineInterface): Promise<void> {
  await update($, snapshotAtom, () => null)
  await update($, noticeAtom, () => null)
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
  void reload($, isForced)
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

/** Takes the busy flag unless another press holds it; `update` retries on a concurrent write. */
async function claimBusy($: EngineInterface): Promise<boolean> {
  let isClaimed = false
  await update($, busyAtom, isBusy => {
    isClaimed = !isBusy
    return true
  })
  return isClaimed
}

/**
 * Completes or drops a candidate, after reading the list again: a candidate another session
 * settled meanwhile is left alone, and the band says so.
 */
async function settle($: EngineInterface, candidate: BandCandidate, action: Settle): Promise<void> {
  if (!(await claimBusy($))) {
    return
  }
  let isWritten = false
  try {
    await bandJobs(async () => {
      isWritten = await settleNow($, candidate, action)
    })
  } finally {
    await update($, busyAtom, () => false)
  }
  if (isWritten) {
    await reload($, true)
  }
}

async function settleNow($: EngineInterface, candidate: BandCandidate, action: Settle): Promise<boolean> {
  await update($, noticeAtom, () => null)
  const { snapshot } = await loadView($, TASKS_ANSWER)
  if (snapshot.error !== null) {
    await update($, snapshotAtom, () => snapshot)
    return false
  }
  const current = snapshot.candidates
  if (!current.some(open => open.id === candidate.id)) {
    await update($, noticeAtom, () => `Already settled in another session, nothing written: ${candidate.title}`)
    await update($, snapshotAtom, snapshot => (snapshot === null ? snapshot : { ...snapshot, candidates: current }))
    return false
  }
  const outcome = await runM2b($, ['tasks', action, candidate.id], WRITE_TIMEOUT_MS)
  if (!outcome.ok) {
    const verb = action === 'complete' ? 'keep' : 'drop'
    await update($, snapshotAtom, () => failed(`m2b could not ${verb} "${candidate.title}": ${outcome.error}`))
    return false
  }
  return true
}

function failed(error: string): BandSnapshot {
  return { candidates: [], review: null, error }
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
    $.clock.every(REFRESH_EVERY_MS, () => void refresh($))
    $.clock.after(0, () => void refresh($))
    void noteSeen($)
    return result
  })

  on('turn.complete', async ($, e, next) => {
    const result = await next(e)
    if (e.agentId === undefined && !(await isCurationRun($))) {
      $.clock.after(0, () => void refresh($, true))
    }
    return result
  })

  // The band only clears its notice here; when that throws or overruns, the prompt still enters
  // as typed, through the catch instead of an engine report naming m2b as the failed hook.
  on('prompt.submit', async ($, e, next) => {
    await update($, noticeAtom, () => null)
    return next(e)
  }).catch(($, e, next) => next(e))

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    if (e.props.hasSurvey) {
      return next(e)
    }
    const snapshot = await read($, snapshotAtom)
    const notice = await read($, noticeAtom)
    const isBusy = await read($, busyAtom)
    if (snapshot === null && notice === null) {
      return next(e)
    }
    const candidates = snapshot?.candidates ?? []
    const review = snapshot?.review ?? null
    const error = snapshot?.error ?? null
    if (candidates.length === 0 && review === null && error === null && notice === null) {
      return next(e)
    }

    const { Box, Button, Text } = $.ui.resolve(e)
    const moreCandidates = andMore(candidates.length - CANDIDATES_SHOWN, 'candidates')
    const findings = review?.findings ?? []
    const moreFindings = andMore(findings.length - FINDINGS_SHOWN, 'findings')

    return (
      <Box flexDirection="column">
        {error !== null && (
          <Text color="error" wrap="truncate-end">
            {error}
          </Text>
        )}
        {candidates.slice(0, CANDIDATES_SHOWN).map(candidate => (
          <Box key={`row:${candidate.id}`} flexDirection="row">
            <Button
              key={`keep:${candidate.id}`}
              label="keep"
              onPress={() => settle($, candidate, 'complete')}
            />
            <Text> </Text>
            <Button
              key={`drop:${candidate.id}`}
              label="drop"
              onPress={() => settle($, candidate, 'drop')}
            />
            <Text wrap="truncate-end"> {candidate.title}</Text>
          </Box>
        ))}
        {moreCandidates !== null && <Text dimColor>{moreCandidates}</Text>}
        {review !== null && (
          <Text weight="semibold" wrap="truncate-end">
            {review.title}
          </Text>
        )}
        {findings.slice(0, FINDINGS_SHOWN).map(finding => (
          <Text wrap="truncate-end">
            {'  '}
            {finding}
          </Text>
        ))}
        {moreFindings !== null && <Text dimColor>{`  ${moreFindings}`}</Text>}
        {isBusy && <Text dimColor>working…</Text>}
        {notice !== null && (
          <Text color="warning" wrap="truncate-end">
            {notice}
          </Text>
        )}
      </Box>
    )
  })
}
