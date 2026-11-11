import type { EngineInterface, ResolveInput } from 'claude-code'

import type { BandCandidate, BandPress, BandReview, BandSettle } from '../types'
import { plainLine } from './plain-text'

/** What a row's buttons do; the band and the pane share one way of keeping and dropping. */
export type RowActions = {
  press: (candidate: BandCandidate, action: BandSettle) => Promise<void>
  undo: (id: string) => Promise<void>
}

/**
 * One candidate or question: keep and drop, or while a press waits undo and what it will do, or
 * while it writes that line alone. `wrap` is how a long title is drawn: cut in the band, wrapped in
 * the pane.
 */
export function candidateRow(
  $: EngineInterface,
  e: ResolveInput,
  candidate: BandCandidate,
  pressed: BandPress | undefined,
  actions: RowActions,
  wrap: 'truncate-end' | 'wrap' = 'truncate-end',
) {
  const { Box, Button, Text } = $.ui.resolve(e)
  if (pressed === undefined) {
    return (
      <Box key={`row:${candidate.id}`} flexDirection="row">
        <Button key={`keep:${candidate.id}`} label="keep" onPress={() => actions.press(candidate, 'complete')} />
        <Text> </Text>
        <Button key={`drop:${candidate.id}`} label="drop" onPress={() => actions.press(candidate, 'drop')} />
        <Text wrap={wrap}> {plainLine(candidate.title)}</Text>
      </Box>
    )
  }
  if (pressed.phase === 'waiting') {
    return (
      <Box key={`row:${candidate.id}`} flexDirection="row">
        <Button key={`undo:${candidate.id}`} label="undo" onPress={() => actions.undo(candidate.id)} />
        <Text dimColor wrap={wrap}>
          {pressedLine(pressed.action, candidate.title)}
        </Text>
      </Box>
    )
  }
  return (
    <Text key={`row:${candidate.id}`} dimColor wrap={wrap}>
      {pressedLine(pressed.action, candidate.title)}
    </Text>
  )
}

/**
 * The open review: `ok` closes it, as a keep closes a candidate, with the same undo. Beside the
 * title, which facts the run changed, by what they are about.
 */
export function reviewRow(
  $: EngineInterface,
  e: ResolveInput,
  review: BandReview,
  pressed: BandPress | undefined,
  actions: RowActions,
  wrap: 'truncate-end' | 'wrap' = 'truncate-end',
) {
  const { Box, Button, Text } = $.ui.resolve(e)
  const title = plainLine(review.title)
  if (pressed === undefined) {
    return (
      <Box key={`review:${review.id}`} flexDirection="row">
        <Button key={`ok:${review.id}`} label="ok" onPress={() => actions.press(review, 'complete')} />
        <Text weight="semibold"> {title}</Text>
        <Text wrap={wrap}>{changesSummary(review)}</Text>
      </Box>
    )
  }
  const line = ` closing: ${title}`
  if (pressed.phase === 'waiting') {
    return (
      <Box key={`review:${review.id}`} flexDirection="row">
        <Button key={`undo:${review.id}`} label="undo" onPress={() => actions.undo(review.id)} />
        <Text dimColor wrap={wrap}>
          {line}
        </Text>
      </Box>
    )
  }
  return (
    <Text key={`review:${review.id}`} dimColor wrap={wrap}>
      {line}
    </Text>
  )
}

/** `  2 facts changed: Sam, Dana`, or nothing for a review without changes of the facts. */
export function changesSummary(review: BandReview): string {
  const changes = review.changes ?? []
  if (changes.length === 0) {
    return ''
  }
  const topics = [...new Set(changes.map(change => plainLine(change.topic)))]
  return `  ${changes.length} ${changes.length === 1 ? 'fact' : 'facts'} changed: ${topics.join(', ')}`
}

function pressedLine(action: BandSettle, title: string): string {
  return ` ${action === 'complete' ? 'keeping' : 'dropping'}: ${plainLine(title)}`
}
