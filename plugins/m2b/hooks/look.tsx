import type { ElementTable, RenderChildren, ThemeKey, UiPressArgument } from 'claude-code'

import type { BandDueTask } from '../types'
import { plainLine, wholePath } from './plain-text'

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
  // The one of several that holds now: the tab whose view is shown, the value a setting has.
  | 'shown'
  // What a line is about, where a part lists several things.
  | 'strong'
  // Words a change added to a text, and words it took out.
  | 'added'
  | 'removed'

type Style = { color?: ThemeKey; dimColor?: true; weight?: 'bold'; strikethrough?: true }

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
  strong: { weight: 'bold' },
  added: { color: 'success' },
  // Struck through as well, so a removed word reads as removed without its color.
  removed: { color: 'error', strikethrough: true },
}

/** The `Text` props a tone is drawn with. */
export function styleOf(tone: Tone): Style {
  return STYLES[tone]
}

/** A line of text in its tone, wrapped: every view of the pane can be as narrow as 24 columns. */
export function said(ui: Pick<ElementTable, 'Text'>, text: string, tone: Tone = 'plain') {
  const { Text } = ui
  return (
    <Text {...styleOf(tone)} wrap="wrap">
      {text}
    </Text>
  )
}

// How far a text stands in that belongs to the line above it.
const INDENT = 2

/** What belongs to the line above it, indented whole: where a text in it wraps, its further lines stand in as well. */
export function inset(ui: Pick<ElementTable, 'Box'>, child: RenderChildren) {
  const { Box } = ui
  return <Box paddingLeft={INDENT}>{child}</Box>
}

/** A text that belongs to the line above it, indented whole and, where no tone is named, stepped back. */
export function under(ui: Pick<ElementTable, 'Box' | 'Text'>, text: string, tone: Tone = 'quiet') {
  return inset(ui, said(ui, text, tone))
}

export const M2B = 'm2b'
/** The title of the part that holds what needs an answer, wherever a view has one. */
export const WAITS_FOR_YOU = 'Waits for you'
export const NOTHING_WAITS = 'Nothing waits for you.'
/** Before m2b's first answer: not known, which is never "none". */
export const NOT_LOOKED = 'm2b has not looked yet.'
export const DUE_TODAY = 'due today'
export const OVERDUE = 'overdue'

function counted(number: number, one: string, several: string): string {
  return `${number} ${number === 1 ? one : several}`
}

/** `1 waits for you`, `4 wait for you`: how every surface counts what needs an answer. */
export function waitForYou(count: number): string {
  return `${counted(count, 'waits', 'wait')} for you`
}

/** `1 handed in`, `2 handed in`: the proposals sessions handed in that wait for a curation run, in the band's row. */
export function handedInCount(count: number): string {
  return `${count} handed in`
}

// As long as a button and a tab can be in the narrowest pane; the topic's view names it whole in its heading.
const TOPIC_LABEL_LENGTH = 20

