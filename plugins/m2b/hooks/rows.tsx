import type { EngineInterface, ResolveInput } from 'claude-code'

import type { BandCandidate, BandPress, BandReview, BandSettle } from '../types'
import { button, pressLine, row, said } from './look'
import type { ButtonSpec } from './look'
import { plainLine } from './plain-text'

/** The press on `curate now`, the key of that button, and the key of `undo` while the press waits. */
export const CURATE_PRESS = 'curate'
export const CURATE_NOW = 'curate:now'
export const UNDO_CURATE = 'undo:curate'
/** The row that holds the button, in every view that offers it. */
export const CURATE_ROW = 'row:curate'

const STARTING_A_RUN = 'starting a curation run'

/** A curation run now, with its undo. */
export type CurateActions = {
  curateNow: () => Promise<void>
  undoCurate: () => Promise<void>
}

/**
 * The button that starts a curation run now. Like keep and drop the press waits for undo, and
 * while it starts the run there is nothing to press.
 */
export function curateButton($: EngineInterface, e: ResolveInput, pressed: BandPress | undefined, actions: CurateActions) {
  const ui = $.ui.resolve(e)
  if (pressed === undefined) {
    return button(ui, { key: CURATE_NOW, label: 'curate now', kind: 'default', onPress: actions.curateNow })
  }
  return pressed.phase === 'waiting'
    ? pressLine(ui, [{ key: UNDO_CURATE, label: 'undo', kind: 'default', onPress: actions.undoCurate }], STARTING_A_RUN)
    : said(ui, `${STARTING_A_RUN}…`, 'quiet')
}

/** What a row says it does once pressed, by what was pressed. */
const DOING: Partial<Record<BandPress['action'], string>> = { drop: 'dropping', 'every-project': 'keeping for every project' }

/** What a row's buttons do; every view of the pane shares one way of keeping and dropping. */
export type RowActions = {
  press: (candidate: BandCandidate, action: BandSettle) => Promise<void>
  undo: (id: string) => Promise<void>
}

/** What the review is called in the pane, whatever its task is titled in the task list. */
export const REVIEW = 'Review of the last curation run'

/** The key of `undo` on the row of the item `id`, which the row draws only while a press on it waits. */
export function undoKey(id: string): string {
  return `undo:${id}`
}

/**
 * A row that can be answered, in the three states of a press: its buttons; while the press waits,
 * `undo` and what it will do; while it is written, that alone, stepped back. `doing` is the press
 * in a word (`keeping`).
 */
function pressableRow(
  $: EngineInterface,
  e: ResolveInput,
  spec: { key: string; id: string; text: string; detail: string | null; buttons: readonly ButtonSpec[]; doing: string },
  pressed: BandPress | undefined,
  undo: () => void,
) {
  const ui = $.ui.resolve(e)
  if (pressed === undefined) {
    return row(ui, { key: spec.key, text: spec.text, buttons: spec.buttons, detail: spec.detail })
  }
  if (pressed.phase === 'waiting') {
    const takeBack: ButtonSpec = { key: undoKey(spec.id), label: 'undo', kind: 'default', onPress: undo }
    return row(ui, { key: spec.key, text: spec.text, buttons: [takeBack], detail: spec.doing })
  }
  return said(ui, `${spec.doing}: ${spec.text}`, 'quiet')
}

/**
 * One candidate, question or proposal: its title, and below it keep and drop, or while a press
 * waits undo and what it will do, or while it writes that line alone. `detail` is what it is, in
 * a few words beside keep and drop.
 */
export function candidateRow(
  $: EngineInterface,
  e: ResolveInput,
  candidate: BandCandidate,
  pressed: BandPress | undefined,
  actions: RowActions,
  detail: string | null = null,
  more: readonly ButtonSpec[] = [],
) {
  const buttons: ButtonSpec[] = [
    { key: `keep:${candidate.id}`, label: 'keep', kind: 'accent', onPress: () => actions.press(candidate, 'complete') },
    { key: `drop:${candidate.id}`, label: 'drop', kind: 'quiet', onPress: () => actions.press(candidate, 'drop') },
    ...more,
  ]
  const doing = DOING[pressed?.action ?? 'complete'] ?? 'keeping'
  const spec = { key: `row:${candidate.id}`, id: candidate.id, text: plainLine(candidate.title), detail, buttons, doing }
  return pressableRow($, e, spec, pressed, () => actions.undo(candidate.id))
}

/**
 * The open review: `ok` closes it, as a keep closes a candidate, with the same undo. Beside the
 * button, which facts the run changed, by what they are about.
 */
export function reviewRow(
  $: EngineInterface,
  e: ResolveInput,
  review: BandReview,
  pressed: BandPress | undefined,
  actions: RowActions,
) {
  const buttons: ButtonSpec[] = [{ key: `ok:${review.id}`, label: 'ok', kind: 'accent', onPress: () => actions.press(review, 'complete') }]
  const spec = { key: `review:${review.id}`, id: review.id, text: REVIEW, detail: changesSummary(review), buttons, doing: 'closing' }
  return pressableRow($, e, spec, pressed, () => actions.undo(review.id))
}

/** `2 facts changed: Sam, Dana`, or null for a review without changes of the facts. */
export function changesSummary(review: BandReview): string | null {
  const changes = review.changes ?? []
  if (changes.length === 0) {
    return null
  }
  const topics = [...new Set(changes.map(change => plainLine(change.topic)))]
  return `${changes.length} ${changes.length === 1 ? 'fact' : 'facts'} changed: ${topics.join(', ')}`
}
