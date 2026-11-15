import type { EngineInterface, ResolveInput } from 'claude-code'

import type { BandCandidate, BandPress, BandProposals, BandSession, BandSnapshot } from '../types'
import { plainLine } from './plain-text'
import { couldNotLookLine, countLine, errorBesideTasks, proposalsRow } from './proposals'
import { candidateRow, reviewRow } from './rows'
import type { RowActions } from './rows'
import { WAITS_FOR_YOU, dueFirst, dueLine } from './session-view'
import { untoldFindings } from './tasks'

/*
 * What the band above the prompt draws. On its own it is every row with its buttons. Beside the
 * m2b pane, which holds the same rows, it steps back to one line, so nothing stands twice. Where
 * the pane is not in view, it carries one row more: how many topics m2b gave this session, with
 * the button that shows the pane.
 */

const CANDIDATES_SHOWN = 3
const FINDINGS_SHOWN = 3
const DUE_SHOWN = 3

/**
 * Everything the band draws from. `topics` is the number of topics m2b gave this session where the
 * band has a row for it, and 0 where it has none.
 */
export type BandModel = {
  snapshot: BandSnapshot | null
  proposals: BandProposals | null
  notice: string | null
  proposalsNotice: string | null
  versionLine: string | null
  presses: Record<string, BandPress>
  topics: number
}

/** What the band's buttons do: keep, drop and `ok`, and `show` for the proposals and for this session. */
export type BandActions = RowActions & {
  showProposals: () => Promise<void>
  showSession: () => Promise<void>
}

/** The band's one line beside the pane, and how it is drawn. */
export type BandLine = { text: string; tone: 'plain' | 'warning' | 'error' }

/**
 * How many topics the band's row names. A session that was given none, that m2b has not looked at
 * or holds no note of, and a look that failed give no row: the row is a count, a count of nothing
 * would cost a line in every session, and `/m2b-pane` says which of these it is.
 */
export function topicsGiven(given: BandSession | null): number {
  return given !== null && given.error === null && given.known ? given.topics.length : 0
}

/**
 * The band's one line beside the pane, or null for none. First what the pane's start view does not
 * show, so it would be said nowhere: why a press wrote nothing, then that this session runs an
 * older band. Then an error: without the task list there is nothing to count, and it stays where
 * it has always been said, though the start view says it too. Else what needs an answer, as
 * counts: the rows and their buttons are in the pane. The tasks due need no answer and stay there.
 * A row that was pressed counts until its write has landed, as it stays a row until then.
 */
export function lineBesidePane(model: BandModel): BandLine | null {
  const { snapshot, proposals } = model
  const unsaid = model.notice ?? model.proposalsNotice ?? model.versionLine
  if (unsaid !== null) {
    return { text: plainLine(unsaid), tone: 'warning' }
  }
  const error = snapshot?.error ?? null
  if (error !== null) {
    return { text: plainLine(error), tone: 'error' }
  }
  const storeError = errorBesideTasks(error, proposals)
  if (storeError !== null) {
    return { text: couldNotLookLine(storeError), tone: 'error' }
  }
  const candidates = snapshot?.candidates.length ?? 0
  const waiting = proposals?.waiting.length ?? 0
  const waits = [
    ...(candidates > 0 ? [`${candidates} to keep or drop`] : []),
    ...(waiting > 0 ? [countLine(waiting)] : []),
    ...(snapshot?.review ? ['the review'] : []),
  ]
  return waits.length === 0 ? null : { text: `${WAITS_FOR_YOU}: ${waits.join(', ')}`, tone: 'plain' }
}

export function lineRow($: EngineInterface, e: ResolveInput, line: BandLine) {
  const { Text } = $.ui.resolve(e)
  return line.tone === 'plain' ? (
    <Text wrap="truncate-end">{line.text}</Text>
  ) : (
    <Text color={line.tone} wrap="truncate-end">
      {line.text}
    </Text>
  )
}

function andMore(hidden: number, what: string): string | null {
  return hidden > 0 ? `and ${hidden} more ${what}` : null
}

function topicsLine(topics: number): string {
  return `${topics} ${topics === 1 ? 'topic' : 'topics'} given to this session`
}

/** The band on its own: every row with its buttons, or null where there is nothing to draw. */
export function bandRows($: EngineInterface, e: ResolveInput, model: BandModel, actions: BandActions) {
  const { snapshot, proposals, notice, proposalsNotice, versionLine, presses, topics } = model
  const candidates = snapshot?.candidates ?? []
  const review = snapshot?.review ?? null
  const error = snapshot?.error ?? null
  const due = snapshot?.due ?? []
  const waiting = proposals?.waiting.length ?? 0
  const proposalsError = errorBesideTasks(error, proposals)
  const hasRows =
    candidates.length > 0 || due.length > 0 || review !== null || error !== null || waiting > 0 || proposalsError !== null || topics > 0
  if (!hasRows && notice === null && proposalsNotice === null && versionLine === null) {
    return null
  }

  const { Box, Button, Text } = $.ui.resolve(e)
  const moreCandidates = andMore(candidates.length - CANDIDATES_SHOWN, 'candidates')
  const moreDue = andMore(due.length - DUE_SHOWN, 'due')
  const findings = review === null ? [] : untoldFindings(review)
  const moreFindings = andMore(findings.length - FINDINGS_SHOWN, 'findings')
  const isWriting = Object.values(presses).some(pressed => pressed.phase === 'writing')
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
      {waiting > 0 && proposalsRow($, e, waiting, actions.showProposals)}
      {proposalsError !== null && (
        <Text color="error" wrap="truncate-end">
          {couldNotLookLine(proposalsError)}
        </Text>
      )}
      {dueFirst(due).slice(0, DUE_SHOWN).map(task => (
        <Text dimColor wrap="truncate-end">
          {dueLine(task)}
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
      {topics > 0 && (
        <Box key="row:session" flexDirection="row">
          <Button key="show:session" label="show" onPress={actions.showSession} />
          <Text wrap="truncate-end"> {topicsLine(topics)}</Text>
        </Box>
      )}
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
}
