import type { CommandSpec, EngineInterface, ResolveInput } from 'claude-code'

import type { BandPress, BandProposal, BandProposals, BandSettle } from '../types'
import { plainLine, writtenOut } from './plain-text'
import { NOT_LOOKED, button, part, pressLine, said, under } from './look'
import { candidateRow } from './rows'

/*
 * What a reading of the sessions proposed for the memory and still waits for an answer: one row
 * with their number in the pane's start view, and under their tab each proposal, what it is and
 * the words it stands on, said or pasted, to keep or drop. Every text of a proposal is drawn
 * written out, never cleaned: what the person keeps is what they were shown.
 */

export const PROPOSALS_COMMAND: CommandSpec = {
  name: 'm2b-proposals',
  description: 'Show what your sessions proposed for your memory in a pane, each to keep or drop',
  immediate: true,
}

export const PROPOSALS_PLACED = 'the proposals from your sessions are in the m2b pane'

/** The key of the press on keep all, beside the keys of the presses on single proposals. */
export const KEEP_ALL = 'proposals:all'
/** The key of `undo` beside keep all, drawn only while that press waits. */
export const UNDO_ALL = 'undo:all'

const NO_PROPOSALS: BandProposals = { waiting: [], answered: 0, error: null }
// Where a quote stands when it was typed, as the core names it.
const TYPED = 'typed'

const OTHER_SHAPE = 'm2b answered something other than the proposals that wait'
const NONE_WAITS = 'No proposal waits for an answer.'
const FROM_YOUR_SESSIONS = 'Proposals from your sessions'
// Until the band's first answer about proposals has landed: not known is never "none wait". For a text, which has no pane to wait in.
const NOT_LOOKED_SAYS_HOW = 'm2b has not looked for proposals yet; m2b proposals lists them in a shell'
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
    isTextOrNull(value['due']) &&
    // An m2b before the field names no source: the words were typed.
    (value['source'] === undefined || typeof value['source'] === 'string') &&
    // Nor does one before a session could hand in name a tool or who proposed.
    (value['tool'] === undefined || isTextOrNull(value['tool'])) &&
    (value['by'] === undefined || isTextOrNull(value['by']))
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
  const waiting = part['proposals'].map(({ id, kind, text, quote, day, topic, due, source, tool, by }) => ({
    id,
    kind,
    text,
    quote,
    day,
    topic,
    due,
    source,
    tool,
    by,
  }))
  return { waiting, answered: part['answered'], error: null }
}

export function countLine(count: number): string {
  return `${count} ${count === 1 ? 'proposal' : 'proposals'} from your sessions`
}

export function couldNotLookLine(error: string): string {
  return `m2b could not look for proposals: ${plainLine(error)}`
}

/**
 * Why the proposals could not be looked at, where that is worth a line of its own: beside a task
 * list that could not be read, the store is most often the same reason, so one line says it.
 */
export function errorBesideTasks(tasksError: string | null, proposals: BandProposals | null): string | null {
  return tasksError === null ? (proposals?.error ?? null) : null
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
  if (proposal.by) {
    // Also where its words were typed: an agent worded its text, having read more than those words.
    parts.push(proposal.by === HANDED_IN_BY ? 'handed in by a session' : `proposed by ${writtenOut(proposal.by)}`)
  }
  return parts.join(', ')
}

// Who proposed, where it was no reading of the sessions: a session, by itself.
const HANDED_IN_BY = 'session'

// How the line under a proposal begins for the sources the band knows, as `m2b proposals` begins it.
const LEADS = new Map([
  [TYPED, 'said on'],
  ['pasted', 'pasted on'],
  ['agent', 'Claude wrote on'],
])

/**
 * Where the words a proposal stands on were found: typed words were said, pasted ones are named
 * so, words a tool returned with the tool, and words of an answer as Claude's.
 */
function saidLine(proposal: BandProposal): string {
  // An answer of an m2b before the field, or one a band before it kept, names no source.
  const source = proposal.source ?? TYPED
  const lead =
    source === 'tool'
      ? `in a result of ${proposal.tool ? writtenOut(proposal.tool) : 'a tool'} on`
      : (LEADS.get(source) ?? `from ${writtenOut(source)} on`)
  return `${lead} ${writtenOut(proposal.day)}: "${writtenOut(proposal.quote)}"`
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
    return [NOT_LOOKED_SAYS_HOW]
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

/**
 * The view's drawing, one part: keep all for the proposals not pressed on their own, then each
 * proposal as a row, its text, keep and drop with what it is beside them, and below them the
 * words it stands on, indented whole. `notice` is what m2b said to the last answer it refused,
 * said here, where it was pressed. Before the band's first answer about proposals the part says
 * that m2b has not looked. `columns` is the width of the pane's body.
 */
export function proposalsPane(
  $: EngineInterface,
  e: ResolveInput,
  proposals: BandProposals | null,
  presses: Record<string, BandPress>,
  notice: string | null,
  actions: ProposalActions,
  columns: number,
) {
  const ui = $.ui.resolve(e)
  const { Box } = ui
  const waiting = proposals?.waiting ?? []
  const spec = { key: 'proposals', title: FROM_YOUR_SESSIONS, waits: waiting.length > 0, count: waiting.length > 0 ? String(waiting.length) : null, columns }
  if (proposals === null) {
    return part(ui, spec, [said(ui, NOT_LOOKED, 'quiet')])
  }
  const { answered, error } = proposals
  const all = presses[KEEP_ALL]
  const inAll = new Set(all?.ids ?? [])
  const pressOf = (proposal: BandProposal): BandPress | undefined =>
    presses[pressKey(proposal.id)] ?? (all !== undefined && inAll.has(proposal.id) ? { ...all, phase: 'writing' } : undefined)
  // What no reading proposed is answered one by one: keep all leaves it, as `m2b proposals keep --all` does.
  const unpressed = waiting.filter(proposal => pressOf(proposal) === undefined && !proposal.by)
  return part(ui, spec, [
    error !== null && said(ui, couldNotLookLine(error), 'trouble'),
    notice !== null && said(ui, plainLine(notice), 'trouble'),
    keepAllRow($, e, all, unpressed, actions),
    ...waiting.map(proposal => (
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
          heading(proposal),
        )}
        {under(ui, saidLine(proposal))}
      </Box>
    )),
    error === null && waiting.length === 0 && said(ui, NONE_WAITS, 'quiet'),
    answered > 0 && said(ui, answeredLine(answered), 'quiet'),
  ])
}

/** Keep all while two or more can still be pressed; once pressed, what it will keep, with undo while it waits. */
function keepAllRow(
  $: EngineInterface,
  e: ResolveInput,
  pressed: BandPress | undefined,
  unpressed: BandProposal[],
  actions: ProposalActions,
) {
  const ui = $.ui.resolve(e)
  if (pressed === undefined) {
    return unpressed.length < 2 ? null : button(ui, { key: 'keep-all', label: 'keep all', kind: 'default', onPress: () => actions.keepAll(unpressed) })
  }
  const doing = `keeping all ${pressed.ids?.length ?? 0} proposals`
  if (pressed.phase === 'waiting') {
    return pressLine(ui, [{ key: UNDO_ALL, label: 'undo', kind: 'default', onPress: () => actions.undo(KEEP_ALL) }], doing, 'row:keep-all')
  }
  return said(ui, `${doing}…`, 'quiet')
}
