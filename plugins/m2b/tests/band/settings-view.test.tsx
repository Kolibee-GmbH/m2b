import { expect, test } from 'claude-code/testing'
import type { CommandRunResult } from 'claude-code'
import type { Engine } from 'claude-code/testing'

import { OFF_THE_VALUES, SETTINGS_UNDO, foldKey, valueKey } from '../../hooks/settings'
import {
  NOTES,
  SETTING_AT,
  boxesAt,
  buttonsAt,
  drawnSettings,
  everyText,
  fakeSetting,
  insetsAt,
  inView,
  linesAt,
  lookOf,
  pane,
  partLines,
  partLook,
  piecesAt,
  pressTab,
  settingLines,
  settingsCatalog,
  settingsWorld,
  shownParts,
  shownTab,
  shownTabs,
  shownValues,
  start,
  texts,
  valueKeys,
  valuesLine,
  viewButtons,
} from './harness'
import type { PartKey } from './harness'

// What the settings draw: a part for each group of the core's list, a setting of a group of
// choices with its values side by side, and one row for the settings that only inform, which
// turns the view to them under a tab of their own. When the list is read, what a press does and
// the switch for handing in are held in settings.test.tsx.

const PANE = 'm2b'
const READING = 'm2b is reading its settings…'
const FOLDED = 'that only inform or are changed by a command'
const DOES_NOT_CURATE = 'This machine does not curate: the settings of the curation run do nothing here.'
const LIST = ['settings', '--json']
const UNDO_MS = 5_000

const { MACHINE_ID, PATH, DUE, MODEL, PAUSED, PROPOSE, SKIP, EXECUTABLES, CURATING, BACKEND, TIMEOUT, LANGUAGE, CUSTOMERS } = SETTING_AT
/** The settings of the three groups of choices, and those of the group kept behind one row, each in the order drawn. */
const CHOICES = [DUE, PROPOSE, SKIP, MODEL, CURATING, PAUSED, LANGUAGE]
const ABOUT = [PATH, MACHINE_ID, BACKEND, TIMEOUT, EXECUTABLES, CUSTOMERS]
/**
 * The button of the row the settings that only inform are kept behind, which turns the view to
 * them. Its key names the phase the view is drawn in: while a press waits, and while it is written.
 */
const ABOUT_ROW = 'settings:fold:about'
const ABOUT_ROW_WAITING = 'settings:fold:about:waiting'
const ABOUT_ROW_WRITING = 'settings:fold:about:writing'
/** The tab that leads from that group back to the choices, by a new opening of the settings. */
const BACK_TO_THE_CHOICES = 'tab:settings:in:aside'
/** The title of the one part the view draws once it is turned to that group. */
const ABOUT_TITLE = `6 settings ${FOLDED}`
/** The row of tabs above that group: the six that stay, each a button, and a seventh that bears the group's title. */
const TABS_ABOVE_ABOUT = [
  { label: 'Overview', key: 'tab:overview:in:aside' },
  { label: 'Proposals', key: 'tab:proposals:in:aside' },
  { label: 'Review', key: 'tab:review:in:aside' },
  { label: 'Tasks', key: 'tab:tasks:in:aside' },
  { label: 'Facts', key: 'tab:facts:in:aside' },
  { label: 'Settings', key: BACK_TO_THE_CHOICES },
  { label: 'About this setup', key: null },
]
/** The buttons that set a value in the view as it is read in a terminal, in the order drawn. */
const VALUE_BUTTONS = [`set:${DUE}:0`, `set:${DUE}:2`, `set:${PROPOSE}:0`, `set:${MODEL}:1`, `set:${PAUSED}:0`, `set:${LANGUAGE}:0`]
/** What the view draws of the group kept behind one row once it is turned to it. */
const ABOUT_LINES = [
  `Store folder: ${NOTES}`,
  'change: m2b config set store.path <folder>',
  "This machine's name: tower-1",
  'kept by m2b, never changed by hand',
  'Task list: markdown',
  'set up with /m2b:setup',
  'Time limit of a tasks call: 20',
  'by hand: edit tasks.timeout_seconds in store.json, in the store folder',
  'Programs m2b starts: 3 named',
  'change: m2b config set executables.<program> <path>',
  'Customers: 2 customers',
  'set up with /m2b:worklog-setup',
]
const PART_KEYS: readonly PartKey[] = ['shows', 'reads', 'curation', 'about']

const world = settingsWorld

function typed($: Engine, command: string, args = ''): Promise<CommandRunResult> {
  return $.command.run({ command, args, origin: { kind: 'composer' }, presentation: { isFullscreen: false, columns: 100 } })
}

type Clock = Awaited<ReturnType<typeof start>>['clock']

/** The settings, opened with the command and read. */
async function openView($: Engine, clock: Clock, columns = 80, surface: 'terminal' | 'mobile' = 'terminal') {
  await typed($, 'm2b-settings')
  await clock.advance(1)
  return $.ui.mount({ ...pane(PANE, columns), surface })
}

/** A drawing of the pane, on whatever surface it was mounted. */
type Mounted = Parameters<typeof inView>[0]

type On = Parameters<typeof start>[1]

/** Every write to the session's state from here on, as JSON: that state is one every plugin can read. */
function stateWrites(on: On): string[] {
  const writes: string[] = []
  on('state.set', (_, e, next) => {
    writes.push(JSON.stringify(e))
    return next(e)
  })
  return writes
}

/** The key of every button the pane draws, the tabs among them. */
async function everyButton(ui: Mounted): Promise<string[]> {
  return (await ui.findAll({ type: 'Button' })).map(button => String(button.key))
}

/** The key and the title of each part of the view, in the order drawn. */
async function headings(ui: Mounted): Promise<string[][]> {
  return (await shownParts(ui)).map(part => [part.key, part.title])
}

/** The rows of values of the settings at `places`, each as the line it stands on. */
async function rows(ui: Mounted, places: readonly number[]): Promise<(string | null)[]> {
  return Promise.all(places.map(at => valuesLine(ui, at)))
}

/** The switches of the test catalog, in the order drawn. */
const SWITCHES = [DUE, PROPOSE, MODEL, PAUSED, LANGUAGE]
/** Their rows as read, and while no value can be pressed. */
const ROWS_TO_PRESS = ['[off] ● count [list]', '[on] ● off', '● haiku [sonnet]', '[on] ● off', '[de] ● en']
const ROWS_STEPPED_BACK = ['off ● count list', 'on ● off', '● haiku sonnet', 'on ● off', 'de ● en']

test('the view is the groups of the core as parts, in its order and under its titles, and each setting stands at its place in its group whatever the order of the list', async ($, on) => {
  // Covers: B197
  const { fake, settings } = world()
  const { clock } = await start($, on, fake)
  const ui = await openView($, clock)
  const asListed = await shownParts(ui)
  expect(asListed.map(part => [part.key, part.title])).toEqual([
    ['shows', 'What m2b shows'],
    ['reads', 'What m2b reads'],
    ['curation', 'Curation'],
    ['about', 'About this setup'],
  ])
  expect(await drawnSettings(ui)).toEqual(CHOICES)
  await ui.press({ key: ABOUT_ROW })
  expect(await drawnSettings(ui)).toEqual(ABOUT)
  expect(await partLines(ui, 'about')).toEqual(ABOUT_LINES)

  // The same settings listed backwards, and the groups named in another order under other titles.
  settings.entries.reverse()
  settings.groups = [
    { name: 'curation', title: 'Runs', folded: false },
    { name: 'about', title: 'Facts', folded: true },
    { name: 'shows', title: 'In the band', folded: false },
    { name: 'reads', title: 'Read by m2b', folded: false },
  ]
  await typed($, 'm2b-settings')
  await clock.advance(1)

  expect(await headings(ui)).toEqual([
    ['curation', 'Runs'],
    ['about', 'Facts'],
    ['shows', 'In the band'],
    ['reads', 'Read by m2b'],
  ])
  // Each part holds the lines it held before: the order in a group is the core's place, not the list's.
  for (const part of await shownParts(ui)) {
    expect(part.lines).toEqual(asListed.find(one => one.key === part.key)?.lines)
  }
  // A setting is keyed by where it stands in the list as read, which a press names.
  const last = settingsCatalog().length - 1
  expect(await drawnSettings(ui)).toEqual([MODEL, CURATING, PAUSED, LANGUAGE, DUE, PROPOSE, SKIP].map(at => last - at))
  // The row of the folded group stands where the core names the group: second, below the first part's values.
  expect(await viewButtons(ui)).toEqual([
    `set:${last - MODEL}:1`,
    `set:${last - PAUSED}:0`,
    `set:${last - LANGUAGE}:0`,
    ABOUT_ROW,
    `set:${last - DUE}:0`,
    `set:${last - DUE}:2`,
    `set:${last - PROPOSE}:0`,
  ])
  // Under its tab, which bears the title the core gave it, the group holds its settings in the order of their place.
  await ui.press({ key: ABOUT_ROW })
  expect((await shownTabs(ui)).at(-1)).toEqual({ label: 'Facts', key: null })
  expect(await partLines(ui, 'about')).toEqual(ABOUT_LINES)
  expect(await drawnSettings(ui)).toEqual(ABOUT.map(at => last - at))
  await ui.unmount()
})

