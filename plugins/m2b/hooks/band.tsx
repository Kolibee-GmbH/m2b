import type { EngineInterface, ResolveInput } from 'claude-code'

import type { BandDueTask, BandProposals, BandSession, BandShows, BandSnapshot } from '../types'
import { M2B, button, dueCounts, styleOf, taskLine, topicsCount, waitForYou } from './look'
import type { Tone } from './look'
import { plainLine } from './plain-text'
import { couldNotLookLine, errorBesideTasks } from './proposals'
import { dueFirst } from './session-view'

/*
 * What the band above the prompt draws: one row, in m2b's name, that says how many things wait for
 * an answer and has one button, which shows the pane. Everything that is answered, and every row
 * with a button that writes, is in the pane: the person can fold the band away, and nothing may
 * stand only there. The tasks due are in the row as counts, below it by name, or not in the band at
 * all, as the machine's `band.due_tasks` says, and the count of topics only with `band.topics` on.
 */

const DUE_SHOWN = 3
// Cells between m2b's name, the pieces of the row and its button.
const ROW_GAP = 2
/** The key of the band's one button. */
export const OPEN = 'open'

/** What the band shows where the answer it draws from names no settings: what a machine without an entry shows. */
export const SHOWS_BY_DEFAULT: BandShows = { dueTasks: 'count', topics: false }

/**
 * Everything the band draws from. `topics` is the number of topics m2b gave this session. The
 * notices are what m2b said to a press that wrote nothing, and `versionLine` that this session
 * runs the band of another m2b version.
 */
export type BandModel = {
  snapshot: BandSnapshot | null
  proposals: BandProposals | null
  notice: string | null
  proposalsNotice: string | null
  versionLine: string | null
  topics: number
}

/** A piece of the band's row, and what it is. */
export type BandPart = { text: string; tone: Tone }

/**
 * The band's row: its pieces in the order drawn, and the tasks listed by name below it.
 * `isNamed` is false where the row is a sentence that names m2b itself.
 */
export type BandLine = { parts: BandPart[]; isNamed: boolean; listed: BandDueTask[]; more: number }

/**
 * How many topics the band counts. A session that was given none, that m2b has not looked at or
 * holds no note of, and a look that failed count none: the pane says which of these it is.
 */
export function topicsGiven(given: BandSession | null): number {
  return given !== null && given.error === null && given.known ? given.topics.length : 0
}

function sentence(text: string, tone: Tone): BandLine {
  const line = plainLine(text)
  return { parts: [{ text: line, tone }], isNamed: !line.startsWith(`${M2B} `), listed: [], more: 0 }
}

/**
 * What the band's row says, or null where the band draws nothing. First what a press could not
 * write, then that this session runs an older band: both would be said nowhere else. Then what
 * keeps m2b from counting, the task list or the store it could not read. Else the counts: what
 * waits for an answer, the tasks due as the machine shows them, the topics where it shows them.
 * A row that was pressed counts until its write has landed.
 */
export function bandLine(model: BandModel): BandLine | null {
  const { snapshot, proposals } = model
  const refused = model.notice ?? model.proposalsNotice
  if (refused !== null) {
    return sentence(refused, 'trouble')
  }
  if (model.versionLine !== null) {
    return sentence(model.versionLine, 'waits')
  }
  const tasksError = snapshot?.error ?? null
  if (tasksError !== null) {
    return sentence(tasksError, 'trouble')
  }
  const storeError = errorBesideTasks(tasksError, proposals)
  if (storeError !== null) {
    return sentence(couldNotLookLine(storeError), 'trouble')
  }
  const shows = snapshot?.shows ?? SHOWS_BY_DEFAULT
  const due = snapshot?.due ?? []
  const waiting = (snapshot?.candidates.length ?? 0) + (proposals?.waiting.length ?? 0) + (snapshot?.review ? 1 : 0)
  const parts: BandPart[] = [
    ...(waiting > 0 ? [{ text: waitForYou(waiting), tone: 'waits' as const }] : []),
    ...(shows.dueTasks === 'count' ? dueCounts(due) : []),
    ...(shows.topics && model.topics > 0 ? [{ text: topicsCount(model.topics), tone: 'quiet' as const }] : []),
  ]
  const listed = shows.dueTasks === 'list' ? dueFirst(due).slice(0, DUE_SHOWN) : []
  if (parts.length === 0 && listed.length === 0) {
    return null
  }
  return { parts, isNamed: true, listed, more: shows.dueTasks === 'list' ? due.length - listed.length : 0 }
}

/** The band's drawing: the row with its one button, and below it the tasks the machine lists by name. */
export function bandRow($: EngineInterface, e: ResolveInput, line: BandLine, onOpen: () => void) {
  const ui = $.ui.resolve(e)
  const { Box, Text } = ui
  // Under the pieces of the row, past m2b's name.
  const indent = line.isNamed ? M2B.length + ROW_GAP : 0
  return (
    <Box flexDirection="column">
      <Box key="row:m2b" flexDirection="row" columnGap={ROW_GAP}>
        {line.isNamed && <Text {...styleOf('brand')}>{M2B}</Text>}
        <Text wrap="truncate-end">
          {line.parts.map((part, place) => (
            <Text {...styleOf(part.tone)}>{`${place === 0 ? '' : '  '}${part.text}`}</Text>
          ))}
        </Text>
        {button(ui, { key: OPEN, label: 'open', kind: 'default', onPress: onOpen })}
      </Box>
      {line.listed.length > 0 && (
        <Box key="tasks" flexDirection="column" paddingLeft={indent}>
          {line.listed.map(task => taskLine(ui, task, 'truncate-end'))}
          {line.more > 0 && <Text {...styleOf('quiet')}>{`and ${line.more} more`}</Text>}
        </Box>
      )}
    </Box>
  )
}
