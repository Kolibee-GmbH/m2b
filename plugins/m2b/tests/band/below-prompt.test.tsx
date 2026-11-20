import { expect, test } from 'claude-code/testing'
import type { Engine } from 'claude-code/testing'

import { bandLine, belowPrompt, placeOn } from '../../hooks/band'
import type { BandLine, BandModel } from '../../hooks/band'
import type { BandShows } from '../../types'
import {
  BAND,
  ENGINES_OWN_DRAWING,
  FakeM2b,
  HINT,
  HINT_ROW,
  HOME,
  NOW,
  OPEN,
  PROMPT_HINT,
  buttonsAt,
  enginesHint,
  everyText,
  fail,
  orderAt,
  pane,
  partLines,
  piecesAt,
  sentenceOfM2b,
  shownBand,
  shownTab,
  start,
  startView,
} from './harness'
import type { Files, ShownPiece } from './harness'

const PANE = 'm2b'
const COMMAND = 'm2b-pane'
const UNDO_MS = 5_000
const SHARED_ANSWER = `${HOME}/.local/state/m2b/band-answer.json`
const AS_A_DIALOG = { id: PANE, title: 'm2b', closeOnEscape: true, focus: true }
const TO_STAY = { id: PANE, title: 'm2b', focus: true }
const BELOW: BandShows = { place: 'below', dueTasks: 'count', topics: false }

/** What the band of `belowFake` says, as the pieces of a row and as the words the engine adds to its line. */
const SAYS = '1 waits for you  1 overdue'
const TAIL = 'm2b 1 waits for you · 1 overdue · /m2b-pane'
const CALM_TAIL = 'm2b · /m2b-pane'
/**
 * The cells the row of `belowFake` needs after the hint `? for shortcuts`: 2 kept free, 27 for the
 * mode, 15 of hint and 2 after it, `m2b` and 2, the 26 of the pieces and 2, and the 9 of `/m2b-pane`.
 */
const ROOM_FOR_THE_ROW = 2 + 27 + 15 + 2 + 5 + 28 + 9
/** The same with the mark in place of the second count: `1 waits for you  …` is 18 cells, and 2. */
const ROOM_FOR_THE_FIRST_COUNT = 2 + 27 + 15 + 2 + 5 + 20 + 9
/** The same without pieces: what the calm row needs. */
const ROOM_FOR_THE_CALM_ROW = 2 + 27 + 15 + 2 + 5 + 9
/** The row of `belowFake` where its second count gave way. */
const SAYS_THE_FIRST = '1 waits for you  …'

type Viewport = { columns: number; rows: number; isFullscreen: boolean }

function fullscreen(columns: number): Viewport {
  return { columns, rows: 50, isFullscreen: true }
}

function mainScreen(columns: number): Viewport {
  return { columns, rows: 50, isFullscreen: false }
}

/** A machine whose band is below the prompt, with a candidate that waits and a task overdue. */
function belowFake(): FakeM2b {
  const fake = new FakeM2b().candidate('c1', 'Remember? Dana prefers tea')
  fake.shows = BELOW
  fake.dueTasks = [{ id: 'd1', title: 'Call the plumber', due: '2026-03-10', overdue: true }]
  return fake
}

/** The hint line as the engine raises it, in a viewport or where none is told, with what another plugin added to it. */
function drawHint($: Engine, viewport: Viewport | null, tail?: string) {
  return $.ui.mount({
    ...PROMPT_HINT,
    props: { ...PROMPT_HINT.props, ...(tail === undefined ? {} : { tail }) },
    surface: 'terminal',
    ...(viewport === null ? {} : { viewport }),
  })
}

function dim(text: string): ShownPiece {
  return { text, color: undefined, dimColor: true, weight: undefined, strikethrough: undefined }
}

function colored(text: string, color: string, weight?: 'bold'): ShownPiece {
  return { text, color, dimColor: undefined, weight, strikethrough: undefined }
}

const NAME = colored('m2b', 'remember', 'bold')
const PIECES = [colored('1 waits for you', 'warning'), colored('  1 overdue', 'error')]
/** What stands for the counts a row has no room for. */
const MARK = dim('  …')

function model(fields: Partial<BandModel> = {}): BandModel {
  return { snapshot: null, proposals: null, notice: null, topics: 0, health: null, ...fields }
}

function lineOf(fields: Partial<BandLine>): BandLine {
  return { parts: [], isNamed: true, isCalm: false, listed: [], more: 0, ...fields }
}

/** The piece that stands for the counts a row has no room for. */
const MORE = { text: '…', tone: 'quiet' as const }

test('with the band below the prompt m2b draws nothing above it: not what waits, not a task list it could not read, not a calm row', async ($, on) => {
  // Covers: B214, B191
  const fake = belowFake()
  const { clock } = await start($, on, fake)
  const band = await $.ui.mount({ ...BAND, surface: 'terminal', viewport: mainScreen(160) })
  expect(await everyText(band)).toEqual([ENGINES_OWN_DRAWING])
  expect(await band.findAll({ type: 'Button' })).toEqual([])

  fake.failure = 'the task list did not answer'
  await clock.advance(60_000)
  expect(await everyText(band)).toEqual([ENGINES_OWN_DRAWING])

  fake.failure = null
  fake.tasks = []
  fake.dueTasks = []
  await clock.advance(60_000)
  expect(await everyText(band)).toEqual([ENGINES_OWN_DRAWING])
  await band.unmount()
})

test('where the hint line has room, m2b draws it: the hint stepped back, m2b, the pieces in their colors, and on the main screen the command, stepped back, and no button', async ($, on) => {
  // Covers: B214
  const { opened } = await start($, on, belowFake())

  const hint = await drawHint($, mainScreen(160))

  expect(await enginesHint(hint)).toBeNull()
  expect(await orderAt(hint, HINT_ROW)).toEqual([HINT, 'm2b', SAYS, `/${COMMAND}`])
  expect(await piecesAt(hint, HINT_ROW)).toEqual([dim(HINT), NAME, ...PIECES, dim(`/${COMMAND}`)])
  // No key reaches a button below the prompt, and off the fullscreen layout no click does.
  expect(await hint.findAll({ type: 'Button' })).toEqual([])
  expect(opened).toEqual([])
  await hint.unmount()
})