test('a group without a setting draws no part, and a setting is drawn in its group whatever file it lives in', async ($, on) => {
  // Covers: B197
  const { fake, settings } = world()
  settings.entries = settings.entries.filter(entry => entry.group !== 'shows')
  settings.groups?.push({ name: 'more', title: 'More', folded: true })
  const { clock } = await start($, on, fake)
  /** The group, the key and the file of each setting the view draws, in the order drawn. */
  const filed = async (): Promise<(string | undefined)[][]> =>
    (await drawnSettings(ui)).map(at => settings.entries[at]).map(entry => [entry?.group, entry?.key, entry?.file])
  /** What the view says that sorts the settings by file: a heading of the list there was, or the name of a file a setting lives in. */
  const byFile = async (): Promise<string[]> =>
    (await texts(ui)).filter(text => /^(This machine|The store, for every machine|The owner, for every machine)$|config\.json|profile\.json/.test(text))

  const ui = await openView($, clock)

  // Neither the group of choices without a setting nor the folded one without any has a part or a row.
  expect(await headings(ui)).toEqual([
    ['reads', 'What m2b reads'],
    ['curation', 'Curation'],
    ['about', 'About this setup'],
  ])
  expect(await viewButtons(ui)).toEqual([...VALUE_BUTTONS.slice(2).map(key => key.replace(/^set:(\d+)/, (_, at) => `set:${Number(at) - 1}`)), ABOUT_ROW])
  expect(await filed()).toEqual([
    ['reads', 'sessions.propose', 'config.json'],
    ['reads', 'distillate.skip_under', 'config.json'],
    ['curation', 'curation.model', 'config.json'],
    ['curation', 'curating_machine', 'store.json'],
    ['curation', 'curation.paused', 'config.json'],
    ['curation', 'language', 'profile.json'],
  ])
  expect(await byFile()).toEqual([])

  await ui.press({ key: ABOUT_ROW })

  expect(await filed()).toEqual([
    ['about', 'store.path', 'config.json'],
    ['about', 'machine_id', 'config.json'],
    ['about', 'tasks.backend', 'store.json'],
    ['about', 'tasks.timeout_seconds', 'store.json'],
    ['about', 'executables', 'config.json'],
    ['about', 'customers', 'profile.json'],
  ])
  expect(await byFile()).toEqual([])
  await ui.unmount()
})

test('the view is drawn as parts and nothing of it stands outside one: no heading repeats its tab, no part counts or is in the color of what waits, and each is framed from 36 columns', async ($, on) => {
  // Covers: B197
  const { fake } = world()
  const { clock } = await start($, on, fake)

  for (const [columns, frame] of [
    [80, { borderStyle: 'round', paddingX: 1 }],
    [36, { borderStyle: 'round', paddingX: 1 }],
    [35, { borderStyle: 'quote', paddingX: 0 }],
    [24, { borderStyle: 'quote', paddingX: 0 }],
  ] as const) {
    const calm = { ...frame, borderColor: 'subtle', titleColor: 'remember', titleWeight: 'bold', countColor: undefined }
    const ui = await openView($, clock, columns)
    // A press that waits is nothing that waits for an answer: the part keeps its color.
    await ui.press({ key: `set:${PAUSED}:0` })

    const parts = await shownParts(ui)
    expect(parts.map(part => part.key)).toEqual([...PART_KEYS])
    const inParts = parts.flatMap(part => [part.title, ...part.lines])
    expect((await texts(ui)).filter(text => !inParts.some(line => line.includes(text)))).toEqual([])
    expect((await texts(ui))[0]).toBe('What m2b shows')
    expect(await texts(ui)).not.toContain('Settings')
    for (const key of PART_KEYS) {
      expect(await partLook(ui, key)).toEqual(calm)
    }
    expect(parts.map(part => part.count)).toEqual([null, null, null, null])

    // The folded group under its own tab is one part of the same form: the tab is the one place
    // that bears the group's title, and the part says what it holds.
    await ui.press({ key: ABOUT_ROW_WAITING })
    expect(await shownParts(ui)).toEqual([{ key: 'about', title: ABOUT_TITLE, count: null, lines: ABOUT_LINES }])
    expect(await texts(ui)).toEqual([ABOUT_TITLE, ...ABOUT_LINES])
    expect(await partLook(ui, 'about')).toEqual(calm)
    await ui.unmount()
  }
})

test('a setting of a group of choices is its title, bold, what it does, dim, and its values side by side: the one in force marked and no button, every other a button labelled with the value', async ($, on) => {
  // Covers: B211
  const { fake } = world()
  const { clock } = await start($, on, fake)

  const ui = await openView($, clock)

  expect(await settingLines(ui, PAUSED)).toEqual(['Curation paused', 'What curation.paused does.', '[on] ● off'])
  // The texts of the block: the buttons stand between them, in the row.
  expect(await piecesAt(ui, `setting:${PAUSED}`)).toEqual([
    { text: 'Curation paused', color: undefined, dimColor: undefined, weight: 'bold', strikethrough: undefined },
    { text: 'What curation.paused does.', color: undefined, dimColor: true, weight: undefined, strikethrough: undefined },
    { text: '● off', color: 'remember', dimColor: undefined, weight: 'bold', strikethrough: undefined },
  ])
  // On and off for a switch of two, any other value as the core names it, in the core's order.
  expect(await shownValues(ui, PAUSED)).toEqual([
    { label: 'on', is: 'to press', key: `set:${PAUSED}:0` },
    { label: 'off', is: 'in force', key: null },
  ])
  expect(await shownValues(ui, DUE)).toEqual([
    { label: 'off', is: 'to press', key: `set:${DUE}:0` },
    { label: 'count', is: 'in force', key: null },
    { label: 'list', is: 'to press', key: `set:${DUE}:2` },
  ])
  expect(await shownValues(ui, MODEL)).toEqual([
    { label: 'haiku', is: 'in force', key: null },
    { label: 'sonnet', is: 'to press', key: `set:${MODEL}:1` },
  ])
  // A value's button is neither the accent of its row nor stepped back.
  for (const value of await buttonsAt(ui, `values:${DUE}`)) {
    expect(value.variant).toBeUndefined()
    expect(value.dimColor).not.toBe(true)
  }
  // The block is a column, its values a row that breaks between them where it is too narrow.
  expect(await boxesAt(ui, `setting:${DUE}`)).toEqual([{ key: `values:${DUE}`, flexDirection: 'row', rowGap: undefined, columnGap: 1, flexWrap: 'wrap', holds: [] }])
  expect((await ui.find({ key: `setting:${DUE}` }))?.props['flexDirection']).toBe('column')
  await ui.unmount()
})

test('the settings of a group of choices stand apart, an empty line between them, in one box below the title of their part', async ($, on) => {
  // Covers: B211
  const { fake } = world()
  const { clock } = await start($, on, fake)

  const ui = await openView($, clock)

  for (const [part, holds] of [
    ['shows', [DUE]],
    ['reads', [PROPOSE, SKIP]],
    ['curation', [MODEL, CURATING, PAUSED, LANGUAGE]],
  ] as const) {
    const [heading, apart, ...more] = await boxesAt(ui, `part:${part}`)
    expect(heading?.flexDirection).toBe('row')
    expect(apart).toMatchObject({ key: null, flexDirection: 'column', rowGap: 1 })
    expect(apart?.holds.map(box => box.key)).toEqual(holds.map(at => `setting:${at}`))
    expect(more).toEqual([])
  }
  await ui.unmount()
})

