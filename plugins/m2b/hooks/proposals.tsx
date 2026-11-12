import type { CommandSpec, EngineInterface, ResolveInput } from 'claude-code'

import type { BandPress, BandProposal, BandProposals, BandSettle } from '../types'
import { plainLine, writtenOut } from './plain-text'
import { candidateRow } from './rows'

/*
 * What a reading of the sessions proposed for the memory and still waits for an answer: one row in
 * the band with their number, and the m2b pane with each proposal, the person's own words beside
 * it, to keep or drop. Every text of a proposal is drawn written out, never cleaned: what the
 * person keeps is what they were shown.
 */

export const PROPOSALS_COMMAND: CommandSpec = {
  name: 'm2b-proposals',
  description: 'Show what your sessions proposed for your memory in a pane, each to keep or drop',
  immediate: true,
}

export const PROPOSALS_PLACED = 'the proposals from your sessions are in the m2b pane'

/** The key of the press on keep all, beside the keys of the presses on single proposals. */
export const KEEP_ALL = 'proposals:all'

const NO_PROPOSALS: BandProposals = { waiting: [], answered: 0, error: null }

const OTHER_SHAPE = 'm2b answered something other than the proposals that wait'
const NONE_WAITS = 'No proposal waits for an answer.'
// Until the band's first answer about proposals has landed: not known is never "none wait".
const NOT_LOOKED = 'm2b has not looked for proposals yet; m2b proposals lists them in a shell'
const LIST_AND_ANSWER =
  'list with: m2b proposals; keep with: m2b proposals keep <id>... (or keep --all); drop with: m2b proposals drop <id>...'
// As the core makes it. An id goes to `m2b proposals keep` as an argument, so nothing else is one.
const ID = /^[0-9a-f]{12}$/

/** What the pane's buttons do; a press waits for undo like a press on a candidate. */
export type ProposalActions = {
  answer: (proposal: BandProposal, action: BandSettle) => Promise<void>
  keepAll: (proposals: BandProposal[]) => Promise<void>
  undo: (key: string) => Promise<void>
}