test('under the fullscreen layout the row below the prompt ends in the button open, and a press opens the pane to stay, in the view it starts in', async ($, on) => {
  // Covers: B214
  const fake = belowFake()
  const { clock, opened } = await start($, on, fake)
  const hint = await drawHint($, fullscreen(160))
  expect(await orderAt(hint, HINT_ROW)).toEqual([HINT, 'm2b', SAYS, `[${OPEN}]`])
  expect(await piecesAt(hint, HINT_ROW)).toEqual([dim(HINT), NAME, ...PIECES])
  expect(await buttonsAt(hint, HINT_ROW)).toEqual([{ key: OPEN, label: 'open', variant: undefined, dimColor: false }])
  expect(opened).toEqual([])
  const looksBefore = fake.looks.length

  await hint.press({ key: OPEN })
  await clock.advance(1)

  expect(opened).toEqual([TO_STAY])
  // As the band's open above the prompt: it asks again what the session was given, and writes nothing.
  expect(fake.looks.length).toBe(looksBefore + 1)
  expect(fake.writes()).toEqual([])
  const beside = await $.ui.mount({ ...pane(PANE, 50, 'dock'), surface: 'terminal' })
  expect(await shownTab(beside)).toBe('overview')
  expect(await partLines(beside, 'waits')).toEqual(['Remember? Dana prefers tea', '[keep] [drop]'])
  await beside.unmount()
  await hint.unmount()
})

test('under the fullscreen layout below 110 columns the press on open below the prompt opens the pane as a dialog', async ($, on) => {
  // Covers: B214
  const fake = new FakeM2b()
  fake.shows = BELOW
  const { opened } = await start($, on, fake)
  const hint = await drawHint($, fullscreen(109))

  await hint.press({ key: OPEN })

  expect(opened).toEqual([AS_A_DIALOG])
  await hint.unmount()
})

for (const [layout, viewport, way] of [
  ['under the fullscreen layout', fullscreen(ROOM_FOR_THE_ROW), `[${OPEN}]`],
  ['on the main screen', mainScreen(ROOM_FOR_THE_ROW), `/${COMMAND}`],
] as const) {
  test(`${layout}, exactly the cells the row needs are room for all of it; from one cell less the last count gives way to the mark, down to the room of the first count and the mark; below that the line is the engine's, with every word of m2b at its end`, async ($, on) => {
    // Covers: B214
    await start($, on, belowFake())

    const fits = await drawHint($, viewport)
    expect(await enginesHint(fits)).toBeNull()
    expect(await orderAt(fits, HINT_ROW)).toEqual([HINT, 'm2b', SAYS, way])
    await fits.unmount()

    for (const columns of [ROOM_FOR_THE_ROW - 1, ROOM_FOR_THE_FIRST_COUNT]) {
      const shortened = await drawHint($, { ...viewport, columns })
      expect(await enginesHint(shortened)).toBeNull()
      expect(await orderAt(shortened, HINT_ROW)).toEqual([HINT, 'm2b', SAYS_THE_FIRST, way])
      // The count kept holds its color, and the mark is stepped back.
      expect((await piecesAt(shortened, HINT_ROW)).slice(0, 4)).toEqual([dim(HINT), NAME, colored('1 waits for you', 'warning'), MARK])
      await shortened.unmount()
    }

    const tooNarrow = await drawHint($, { ...viewport, columns: ROOM_FOR_THE_FIRST_COUNT - 1 })
    expect(await tooNarrow.find({ key: HINT_ROW })).toBeUndefined()
    expect(await enginesHint(tooNarrow)).toEqual({ hint: HINT, tail: TAIL })
    expect(await tooNarrow.findAll({ type: 'Button' })).toEqual([])
    await tooNarrow.unmount()
  })
}

test('where no viewport is told the line stays the engine\'s, with m2b\'s words at its end', async ($, on) => {
  // Covers: B214
  await start($, on, belowFake())

  const hint = await drawHint($, null)

  expect(await hint.find({ key: HINT_ROW })).toBeUndefined()
  expect(await enginesHint(hint)).toEqual({ hint: HINT, tail: TAIL })
  await hint.unmount()
})

test('a longer hint of the engine takes its cells from the room: a count gives way, then the row to the words, and the hint is never cut for m2b', async ($, on) => {
  // Covers: B214
  await start($, on, belowFake())
  const working = 'esc to interrupt · ctrl+t to hide tasks'
  const props = { ...PROMPT_HINT.props, isWorking: true, hint: working }
  const longer = working.length - HINT.length

  const fits = await $.ui.mount({ ...PROMPT_HINT, props, surface: 'terminal', viewport: mainScreen(ROOM_FOR_THE_ROW + longer) })
  expect(await orderAt(fits, HINT_ROW)).toEqual([working, 'm2b', SAYS, `/${COMMAND}`])
  await fits.unmount()

  for (const columns of [ROOM_FOR_THE_ROW + longer - 1, ROOM_FOR_THE_FIRST_COUNT + longer]) {
    const shortened = await $.ui.mount({ ...PROMPT_HINT, props, surface: 'terminal', viewport: mainScreen(columns) })
    expect(await orderAt(shortened, HINT_ROW)).toEqual([working, 'm2b', SAYS_THE_FIRST, `/${COMMAND}`])
    await shortened.unmount()
  }

  const tooNarrow = await $.ui.mount({ ...PROMPT_HINT, props, surface: 'terminal', viewport: mainScreen(ROOM_FOR_THE_FIRST_COUNT + longer - 1) })
  expect(await enginesHint(tooNarrow)).toEqual({ hint: working, tail: TAIL })
  await tooNarrow.unmount()
})

test('below the prompt the tasks are counted, never listed: a machine that lists them gets their counts in the row and in the words', async ($, on) => {
  // Covers: B214, B102
  const fake = belowFake()
  fake.shows = { place: 'below', dueTasks: 'list', topics: false }
  fake.dueTasks = [
    { id: 'd1', title: 'Call the plumber', due: '2026-03-10', overdue: true },
    { id: 'd2', title: 'Send the offer to Acme', due: '2026-03-14', overdue: false },
  ]
  const { clock } = await start($, on, fake)

  const row = await drawHint($, mainScreen(160))
  expect(await orderAt(row, HINT_ROW)).toEqual([HINT, 'm2b', '1 waits for you  1 overdue  1 due today', `/${COMMAND}`])
  expect(await row.find({ key: 'tasks' })).toBeUndefined()
  expect(await row.find({ key: 'task:d1' })).toBeUndefined()
  expect((await everyText(row)).join('\n')).not.toContain('Call the plumber')
  await row.unmount()

  const words = await drawHint($, mainScreen(ROOM_FOR_THE_FIRST_COUNT - 1))
  expect(await enginesHint(words)).toEqual({ hint: HINT, tail: 'm2b 1 waits for you · 1 overdue · 1 due today · /m2b-pane' })
  await words.unmount()

  // With off they are not counted there either.
  fake.shows = { place: 'below', dueTasks: 'off', topics: false }
  await clock.advance(60_000)
  const off = await drawHint($, mainScreen(160))
  expect(await orderAt(off, HINT_ROW)).toEqual([HINT, 'm2b', '1 waits for you', `/${COMMAND}`])
  await off.unmount()
})