test('a value the file holds that is none of the choices stands first, marked as in force, before every choice as a button', async ($, on) => {
  // Covers: B211
  const { fake, settings } = world()
  Object.assign(settings.entries[MODEL] ?? {}, { value: 'opus', shows: 'opus' })
  Object.assign(settings.entries[LANGUAGE] ?? {}, { value: 'fr', shows: 'fr' })
  const { clock } = await start($, on, fake)

  const ui = await openView($, clock)

  expect(await shownValues(ui, MODEL)).toEqual([
    { label: 'opus', is: 'in force', key: null },
    { label: 'haiku', is: 'to press', key: `set:${MODEL}:0` },
    { label: 'sonnet', is: 'to press', key: `set:${MODEL}:1` },
  ])
  expect(await valuesLine(ui, LANGUAGE)).toBe('● fr [de] [en]')
  // Each of the choices can be changed to.
  await ui.press({ key: `set:${MODEL}:0` })
  expect(await valuesLine(ui, MODEL)).toBe('[undo] changing to haiku')
  await clock.advance(UNDO_MS)
  await clock.advance(1)
  expect(fake.settingCalls().slice(1)).toEqual([['settings', 'set', '--', 'curation.model', 'haiku'], LIST])
  expect(await valuesLine(ui, MODEL)).toBe('● haiku [sonnet]')
  await ui.unmount()
})

test('a setting that is no switch has, in a group of choices, its one value, marked, and below it, indented whole and dim, how it changes; it offers nothing to press', async ($, on) => {
  // Covers: B211
  const { fake, settings } = world()
  // One of each way a setting changes, sorted into a group of choices.
  for (const [at, place] of [
    [MACHINE_ID, 2],
    [PATH, 3],
    [BACKEND, 4],
    [TIMEOUT, 5],
  ] as const) {
    Object.assign(settings.entries[at] ?? {}, { group: 'shows', place })
  }
  const { clock } = await start($, on, fake)
  const ui = await openView($, clock)
  const noSwitch: [number, string, string, string][] = [
    [SKIP, 'Folders m2b is left out of', '2 folders', 'change: m2b distillate off|on [<folder>]'],
    [CURATING, 'Curating machine', 'tower-1', 'change: m2b curate take-over'],
    [MACHINE_ID, "This machine's name", 'tower-1', 'kept by m2b, never changed by hand'],
    [PATH, 'Store folder', NOTES, 'change: m2b config set store.path <folder>'],
    [BACKEND, 'Task list', 'markdown', 'set up with /m2b:setup'],
    [TIMEOUT, 'Time limit of a tasks call', '20', 'by hand: edit tasks.timeout_seconds in store.json, in the store folder'],
  ]

  for (const [at, title, value, how] of noSwitch) {
    const key = settingsCatalog()[at]?.key
    expect(await settingLines(ui, at)).toEqual([title, `What ${key} does.`, `● ${value}`, how])
    expect(await shownValues(ui, at)).toEqual([{ label: value, is: 'in force', key: null }])
    expect(await insetsAt(ui, `setting:${at}`)).toEqual([{ paddingLeft: 2, lines: [how] }])
    expect(await piecesAt(ui, `setting:${at}`)).toMatchObject([
      { text: title, weight: 'bold' },
      { text: `What ${key} does.`, dimColor: true },
      { text: `● ${value}`, color: 'remember', weight: 'bold' },
      { text: how, dimColor: true },
    ])
    expect(await buttonsAt(ui, `setting:${at}`)).toEqual([])
  }
  // A switch says its command nowhere: its values are the way it changes.
  expect((await texts(ui)).filter(text => text.includes('m2b settings set'))).toEqual([])
  expect(await insetsAt(ui, `setting:${PAUSED}`)).toEqual([])
  await ui.unmount()
})

for (const [what, at, place, isOnBefore, words, written, after] of [
  ['on', PAUSED, 0, false, 'turning on', ['curation.paused', 'true'], '● on [off]'],
  ['off', PAUSED, 1, true, 'turning off', ['curation.paused', 'false'], '[on] ● off'],
  ['another name', DUE, 2, false, 'changing to list', ['band.due_tasks', 'list'], '[off] [count] ● list'],
] as const) {
  test(`a press that turns a setting to ${what} puts undo and "${words}" where its values stood; while it waits and while it is written no value of any setting is a button, and after it every value is one again`, async ($, on) => {
    // Covers: B198, B211
    const { fake, settings } = world()
    if (isOnBefore) {
      Object.assign(settings.entries[PAUSED] ?? {}, { value: true, shows: 'on' })
    }
    fake.delayMs = args => (args[0] === 'settings' && args[1] === 'set' ? 3_000 : 0)
    const { clock } = await start($, on, fake)
    const ui = await openView($, clock)
    const others = SWITCHES.filter(other => other !== at)
    const steppedBack = others.map(other => ROWS_STEPPED_BACK[SWITCHES.indexOf(other)])
    const before = await rows(ui, others)
    expect(before.every(row => row?.includes('['))).toBe(true)

    await ui.press({ key: `set:${at}:${place}` })

    // Waiting: undo, a button like any value's, and dim beside it what the press does.
    expect(await linesAt(ui, `values:${at}`)).toEqual([`[undo] ${words}`])
    expect(await buttonsAt(ui, `values:${at}`)).toMatchObject([{ key: 'settings:undo', label: 'undo', variant: undefined }])
    expect(await piecesAt(ui, `values:${at}`)).toMatchObject([{ text: words, dimColor: true }])
    expect((await ui.find({ key: `values:${at}` }))?.props).toMatchObject({ flexDirection: 'row', flexWrap: 'wrap' })
    expect(await rows(ui, others)).toEqual(steppedBack)
    expect(await viewButtons(ui)).toEqual(['settings:undo', ABOUT_ROW_WAITING])
    // What stepped back is dim text, the value in force keeps its mark.
    for (const other of others) {
      expect((await shownValues(ui, other))?.map(value => value.is).sort()).toEqual(
        other === DUE ? ['in force', 'stepped back', 'stepped back'] : ['in force', 'stepped back'],
      )
    }

    await clock.advance(UNDO_MS)

    // Being written: the words alone, with a mark that it goes on, and no button.
    expect((await settingLines(ui, at))?.at(-1)).toBe(`${words}…`)
    expect((await lookOf(ui, `${words}…`))?.dimColor).toBe(true)
    expect(await buttonsAt(ui, `setting:${at}`)).toEqual([])
    expect(await rows(ui, others)).toEqual(steppedBack)
    expect(await viewButtons(ui)).toEqual([ABOUT_ROW_WRITING])

    await clock.advance(3_000)
    await clock.advance(1)

    expect(fake.settingCalls().slice(1)).toEqual([['settings', 'set', '--', ...written], LIST])
    expect(await valuesLine(ui, at)).toBe(after)
    expect(await rows(ui, others)).toEqual(before)
    expect((await viewButtons(ui)).at(-1)).toBe(ABOUT_ROW)
    await ui.unmount()
  })
}

test('undo puts the values back where they stood, every other value is a button again, and nothing is written', async ($, on) => {
  // Covers: B198, B211
  const { fake } = world()
  const { clock } = await start($, on, fake)
  const ui = await openView($, clock)

  await ui.press({ key: `set:${DUE}:2` })
  expect(await rows(ui, SWITCHES)).toEqual(['[undo] changing to list', ...ROWS_STEPPED_BACK.slice(1)])
  await ui.press({ key: SETTINGS_UNDO })

  expect(await rows(ui, SWITCHES)).toEqual(ROWS_TO_PRESS)
  expect(await valueKeys(ui)).toEqual(VALUE_BUTTONS)
  await clock.advance(10_000)
  expect(fake.settingCalls()).toEqual([LIST])
  expect(await rows(ui, SWITCHES)).toEqual(ROWS_TO_PRESS)
  await ui.unmount()
})

test('a group the core marks as folded is one row among the choices: a button that counts its settings and, dim beside it, what they are; none of its settings is drawn there', async ($, on) => {
  // Covers: B212
  const { fake, settings } = world()
  const { clock } = await start($, on, fake)

  const ui = await openView($, clock)

  expect(await partLines(ui, 'about')).toEqual([`[6 settings] ${FOLDED}`])
  expect(await buttonsAt(ui, 'folded:about')).toMatchObject([{ key: ABOUT_ROW, label: '6 settings', variant: undefined }])
  expect((await buttonsAt(ui, 'folded:about'))[0]?.dimColor).not.toBe(true)
  expect((await lookOf(ui, FOLDED))?.dimColor).toBe(true)
  expect(await boxesAt(ui, 'part:about')).toMatchObject([{ flexDirection: 'row' }, { key: 'folded:about', flexDirection: 'row', columnGap: 1, flexWrap: 'wrap' }])
  expect(await drawnSettings(ui)).toEqual(CHOICES)
  const shown = await texts(ui)
  for (const line of ABOUT_LINES) {
    expect(shown).not.toContain(line)
  }
  expect(foldKey('about')).toBe(ABOUT_ROW)
  await ui.unmount()

  // One setting is counted as one, in the row and in the title of the part the row leads to.
  settings.entries = settings.entries.filter(entry => entry.group !== 'about' || entry.key === 'store.path')
  const single = await openView($, clock)
  expect(await partLines(single, 'about')).toEqual([`[1 setting] ${FOLDED}`])
  await single.press({ key: ABOUT_ROW })
  expect(await shownParts(single)).toEqual([{ key: 'about', title: `1 setting ${FOLDED}`, count: null, lines: ABOUT_LINES.slice(0, 2) }])
  await single.unmount()
})