/** A topic's name as the label of its button and of its tab: one line, cut where it is longer than a label may be. */
export function topicLabel(name: string): string {
  const line = plainLine(name)
  const characters = Array.from(line)
  return characters.length <= TOPIC_LABEL_LENGTH ? line : `${characters.slice(0, TOPIC_LABEL_LENGTH - 1).join('')}…`
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

/** `onPress` is handed the press, which names the surface it was made on. */
/** `hotkey` is the letter that presses the button while the pane holds the keyboard, as a tab's (B315). */
export type ButtonSpec = { key: string; label: string; kind: ButtonKind; onPress: (pressed: UiPressArgument) => void; hotkey?: string }

export function button(ui: Pick<ElementTable, 'Button'>, spec: ButtonSpec) {
  const { Button } = ui
  const reach = spec.hotkey === undefined ? {} : { hotkey: spec.hotkey }
  return spec.kind === 'accent' ? (
    <Button key={spec.key} label={spec.label} variant="primary" {...reach} onPress={spec.onPress} />
  ) : (
    <Button key={spec.key} label={spec.label} dimColor={spec.kind === 'quiet'} {...reach} onPress={spec.onPress} />
  )
}

/** The glyph before a task that ticks it: a control by itself, the row's one action that writes. */
const TICK_MARK = '○'

/** The mark before a task, a button without chrome that ticks it. */
export function tickMark(ui: Pick<ElementTable, 'Button'>, spec: { key: string; onPress: () => void }) {
  const { Button } = ui
  return <Button key={spec.key} plain label={TICK_MARK} onPress={spec.onPress} />
}
/** What ends a row that opens what it names. */
export const OPENS = '›'
// A space that never breaks: the mark stays with the last word, never alone on a line.
const KEEPS_TOGETHER = '\u00a0'

/** A row's text as a row that opens what it names draws it. */
export function opening(text: string): string {
  return `${text}${KEEPS_TOGETHER}${OPENS}`
}

/**
 * A row that is its own button: the text drawn without chrome, wrapped over as many lines as it
 * takes, `›` at its end, and a press anywhere on it opens what it names. The focus inverts every
 * line of it, so the row one stands on is seen among many.
 */
export function opensRow(ui: Pick<ElementTable, 'Button' | 'Text'>, spec: { key: string; text: string; onPress: () => void }) {
  const { Button, Text } = ui
  return (
    <Button key={spec.key} plain label={opening(spec.text)} onPress={spec.onPress}>
      <Text wrap="wrap">{opening(spec.text)}</Text>
    </Button>
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

/**
 * A tab of a row: `turn` is the press that shows its view, null for a tab beside the six whose view
 * is shown, which nothing reads again. `isShown` marks the tab of the view below, `hotkey` is the
 * letter that presses it while the pane holds the keyboard.
 */
export type Tab = { label: string; turn: { key: string; onPress: () => void } | null; isShown: boolean; hotkey: string | null }

/**
 * A row of tabs above a view. The one shown is marked: one of the six is a button in the accent,
 * which reads its view again and takes the focus after a turn, so the focus is the one mark there;
 * a tab beside the six is text, bold and underlined so it reads without color. Every other tab is
 * a dim button that turns to its view. The row breaks between tabs where it is too narrow.
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
          button(ui, {
            key: tab.turn.key,
            label: tab.label,
            kind: tab.isShown ? 'accent' : 'quiet',
            onPress: tab.turn.onPress,
            ...(tab.hotkey === null ? {} : { hotkey: tab.hotkey }),
          })
        ),
      )}
    </Box>
  )
}

/**
 * One value of a setting. `set` is the press that sets it: null for the value in force, and for a
 * value that cannot be pressed where and when the row is drawn.
 */
export type ValueSpec = { label: string; isInForce: boolean; set: { key: string; onPress: (pressed: UiPressArgument) => void } | null }

// Before the value in force, so it reads as the one that holds without its color.
const IN_FORCE = '●'

/**
 * The values of a setting side by side: the one in force is marked and is no button, every other
 * is a button that sets it, or stepped back where it cannot be pressed. The row breaks between
 * values where it is too narrow for them.
 */
export function valueRow(ui: Pick<ElementTable, 'Box' | 'Button' | 'Text'>, values: readonly ValueSpec[], key?: string) {
  const { Box, Text } = ui
  return (
    <Box key={key} flexDirection="row" columnGap={1} flexWrap="wrap">
      {values.map(value => {
        if (value.isInForce) {
          return (
            <Text {...styleOf('shown')} wrap="wrap">
              {`${IN_FORCE} ${value.label}`}
            </Text>
          )
        }
        return value.set === null ? (
          <Text {...styleOf('quiet')} wrap="wrap">
            {value.label}
          </Text>
        ) : (
          button(ui, { key: value.set.key, label: value.label, kind: 'default', onPress: value.set.onPress })
        )
      })}
    </Box>
  )
}

/** Blocks of several lines each, with an empty line between them, so each reads as one thing. */
export function apart(ui: Pick<ElementTable, 'Box'>, blocks: readonly RenderChildren[]) {
  const { Box } = ui
  return (
    <Box flexDirection="column" rowGap={1}>
      {blocks}
    </Box>
  )
}

// Below this width of the pane's body a frame and its padding, four columns, are too large a share: a bar down the left, two columns, stands in.
const FRAME_FROM_COLUMNS = 36

// A part's title and frame: m2b's own color and a frame that steps back, and both in the color of what waits while something in the part does.
const PART_COLORS = {
  calm: { title: 'remember', frame: 'subtle' },
  waits: { title: 'warning', frame: 'warning' },
} as const satisfies Record<string, { title: ThemeKey; frame: ThemeKey }>

/**
 * What heads a part: `waits` while something in it needs an answer, `count` how many, said at the
 * end of the title's line. `columns` is the width of the pane's body.
 */
export type PartSpec = { key: string; title: string; waits: boolean; count?: string | null; columns: number }

/**
 * A part of a view: a frame around its title and what stands in it, in the color of what waits
 * while something in it does. In a narrow pane the frame is a bar down the left.
 */
export function part(ui: Pick<ElementTable, 'Box' | 'Text'>, spec: PartSpec, body: readonly RenderChildren[]) {
  const { Box, Text } = ui
  const isFramed = spec.columns >= FRAME_FROM_COLUMNS
  const colors = PART_COLORS[spec.waits ? 'waits' : 'calm']
  return (
    <Box
      key={`part:${spec.key}`}
      flexDirection="column"
      borderStyle={isFramed ? 'round' : 'quote'}
      borderColor={colors.frame}
      paddingX={isFramed ? 1 : 0}
    >
      <Box flexDirection="row" justifyContent="space-between" columnGap={1}>
        <Text weight="bold" color={colors.title} wrap="wrap">
          {spec.title}
        </Text>
        {spec.count ? <Text {...styleOf('waits')}>{spec.count}</Text> : null}
      </Box>
      {body}
    </Box>
  )
}

/**
 * A row: its text, and on the line below its buttons with a detail beside them. `tone` is how the
 * text is drawn, plain where none is named.
 */
export type RowSpec = { key: string; text: string; tone?: Tone; buttons: readonly ButtonSpec[]; detail?: string | null }

/**
 * What can be pressed, with a detail beside it, on one line. Where the pane is too narrow for
 * both, the detail goes below the buttons whole: squeezed into what the buttons leave, it would
 * break after every few letters. `key` names the line where a drawing has to find it.
 */
export function pressLine(
  ui: Pick<ElementTable, 'Box' | 'Button' | 'Text'>,
  buttons: readonly ButtonSpec[],
  detail: string | null = null,
  key?: string,
) {
  const { Box } = ui
  return (
    <Box key={key} flexDirection="row" columnGap={1} flexWrap="wrap">
      {buttons.map(one => button(ui, one))}
      {detail === null ? null : said(ui, detail, 'quiet')}
    </Box>
  )
}

/** A row of a part: the text first, at full width, then what can be pressed, so a long text never pushes a button aside. */
export function row(ui: Pick<ElementTable, 'Box' | 'Button' | 'Text'>, spec: RowSpec) {
  const { Box } = ui
  const detail = spec.detail ? spec.detail : null
  return (
    <Box key={spec.key} flexDirection="column">
      {said(ui, spec.text, spec.tone)}
      {(spec.buttons.length > 0 || detail !== null) && pressLine(ui, spec.buttons, detail)}
    </Box>
  )
}

/**
 * A path, whole, on as many lines as it needs: it breaks before a folder's slash and never inside
 * a name, and every character is drawn as `wholePath` writes it, so two paths read alike only when
 * they are the same.
 */
export function pathLine(ui: Pick<ElementTable, 'Box' | 'Text'>, path: string, tone: Tone = 'quiet') {
  const { Box, Text } = ui
  return (
    <Box flexDirection="row" flexWrap="wrap">
      {wholePath(path)
        .split(/(?=\/)/)
        .map(piece => (
          <Text {...styleOf(tone)}>{piece}</Text>
        ))}
    </Box>
  )
}

/**
 * A file's name on as many lines as it needs: it breaks after a `-`, `_` or `.` and never inside
 * a word, as `pathLine` breaks a path before its slashes; a name with none of them wraps where it
 * must.
 */
export function nameLine(ui: Pick<ElementTable, 'Box' | 'Text'>, name: string, tone: Tone = 'plain') {
  const { Box, Text } = ui
  return (
    <Box flexDirection="row" flexWrap="wrap">
      {plainLine(name)
        .split(/(?<=[-_.])/)
        .map(piece => (
          <Text {...styleOf(tone)} wrap="wrap">
            {piece}
          </Text>
        ))}
    </Box>
  )
}