test('the count of topics, where the machine shows it, is a piece of the row below the prompt and of the words, stepped back', async ($, on) => {
  // Covers: B214, B192
  const fake = belowFake()
  fake.shows = { place: 'below', dueTasks: 'count', topics: true }
  fake.given = { topics: [{ name: 'Northwind', facts: 3, current: 0 }], atStart: 'whole', offUnder: null }
  await start($, on, fake)

  const row = await drawHint($, mainScreen(160))
  expect(await piecesAt(row, HINT_ROW)).toEqual([dim(HINT), NAME, ...PIECES, dim('  1 topic'), dim(`/${COMMAND}`)])
  await row.unmount()

  const words = await drawHint($, mainScreen(ROOM_FOR_THE_FIRST_COUNT - 1))
  expect(await enginesHint(words)).toEqual({ hint: HINT, tail: 'm2b 1 waits for you · 1 overdue · 1 topic · /m2b-pane' })
  await words.unmount()
})

test('with nothing to say the band below the prompt is calm: m2b and the way into the pane, both stepped back, in the row and as the words m2b · /m2b-pane', async ($, on) => {
  // Covers: B214, B213
  const fake = new FakeM2b()
  fake.shows = BELOW
  const { opened } = await start($, on, fake)

  const onMainScreen = await drawHint($, mainScreen(ROOM_FOR_THE_CALM_ROW))
  expect(await piecesAt(onMainScreen, HINT_ROW)).toEqual([dim(HINT), dim('m2b'), dim(`/${COMMAND}`)])
  expect(await onMainScreen.findAll({ type: 'Button' })).toEqual([])
  await onMainScreen.unmount()

  const underFullscreen = await drawHint($, fullscreen(ROOM_FOR_THE_CALM_ROW))
  expect(await orderAt(underFullscreen, HINT_ROW)).toEqual([HINT, 'm2b', `[${OPEN}]`])
  expect(await piecesAt(underFullscreen, HINT_ROW)).toEqual([dim(HINT), dim('m2b')])
  expect(await buttonsAt(underFullscreen, HINT_ROW)).toEqual([{ key: OPEN, label: 'open', variant: undefined, dimColor: true }])
  await underFullscreen.press({ key: OPEN })
  expect(opened).toEqual([AS_A_DIALOG])
  await underFullscreen.unmount()

  for (const viewport of [mainScreen(ROOM_FOR_THE_CALM_ROW - 1), fullscreen(ROOM_FOR_THE_CALM_ROW - 1), null]) {
    const words = await drawHint($, viewport)
    expect(await words.find({ key: HINT_ROW })).toBeUndefined()
    expect(await enginesHint(words)).toEqual({ hint: HINT, tail: CALM_TAIL })
    await words.unmount()
  }
})

test('a task list that could not be read is said below the prompt, where the band stands: as the words, a sentence as it is, and as the row where it has room', async ($, on) => {
  // Covers: B214, B191
  const fake = belowFake()
  fake.failure = 'the task list did not answer'
  await start($, on, fake)
  const sentence = 'm2b could not read the tasks: the task list did not answer'
  // No `m2b` stands before a sentence that names it: the sentence and 2 after the engine's cells, then the command.
  const room = 2 + 27 + 15 + 2 + (sentence.length + 2) + 9

  // A sentence is never shortened: one cell short of its room it is the words, whole.
  const words = await drawHint($, mainScreen(room - 1))
  // The sentence names m2b itself and no command: no `m2b` before it, nothing after it.
  expect(await enginesHint(words)).toEqual({ hint: HINT, tail: sentence })
  await words.unmount()

  const row = await drawHint($, mainScreen(room))
  expect(await piecesAt(row, HINT_ROW)).toEqual([dim(HINT), colored(sentence, 'error'), dim(`/${COMMAND}`)])
  await row.unmount()

  const above = await $.ui.mount({ ...BAND, surface: 'terminal', viewport: mainScreen(200) })
  expect(await everyText(above)).toEqual([ENGINES_OWN_DRAWING])
  await above.unmount()
})

test('proposals that could not be looked at are said below the prompt as that one sentence', async ($, on) => {
  // Covers: B214, B191
  const fake = belowFake()
  fake.proposalsError = 'the store at /home/alex/Notes cannot be read'
  await start($, on, fake)

  const words = await drawHint($, null)

  expect(await enginesHint(words)).toEqual({
    hint: HINT,
    tail: 'm2b could not look for proposals: the store at /home/alex/Notes cannot be read',
  })
  await words.unmount()
})

test('where the pane cannot be shown, open below the prompt says so in the line, with m2b before the sentence, until the next prompt', async ($, on) => {
  // Covers: B214, B191
  on('prompt.submit', (_, e) => ({ text: e.text }))
  const fake = belowFake()
  fake.paneWaits = 'no surface attached places panes'
  const { openPanes } = await start($, on, fake)
  const hint = await drawHint($, fullscreen(120))

  await hint.press({ key: OPEN })

  expect(openPanes.has(PANE)).toBe(false)
  const notShown = 'the m2b pane cannot be shown here: no surface attached places panes; /m2b-pane answers with the lines'
  // The sentence is longer than the line has room for, and no word of it gives way: the engine's line, and the sentence at its end.
  expect(await enginesHint(hint)).toEqual({ hint: HINT, tail: `m2b ${notShown}` })

  await $.prompt.submit({ text: 'go on', origin: { kind: 'composer' }, wait: false })
  expect(await orderAt(hint, HINT_ROW)).toEqual([HINT, 'm2b', SAYS, `[${OPEN}]`])
  await hint.unmount()
})

