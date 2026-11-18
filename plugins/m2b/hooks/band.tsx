import type { ElementTable, EngineInterface, ResolveInput } from 'claude-code'

import type { BandDueTask, BandHealth, BandProposals, BandSession, BandSnapshot } from '../types'
import { M2B, button, dueCounts, handedInCount, styleOf, taskLine, topicsCount, waitForYou } from './look'
import type { Tone } from './look'
import { plainLine } from './plain-text'
import { couldNotLookLine, errorBesideTasks } from './proposals'
import { dueFirst, waitCount } from './session-view'
import { SHOWS_BY_DEFAULT } from './tasks'

/*
 * What the band draws: one row, in m2b's name, that says how many things wait for an answer and
 * has one button, which shows the pane. Everything that is answered, and every row with a button
 * that writes, is in the pane: the person can fold the band away, and nothing may stand only
 * there. What sessions handed in is counted beside what waits: it waits for a curation run, and
 * the row is where the person sees that a run is worth starting. The tasks due are in the row
 * as counts, below it by name, or not in the band at all, as the machine's `band.due_tasks`
 * says, and the count of topics only with `band.topics` on.
 *
 * Where the row stands is the machine's `band.place`. Above the prompt it is always there, calm
 * while it has nothing to say, so the pane is one press away in every session; or it is there only
 * while something waits. Below the prompt it is the end of the hint line: the same pieces after
 * the engine's own text, on one line, so the tasks are counted there and never listed.
 */

const DUE_SHOWN = 3
// Cells between m2b's name, the pieces of the row and its button.
const ROW_GAP = 2
// Between two pieces of a row, inside the one text they are.
const PIECE_GAP = '  '
/** The key of the band's one button. */
export const OPEN = 'open'
const OPEN_LABEL = 'open'
// As Claude Code draws a button: its label between brackets.
const BUTTON_CELLS = `[ ${OPEN_LABEL} ]`.length
// What the engine keeps free before the line below the prompt.
const HINT_MARGIN = 2
// Before the hint the engine draws the label of the session's mode, which no hook is handed and
// whose width a mod is not told. A tree wider than the line has room for squeezes that label
// onto two lines, so the room is counted with the widest one, `bypass permissions on` with its
// sign and the dot after it. What follows a label (`(shift+tab to cycle)`) is part of the hint.
const MODE_CELLS = 27
// In place of the counts a row below the prompt has no room for.
const MORE: BandPart = { text: '…', tone: 'quiet' }

/**
 * Everything the band draws from. `topics` is the number of topics m2b gave this session, `notice`
 * why the band's own button showed no pane, `health` how m2b itself stands, null before it said so.
 */
export type BandModel = {
  snapshot: BandSnapshot | null
  proposals: BandProposals | null
  notice: string | null
  topics: number
  health: BandHealth | null
}

/** A piece of the band's row, and what it is. */
export type BandPart = { text: string; tone: Tone }

/**
 * The band's row: its pieces in the order drawn, and the tasks listed by name below it.
 * `isNamed` is false where the row is a sentence that names m2b itself. `isCalm` where the row has
 * nothing to say and is there as the way into the pane: its name and its button step back.
 */
export type BandLine = { parts: BandPart[]; isNamed: boolean; isCalm: boolean; listed: BandDueTask[]; more: number }

const CALM: BandLine = { parts: [], isNamed: true, isCalm: true, listed: [], more: 0 }

/**
 * How many topics the band counts. A session that was given none, that m2b has not looked at or
 * holds no note of, and a look that failed count none: the pane says which of these it is.
 */
export function topicsGiven(given: BandSession | null): number {
  return given !== null && given.error === null && given.known ? given.topics.length : 0
}

function sentence(text: string, tone: Tone): BandLine {
  const line = plainLine(text)
  return { parts: [{ text: line, tone }], isNamed: !line.startsWith(`${M2B} `), isCalm: false, listed: [], more: 0 }
}

