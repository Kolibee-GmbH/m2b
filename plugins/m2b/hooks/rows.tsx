import type { EngineInterface, ResolveInput } from 'claude-code'

import type { BandCandidate, BandPress, BandSettle } from '../types'
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

function pressedLine(action: BandSettle, title: string): string {
  return ` ${action === 'complete' ? 'keeping' : 'dropping'}: ${plainLine(title)}`
}