for (const [phase, row] of [
  ['no change is under way', ABOUT_ROW],
  ['a press on a value waits', ABOUT_ROW_WAITING],
  ['a press is being written', ABOUT_ROW_WRITING],
] as const) {
  test(`while ${phase} the row of the folded group is drawn under the key of that phase, and its press turns the view to the group under a tab of its own, without asking m2b again`, async ($, on) => {
    // Covers: B212, B200
    const { fake } = world()
    fake.delayMs = args => (args[0] === 'settings' && args[1] === 'set' ? 3_000 : 0)
    const writes = stateWrites(on)
    const { clock } = await start($, on, fake)
    const ui = await openView($, clock)
    if (row !== ABOUT_ROW) {
      await ui.press({ key: `set:${DUE}:0` })
    }
    if (row === ABOUT_ROW_WRITING) {
      await clock.advance(UNDO_MS)
    }

    // The row reads the same in every phase; of its three keys the view draws the one of the phase.
    expect(await partLines(ui, 'about')).toEqual([`[6 settings] ${FOLDED}`])
    expect(await buttonsAt(ui, 'folded:about')).toMatchObject([{ key: row, label: '6 settings', variant: undefined }])
    expect((await everyButton(ui)).filter(key => key.startsWith('settings:fold:'))).toEqual([row])
    expect(await shownTab(ui)).toBe('settings')
    const callsBefore = fake.settingCalls().length

    await ui.press({ key: row })

    // The seventh tab bears the group's title and is the one shown; `Settings` is a button again, which leads back.
    expect(await shownTabs(ui)).toEqual(TABS_ABOVE_ABOUT)
    expect(await shownTab(ui)).toBe('aside')
    expect(await shownParts(ui)).toEqual([{ key: 'about', title: ABOUT_TITLE, count: null, lines: ABOUT_LINES }])
    expect(await drawnSettings(ui)).toEqual(ABOUT)
    // Nothing below the tabs can be pressed, and the group is drawn from the list as it was read.
    expect(await viewButtons(ui)).toEqual([])
    expect(fake.settingCalls().slice(callsBefore)).toEqual([])
    // The session's state names the group by the name and the title the core gave it, and holds no value of it.
    const kept = writes.join('\n')
    expect(kept).toContain('"aside":{"name":"about","title":"About this setup"}')
    for (const held of [NOTES, 'tower-1', 'markdown', '3 named', '2 customers', 'Store folder', 'Task list']) {
      expect(kept).not.toContain(held)
    }
    await clock.advance(10_000)
    await ui.unmount()
  })
}

test('the folded group under its tab is one part titled by how many settings it holds: each in the order of its place, as its title with its value and, indented whole and dim below, how it changes; the view holds no button', async ($, on) => {
  // Covers: B212
  const { fake } = world()
  const { clock } = await start($, on, fake)
  const ui = await openView($, clock)

  await ui.press({ key: ABOUT_ROW })

  expect(await texts(ui)).toEqual([ABOUT_TITLE, ...ABOUT_LINES])
  expect(await partLines(ui, 'about')).toEqual(ABOUT_LINES)
  expect(await drawnSettings(ui)).toEqual(ABOUT)
  expect(await insetsAt(ui, 'part:about')).toEqual(ABOUT_LINES.filter((_, line) => line % 2 === 1).map(how => ({ paddingLeft: 2, lines: [how] })))
  // The choices are not drawn below or above it: the group stands alone, with nothing to press.
  expect(await viewButtons(ui)).toEqual([])
  expect(await ui.find({ key: 'folded:about' })).toBeUndefined()
  for (const part of ['shows', 'reads', 'curation'] as const) {
    expect(await partLines(ui, part)).toBeNull()
  }
  // A setting there is to be read: its line plain, what changes it stepped back.
  expect(await piecesAt(ui, `setting:${PATH}`)).toEqual([
    { text: `Store folder: ${NOTES}`, color: undefined, dimColor: undefined, weight: undefined, strikethrough: undefined },
    { text: 'change: m2b config set store.path <folder>', color: undefined, dimColor: true, weight: undefined, strikethrough: undefined },
  ])
  // Each setting is a column of its own, directly below the title: no row of values, and no line between them.
  const [heading, ...blocks] = await boxesAt(ui, 'part:about')
  expect(heading?.flexDirection).toBe('row')
  expect(blocks.map(block => [block.key, block.flexDirection, block.rowGap])).toEqual(ABOUT.map(at => [`setting:${at}`, 'column', undefined]))
  for (const at of ABOUT) {
    expect(await shownValues(ui, at)).toBeNull()
  }
  // Shown from the list as read: m2b is not asked again.
  expect(fake.settingCalls()).toEqual([LIST])
  await ui.unmount()
})

test('whatever the core sorts into a folded group is a line with its value and no button: a switch there names its command', async ($, on) => {
  // Covers: B212
  const { fake, settings } = world()
  Object.assign(settings.entries[PAUSED] ?? {}, { group: 'about', place: 7 })
  const { clock } = await start($, on, fake)
  const ui = await openView($, clock)
  expect(await partLines(ui, 'about')).toEqual([`[7 settings] ${FOLDED}`])
  expect(await valueKeys(ui)).toEqual(VALUE_BUTTONS.filter(key => key !== `set:${PAUSED}:0`))

  await ui.press({ key: ABOUT_ROW })

  expect(await shownParts(ui)).toEqual([
    {
      key: 'about',
      title: `7 settings ${FOLDED}`,
      count: null,
      lines: [...ABOUT_LINES, 'Curation paused: off', 'change: m2b settings set curation.paused true|false'],
    },
  ])
  expect(await shownValues(ui, PAUSED)).toBeNull()
  expect(await viewButtons(ui)).toEqual([])
  await ui.unmount()
})

test('the tab Settings above a folded group leads back to the choices by a new opening, which reads the list again; every new opening starts with the choices', async ($, on) => {
  // Covers: B212, B204
  const { fake } = world()
  const { clock } = await start($, on, fake)
  const ui = await openView($, clock)
  const choices = await shownParts(ui)
  const backAtTheChoices = async (reads: number): Promise<void> => {
    expect(await shownTab(ui)).toBe('settings')
    expect(await shownParts(ui)).toEqual(choices)
    expect(await viewButtons(ui)).toEqual([...VALUE_BUTTONS, ABOUT_ROW])
    expect(fake.settingCalls()).toEqual(Array.from({ length: reads }, () => LIST))
  }

  // By the tab Settings, a button above the group and the tab shown again after its press.
  await ui.press({ key: ABOUT_ROW })
  expect(await shownTab(ui)).toBe('aside')
  expect(fake.settingCalls()).toEqual([LIST])
  await ui.press({ key: BACK_TO_THE_CHOICES })
  await clock.advance(1)
  await backAtTheChoices(2)

  // The tab Overview above the group leads to the start view, as it does from the choices; opened again, the settings are the choices.
  await ui.press({ key: ABOUT_ROW })
  await pressTab(ui, 'overview')
  expect(await shownTab(ui)).toBe('overview')
  expect(await texts(ui)).toContain('Waits for you')
  expect(await texts(ui)).not.toContain(ABOUT_TITLE)
  await pressTab(ui, 'settings')
  await clock.advance(1)
  await backAtTheChoices(3)

  // The command typed above the group opens the settings anew.
  await ui.press({ key: ABOUT_ROW })
  await typed($, 'm2b-settings')
  await clock.advance(1)
  await backAtTheChoices(4)

  // Another view between two openings changes nothing of it.
  await ui.press({ key: ABOUT_ROW })
  await typed($, 'm2b-review')
  expect(await shownTab(ui)).toBe('review')
  await typed($, 'm2b-settings')
  await clock.advance(1)
  await backAtTheChoices(5)
  await ui.unmount()
})

