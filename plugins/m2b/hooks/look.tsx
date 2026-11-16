import type { ElementTable, ThemeKey } from 'claude-code'

import type { BandDueTask } from '../types'
import { plainLine } from './plain-text'

/*
 * How m2b looks and what it calls things, for every surface it draws on: one table from what a
 * thing is to its color and weight, the words that say it, and the pieces a drawing is built from.
 * A drawing names what a thing is (`waits`, `overdue`, `trouble`) and never a color, so one place
 * decides how the band, the pane and a line of text say the same thing. Colors are theme keys:
 * they follow the person's theme.
 */

/** What a piece of text is, by which it is drawn. */
export type Tone =
  // m2b's own name, where a line stands outside the pane.
  | 'brand'
  // Needs an answer of the person.
  | 'waits'
  | 'dueToday'
  | 'overdue'
  // Settled: kept, dropped, written.
  | 'done'
  // m2b could not do or read something.
  | 'trouble'
  // To be read.
  | 'plain'
  // May be skipped: detail, what is not known yet.
  | 'quiet'
  // The one of several that holds now: the tab whose view is shown.
  | 'shown'

type Style = { color?: ThemeKey; dimColor?: true; weight?: 'bold' }

const STYLES: Readonly<Record<Tone, Style>> = {
  brand: { color: 'remember', weight: 'bold' },
  waits: { color: 'warning' },
  dueToday: { color: 'warning' },
  overdue: { color: 'error' },
  done: { color: 'success' },
  trouble: { color: 'error' },
  plain: {},
  quiet: { dimColor: true },
  shown: { color: 'remember', weight: 'bold' },
}

/** The `Text` props a tone is drawn with. */
export function styleOf(tone: Tone): Style {
  return STYLES[tone]
}

export const M2B = 'm2b'
export const DUE_TODAY = 'due today'
export const OVERDUE = 'overdue'

function counted(number: number, one: string, several: string): string {
  return `${number} ${number === 1 ? one : several}`
}

/** `1 waits for you`, `4 wait for you`: how every surface counts what needs an answer. */
export function waitForYou(count: number): string {
  return `${counted(count, 'waits', 'wait')} for you`
}

/** `1 topic`, `4 topics`. */
export function topicsCount(count: number): string {
  return counted(count, 'topic', 'topics')
}

/** How many tasks are due today and how many overdue, each with its tone; none where there is none. */
export function dueCounts(due: readonly BandDueTask[]): { text: string; tone: Tone }[] {
  const overdue = due.filter(task => task.overdue).length
  const today = due.length - overdue
  return [
    ...(overdue > 0 ? [{ text: `${overdue} ${OVERDUE}`, tone: 'overdue' as const }] : []),
    ...(today > 0 ? [{ text: `${today} ${DUE_TODAY}`, tone: 'dueToday' as const }] : []),
  ]
}

/** How much a button asks to be pressed: the one action of its row, any other, or one beside the point. */
export type ButtonKind = 'accent' | 'default' | 'quiet'

export type ButtonSpec = { key: string; label: string; kind: ButtonKind; onPress: () => void }

export function button(ui: Pick<ElementTable, 'Button'>, spec: ButtonSpec) {
  const { Button } = ui
  return spec.kind === 'accent' ? (
    <Button key={spec.key} label={spec.label} variant="primary" onPress={spec.onPress} />
  ) : (
    <Button key={spec.key} label={spec.label} dimColor={spec.kind === 'quiet'} onPress={spec.onPress} />
  )
}

// As wide as the longer of the two, so the titles of a list start in one column.
const DUE_COLUMN = Math.max(DUE_TODAY.length, OVERDUE.length)

/**
 * A task due as one line: when it is due in its color and a column of its own, the title at full
 * strength, since a task is read. `wrap` is how a long title is drawn: cut in the band, wrapped in
 * the pane.
 */
export function taskLine(ui: Pick<ElementTable, 'Box' | 'Text'>, task: BandDueTask, wrap: 'truncate-end' | 'wrap') {
  const { Box, Text } = ui
  return (
    <Box key={`task:${task.id}`} flexDirection="row" columnGap={1}>
      <Text {...styleOf(task.overdue ? 'overdue' : 'dueToday')}>{(task.overdue ? OVERDUE : DUE_TODAY).padEnd(DUE_COLUMN)}</Text>
      <Text wrap={wrap}>{plainLine(task.title)}</Text>
    </Box>
  )
}

/** A tab of a row: `turn` is the press that shows its view, null for the tab whose view is shown. */
export type Tab = { label: string; turn: { key: string; onPress: () => void } | null }

/**
 * A row of tabs above a view: the one shown is marked, underlined too so it reads without color,
 * and is no button; every other turns to its view. The row breaks between tabs where it is too
 * narrow for them.
 */
export function tabRow(ui: Pick<ElementTable, 'Box' | 'Button' | 'Text'>, tabs: readonly Tab[]) {
  const { Box, Text } = ui
  return (
    <Box key="tabs" flexDirection="row" columnGap={1} flexWrap="wrap">
      {tabs.map(tab =>
        tab.turn === null ? (
          <Text {...styleOf('shown')} underline>
            {tab.label}
          </Text>
        ) : (
          button(ui, { key: tab.turn.key, label: tab.label, kind: 'quiet', onPress: tab.turn.onPress })
        ),
      )}
    </Box>
  )
}