/**
 * The proposals sessions handed in that wait for a curation run, as a piece of the row. At full
 * strength on the machine that curates, where `curate now` in the pane starts that run; stepped
 * back on every other one and where m2b has not said which machine curates. None while a run is
 * under way, which takes them in, and none where m2b could not count them: the pane says that.
 */
function handedInParts(model: BandModel): BandPart[] {
  const count = model.proposals?.handedIn ?? 0
  if (count === 0 || model.health?.isCurating === true) {
    return []
  }
  return [{ text: handedInCount(count), tone: model.health?.curates === true ? 'plain' : 'quiet' }]
}

/** Whether the band is the end of the hint line below the prompt; above the prompt until m2b's answer says where. */
export function standsBelow(model: BandModel): boolean {
  return (model.snapshot?.shows ?? SHOWS_BY_DEFAULT).place === 'below'
}

/**
 * What the band's row says, or null where the band draws nothing. First why its own button showed
 * no pane: a press that did nothing is said where it was pressed. Then what keeps m2b from
 * counting, the task list or the store it could not read. Else the counts: what waits for an
 * answer, what sessions handed in for the next curation run, the tasks due as the machine shows
 * them, the topics where it shows them. With none of these the row is calm, or there is none:
 * before m2b's first answer, and on a machine whose band is there only while something waits.
 */