for (const [what, without] of [
  ['without the group', 'the group'],
  ['with the group empty', 'its settings'],
] as const) {
  test(`a list read again ${what} turns the view back from the group to the choices, under the tab Settings`, async ($, on) => {
    // Covers: B212, B204
    const { fake, settings } = world()
    fake.delayMs = args => (args[0] === 'settings' && args[1] === 'set' ? 3_000 : 0)
    const { clock } = await start($, on, fake)
    const ui = await openView($, clock)
    // The list is read again when a write ends: the view is turned to the group while one is under way.
    await ui.press({ key: `set:${PAUSED}:0` })
    await clock.advance(UNDO_MS)
    await ui.press({ key: ABOUT_ROW_WRITING })
    expect(await shownParts(ui)).toEqual([{ key: 'about', title: ABOUT_TITLE, count: null, lines: ABOUT_LINES }])
    // The core that answers next has none of those settings, as after an update of m2b in another session.
    settings.entries = settings.entries.filter(entry => entry.group !== 'about')
    if (without === 'the group') {
      settings.groups = (settings.groups ?? []).filter(group => group.name !== 'about')
    }

    await clock.advance(3_000)
    await clock.advance(1)

    expect(fake.settingCalls()).toEqual([LIST, ['settings', 'set', '--', 'curation.paused', 'true'], LIST])
    // The tabs name what is drawn below them: the seventh is gone, and `Settings` is the one shown.
    expect(await shownTab(ui)).toBe('settings')
    expect(await headings(ui)).toEqual([
      ['shows', 'What m2b shows'],
      ['reads', 'What m2b reads'],
      ['curation', 'Curation'],
    ])
    // The list is shorter now, and a setting is keyed by where it stands in it.
    const at = (key: string): number => settings.entries.findIndex(entry => entry.key === key)
    expect(await drawnSettings(ui)).toEqual(
      ['band.due_tasks', 'sessions.propose', 'distillate.skip_under', 'curation.model', 'curating_machine', 'curation.paused', 'language'].map(at),
    )
    expect(await valuesLine(ui, at('curation.paused'))).toBe('● on [off]')
    expect((await viewButtons(ui)).filter(key => key.startsWith('settings:fold:'))).toEqual([])
    await ui.unmount()
  })
}

test('each folded group has a row of its own and opens under a tab that bears its own title, alone', async ($, on) => {
  // Covers: B212
  const { fake, settings } = world()
  settings.groups?.push({ name: 'worklog', title: 'Worklog', folded: true })
  Object.assign(settings.entries[CUSTOMERS] ?? {}, { group: 'worklog', place: 1 })
  const { clock } = await start($, on, fake)
  const ui = await openView($, clock)
  const customers = ['Customers: 2 customers', 'set up with /m2b:worklog-setup']
  const worklogRow = async (): Promise<string[] | undefined> => (await shownParts(ui)).find(part => part.key === 'worklog')?.lines
  expect(await partLines(ui, 'about')).toEqual([`[5 settings] ${FOLDED}`])
  expect(await worklogRow()).toEqual([`[1 setting] ${FOLDED}`])
  expect(await viewButtons(ui)).toEqual([...VALUE_BUTTONS, ABOUT_ROW, 'settings:fold:worklog'])

  await ui.press({ key: 'settings:fold:worklog' })

  expect((await shownTabs(ui)).at(-1)).toEqual({ label: 'Worklog', key: null })
  expect(await shownParts(ui)).toEqual([{ key: 'worklog', title: `1 setting ${FOLDED}`, count: null, lines: customers }])
  expect(await viewButtons(ui)).toEqual([])

  // Back at the choices both are rows again; the other group opens under its own tab, without the first.
  await ui.press({ key: BACK_TO_THE_CHOICES })
  await clock.advance(1)
  expect(await viewButtons(ui)).toEqual([...VALUE_BUTTONS, ABOUT_ROW, 'settings:fold:worklog'])
  await ui.press({ key: ABOUT_ROW })

  expect((await shownTabs(ui)).at(-1)).toEqual({ label: 'About this setup', key: null })
  expect(await shownParts(ui)).toEqual([{ key: 'about', title: `5 settings ${FOLDED}`, count: null, lines: ABOUT_LINES.slice(0, -2) }])
  expect(await viewButtons(ui)).toEqual([])
  await ui.unmount()
})

test('the tab of a folded group bears its title cut to 20 characters, a longer one whole nowhere in the row of tabs, and a title of the core is cleaned for the tab and for the state', async ($, on) => {
  // Covers: B204, B212
  const { fake, settings } = world()
  const writes = stateWrites(on)
  const { clock } = await start($, on, fake)
  const escape = String.fromCharCode(0x1b)
  const retitled = async (title: string): Promise<Awaited<ReturnType<typeof openView>>> => {
    settings.groups = (settings.groups ?? []).map(group => (group.name === 'about' ? { ...group, title } : group))
    const ui = await openView($, clock)
    await ui.press({ key: ABOUT_ROW })
    return ui
  }

  // Twenty characters are shown whole.
  const exact = await retitled('About this setup now')
  expect((await shownTabs(exact)).at(-1)).toEqual({ label: 'About this setup now', key: null })
  await exact.unmount()

  // One more is cut, like the name of a topic.
  const long = 'About this setup and this machine'
  const cut = await retitled(long)
  const label = (await shownTabs(cut)).at(-1)?.label ?? ''
  expect(label).toBe('About this setup an…')
  expect(Array.from(label)).toHaveLength(20)
  expect((await shownTabs(cut)).filter(tab => tab.label.includes(long))).toEqual([])
  expect(await shownTab(cut)).toBe('aside')
  // The six tabs that stay are as above every group.
  expect((await shownTabs(cut)).slice(0, 6)).toEqual(TABS_ABOVE_ABOUT.slice(0, 6))
  await cut.unmount()

  // What a terminal would run, and a line break, are gone before the title reaches the tab or the session's state.
  const cleaned = await retitled(`Ab${escape}[31mout\nthis setup`)
  expect((await shownTabs(cleaned)).at(-1)).toEqual({ label: 'About this setup', key: null })
  expect((await everyText(cleaned)).filter(text => text.includes(escape) || text.includes('\n'))).toEqual([])
  const kept = writes.join('\n')
  expect(kept).toContain('"aside":{"name":"about","title":"About this setup"}')
  expect(kept).toContain(`"aside":{"name":"about","title":"${long}"}`)
  expect(kept.includes('\\u001b') || kept.includes(escape) || kept.includes('[31m')).toBe(false)
  await cleaned.unmount()
})

test('on a machine that does not curate, each part that holds a setting of the curation run says so once, dim, and the titles of those settings step back; their values are buttons all the same', async ($, on) => {
  // Covers: B197, B211
  const { fake, settings } = world()
  settings.curates = false
  settings.entries.push(fakeSetting('curation.max_turns', 'Turns of a model step', 'about', 7, { value: 40, shows: '40', curation: true }))
  const { clock } = await start($, on, fake)

  const ui = await openView($, clock)

  // Above the settings of the part, and in no part that holds none of the curation run.
  expect((await partLines(ui, 'curation'))?.[0]).toBe(DOES_NOT_CURATE)
  expect((await lookOf(ui, DOES_NOT_CURATE))?.dimColor).toBe(true)
  expect((await texts(ui)).filter(text => text === DOES_NOT_CURATE)).toHaveLength(1)
  for (const part of ['shows', 'reads', 'about'] as const) {
    expect(await partLines(ui, part)).not.toContain(DOES_NOT_CURATE)
  }
  const [, apart] = await boxesAt(ui, 'part:curation')
  expect(apart?.holds.map(box => box.key)).toEqual([MODEL, CURATING, PAUSED, LANGUAGE].map(at => `setting:${at}`))
  // The two settings of the curation run step back; the two beside them in the part do not.
  for (const [at, title] of [
    [MODEL, 'Model of curation'],
    [PAUSED, 'Curation paused'],
  ] as const) {
    expect((await piecesAt(ui, `setting:${at}`))[0]).toEqual({ text: title, color: undefined, dimColor: true, weight: undefined, strikethrough: undefined })
  }
  for (const [at, title] of [
    [CURATING, 'Curating machine'],
    [LANGUAGE, 'Language'],
    [DUE, 'Tasks in the band'],
  ] as const) {
    expect((await piecesAt(ui, `setting:${at}`))[0]).toMatchObject({ text: title, dimColor: undefined, weight: 'bold' })
  }
  // They do nothing here, and are set all the same: another machine of the store may curate with them later.
  expect(await rows(ui, [MODEL, PAUSED])).toEqual(['● haiku [sonnet]', '[on] ● off'])
  await ui.press({ key: `set:${PAUSED}:0` })
  await clock.advance(UNDO_MS)
  await clock.advance(1)
  expect(fake.settingCalls().slice(1)).toEqual([['settings', 'set', '--', 'curation.paused', 'true'], LIST])

  // The folded group under its tab says it too, above its settings, and its setting of the run steps back.
  await ui.press({ key: ABOUT_ROW })
  expect(await shownParts(ui)).toEqual([
    {
      key: 'about',
      title: `7 settings ${FOLDED}`,
      count: null,
      lines: [DOES_NOT_CURATE, ...ABOUT_LINES, 'Turns of a model step: 40', 'change: m2b config set curation.max_turns <value>'],
    },
  ])
  expect((await lookOf(ui, DOES_NOT_CURATE))?.dimColor).toBe(true)
  expect((await lookOf(ui, 'Turns of a model step: 40'))?.dimColor).toBe(true)
  expect((await lookOf(ui, `Store folder: ${NOTES}`))?.dimColor).toBeUndefined()
  await ui.unmount()

  // A folded group that holds no setting of the run says nothing of it.
  settings.entries.pop()
  const without = await openView($, clock)
  await without.press({ key: ABOUT_ROW })
  expect(await texts(without)).toEqual([ABOUT_TITLE, ...ABOUT_LINES])
  await without.unmount()
})