test('what another plugin added to the hint line stays: before m2b\'s words at the end of the engine\'s line, and after the hint in the row m2b draws', async ($, on) => {
  // Covers: B214
  await start($, on, belowFake())
  const added = 'notes: 2 open'

  const words = await drawHint($, mainScreen(ROOM_FOR_THE_ROW), added)
  // The row would have had room beside the hint alone: what was added counts as the engine's text.
  expect(await words.find({ key: HINT_ROW })).toBeUndefined()
  expect(await enginesHint(words)).toEqual({ hint: HINT, tail: `${added} · ${TAIL}` })
  await words.unmount()

  const columns = ROOM_FOR_THE_ROW + 1 + added.length
  const row = await drawHint($, mainScreen(columns), added)
  expect(await enginesHint(row)).toBeNull()
  expect(await piecesAt(row, HINT_ROW)).toEqual([dim(`${HINT} ${added}`), NAME, ...PIECES, dim(`/${COMMAND}`)])
  await row.unmount()

  const oneLess = await drawHint($, mainScreen(columns - 1), added)
  expect(await piecesAt(oneLess, HINT_ROW)).toEqual([dim(`${HINT} ${added}`), NAME, colored('1 waits for you', 'warning'), MARK, dim(`/${COMMAND}`)])
  await oneLess.unmount()

  const tooNarrow = await drawHint($, mainScreen(ROOM_FOR_THE_FIRST_COUNT + 1 + added.length - 1), added)
  expect(await enginesHint(tooNarrow)).toEqual({ hint: HINT, tail: `${added} · ${TAIL}` })
  await tooNarrow.unmount()
})

for (const place of ['above', 'waiting'] as const) {
  test(`with the band ${place} the hint line is the engine's own, as it was handed, whatever waits`, async ($, on) => {
    // Covers: B214
    const fake = belowFake()
    fake.shows = { place, dueTasks: 'count', topics: false }
    const { clock } = await start($, on, fake)

    const hint = await drawHint($, fullscreen(200))
    expect(await hint.find({ key: HINT_ROW })).toBeUndefined()
    expect(await enginesHint(hint)).toEqual({ hint: HINT, tail: null })
    expect(await hint.findAll({ type: 'Button' })).toEqual([])
    await hint.unmount()

    const withATail = await drawHint($, fullscreen(200), 'notes: 2 open')
    expect(await enginesHint(withATail)).toEqual({ hint: HINT, tail: 'notes: 2 open' })
    await withATail.unmount()

    // With nothing to say as well: the calm row of a band above is above the prompt, not here.
    fake.tasks = []
    fake.dueTasks = []
    await clock.advance(60_000)
    const idle = await drawHint($, fullscreen(200))
    expect(await enginesHint(idle)).toEqual({ hint: HINT, tail: null })
    await idle.unmount()
  })
}

test('before m2b\'s first answer the hint line is the engine\'s own, on a machine whose band is below the prompt too; once it answered, the band is there', async ($, on) => {
  // Covers: B214, B213
  const fake = belowFake()
  fake.delayMs = args => (args[0] === 'band' && !args.includes('--session-only') ? 5_000 : 0)
  const { clock } = await start($, on, fake)

  const hint = await drawHint($, mainScreen(160), 'notes: 2 open')
  expect(await hint.find({ key: HINT_ROW })).toBeUndefined()
  expect(await enginesHint(hint)).toEqual({ hint: HINT, tail: 'notes: 2 open' })

  await clock.advance(5_000)
  expect(await orderAt(hint, HINT_ROW)).toEqual([`${HINT} notes: 2 open`, 'm2b', SAYS, `/${COMMAND}`])
  await hint.unmount()
})

test('before m2b is set up the hint line is the engine\'s own', async ($, on) => {
  // Covers: B214
  const fake = belowFake()
  fake.isSetUp = false
  await start($, on, fake)

  const hint = await drawHint($, mainScreen(160))

  expect(await enginesHint(hint)).toEqual({ hint: HINT, tail: null })
  expect(fake.calls).toEqual([])
  await hint.unmount()
})

/** Ways m2b gives no answer to read, each with how the sentence it leaves begins. */
const NO_ANSWER: [string, (fake: FakeM2b) => void, string][] = [
  [
    'm2b cannot be started',
    fake => {
      fake.runFails = 'timed out after 90000 ms'
    },
    `m2b could not read the tasks: could not run ${HOME}/.local/bin/m2b: `,
  ],
  [
    'm2b ends with an error',
    fake => {
      fake.statusFails = true
    },
    'm2b could not read the tasks: could not read the machine config',
  ],
  [
    'm2b answers no JSON',
    fake => {
      fake.bandPrints = 'Traceback (most recent call last):'
    },
    'm2b band answered something that is not JSON',
  ],
]

for (const [situation, arrange, begins] of NO_ANSWER) {
  test(`a band below the prompt stays there once ${situation}: the sentence at the end of the hint line, nothing above the prompt, and the counts again once m2b answers`, async ($, on) => {
    // Covers: B214, B213
    const fake = belowFake()
    const { clock } = await start($, on, fake)
    const above = await $.ui.mount({ ...BAND, surface: 'terminal', viewport: mainScreen(200) })
    const hint = await drawHint($, null)
    expect(await enginesHint(hint)).toEqual({ hint: HINT, tail: TAIL })

    arrange(fake)
    await clock.advance(60_000)

    expect(await everyText(above)).toEqual([ENGINES_OWN_DRAWING])
    expect(await hint.find({ key: HINT_ROW })).toBeUndefined()
    const said = await enginesHint(hint)
    expect(said?.hint).toBe(HINT)
    // A sentence that names m2b itself: as it is, no `m2b` before it and no command after it.
    expect(said?.tail).toStartWith(begins)
    expect(said?.tail).not.toContain(`/${COMMAND}`)

    fake.runFails = null
    fake.statusFails = false
    fake.bandPrints = null
    await clock.advance(60_000)
    expect(await enginesHint(hint)).toEqual({ hint: HINT, tail: TAIL })
    expect(await everyText(above)).toEqual([ENGINES_OWN_DRAWING])
    await hint.unmount()
    await above.unmount()
  })
}

