import type { EngineInterface, ResolveInput } from 'claude-code'

import { said } from './look'
import type { Tone } from './look'
import { plainLine } from './plain-text'

/*
 * The field `search` at the top of the tab Facts: a text typed there and Enter search the store as
 * `/m2b-search` does. Hits turn the pane to the search's view under the seventh tab, as the
 * command does, and the tab Facts leads back; no hit, or a search m2b could not make, is said
 * below the field, and the pane stays where it is.
 *
 * What is typed is held by the field and by this module alone until Enter, never in the session's
 * state, which other plugins can read: the draft, and the line said below it. The search Enter
 * starts is the command's own view, which keeps its words and hits as the command keeps them.
 */

/** The key of the box the field and what it says stand in. */
export const SEARCH_BOX = 'facts:search'
/** The key of the field. */
export const SEARCH_FIELD = 'facts:search:field'

// Below this width of the pane's body the label would leave the text a few characters.
const LABEL_FROM_COLUMNS = 36

/** A search Enter started: its text as typed. Each is an object of its own, so its answer can be told from another's. */
export type TakenSearch = { text: string }

/**
 * What the field holds between draws: the draft as typed, the search that runs, and what the last
 * one said. A search forgotten while it ran, by `/clear` or a resume, is no longer `running`.
 */
const held: { draft: string; running: TakenSearch | null; said: { line: string; tone: Tone } | null } = {
  draft: '',
  running: null,
  said: null,
}

/** What Enter in the field does: `search` starts a search with the text Enter gave. */
export type SearchFieldActions = { search: (value: string) => Promise<void> }

/** Every change of the text, kept so the field draws it again after the pane turned away. */
export function typedSearch(value: string): void {
  held.draft = value
}

/**
 * Enter: the search to start, or null for a text of blanks alone and while a search runs. The text
 * stays in the field, so a search that leads back can be narrowed.
 */
export function takeSearch(value: string): TakenSearch | null {
  if (plainLine(value).trim() === '' || held.running !== null) {
    return null
  }
  held.draft = value
  held.running = { text: value }
  held.said = null
  return held.running
}

/**
 * What `taken` said, to be drawn below the field: nothing where it turned the pane to its hits.
 * Answers whether it is still the search the field holds; one forgotten while it ran changes
 * nothing, and its hits are not to be shown.
 */
export function searched(taken: TakenSearch, line: string | null, tone: Tone = 'quiet'): boolean {
  if (held.running !== taken) {
    return false
  }
  held.running = null
  held.said = line === null ? null : { line, tone }
  return true
}

/** Forgets everything held: a session that starts, and the conversation after `/clear` or a resume, start with an empty field. */
export function forgetSearchField(): void {
  held.draft = ''
  held.running = null
  held.said = null
}

/** The field above the parts of the tab Facts, and below it that a search runs or what the last one said. */
export function searchField($: EngineInterface, e: ResolveInput, actions: SearchFieldActions, columns: number) {
  const ui = $.ui.resolve(e)
  const { Box, Input } = ui
  const isWide = columns >= LABEL_FROM_COLUMNS
  return (
    <Box key={SEARCH_BOX} flexDirection="column" marginBottom={1}>
      <Input
        key={SEARCH_FIELD}
        {...(isWide ? { label: 'search', placeholder: 'what to look for' } : { placeholder: 'search' })}
        // Drawn as a plain line: a control character in a drawn text makes the engine refuse the pane.
        value={plainLine(held.draft)}
        submitLabel="search"
        onInput={value => typedSearch(value)}
        onSubmit={value => void actions.search(value)}
      />
      {held.running !== null && said(ui, 'searching…', 'quiet')}
      {held.said !== null && said(ui, held.said.line, held.said.tone)}
    </Box>
  )
}