for (const [curates, what] of [
  [true, 'on the machine that curates'],
  [null, 'where m2b cannot say whether this machine curates'],
] as const) {
  test(`${what} nothing says that it does not, and no setting of the curation run steps back`, async ($, on) => {
    // Covers: B197, B211
    const { fake, settings } = world()
    settings.curates = curates
    settings.entries.push(fakeSetting('curation.max_turns', 'Turns of a model step', 'about', 7, { value: 40, shows: '40', curation: true }))
    const { clock } = await start($, on, fake)

    const ui = await openView($, clock)

    expect(await texts(ui)).not.toContain(DOES_NOT_CURATE)
    for (const at of [MODEL, PAUSED]) {
      expect((await piecesAt(ui, `setting:${at}`))[0]).toMatchObject({ dimColor: undefined, weight: 'bold' })
    }
    await ui.press({ key: ABOUT_ROW })
    expect(await texts(ui)).not.toContain(DOES_NOT_CURATE)
    expect((await partLines(ui, 'about'))?.slice(-2)).toEqual(['Turns of a model step: 40', 'change: m2b config set curation.max_turns <value>'])
    expect((await lookOf(ui, 'Turns of a model step: 40'))?.dimColor).toBeUndefined()
    await ui.unmount()
  })
}

test('a file that could not be read is said once at the top of the view, with why; its settings say not read in their groups and offer nothing to press', async ($, on) => {
  // Covers: B197
  const { fake, settings } = world()
  const unread = 'm2b could not read profile.json: no profile.json in the store yet'
  settings.notRead = { 'profile.json': 'no profile.json in the store yet' }
  settings.curates = null
  for (const at of [LANGUAGE, CUSTOMERS]) {
    Object.assign(settings.entries[at] ?? {}, { read: false, value: null, shows: null })
  }
  const { clock } = await start($, on, fake)

  const ui = await openView($, clock)

  const shown = await texts(ui)
  expect(shown.slice(0, 2)).toEqual([unread, 'What m2b shows'])
  expect(shown.filter(text => text.startsWith('m2b could not read'))).toEqual([unread])
  expect((await lookOf(ui, unread))?.color).toBe('error')
  // Whether this machine curates is not known without the store: nothing says that it does not.
  expect(shown).not.toContain(DOES_NOT_CURATE)
  // The setting keeps its place in its group, its title and what it does; where its values would stand it says that it was not read.
  expect(await settingLines(ui, LANGUAGE)).toEqual(['Language', 'What language does.', 'not read'])
  expect((await lookOf(ui, 'not read'))?.dimColor).toBe(true)
  expect(await shownValues(ui, LANGUAGE)).toBeNull()
  expect(await buttonsAt(ui, `setting:${LANGUAGE}`)).toEqual([])
  expect(await valueKeys(ui)).toEqual(VALUE_BUTTONS.filter(key => key !== `set:${LANGUAGE}:0`))
  // The reason is said at the top alone: no part repeats it.
  expect(shown.filter(text => text.includes('no profile.json in the store yet'))).toEqual([unread])
  // Under the tab of the folded group the reason stands above the group's part as it does above the choices.
  await ui.press({ key: ABOUT_ROW })
  expect((await texts(ui)).slice(0, 2)).toEqual([unread, ABOUT_TITLE])
  expect((await partLines(ui, 'about'))?.slice(-2)).toEqual(['Customers: not read', 'set up with /m2b:worklog-setup'])
  expect(await viewButtons(ui)).toEqual([])
  await ui.unmount()
})

test('two files that could not be read for one reason are said in one line, a file with a reason of its own in another; a setting that is no switch says not read and still how it changes', async ($, on) => {
  // Covers: B197
  const { fake, settings } = world()
  const outOfReach = 'the store folder /home/alex/Notes cannot be reached'
  settings.notRead = { 'store.json': outOfReach, 'profile.json': outOfReach }
  for (const entry of settings.entries.filter(one => one.file !== 'config.json')) {
    Object.assign(entry, { read: false, value: null, shows: null })
  }
  const { clock } = await start($, on, fake)

  const ui = await openView($, clock)

  const together = `m2b could not read store.json and profile.json: ${outOfReach}`
  expect((await texts(ui)).slice(0, 2)).toEqual([together, 'What m2b shows'])
  expect((await texts(ui)).filter(text => text.includes(outOfReach))).toEqual([together])
  expect(await settingLines(ui, CURATING)).toEqual(['Curating machine', 'What curating_machine does.', 'not read', 'change: m2b curate take-over'])
  expect(await insetsAt(ui, `setting:${CURATING}`)).toEqual([{ paddingLeft: 2, lines: ['change: m2b curate take-over'] }])
  expect(await settingLines(ui, LANGUAGE)).toEqual(['Language', 'What language does.', 'not read'])
  // The settings of the file that was read are to press as ever.
  expect(await valueKeys(ui)).toEqual(VALUE_BUTTONS.filter(key => key !== `set:${LANGUAGE}:0`))
  await ui.unmount()

  // Another reason for one of them: a line each, in the order the core named the files.
  settings.notRead = { 'store.json': outOfReach, 'profile.json': 'profile.json is not valid JSON' }
  const apart = await openView($, clock)
  expect((await texts(apart)).slice(0, 3)).toEqual([
    `m2b could not read store.json: ${outOfReach}`,
    'm2b could not read profile.json: profile.json is not valid JSON',
    'What m2b shows',
  ])
  for (const line of (await texts(apart)).slice(0, 2)) {
    expect((await lookOf(apart, line))?.color).toBe('error')
  }
  await apart.unmount()
})

test('a later read that failed is said above the files that were not read, and both above the parts, which stay as they were read', async ($, on) => {
  // Covers: B197
  const { fake, settings } = world()
  settings.notRead = { 'profile.json': 'no profile.json in the store yet' }
  for (const at of [LANGUAGE, CUSTOMERS]) {
    Object.assign(settings.entries[at] ?? {}, { read: false, value: null, shows: null })
  }
  const { clock } = await start($, on, fake)
  const ui = await openView($, clock)
  const partsBefore = await shownParts(ui)

  await ui.press({ key: `set:${DUE}:2` })
  settings.listFails = 'the store cannot be reached'
  await clock.advance(UNDO_MS)
  await clock.advance(1)

  expect((await texts(ui)).slice(0, 3)).toEqual([
    'm2b could not read its settings again: the store cannot be reached',
    'm2b could not read profile.json: no profile.json in the store yet',
    'What m2b shows',
  ])
  expect(await shownParts(ui)).toEqual(partsBefore)
  await ui.unmount()
})