test('a keep m2b could not write is said below the prompt where the band stands there, and nothing above it', async ($, on) => {
  // Covers: B214, B213
  const fake = belowFake()
  const { clock } = await start($, on, fake)
  const above = await $.ui.mount({ ...BAND, surface: 'terminal', viewport: mainScreen(200) })
  const hint = await drawHint($, null)
  const ui = await startView($)
  const handle = fake.handle.bind(fake)
  fake.handle = (argv, ...rest) => (argv[2] === 'complete' ? fail('the task list is read-only') : handle(argv, ...rest))

  await ui.press({ key: 'keep:c1' })
  await clock.advance(UNDO_MS)

  const sentence = 'm2b could not keep "Remember? Dana prefers tea": the task list is read-only'
  expect(await enginesHint(hint)).toEqual({ hint: HINT, tail: sentence })
  expect(await everyText(above)).toEqual([ENGINES_OWN_DRAWING])
  await hint.unmount()
  // Where the line has room the sentence is the row, in the color of trouble.
  const wide = await drawHint($, mainScreen(200))
  expect(await piecesAt(wide, HINT_ROW)).toEqual([dim(HINT), colored(sentence, 'error'), dim(`/${COMMAND}`)])

  fake.handle = handle
  await clock.advance(60_000)
  expect(await piecesAt(wide, HINT_ROW)).toEqual([dim(HINT), NAME, ...PIECES, dim(`/${COMMAND}`)])
  await wide.unmount()
  await ui.unmount()
  await above.unmount()
})

/** Ways the look at the tasks before a keep fails, each with the sentence it leaves. */
const SECOND_LOOK_FAILS: [string, (fake: FakeM2b) => void, string][] = [
  [
    'm2b ends with an error',
    fake => {
      const handle = fake.handle.bind(fake)
      fake.handle = (argv, ...rest) => (argv.includes('--tasks-only') ? fail('could not read the machine config') : handle(argv, ...rest))
    },
    'm2b could not read the tasks: could not read the machine config',
  ],
  [
    'the task list does not answer',
    fake => {
      fake.failure = 'reminders did not answer within 20 seconds'
    },
    'm2b could not read the tasks: reminders did not answer within 20 seconds',
  ],
]

for (const [situation, arrange, sentence] of SECOND_LOOK_FAILS) {
  test(`where ${situation} at the look before a keep, nothing is written and the sentence is said below the prompt where the band stands there`, async ($, on) => {
    // Covers: B214, B213
    const fake = belowFake()
    const { clock } = await start($, on, fake)
    const above = await $.ui.mount({ ...BAND, surface: 'terminal', viewport: mainScreen(200) })
    const hint = await drawHint($, null)
    const ui = await startView($)
    arrange(fake)

    await ui.press({ key: 'keep:c1' })
    await clock.advance(UNDO_MS)

    expect(fake.writes()).toEqual([])
    expect(await enginesHint(hint)).toEqual({ hint: HINT, tail: sentence })
    expect(await everyText(above)).toEqual([ENGINES_OWN_DRAWING])
    await ui.unmount()
    await hint.unmount()
    await above.unmount()
  })
}

test('a first look that fails says its sentence where a machine without an entry has the band: below the prompt in a terminal, above it in the desktop app; once m2b answers the band is below', async ($, on) => {
  // Covers: B213, B214
  const fake = belowFake()
  fake.statusFails = true
  const { clock } = await start($, on, fake)
  const above = await $.ui.mount({ ...BAND, surface: 'terminal', viewport: mainScreen(200) })
  const inDesktop = await $.ui.mount({ ...BAND, surface: 'desktop', viewport: mainScreen(200) })
  const hint = await drawHint($, null)

  // No answer said where the band stands yet.
  const sentence = 'm2b could not read the tasks: could not read the machine config'
  expect(await everyText(above)).toEqual([ENGINES_OWN_DRAWING])
  expect(await enginesHint(hint)).toEqual({ hint: HINT, tail: sentence })
  expect(await shownBand(inDesktop)).toEqual(sentenceOfM2b(sentence))
  await inDesktop.unmount()

  fake.statusFails = false
  await clock.advance(60_000)
  expect(await everyText(above)).toEqual([ENGINES_OWN_DRAWING])
  expect(await enginesHint(hint)).toEqual({ hint: HINT, tail: TAIL })
  await hint.unmount()
  await above.unmount()
})

test('an error another session shared is not taken: this band asks m2b itself and keeps its counts below the prompt', async ($, on) => {
  // Covers: B93, B214
  const files: Files = new Map()
  const fake = belowFake()
  const { clock } = await start($, on, fake, {}, files)
  const above = await $.ui.mount({ ...BAND, surface: 'terminal', viewport: mainScreen(200) })
  const hint = await drawHint($, null)
  expect(await enginesHint(hint)).toEqual({ hint: HINT, tail: TAIL })
  await clock.advance(50_000)
  const sentence = 'm2b could not read the tasks: reminders did not answer within 20 seconds'
  const snapshot = { candidates: [], review: null, error: sentence }
  files.set(SHARED_ANSWER, JSON.stringify({ writtenAtMs: clock.now(), value: { snapshot, status: 'could not look', version: '0.3.0' } }))
  const callsBefore = fake.calls.length

  await clock.advance(10_000)

  expect(fake.calls).toHaveLength(callsBefore + 1)
  expect(await enginesHint(hint)).toEqual({ hint: HINT, tail: TAIL })
  expect(await everyText(above)).toEqual([ENGINES_OWN_DRAWING])
  await hint.unmount()
  await above.unmount()
})

test('a shared answer that names the place below is taken, and the band is below the prompt without asking m2b', async ($, on) => {
  // Covers: B214, B213
  const candidates = [{ id: 'c8', title: 'Remember? From the other session' }]
  const snapshot = { candidates, review: null, error: null, due: [], shows: BELOW }
  const stored = { writtenAtMs: NOW - 1_000, value: { snapshot, status: null, version: '0.3.0' } }
  const files: Files = new Map([[`${HOME}/.local/state/m2b/band-answer.json`, JSON.stringify(stored)]])
  const fake = new FakeM2b()
  await start($, on, fake, {}, files)

  const hint = await drawHint($, null)

  expect(fake.calls).toEqual([])
  expect(await enginesHint(hint)).toEqual({ hint: HINT, tail: 'm2b 1 waits for you · /m2b-pane' })
  await hint.unmount()
})

/** A machine whose band is below the prompt and counts the topics, with one thing of each kind the row counts. */
function fourCounts(): FakeM2b {
  const fake = belowFake()
  fake.shows = { place: 'below', dueTasks: 'count', topics: true }
  fake.dueTasks = [
    { id: 'd1', title: 'Call the plumber', due: '2026-03-10', overdue: true },
    { id: 'd2', title: 'Send the offer to Acme', due: '2026-03-14', overdue: false },
  ]
  fake.given = { topics: [{ name: 'Northwind', facts: 3, current: 0 }], atStart: 'whole', offUnder: null }
  return fake
}