export function bandLine(model: BandModel): BandLine | null {
  const { snapshot, proposals } = model
  if (model.notice !== null) {
    return sentence(model.notice, 'trouble')
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
  const waiting = waitCount(snapshot, proposals)
  // The hint line is one line: a machine that lists the tasks counts them there.
  const dueTasks = shows.place === 'below' && shows.dueTasks === 'list' ? 'count' : shows.dueTasks
  const parts: BandPart[] = [
    ...(waiting > 0 ? [{ text: waitForYou(waiting), tone: 'waits' as const }] : []),
    ...handedInParts(model),
    ...(dueTasks === 'count' ? dueCounts(due) : []),
    ...(shows.topics && model.topics > 0 ? [{ text: topicsCount(model.topics), tone: 'quiet' as const }] : []),
  ]
  const listed = dueTasks === 'list' ? dueFirst(due).slice(0, DUE_SHOWN) : []
  if (parts.length === 0 && listed.length === 0) {
    return snapshot === null || shows.place === 'waiting' ? null : CALM
  }
  return { parts, isNamed: true, isCalm: false, listed, more: dueTasks === 'list' ? due.length - listed.length : 0 }
}

/** The pieces of a row as the one text they are drawn in, two cells apart. */
function piecesOf(ui: Pick<ElementTable, 'Text'>, parts: readonly BandPart[]) {
  const { Text } = ui
  return (
    <Text wrap="truncate-end">
      {parts.map((part, place) => (
        <Text {...styleOf(part.tone)}>{`${place === 0 ? '' : PIECE_GAP}${part.text}`}</Text>
      ))}
    </Text>
  )
}

/**
 * m2b's name before a row, and the row's one button: both stepped back while the row is calm.
 * The name is whole at any width: a row too long for its line cuts its counts, never the name.
 */
function nameOf(ui: Pick<ElementTable, 'Box' | 'Text'>, line: BandLine) {
  const { Box, Text } = ui
  return (
    <Box flexShrink={0}>
      <Text {...styleOf(line.isCalm ? 'quiet' : 'brand')}>{M2B}</Text>
    </Box>
  )
}

function openButton(ui: Pick<ElementTable, 'Button'>, line: BandLine, onOpen: () => void) {
  return button(ui, { key: OPEN, label: OPEN_LABEL, kind: line.isCalm ? 'quiet' : 'default', onPress: onOpen })
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
        {line.isNamed && nameOf(ui, line)}
        {!line.isCalm && piecesOf(ui, line.parts)}
        {openButton(ui, line, onOpen)}
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

// What a terminal draws two cells wide: the East Asian wide and fullwidth letters, and what is an emoji by default.
const WIDE =
  /[\p{Emoji_Presentation}\u1100-\u115F\u2E80-\uA4CF\uAC00-\uD7A3\uF900-\uFAFF\uFE30-\uFE4F\uFF00-\uFF60\uFFE0-\uFFE6\u{20000}-\u{3FFFD}]/u

/** The cells a text takes in a terminal's line. */
function cells(text: string): number {
  return Array.from(text).reduce((sum, character) => sum + (WIDE.test(character) ? 2 : 1), 0)
}

/**
 * The band below the prompt. `row`: m2b draws the hint line, the engine's text and after it the
 * band's row. `tail`: the line stays the engine's, which adds this text at its end, stepped back
 * and cut where the line ends.
 */
export type BelowPrompt = { kind: 'row'; line: BandLine } | { kind: 'tail'; text: string }

/** The row as one text for the engine to add to its line: the counts, and the command that opens the pane. */
function tailOf(line: BandLine, command: string): string {
  const said = line.parts.map(part => part.text)
  if (line.isCalm) {
    return `${M2B} · /${command}`
  }
  if (line.parts.some(part => part.tone === 'trouble')) {
    return `${line.isNamed ? `${M2B} ` : ''}${said.join(' ')}`
  }
  return `${M2B} ${[...said, `/${command}`].join(' · ')}`
}

function cellsOf(parts: readonly BandPart[]): number {
  return parts.length === 0 ? 0 : cells(parts.map(part => part.text).join(PIECE_GAP)) + ROW_GAP
}

/** The most counts from the front that have room, with the mark that some are left out; none where not even the first has. */
function countsWithRoom(parts: readonly BandPart[], room: number): BandPart[] {
  for (let kept = parts.length - 1; kept > 0; kept -= 1) {
    const shown = [...parts.slice(0, kept), MORE]
    if (cellsOf(shown) <= room) {
      return shown
    }
  }
  return []
}

/**
 * How the band stands below the prompt in a line of `columns` cells, after the engine's `hint`.
 * The engine's text is never cut for m2b: the row is drawn only as far as it has room beside the
 * hint and the widest mode label. Of its counts the last go first, what waits last, and `…`
 * stands for those left out. Where not even the first count has room beside it, where a sentence has not
 * all of its room, and where the width is not known (`columns` null), the engine adds m2b's
 * words to its own line and cuts them to the room it has.
 */
export function belowPrompt(line: BandLine, hint: string, columns: number | null, command: string): BelowPrompt {
  const tail: BelowPrompt = { kind: 'tail', text: tailOf(line, command) }
  if (columns === null) {
    return tail
  }
  const name = line.isNamed ? M2B.length + ROW_GAP : 0
  const way = Math.max(BUTTON_CELLS, cells(`/${command}`))
  const room = columns - HINT_MARGIN - MODE_CELLS - cells(hint) - ROW_GAP - name - way
  if (cellsOf(line.parts) <= room) {
    return { kind: 'row', line }
  }
  const isCounts = line.isNamed && line.parts.every(part => part.tone !== 'trouble')
  const counts = isCounts ? countsWithRoom(line.parts, room) : []
  return counts.length === 0 ? tail : { kind: 'row', line: { ...line, parts: counts } }
}

/**
 * The hint line below the prompt with the band at its end: the engine's text, stepped back as the
 * engine draws it, then the row's pieces in their colors and the way into the pane. That is the
 * button where a click can press it, `onOpen`; no key reaches a button below the prompt, and where
 * no click does either (`onOpen` null) the row names the command instead.
 */
export function hintRow(
  $: EngineInterface,
  e: ResolveInput,
  hint: string,
  line: BandLine,
  onOpen: (() => void) | null,
  command: string,
) {
  const ui = $.ui.resolve(e)
  const { Box, Text } = ui
  return (
    <Box key="row:m2b-below" flexDirection="row" columnGap={ROW_GAP}>
      {hint !== '' && <Text {...styleOf('quiet')}>{hint}</Text>}
      {line.isNamed && nameOf(ui, line)}
      {!line.isCalm && piecesOf(ui, line.parts)}
      {onOpen === null ? <Text {...styleOf('quiet')}>{`/${command}`}</Text> : openButton(ui, line, onOpen)}
    </Box>
  )
}