test('a text of the core is drawn as one plain line: a title, what a setting does, a value and its label, a reason and the title of a group', async ($, on) => {
  // Covers: B197
  const { fake, settings } = world()
  const escape = String.fromCharCode(0x1b)
  const forged = (text: string): string => `${text.slice(0, 2)}${escape}[2J${text.slice(2)}`
  Object.assign(settings.entries[PATH] ?? {}, { shows: `/home/alex/No${escape}[2Jtes\nforged: on${' '.repeat(60)}Language: fr` })
  Object.assign(settings.entries[MODEL] ?? {}, { title: forged('Model of curation'), does: `The model${escape}[31m of a run.\nSecond line.`, choices: ['haiku', forged('sonnet')] })
  Object.assign(settings.entries[SKIP] ?? {}, { shows: `2${escape}[1m folders`, change: `m2b distillate${escape}[0m off|on\n[<folder>]` })
  settings.notRead = { [forged('profile.json')]: `no profile.json${escape}[2J\nin the store yet` }
  settings.groups = (settings.groups ?? []).map(group => ({ ...group, title: forged(group.title) }))
  const { clock } = await start($, on, fake)

  const ui = await openView($, clock)

  const unread = 'm2b could not read profile.json: no profile.json in the store yet'
  expect((await texts(ui))[0]).toBe(unread)
  expect((await headings(ui)).map(([, title]) => title)).toEqual(['What m2b shows', 'What m2b reads', 'Curation', 'About this setup'])
  expect(await settingLines(ui, MODEL)).toEqual(['Model of curation', 'The model of a run. Second line.', '● haiku [sonnet]'])
  expect(await settingLines(ui, SKIP)).toEqual(['Folders m2b is left out of', 'What distillate.skip_under does.', '● 2 folders', 'change: m2b distillate off|on [<folder>]'])
  // No text of the view holds a character that steers a terminal.
  expect((await everyText(ui)).filter(text => text.includes(escape) || text.includes('\n'))).toEqual([])

  // The same under the tab of the folded group, whose title is cleaned for the tab too.
  await ui.press({ key: ABOUT_ROW })
  expect((await shownTabs(ui)).at(-1)).toEqual({ label: 'About this setup', key: null })
  expect((await texts(ui)).slice(0, 2)).toEqual([unread, ABOUT_TITLE])
  // A run of spaces would wrap into what reads as a row of its own.
  expect((await partLines(ui, 'about'))?.[0]).toBe('Store folder: /home/alex/Notes forged: on Language: fr')
  expect((await everyText(ui)).filter(text => text.includes(escape) || text.includes('\n'))).toEqual([])
  await ui.unmount()
})

test('in a pane 24 columns wide every line of a setting wraps, its values break between them, and the row of a folded group fits; under its tab every line of the group wraps', async ($, on) => {
  // Covers: B211, B212
  const { fake } = world()
  const { clock } = await start($, on, fake)

  const ui = await openView($, clock, 24)

  // The same lines as in a wide pane: no narrow form of its own.
  expect(await rows(ui, SWITCHES)).toEqual(ROWS_TO_PRESS)
  expect(await drawnSettings(ui)).toEqual(CHOICES)
  for (const at of CHOICES) {
    const [title, does] = (await settingLines(ui, at)) ?? []
    for (const line of [title ?? '', does ?? '']) {
      expect((await lookOf(ui, line))?.wrap).toBe('wrap')
    }
    expect((await ui.find({ key: `values:${at}` }))?.props).toMatchObject({ flexDirection: 'row', flexWrap: 'wrap' })
  }
  expect((await lookOf(ui, 'change: m2b curate take-over'))?.wrap).toBe('wrap')
  // A terminal draws a button as `[ label ]`: four cells more than its label, and two more for the bar of the part.
  const fits = async (): Promise<void> => {
    for (const button of await inView(ui, 'Button')) {
      expect(String(button.props['label']).length + 4 + 2).toBeLessThanOrEqual(24)
    }
  }
  await fits()
  expect((await ui.find({ key: 'folded:about' }))?.props).toMatchObject({ flexDirection: 'row', flexWrap: 'wrap' })
  expect((await lookOf(ui, FOLDED))?.wrap).toBe('wrap')
  await ui.press({ key: `set:${PAUSED}:0` })
  expect((await lookOf(ui, 'turning on'))?.wrap).toBe('wrap')
  expect(await viewButtons(ui)).toEqual([SETTINGS_UNDO, ABOUT_ROW_WAITING])
  await fits()

  await ui.press({ key: ABOUT_ROW_WAITING })

  // The title of the group's part, which is a sentence, wraps like every line below it.
  for (const line of [ABOUT_TITLE, ...ABOUT_LINES]) {
    expect((await lookOf(ui, line))?.wrap).toBe('wrap')
  }
  // The row of six tabs breaks between its tabs.
  expect(await shownTabs(ui)).toEqual(TABS_ABOVE_ABOUT)
  expect((await ui.find({ key: 'tabs' }))?.props).toMatchObject({ flexDirection: 'row', flexWrap: 'wrap' })
  await ui.unmount()
})

// What the kit shows of the focus: a move the mod asks for fails in the kit and reaches no hook of
// a test, and every test that presses a button of the settings runs with a move that failed, as
// where the pane does not hold the keyboard. So the rule is held on the keys the mod names and on
// the view as drawn: the key asked for is a button then, and was none before the press. Claude
// Code looks a key up in what is drawn when the focus is asked for; one drawn before the press
// would be found at its old place.

test('the tab Overview above the choices, where the focus rests unless the row of a folded group is nearer, is a tab there in every state of the choices, drawn above no other view, and the key of no value', async ($, on) => {
  // Covers: B200
  const { fake, settings } = world()
  fake.delayMs = args => (args[0] === 'settings' && args[1] === 'set' ? 3_000 : 0)
  const { clock } = await start($, on, fake)
  expect(OFF_THE_VALUES).toBe('tab:overview:in:settings')
  const isATab = async (ui: Mounted): Promise<void> => {
    expect((await shownTabs(ui)).filter(tab => tab.key === OFF_THE_VALUES)).toEqual([{ label: 'Overview', key: OFF_THE_VALUES }])
    expect(await viewButtons(ui)).not.toContain(OFF_THE_VALUES)
  }

  // The view the pane starts in, and every other, draws that tab under another key.
  const ui = await $.ui.mount({ ...pane(PANE), surface: 'terminal' })
  for (const command of ['m2b-pane', 'm2b-proposals', 'm2b-review']) {
    await typed($, command)
    expect(await everyButton(ui)).not.toContain(OFF_THE_VALUES)
  }
  // While m2b reads, as read, while a press waits, while it is written, and after.
  await typed($, 'm2b-settings')
  expect(await texts(ui)).toEqual([READING])
  await isATab(ui)
  await clock.advance(1)
  await isATab(ui)
  await ui.press({ key: `set:${PAUSED}:0` })
  await isATab(ui)
  await clock.advance(UNDO_MS)
  expect(await texts(ui)).toContain('turning on…')
  await isATab(ui)
  await clock.advance(3_001)
  await isATab(ui)
  // Above a folded group the tabs are keyed for that view: after the row's press the focus is asked
  // for the tab that leads back to the choices, which is a button there and was none above the choices.
  expect(await everyButton(ui)).not.toContain(BACK_TO_THE_CHOICES)
  await ui.press({ key: ABOUT_ROW })
  expect(await everyButton(ui)).not.toContain(OFF_THE_VALUES)
  expect(await everyButton(ui)).toContain(BACK_TO_THE_CHOICES)
  await ui.press({ key: BACK_TO_THE_CHOICES })
  expect(await shownTab(ui)).toBe('settings')
  // A list that could not be read has the tab too: the focus has a place where the view holds no button.
  settings.listFails = 'the store cannot be reached'
  await typed($, 'm2b-settings')
  await clock.advance(1)
  expect(await viewButtons(ui)).toEqual([])
  await isATab(ui)
  await ui.unmount()

  // No value, no undo and no row of a group, in any phase, is keyed like a tab.
  const keys = settingsCatalog().flatMap((entry, at) => entry.choices.map((_, place) => valueKey(at, place)))
  expect(keys).toHaveLength(11)
  for (const key of [...keys, SETTINGS_UNDO, foldKey('about'), foldKey('about', 'waiting'), foldKey('about', 'writing'), foldKey('overview')]) {
    expect(key.startsWith('tab:')).toBe(false)
  }
})