/**
 * What the row of `fourCounts` says by the columns of the line, at both ends of each stretch. The
 * counts take 15, 9, 11 and 7 cells, two apart, and 2 after them; the mark takes 1.
 */
const COUNTS_BY_ROOM: [number, string][] = [
  [ROOM_FOR_THE_CALM_ROW + 50, '1 waits for you  1 overdue  1 due today  1 topic'],
  [ROOM_FOR_THE_CALM_ROW + 49, '1 waits for you  1 overdue  1 due today  …'],
  [ROOM_FOR_THE_CALM_ROW + 44, '1 waits for you  1 overdue  1 due today  …'],
  [ROOM_FOR_THE_CALM_ROW + 43, '1 waits for you  1 overdue  …'],
  [ROOM_FOR_THE_CALM_ROW + 31, '1 waits for you  1 overdue  …'],
  [ROOM_FOR_THE_CALM_ROW + 30, '1 waits for you  …'],
  [ROOM_FOR_THE_CALM_ROW + 20, '1 waits for you  …'],
]
const ALL_FOUR_WORDS = 'm2b 1 waits for you · 1 overdue · 1 due today · 1 topic · /m2b-pane'

test('where the line has not room for every count the last give way to the mark: first the topics, then what is due today, then the overdue, and what waits stays', async ($, on) => {
  // Covers: B214
  await start($, on, fourCounts())

  for (const [columns, says] of COUNTS_BY_ROOM) {
    const hint = await drawHint($, mainScreen(columns))
    expect(await enginesHint(hint)).toBeNull()
    expect(await orderAt(hint, HINT_ROW)).toEqual([HINT, 'm2b', says, `/${COMMAND}`])
    await hint.unmount()
  }

  // Not even what waits and the mark: the engine's line, and every word of m2b at its end.
  const words = await drawHint($, mainScreen(ROOM_FOR_THE_CALM_ROW + 19))
  expect(await words.find({ key: HINT_ROW })).toBeUndefined()
  expect(await enginesHint(words)).toEqual({ hint: HINT, tail: ALL_FOUR_WORDS })
  await words.unmount()
})

test('the counts a shortened row keeps hold their colors, the mark after them is stepped back, and the way into the pane stays: the command, or the button under the fullscreen layout', async ($, on) => {
  // Covers: B214
  const { opened } = await start($, on, fourCounts())
  const kept = [colored('1 waits for you', 'warning'), colored('  1 overdue', 'error'), colored('  1 due today', 'warning')]

  const onMainScreen = await drawHint($, mainScreen(ROOM_FOR_THE_CALM_ROW + 44))
  expect(await piecesAt(onMainScreen, HINT_ROW)).toEqual([dim(HINT), NAME, ...kept, MARK, dim(`/${COMMAND}`)])
  expect(await onMainScreen.findAll({ type: 'Button' })).toEqual([])
  await onMainScreen.unmount()

  const underFullscreen = await drawHint($, fullscreen(ROOM_FOR_THE_CALM_ROW + 44))
  expect(await piecesAt(underFullscreen, HINT_ROW)).toEqual([dim(HINT), NAME, ...kept, MARK])
  expect(await buttonsAt(underFullscreen, HINT_ROW)).toEqual([{ key: OPEN, label: 'open', variant: undefined, dimColor: false }])
  await underFullscreen.press({ key: OPEN })
  expect(opened).toEqual([AS_A_DIALOG])
  await underFullscreen.unmount()
})

test('a row of counts that has not room for all keeps the most from the front that have room together with the mark, a piece that is stepped back', () => {
  // Covers: B214
  const waits = { text: '1 waits for you', tone: 'waits' as const }
  const overdue = { text: '1 overdue', tone: 'overdue' as const }
  const dueToday = { text: '1 due today', tone: 'dueToday' as const }
  const topics = { text: '1 topic', tone: 'quiet' as const }
  const all = lineOf({ parts: [waits, overdue, dueToday, topics] })
  const fixed = ROOM_FOR_THE_CALM_ROW
  const shown = (line: BandLine, columns: number) => belowPrompt(line, HINT, columns, COMMAND)
  const row = (...parts: BandLine['parts']) => ({ kind: 'row', line: lineOf({ parts }) })

  // All four: 15, 9, 11 and 7 cells, two apart, and 2 after them.
  expect(shown(all, fixed + 50)).toEqual({ kind: 'row', line: all })
  // The mark in place of the topics: 15, 9, 11 and 1, two apart, and 2.
  expect(shown(all, fixed + 49)).toEqual(row(waits, overdue, dueToday, MORE))
  expect(shown(all, fixed + 44)).toEqual(row(waits, overdue, dueToday, MORE))
  expect(shown(all, fixed + 43)).toEqual(row(waits, overdue, MORE))
  expect(shown(all, fixed + 31)).toEqual(row(waits, overdue, MORE))
  expect(shown(all, fixed + 30)).toEqual(row(waits, MORE))
  expect(shown(all, fixed + 20)).toEqual(row(waits, MORE))
  expect(shown(all, fixed + 19)).toEqual({ kind: 'tail', text: ALL_FOUR_WORDS })
  expect(shown(all, 0)).toEqual({ kind: 'tail', text: ALL_FOUR_WORDS })

  // Whatever the row counts first stays last: with nothing waiting, the overdue.
  const due = lineOf({ parts: [overdue, dueToday, topics] })
  expect(shown(due, fixed + 33)).toEqual({ kind: 'row', line: due })
  expect(shown(due, fixed + 32)).toEqual(row(overdue, dueToday, MORE))
  expect(shown(due, fixed + 27)).toEqual(row(overdue, dueToday, MORE))
  expect(shown(due, fixed + 26)).toEqual(row(overdue, MORE))
  expect(shown(due, fixed + 14)).toEqual(row(overdue, MORE))
  expect(shown(due, fixed + 13)).toEqual({ kind: 'tail', text: 'm2b 1 overdue · 1 due today · 1 topic · /m2b-pane' })

  // A wide letter in a count kept counts as two cells.
  const wide = lineOf({ parts: [{ text: '1 件 waits', tone: 'waits' }, topics] })
  expect(shown(wide, fixed + 10 + 2 + 1 + 2)).toEqual(row({ text: '1 件 waits', tone: 'waits' }, MORE))
  expect(shown(wide, fixed + 10 + 2 + 1 + 2 - 1).kind).toBe('tail')
})