/** The key a press on one proposal is kept under; a task of the band's other rows never has it. */
export function pressKey(id: string): string {
  return `proposal:${id}`
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isTextOrNull(value: unknown): value is string | null {
  return value === null || typeof value === 'string'
}

function isProposal(value: unknown): value is BandProposal {
  return (
    isObject(value) &&
    typeof value['id'] === 'string' &&
    ID.test(value['id']) &&
    typeof value['kind'] === 'string' &&
    typeof value['text'] === 'string' &&
    typeof value['quote'] === 'string' &&
    typeof value['day'] === 'string' &&
    isTextOrNull(value['topic']) &&
    isTextOrNull(value['due'])
  )
}

function isCount(value: unknown): value is number {
  return typeof value === 'number' && Number.isInteger(value) && value >= 0
}

/** The whole shape: a session of another m2b version may have written the shared answer. */
export function isProposals(value: unknown): value is BandProposals {
  return (
    isObject(value) &&
    Array.isArray(value['waiting']) &&
    value['waiting'].every(isProposal) &&
    isCount(value['answered']) &&
    isTextOrNull(value['error'])
  )
}

/**
 * The proposals part of `m2b band --json`. A core that does not know proposals leaves the part
 * out, and then none wait; a part of any other shape is could not look, never an empty list.
 */
export function parseProposals(part: unknown): BandProposals {
  if (part === undefined) {
    return NO_PROPOSALS
  }
  if (isObject(part) && typeof part['error'] === 'string') {
    return { ...NO_PROPOSALS, error: part['error'] }
  }
  if (!isObject(part) || !Array.isArray(part['proposals']) || !part['proposals'].every(isProposal) || !isCount(part['answered'])) {
    return { ...NO_PROPOSALS, error: OTHER_SHAPE }
  }
  const waiting = part['proposals'].map(({ id, kind, text, quote, day, topic, due }) => ({ id, kind, text, quote, day, topic, due }))
  return { waiting, answered: part['answered'], error: null }
}

export function countLine(count: number): string {
  return `${count} ${count === 1 ? 'proposal' : 'proposals'} from your sessions`
}

export function couldNotLookLine(error: string): string {
  return `m2b could not look for proposals: ${plainLine(error)}`
}

/** `commitment, due 2026-03-06, topic Northwind`: what kind of thing is proposed, as `m2b proposals` heads it. */
function heading(proposal: BandProposal): string {
  const parts = [writtenOut(proposal.kind)]
  if (proposal.due !== null) {
    parts.push(`due ${writtenOut(proposal.due)}`)
  }
  if (proposal.topic) {
    parts.push(`topic ${writtenOut(proposal.topic)}`)
  }
  return parts.join(', ')
}

function saidLine(proposal: BandProposal): string {
  return `said on ${writtenOut(proposal.day)}: "${writtenOut(proposal.quote)}"`
}

function answeredLine(answered: number): string {
  return `${answered} ${answered === 1 ? 'answer waits' : 'answers wait'} for the next curation run, which files what you kept`
}

/**
 * What the band says when `m2b proposals keep` or `drop` did not answer as pressed: `reason` is
 * m2b's own line. One proposal is named by its text. After keep all, m2b has kept every proposal
 * it could and its line names the one where another answer stands, so the line is given as it is,
 * with the text of each proposal in place of its id, which the pane never showed.
 */
export function refusedLine(proposals: BandProposal[], verb: string, reason: string): string {
  const [only] = proposals
  if (proposals.length === 1 && only !== undefined) {
    return `m2b could not ${verb} "${writtenOut(only.text)}": ${reason}`
  }
  const named = proposals.reduce((line, proposal) => line.split(proposal.id).join(`"${writtenOut(proposal.text)}"`), reason)
  return `${verb} all: ${named}`
}

/**
 * The proposals as lines of text with their ids, for a surface that cannot show the pane. How to
 * list and answer them comes before the proposals: an answer too long to give whole is cut at its
 * end.
 */
export function proposalLines(proposals: BandProposals | null): string[] {
  if (proposals === null) {
    return [NOT_LOOKED]
  }
  const { waiting, answered, error } = proposals
  if (error !== null) {
    return [couldNotLookLine(error)]
  }
  const waits = answered > 0 ? [answeredLine(answered)] : []
  if (waiting.length === 0) {
    return [NONE_WAITS, ...waits]
  }
  return [
    countLine(waiting.length),
    LIST_AND_ANSWER,
    ...waits,
    ...waiting.flatMap(proposal => [
      `${proposal.id}  ${heading(proposal)}`,
      `  ${writtenOut(proposal.text)}`,
      `  ${saidLine(proposal)}`,
    ]),
  ]
}

/** The band's one row for all of them: the number, and `show`, which opens the pane. */
export function proposalsRow($: EngineInterface, e: ResolveInput, count: number, onShow: () => Promise<void>) {
  const { Box, Button, Text } = $.ui.resolve(e)
  return (
    <Box key="row:proposals" flexDirection="row">
      <Button key="show:proposals" label="show" onPress={onShow} />
      <Text wrap="truncate-end"> {countLine(count)}</Text>
    </Box>
  )
}

/**
 * The pane's drawing: each proposal with what it is, the person's words and the day, to keep or
 * drop, and keep all for those not pressed on their own. `notice` is what m2b said to the last
 * answer it refused. Before the band's first answer about proposals, it says that it has not
 * looked.
 */
export function proposalsPane(
  $: EngineInterface,
  e: ResolveInput,
  proposals: BandProposals | null,
  presses: Record<string, BandPress>,
  notice: string | null,
  actions: ProposalActions,
) {
  const { Box, Text } = $.ui.resolve(e)
  if (proposals === null) {
    return <Text wrap="wrap">{NOT_LOOKED}</Text>
  }
  const { waiting, answered, error } = proposals
  const all = presses[KEEP_ALL]
  const inAll = new Set(all?.ids ?? [])
  const pressOf = (proposal: BandProposal): BandPress | undefined =>
    presses[pressKey(proposal.id)] ?? (all !== undefined && inAll.has(proposal.id) ? { ...all, phase: 'writing' } : undefined)
  const unpressed = waiting.filter(proposal => pressOf(proposal) === undefined)
  return (
    <Box flexDirection="column">
      {error === null ? (
        <Text weight="semibold" wrap="wrap">
          {waiting.length === 0 ? NONE_WAITS : countLine(waiting.length)}
        </Text>
      ) : (
        <Text color="error" wrap="wrap">
          {couldNotLookLine(error)}
        </Text>
      )}
      {notice !== null && (
        <Text color="warning" wrap="wrap">
          {plainLine(notice)}
        </Text>
      )}
      {keepAllRow($, e, all, unpressed, actions)}
      {waiting.map(proposal => (
        <Box key={`proposal:${proposal.id}`} flexDirection="column">
          {candidateRow(
            $,
            e,
            { id: proposal.id, title: writtenOut(proposal.text) },
            pressOf(proposal),
            {
              press: (_, action) => actions.answer(proposal, action),
              undo: () => actions.undo(pressKey(proposal.id)),
            },
            'wrap',
          )}
          <Text dimColor wrap="wrap">{`  ${heading(proposal)}`}</Text>
          <Text dimColor wrap="wrap">{`  ${saidLine(proposal)}`}</Text>
        </Box>
      ))}
      {answered > 0 && (
        <Text dimColor wrap="wrap">
          {answeredLine(answered)}
        </Text>
      )}
    </Box>
  )
}

/** Keep all while two or more can still be pressed; once pressed, what it will keep, with undo while it waits. */
function keepAllRow(
  $: EngineInterface,
  e: ResolveInput,
  pressed: BandPress | undefined,
  unpressed: BandProposal[],
  actions: ProposalActions,
) {
  const { Box, Button, Text } = $.ui.resolve(e)
  if (pressed === undefined) {
    return unpressed.length < 2 ? null : (
      <Button key="keep-all" label="keep all" onPress={() => actions.keepAll(unpressed)} />
    )
  }
  const line = `keeping all ${pressed.ids?.length ?? 0} proposals`
  if (pressed.phase === 'waiting') {
    return (
      <Box key="row:keep-all" flexDirection="row">
        <Button key="undo:all" label="undo" onPress={() => actions.undo(KEEP_ALL)} />
        <Text dimColor> {line}</Text>
      </Box>
    )
  }
  return (
    <Text key="row:keep-all" dimColor>
      {line}
    </Text>
  )
}