for (const columns of [80, 24]) {
  test(`the key the focus is asked for is a button of the view at that moment and was none in the drawing before: undo after a press, then, for a setting near the folded group, its row under the key of each phase, in a pane of ${columns} columns`, async ($, on) => {
    // Covers: B200
    const { fake, settings } = world()
    fake.delayMs = args => (args[0] === 'settings' && args[1] === 'set' ? 3_000 : 0)
    const { clock } = await start($, on, fake)
    const ui = await openView($, clock, columns)
    /** Holds that `key` is a button now and was none in the drawing before, and answers the buttons drawn now. */
    const comes = async (key: string, before: readonly string[]): Promise<string[]> => {
      const now = await everyButton(ui)
      expect(now).toContain(key)
      expect(before).not.toContain(key)
      return now
    }
    const asRead = await everyButton(ui)

    // A press on a value: undo, the one button that takes it back.
    await ui.press({ key: `set:${PAUSED}:0` })
    const waiting = await comes(SETTINGS_UNDO, asRead)
    expect(await viewButtons(ui)).toEqual([SETTINGS_UNDO, ABOUT_ROW_WAITING])

    // After undo: the row of the folded group, two settings below the one pressed, under its plain key.
    await ui.press({ key: SETTINGS_UNDO })
    const takenBack = await comes(ABOUT_ROW, waiting)
    expect(takenBack).not.toContain(SETTINGS_UNDO)

    // When the five seconds are over the press is written: the row under the key of that phase.
    await ui.press({ key: `set:${PAUSED}:0` })
    const waitingAgain = await comes(SETTINGS_UNDO, takenBack)
    await clock.advance(UNDO_MS)
    const writing = await comes(ABOUT_ROW_WRITING, waitingAgain)
    expect(await viewButtons(ui)).toEqual([ABOUT_ROW_WRITING])

    // Once the write ended the values are buttons again, and the row has its plain key.
    await clock.advance(3_000)
    await clock.advance(1)
    const written = await comes(ABOUT_ROW, writing)
    expect(written).not.toContain(ABOUT_ROW_WRITING)
    // Whatever became of the focus, the press was written.
    expect(fake.settingCalls().slice(1)).toEqual([['settings', 'set', '--', 'curation.paused', 'true'], LIST])
    expect(settings.changedWith).toHaveLength(1)

    // For a setting near the top the tab Overview is nearer than the row: it stands above the
    // settings in every phase, under one key, since no value moves it.
    await ui.press({ key: `set:${DUE}:0` })
    await comes(SETTINGS_UNDO, written)
    expect(await everyButton(ui)).toContain(OFF_THE_VALUES)
    await ui.press({ key: SETTINGS_UNDO })
    expect(await everyButton(ui)).toContain(OFF_THE_VALUES)

    // After the row's press: the tab that leads back to the choices, drawn above the group alone.
    const beforeTheGroup = await everyButton(ui)
    await ui.press({ key: ABOUT_ROW })
    await comes(BACK_TO_THE_CHOICES, beforeTheGroup)
    expect(await viewButtons(ui)).toEqual([])
    // None of the keys asked for sets a value: Enter pressed once more writes nothing.
    for (const key of [SETTINGS_UNDO, ABOUT_ROW, ABOUT_ROW_WAITING, ABOUT_ROW_WRITING, OFF_THE_VALUES, BACK_TO_THE_CHOICES]) {
      expect(/^set:/.test(key)).toBe(false)
    }
    await ui.unmount()
  })
}

test('no button of a value, undo or the row of a folded group, in any phase, has a hotkey, an action or the focus by itself', async ($, on) => {
  // Covers: B200
  const { fake } = world()
  fake.delayMs = args => (args[0] === 'settings' && args[1] === 'set' ? 3_000 : 0)
  const { clock } = await start($, on, fake)
  const ui = await openView($, clock)
  const reachedByItself = async (): Promise<string[]> =>
    (await inView(ui, 'Button')).filter(button => ['hotkey', 'action', 'autoFocus'].some(reach => button.props[reach] !== undefined)).map(button => String(button.key))

  expect(await viewButtons(ui)).toEqual([...VALUE_BUTTONS, ABOUT_ROW])
  expect(await reachedByItself()).toEqual([])
  await ui.press({ key: `set:${DUE}:0` })
  expect(await viewButtons(ui)).toEqual([SETTINGS_UNDO, ABOUT_ROW_WAITING])
  expect(await reachedByItself()).toEqual([])
  await clock.advance(UNDO_MS)
  expect(await viewButtons(ui)).toEqual([ABOUT_ROW_WRITING])
  expect(await reachedByItself()).toEqual([])
  await clock.advance(3_001)
  await ui.unmount()
})

/** The words the list of every setting and the card of one setting drew, which the view has no more. */
const GONE: readonly RegExp[] = [
  /^(open|previous|next|turn on|turn off)$/,
  /^set to /,
  /^now: /,
  /^default: /,
  /^\d+ of \d+$/,
  /^(This machine|The store, for every machine|The owner, for every machine)$/,
  /^(this machine|the store, for every machine|the owner, for every machine) · /,
  /^A change of .+ is under way\.$/,
  /^turning \S+ (on|off)…?$/,
  /^setting \S+ to /,
  /^This machine does not curate\.$/,
  /^not read: /,
]

/** Every text and every label of a button the pane draws that reads like one of the words that are gone. */
async function goneWords(ui: Mounted): Promise<string[]> {
  const labels = (await ui.findAll({ type: 'Button' })).map(button => String(button.props['label']))
  return [...(await everyText(ui)), ...labels].filter(text => GONE.some(gone => gone.test(text)))
}

/** Where `list` is drawn: it was the label of the button that led from a card back, and is a value of one switch now. */
async function drawnAsList(ui: Mounted): Promise<string[]> {
  const buttons = (await ui.findAll({ type: 'Button' })).filter(button => button.props['label'] === 'list').map(button => String(button.key))
  const said = (await everyText(ui)).filter(text => text === 'list' || text === '● list')
  return [...buttons, ...said]
}

test('none of the words of the list of every setting and of the card of one setting is drawn, in any state of the view', async ($, on) => {
  // Covers: B197, B211
  const { fake, settings } = world()
  fake.delayMs = args => (args[0] === 'settings' && args[1] === 'set' ? 3_000 : 0)
  settings.curates = false
  settings.notRead = { 'profile.json': 'no profile.json in the store yet' }
  Object.assign(settings.entries[CUSTOMERS] ?? {}, { read: false, value: null, shows: null })
  const { clock } = await start($, on, fake)
  const states: string[] = []
  const held = async (state: string, ui: Mounted, list: string[]): Promise<void> => {
    states.push(state)
    expect(await goneWords(ui)).toEqual([])
    expect(await drawnAsList(ui)).toEqual(list)
  }

  await typed($, 'm2b-settings')
  const ui = await $.ui.mount({ ...pane(PANE), surface: 'terminal' })
  await held('while m2b reads', ui, [])
  await clock.advance(1)
  await held('as read', ui, [`set:${DUE}:2`])
  await ui.press({ key: `set:${PAUSED}:0` })
  await held('while a press waits', ui, ['list'])
  expect(await valuesLine(ui, PAUSED)).toBe('[undo] turning on')
  await clock.advance(UNDO_MS)
  await held('while it is written', ui, ['list'])
  expect(await texts(ui)).toContain('turning on…')
  await clock.advance(3_001)
  await held('after the write', ui, [`set:${DUE}:2`])
  await ui.press({ key: `set:${MODEL}:1` })
  settings.refuses = 'config.json does not follow its format'
  await clock.advance(UNDO_MS + 3_001)
  expect(await texts(ui)).toContain('not changed: config.json does not follow its format')
  await held('with a refusal', ui, [`set:${DUE}:2`])
  await ui.press({ key: `set:${DUE}:2` })
  settings.refuses = null
  settings.listFails = 'the store cannot be reached'
  await clock.advance(UNDO_MS + 3_001)
  expect((await texts(ui))[0]).toBe('m2b could not read its settings again: the store cannot be reached')
  await held('with a later read that failed', ui, [`set:${DUE}:2`])
  await ui.press({ key: ABOUT_ROW })
  expect((await texts(ui)).slice(0, 3)).toEqual([
    'm2b could not read its settings again: the store cannot be reached',
    'm2b could not read profile.json: no profile.json in the store yet',
    ABOUT_TITLE,
  ])
  await held('under the tab of the folded group', ui, [])
  await typed($, 'm2b-settings')
  await clock.advance(1)
  await held('with a read that failed', ui, [])
  await ui.unmount()

  settings.listFails = null
  const inTheApp = await openView($, clock, 24, 'mobile')
  await held('in the mobile app, in a narrow pane', inTheApp, ['● list'])
  await inTheApp.unmount()
  expect(states).toHaveLength(10)
})