test('at least one count is kept beside the mark: a single count has nothing to leave out, and where the first count has room alone but not with the mark the row gives way whole', () => {
  // Covers: B214
  const waits = { text: '1 waits for you', tone: 'waits' as const }
  const topics = { text: '1 topic', tone: 'quiet' as const }
  const fixed = ROOM_FOR_THE_CALM_ROW

  const one = lineOf({ parts: [waits] })
  expect(belowPrompt(one, HINT, fixed + 17, COMMAND)).toEqual({ kind: 'row', line: one })
  expect(belowPrompt(one, HINT, fixed + 16, COMMAND)).toEqual({ kind: 'tail', text: 'm2b 1 waits for you · /m2b-pane' })

  const two = lineOf({ parts: [waits, topics] })
  expect(belowPrompt(two, HINT, fixed + 26, COMMAND)).toEqual({ kind: 'row', line: two })
  expect(belowPrompt(two, HINT, fixed + 25, COMMAND)).toEqual({ kind: 'row', line: lineOf({ parts: [waits, MORE] }) })
  expect(belowPrompt(two, HINT, fixed + 20, COMMAND)).toEqual({ kind: 'row', line: lineOf({ parts: [waits, MORE] }) })
  // What waits alone takes 17 cells: room for it, not for the mark that says a count is left out.
  for (const columns of [fixed + 19, fixed + 17]) {
    expect(belowPrompt(two, HINT, columns, COMMAND)).toEqual({ kind: 'tail', text: 'm2b 1 waits for you · 1 topic · /m2b-pane' })
  }
})

test('a sentence is never shortened by m2b: with all of its room it is the row, one cell short it is the words, whole', () => {
  // Covers: B214
  const fixed = ROOM_FOR_THE_CALM_ROW
  const notShown = 'the m2b pane cannot be shown here'
  const named = lineOf({ parts: [{ text: notShown, tone: 'trouble' }] })
  expect(belowPrompt(named, HINT, fixed + 33 + 2, COMMAND)).toEqual({ kind: 'row', line: named })
  for (const columns of [fixed + 33 + 2 - 1, fixed + 20, fixed]) {
    expect(belowPrompt(named, HINT, columns, COMMAND)).toEqual({ kind: 'tail', text: `m2b ${notShown}` })
  }

  // A sentence that names m2b itself has no name before it, and its 5 cells are free.
  const unread = 'm2b could not read the tasks: no answer'
  const ofM2b = lineOf({ parts: [{ text: unread, tone: 'trouble' }], isNamed: false })
  expect(belowPrompt(ofM2b, HINT, fixed - 5 + 39 + 2, COMMAND)).toEqual({ kind: 'row', line: ofM2b })
  for (const columns of [fixed - 5 + 39 + 2 - 1, fixed + 20, fixed]) {
    expect(belowPrompt(ofM2b, HINT, columns, COMMAND)).toEqual({ kind: 'tail', text: unread })
  }
})

test('the calm row has no pieces: where m2b and the way into the pane have room it is the row, one cell short the words, and no mark stands in it', () => {
  // Covers: B214, B213
  const calm = lineOf({ isCalm: true })
  for (const columns of [ROOM_FOR_THE_CALM_ROW, ROOM_FOR_THE_CALM_ROW + 1, 200]) {
    expect(belowPrompt(calm, HINT, columns, COMMAND)).toEqual({ kind: 'row', line: calm })
  }
  for (const columns of [ROOM_FOR_THE_CALM_ROW - 1, 0, null]) {
    expect(belowPrompt(calm, HINT, columns, COMMAND)).toEqual({ kind: 'tail', text: CALM_TAIL })
  }
  // A longer hint takes its cells from that room.
  expect(belowPrompt(calm, `${HINT} · esc`, ROOM_FOR_THE_CALM_ROW + 6, COMMAND).kind).toBe('row')
  expect(belowPrompt(calm, `${HINT} · esc`, ROOM_FOR_THE_CALM_ROW + 5, COMMAND).kind).toBe('tail')
})

test('the room of the row below the prompt: 2 cells kept free, 27 for the mode, the hint and 2, m2b and 2 where the row is named, the pieces two apart and 2, and the wider of the button and the command', () => {
  // Covers: B214
  const waits = { text: '1 waits for you', tone: 'waits' as const }
  const overdue = { text: '1 overdue', tone: 'overdue' as const }
  const counts = lineOf({ parts: [waits, overdue] })

  expect(belowPrompt(counts, HINT, ROOM_FOR_THE_ROW, COMMAND)).toEqual({ kind: 'row', line: counts })
  // One cell short of all of it, the second count gives way to the mark.
  expect(belowPrompt(counts, HINT, ROOM_FOR_THE_ROW - 1, COMMAND)).toEqual({ kind: 'row', line: lineOf({ parts: [waits, MORE] }) })
  expect(belowPrompt(counts, HINT, ROOM_FOR_THE_FIRST_COUNT, COMMAND)).toEqual({ kind: 'row', line: lineOf({ parts: [waits, MORE] }) })
  expect(belowPrompt(counts, HINT, ROOM_FOR_THE_FIRST_COUNT - 1, COMMAND)).toEqual({ kind: 'tail', text: TAIL })
  expect(belowPrompt(counts, HINT, null, COMMAND)).toEqual({ kind: 'tail', text: TAIL })
  // One piece: no gap between pieces, and nothing to leave out.
  const one = lineOf({ parts: [waits] })
  expect(belowPrompt(one, HINT, 2 + 27 + 15 + 2 + 5 + 17 + 9, COMMAND).kind).toBe('row')
  expect(belowPrompt(one, HINT, 2 + 27 + 15 + 2 + 5 + 17 + 9 - 1, COMMAND)).toEqual({ kind: 'tail', text: 'm2b 1 waits for you · /m2b-pane' })
  // No hint: its cells are free, the 2 after it are counted all the same.
  expect(belowPrompt(one, '', 2 + 27 + 2 + 5 + 17 + 9, COMMAND).kind).toBe('row')
  expect(belowPrompt(one, '', 2 + 27 + 2 + 5 + 17 + 9 - 1, COMMAND).kind).toBe('tail')
  // A command shorter than the button `[ open ]` leaves the button's 8 cells counted; a longer one counts itself.
  expect(belowPrompt(one, HINT, 2 + 27 + 15 + 2 + 5 + 17 + 8, 'm2b').kind).toBe('row')
  expect(belowPrompt(one, HINT, 2 + 27 + 15 + 2 + 5 + 17 + 8 - 1, 'm2b')).toEqual({ kind: 'tail', text: 'm2b 1 waits for you · /m2b' })
  expect(belowPrompt(one, HINT, 2 + 27 + 15 + 2 + 5 + 17 + 12, 'm2b-session').kind).toBe('row')
  expect(belowPrompt(one, HINT, 2 + 27 + 15 + 2 + 5 + 17 + 12 - 1, 'm2b-session').kind).toBe('tail')
  // A letter a terminal draws two cells wide counts as two: an emoji, a CJK letter.
  for (const wide of ['😀 for shortcuts', '中 for shortcuts']) {
    expect(belowPrompt(one, wide, 2 + 27 + 16 + 2 + 5 + 17 + 9, COMMAND).kind).toBe('row')
    expect(belowPrompt(one, wide, 2 + 27 + 16 + 2 + 5 + 17 + 9 - 1, COMMAND).kind).toBe('tail')
  }
  // A sign a terminal draws one cell wide stays one, though it can be shown as an emoji.
  expect(belowPrompt(one, '⏸ for shortcuts', 2 + 27 + 15 + 2 + 5 + 17 + 9, COMMAND).kind).toBe('row')
  expect(belowPrompt(one, '⏸ for shortcuts', 2 + 27 + 15 + 2 + 5 + 17 + 9 - 1, COMMAND).kind).toBe('tail')
  // Wide letters in a piece and in the command count the same way.
  const wideLine = lineOf({ parts: [{ text: '1 件 waits', tone: 'waits' }] })
  expect(belowPrompt(wideLine, HINT, 2 + 27 + 15 + 2 + 5 + (10 + 2) + 9, COMMAND).kind).toBe('row')
  expect(belowPrompt(wideLine, HINT, 2 + 27 + 15 + 2 + 5 + (10 + 2) + 9 - 1, COMMAND).kind).toBe('tail')
})

test('the words m2b hands the engine: the counts joined by a dot with the command last, m2b and the command alone while calm, and a sentence as it is, with m2b before it only where it does not name m2b itself', () => {
  // Covers: B214
  const calm = lineOf({ isCalm: true })
  expect(belowPrompt(calm, HINT, ROOM_FOR_THE_CALM_ROW, COMMAND)).toEqual({ kind: 'row', line: calm })
  expect(belowPrompt(calm, HINT, ROOM_FOR_THE_CALM_ROW - 1, COMMAND)).toEqual({ kind: 'tail', text: CALM_TAIL })

  const three = lineOf({
    parts: [
      { text: '4 wait for you', tone: 'waits' },
      { text: '3 overdue', tone: 'overdue' },
      { text: '2 due today', tone: 'dueToday' },
      { text: '2 topics', tone: 'quiet' },
    ],
  })
  expect(belowPrompt(three, HINT, null, COMMAND)).toEqual({
    kind: 'tail',
    text: 'm2b 4 wait for you · 3 overdue · 2 due today · 2 topics · /m2b-pane',
  })

  const ofM2b = lineOf({ parts: [{ text: 'm2b could not read the tasks: no answer', tone: 'trouble' }], isNamed: false })
  expect(belowPrompt(ofM2b, HINT, null, COMMAND)).toEqual({ kind: 'tail', text: 'm2b could not read the tasks: no answer' })
  // Unnamed, the row needs no cells for the name: the sentence's 39 and 2 after the 46 of the engine, then the command's 9.
  expect(belowPrompt(ofM2b, HINT, 46 + 41 + 9, COMMAND)).toEqual({ kind: 'row', line: ofM2b })
  expect(belowPrompt(ofM2b, HINT, 46 + 41 + 9 - 1, COMMAND).kind).toBe('tail')

  const named = lineOf({ parts: [{ text: 'the m2b pane cannot be shown here', tone: 'trouble' }] })
  expect(belowPrompt(named, HINT, null, COMMAND)).toEqual({ kind: 'tail', text: 'm2b the m2b pane cannot be shown here' })
})

test('the line of a band below the prompt: a machine that lists the tasks counts them, nothing is listed, and with nothing to say it is calm once m2b answered', () => {
  // Covers: B214, B102
  const due = [
    { id: 'd1', title: 'Return the ladder to Sam', overdue: true },
    { id: 'd2', title: 'Send the offer to Acme', overdue: false },
    { id: 'd3', title: 'Water the plants', overdue: false },
  ]
  const snapshot = { candidates: [{ id: 'c1', title: 'Remember? Dana prefers tea' }], review: null, error: null, due }
  const showing = (dueTasks: 'off' | 'count' | 'list') => bandLine(model({ snapshot: { ...snapshot, shows: { place: 'below', dueTasks, topics: false } } }), 'terminal')
  const waits = { text: '1 waits for you', tone: 'waits' as const }
  const counted = lineOf({ parts: [waits, { text: '1 overdue', tone: 'overdue' }, { text: '2 due today', tone: 'dueToday' }] })

  expect(showing('list')).toEqual(counted)
  expect(showing('count')).toEqual(counted)
  expect(showing('off')).toEqual(lineOf({ parts: [waits] }))
  // Tasks due alone are counts there too, where above the prompt they are a row that says nothing with their names below it.
  const idle = { candidates: [], review: null, error: null, due }
  expect(bandLine(model({ snapshot: { ...idle, shows: { place: 'below', dueTasks: 'list', topics: false } } }), 'terminal')).toEqual(
    lineOf({ parts: [{ text: '1 overdue', tone: 'overdue' }, { text: '2 due today', tone: 'dueToday' }] }),
  )
  expect(bandLine(model({ snapshot: { ...idle, shows: { place: 'below', dueTasks: 'off', topics: false } } }), 'terminal')).toEqual(lineOf({ isCalm: true }))
  expect(bandLine(model(), 'terminal')).toBeNull()
})

test('a machine without an entry has the band below the prompt in a terminal and above it on every other surface; a place the machine names holds on all of them', () => {
  // Covers: B213
  const unset = { place: null, dueTasks: 'count', topics: false } as const
  expect(placeOn(unset, 'terminal')).toBe('below')
  for (const surface of ['desktop', 'mobile', 'web', '']) {
    expect(placeOn(unset, surface)).toBe('above')
  }
  for (const place of ['above', 'below', 'waiting'] as const) {
    for (const surface of ['terminal', 'desktop', 'mobile']) {
      expect(placeOn({ ...unset, place }, surface)).toBe(place)
    }
  }
})
