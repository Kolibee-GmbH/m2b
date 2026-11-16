import { expect, test } from 'claude-code/testing'
import type { CommandRunResult } from 'claude-code'
import type { Engine } from 'claude-code/testing'

import { closeAnswer } from '../../hooks/pane-seat'
import { shownOf } from '../../hooks/pane-tabs'
import {
  OFF_THE_VALUES,
  SETTINGS_UNDO,
  askSettings,
  beginChange,
  beginSettings,
  dropWaitingChange,
  endChange,
  fillSettings,
  forgetSettingsUnless,
  heldSettings,
  holdsSettings,
  offered,
  openSettings,
  parseSettings,
  pressTurnsHandingInOn,
  restKey,
  settingsPane,
  startWriting,
  undoChange,
  foldKey,
  foldedTitle,
  valueKey,
  waits,
} from '../../hooks/settings'
import type { Setting, SettingsActions } from '../../hooks/settings'
import type { PaneView } from '../../types'
import {
  FakeM2b,
  IN_STORE,
  NOTES,
  NO_SESSION_TURNS_IT_ON,
  OF_OWNER,
  SETTING_AT,
  SETTING_GROUPS,
  buttonsAt,
  fakeSetting,
  inView,
  lookOf,
  onOff,
  orderAt,
  pane,
  partLines,
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
import type { FakeSetting } from './harness'

// The rules of the settings that do not depend on how the view is drawn: when m2b reads the list
// and what the module keeps of it, a press that waits, is taken back or written, and the one
// switch a session's shell does not turn on. What the view draws is held in settings-view.test.tsx.

const PANE = 'm2b'
const AS_A_DIALOG = { id: PANE, title: 'm2b', closeOnEscape: true, focus: true }
const PLACED = 'every setting of m2b is in the m2b pane'
const READING = 'm2b is reading its settings…'
const OLDER_CORE = 'the installed m2b is older than this band; update m2b, then run /reload-plugins'
const OTHER_SHAPE = 'm2b answered something other than its settings'
const FOLDED = 'that only inform or are changed by a command'
const IN_YOUR_OWN_TERMINAL = 'Turned on in a terminal of your own: m2b settings set sessions.propose true'
const LIST = ['settings', '--json']
const BY_YOUR_PRESS = 'Your press here turns it on, as a terminal of your own does.'
const EVERY_MACHINE = 'Every machine that shares the store needs an m2b that knows handing in.'
const AT_ITS_START =
  'A session gets the tool when it starts or its plugins are reloaded: until then, one that ran before this was turned on does not have it.'
/** The surfaces on which the value that turns handing in on is a button; `mobile` is how the mobile app names itself. */
const OFFERED_THE_TURN_ON = ['terminal', 'desktop', 'vscode'] as const
type Surface = (typeof OFFERED_THE_TURN_ON)[number] | 'mobile'
/** What a call of `m2b settings set` is handed: the core takes an empty `CLAUDECODE` as a terminal of the owner's own. */
const OUTSIDE_A_SESSION = { CLAUDECODE: '' }
const INSIDE_A_SESSION = { CLAUDECODE: '1' }

const { PATH, DUE, MODEL, PAUSED, PROPOSE, CURATING, LANGUAGE } = SETTING_AT
/** The button that turns handing in on: the first of its switch's two values. */
const TURN_ON = `set:${PROPOSE}:0`
/**
 * The button of the row the settings that only inform are kept behind, which turns the view to
 * them. Its key names the phase the view is drawn in: while a press waits, and while it is written.
 */
const ABOUT_ROW = 'settings:fold:about'
const ABOUT_ROW_WAITING = 'settings:fold:about:waiting'
const ABOUT_ROW_WRITING = 'settings:fold:about:writing'
/** The tab that leads from that group back to the choices, by a new opening of the settings. */
const BACK_TO_THE_CHOICES = 'tab:settings:in:aside'
/** The view turned to that group, as the session's state names it. */
const ABOUT_SHOWN = { name: 'about', title: 'About this setup' }
/** The buttons of the view as it is read, on a surface that offers to turn handing in on, in the order drawn. */
const BUTTONS = [`set:${DUE}:0`, `set:${DUE}:2`, TURN_ON, `set:${MODEL}:1`, `set:${PAUSED}:0`, `set:${LANGUAGE}:0`, ABOUT_ROW]

const catalog = settingsCatalog
const world = settingsWorld

function typed($: Engine, command: string, args = ''): Promise<CommandRunResult> {
  return $.command.run({ command, args, origin: { kind: 'composer' }, presentation: { isFullscreen: false, columns: 100 } })
}

type Clock = Awaited<ReturnType<typeof start>>['clock']

/** The settings, opened with the command and read. */
async function openView($: Engine, clock: Clock, columns = 80, surface: Surface = 'terminal') {
  await typed($, 'm2b-settings')
  await clock.advance(1)
  return $.ui.mount({ ...pane(PANE, columns), surface })
}

/** A drawing of the pane, on whatever surface it was mounted. */
type Mounted = Parameters<typeof inView>[0]

/** The lines the view draws that begin with `not changed`, wherever they stand. */
async function refusals(ui: Mounted): Promise<string[]> {
  return (await texts(ui)).filter(text => text.startsWith('not changed'))
}

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

test('/m2b-settings opens the view: while m2b reads it says so, then a part for each group of the core holds its settings', async ($, on) => {
  // Covers: B197
  const { fake } = world()
  const { clock, commands, opened } = await start($, on, fake)
  const opensBefore = opened.length

  const answer = await typed($, 'm2b-settings')
  const reading = await $.ui.mount({ ...pane(PANE), surface: 'terminal' })
  // What the view is stands on its tab: the line said while m2b reads has no heading above it.
  expect(await shownTab(reading)).toBe('settings')
  expect(await texts(reading)).toEqual([READING])
  expect((await lookOf(reading, READING))?.dimColor).toBe(true)
  expect(await viewButtons(reading)).toEqual([])
  await clock.advance(1)

  expect(answer.text).toBe(PLACED)
  expect(commands.find(command => command.name === 'm2b-settings')?.immediate).toBe(true)
  expect(opened.slice(opensBefore)).toEqual([AS_A_DIALOG])
  expect(fake.settingCalls()).toEqual([LIST])
  expect(await shownParts(reading)).toEqual([
    { key: 'shows', title: 'What m2b shows', count: null, lines: ['Tasks in the band', 'What band.due_tasks does.', '[off] ● count [list]'] },
    {
      key: 'reads',
      title: 'What m2b reads',
      count: null,
      lines: [
        'Sessions hand in proposals',
        'What sessions.propose does.',
        EVERY_MACHINE,
        BY_YOUR_PRESS,
        '[on] ● off',
        'Folders m2b is left out of',
        'What distillate.skip_under does.',
        '● 2 folders',
        'change: m2b distillate off|on [<folder>]',
      ],
    },
    {
      key: 'curation',
      title: 'Curation',
      count: null,
      lines: [
        'Model of curation',
        'What curation.model does.',
        '● haiku [sonnet]',
        'Curating machine',
        'What curating_machine does.',
        '● tower-1',
        'change: m2b curate take-over',
        'Curation paused',
        'What curation.paused does.',
        '[on] ● off',
        'Language',
        'What language does.',
        '[de] ● en',
      ],
    },
    { key: 'about', title: 'About this setup', count: null, lines: [`[6 settings] ${FOLDED}`] },
  ])
  expect(await viewButtons(reading)).toEqual(BUTTONS)
  await reading.unmount()
})

test('the tab Settings opens the view too, as a dialog, and the tab Overview leads back', async ($, on) => {
  // Covers: B197, B204
  const { fake } = world()
  const { clock, opened } = await start($, on, fake)
  await typed($, 'm2b-pane')
  const ui = await $.ui.mount({ ...pane(PANE), surface: 'terminal' })
  const opensBefore = opened.length

  await pressTab(ui, 'settings')
  await clock.advance(1)

  expect(opened.slice(opensBefore)).toEqual([AS_A_DIALOG])
  expect(fake.settingCalls()).toEqual([LIST])
  expect(await settingLines(ui, PAUSED)).toEqual(['Curation paused', 'What curation.paused does.', '[on] ● off'])
  await pressTab(ui, 'overview')
  expect(await texts(ui)).toContain('Waits for you')
  await ui.unmount()
})

test('every value to press is in the view at once: nothing is opened first, and the view is drawn from one read of the list', async ($, on) => {
  // Covers: B197
  const { fake } = world()
  const { clock } = await start($, on, fake)

  const ui = await openView($, clock)

  expect(await valueKeys(ui)).toEqual(BUTTONS.slice(0, -1))
  expect(valueKey(PAUSED, 0)).toBe(`set:${PAUSED}:0`)
  expect(foldKey('about')).toBe(ABOUT_ROW)
  await ui.press({ key: `set:${PAUSED}:0` })
  await ui.press({ key: SETTINGS_UNDO })
  await ui.press({ key: ABOUT_ROW })
  expect(await partLines(ui, 'about')).toContain(`Store folder: ${NOTES}`)
  // Read once: a press, its undo and the turn to a group read nothing.
  expect(fake.settingCalls()).toEqual([LIST])
  await ui.unmount()
})

test('a press on a value writes nothing for five seconds and offers undo, then runs m2b settings set and reads again', async ($, on) => {
  // Covers: B198
  const { fake } = world()
  const { clock } = await start($, on, fake)
  const ui = await openView($, clock)
  const callsBefore = fake.calls.length

  await ui.press({ key: `set:${PAUSED}:0` })

  expect(await valuesLine(ui, PAUSED)).toBe('[undo] turning on')
  expect(await viewButtons(ui)).toEqual(['settings:undo', ABOUT_ROW_WAITING])
  await clock.advance(4_999)
  expect(fake.calls.slice(callsBefore).filter(call => call[0] === 'settings')).toEqual([])

  await clock.advance(1)
  await clock.advance(1)

  // The change and the list read again come first: the band is not waited for, and is read behind them.
  expect(fake.calls.slice(callsBefore, callsBefore + 2)).toEqual([['settings', 'set', '--', 'curation.paused', 'true'], LIST])
  expect(fake.calls.slice(callsBefore + 2)).toEqual([['band', '--json']])
  expect(await valuesLine(ui, PAUSED)).toBe('● on [off]')
  expect(await buttonsAt(ui, `values:${PAUSED}`)).toMatchObject([{ key: `set:${PAUSED}:1`, label: 'off' }])
  await ui.unmount()
})

test('undo within the five seconds takes the press back: nothing is written', async ($, on) => {
  // Covers: B198
  const { fake } = world()
  const { clock } = await start($, on, fake)
  const ui = await openView($, clock)

  await ui.press({ key: `set:${PAUSED}:0` })
  await clock.advance(2_000)
  await ui.press({ key: 'settings:undo' })
  // At once: the setting offers its value again, and so does every other.
  expect(await valuesLine(ui, PAUSED)).toBe('[on] ● off')
  expect(await viewButtons(ui)).toEqual(BUTTONS)
  await clock.advance(10_000)

  expect(fake.settingCalls()).toEqual([LIST])
  expect(await valuesLine(ui, PAUSED)).toBe('[on] ● off')
  expect(await viewButtons(ui)).toEqual(BUTTONS)
  await ui.unmount()
})

test('a switch of a few names offers each other name, and hands the name on as it is', async ($, on) => {
  // Covers: B198
  const { fake } = world()
  const { clock } = await start($, on, fake)
  const ui = await openView($, clock)

  expect(await valuesLine(ui, MODEL)).toBe('● haiku [sonnet]')
  await ui.press({ key: `set:${MODEL}:1` })
  expect(await valuesLine(ui, MODEL)).toBe('[undo] changing to sonnet')
  await clock.advance(5_000)
  await clock.advance(1)

  expect(fake.settingCalls().slice(1)).toEqual([['settings', 'set', '--', 'curation.model', 'sonnet'], LIST])
  expect(await valuesLine(ui, MODEL)).toBe('[haiku] ● sonnet')
  expect(await buttonsAt(ui, `values:${MODEL}`)).toMatchObject([{ key: `set:${MODEL}:0`, label: 'haiku' }])
  await ui.unmount()
})

test('what the command refuses stands with the setting in its own words, and the value is as it was', async ($, on) => {
  // Covers: B198, B207
  const { fake, settings } = world()
  const { clock } = await start($, on, fake)
  const ui = await openView($, clock)
  const bandReads = fake.calls.filter(call => call[0] === 'band').length
  settings.refuses = 'profile.json in the store does not follow its format; m2b profile get says where'

  await ui.press({ key: `set:${LANGUAGE}:0` })
  await clock.advance(5_000)
  await clock.advance(1)

  expect(fake.settingCalls().slice(1)).toEqual([['settings', 'set', '--', 'language', 'de'], LIST])
  // Below what the setting does and above its values, which are as they were.
  expect(await settingLines(ui, LANGUAGE)).toEqual(['Language', 'What language does.', `not changed: ${settings.refuses}`, '[de] ● en'])
  expect((await lookOf(ui, `not changed: ${settings.refuses}`))?.color).toBe('error')
  // Nothing was written, so the band holds nothing new and is not read.
  expect(fake.calls.filter(call => call[0] === 'band').length).toBe(bandReads)
  // It stands with the setting it was about, and with no other.
  expect(await refusals(ui)).toEqual([`not changed: ${settings.refuses}`])
  // The next press is another try; what the last one met is gone.
  settings.refuses = null
  await ui.press({ key: `set:${LANGUAGE}:0` })
  expect(await refusals(ui)).toEqual([])
  await ui.unmount()
})

test('a refusal goes with the next press on any other setting too, before that press is written', async ($, on) => {
  // Covers: B207
  const { fake, settings } = world()
  const { clock } = await start($, on, fake)
  const ui = await openView($, clock)
  settings.refuses = 'the store cannot be reached'
  await ui.press({ key: `set:${LANGUAGE}:0` })
  await clock.advance(5_000)
  await clock.advance(1)
  expect(await refusals(ui)).toEqual(['not changed: the store cannot be reached'])
  const setsBefore = settings.changedWith.length

  await ui.press({ key: `set:${PAUSED}:0` })

  expect(await refusals(ui)).toEqual([])
  expect(settings.changedWith).toHaveLength(setsBefore)
  await ui.unmount()
})

test('in a terminal, the desktop app and VS Code the value that turns handing in on is a button: below the line that says how, with no hotkey and no key of its own', async ($, on) => {
  // Covers: B199
  const { fake } = world()
  const { clock } = await start($, on, fake)

  for (const surface of OFFERED_THE_TURN_ON) {
    const ui = await openView($, clock, 80, surface)

    // The value is in the view as it is read: nothing is opened to reach it.
    expect(await valueKeys(ui)).toContain(TURN_ON)
    expect(await shownValues(ui, PROPOSE)).toEqual([
      { label: 'on', is: 'to press', key: TURN_ON },
      { label: 'off', is: 'in force', key: null },
    ])
    const turnOn = await ui.find({ key: TURN_ON })
    for (const reach of ['hotkey', 'action', 'autoFocus', 'variant', 'role']) {
      expect(turnOn?.props[reach]).toBeUndefined()
    }
    expect(await texts(ui)).not.toContain(IN_YOUR_OWN_TERMINAL)
    // What it needs, then how it is turned on, then the button: the last thing to press in its block.
    expect(await orderAt(ui, `setting:${PROPOSE}`)).toEqual([
      'Sessions hand in proposals',
      'What sessions.propose does.',
      EVERY_MACHINE,
      BY_YOUR_PRESS,
      `[${TURN_ON}]`,
      '● off',
    ])
    expect(await texts(ui)).not.toContain(AT_ITS_START)
    // What it needs may be skipped; how it is turned on is to be read before the press.
    expect((await lookOf(ui, EVERY_MACHINE))?.dimColor).toBe(true)
    expect((await lookOf(ui, BY_YOUR_PRESS))?.dimColor).toBeUndefined()
    await ui.unmount()
  }
})

test('the press on the value that turns handing in on waits five seconds with undo, is then the one call handed to m2b as made outside a session, and the setting says what it reaches', async ($, on) => {
  // Covers: B199
  const { fake, settings } = world()
  const { clock } = await start($, on, fake)

  for (const [turn, surface] of OFFERED_THE_TURN_ON.entries()) {
    Object.assign(settings.entries[PROPOSE] ?? {}, onOff('sessions.propose', false))
    const ui = await openView($, clock, 80, surface)

    await ui.press({ key: TURN_ON })

    expect(await valuesLine(ui, PROPOSE)).toBe('[undo] turning on')
    expect(await viewButtons(ui)).toEqual(['settings:undo', ABOUT_ROW_WAITING])
    await clock.advance(4_999)
    expect(settings.changedWith).toHaveLength(turn)
    await clock.advance(1)
    await clock.advance(1)

    expect(settings.changedWith).toHaveLength(turn + 1)
    expect(await refusals(ui)).toEqual([])
    expect(await valuesLine(ui, PROPOSE)).toBe('● on [off]')
    expect(await texts(ui)).toContain(AT_ITS_START)
    expect(await texts(ui)).toContain(EVERY_MACHINE)
    expect(await texts(ui)).not.toContain(BY_YOUR_PRESS)
    expect(await buttonsAt(ui, `setting:${PROPOSE}`)).toMatchObject([{ key: `set:${PROPOSE}:1`, label: 'off' }])
    await ui.unmount()
  }

  const written = fake.settingCalls().filter(call => call[1] === 'set')
  expect(written).toEqual(OFFERED_THE_TURN_ON.map(() => ['settings', 'set', '--', 'sessions.propose', 'true']))
  expect(settings.changedWith).toEqual(OFFERED_THE_TURN_ON.map(() => OUTSIDE_A_SESSION))
})

test('what the core refuses to the press that turns handing in on stands above the line that says how it is turned on, and the value is off as before', async ($, on) => {
  // Covers: B199, B207
  const { fake, settings } = world()
  const { clock } = await start($, on, fake)
  const ui = await openView($, clock)
  // The core's own word, as where it takes the call for a session's after all.
  settings.refuses = NO_SESSION_TURNS_IT_ON

  await ui.press({ key: TURN_ON })
  await clock.advance(5_000)
  await clock.advance(1)

  expect(fake.settingCalls().slice(1)).toEqual([['settings', 'set', '--', 'sessions.propose', 'true'], LIST])
  expect(settings.changedWith).toEqual([OUTSIDE_A_SESSION])
  expect(await settingLines(ui, PROPOSE)).toEqual([
    'Sessions hand in proposals',
    'What sessions.propose does.',
    EVERY_MACHINE,
    `not changed: ${NO_SESSION_TURNS_IT_ON}`,
    BY_YOUR_PRESS,
    '[on] ● off',
  ])
  expect(await texts(ui)).not.toContain(AT_ITS_START)

  // Turned on, a refusal to turn it off stands below what the setting says while it is on.
  settings.refuses = null
  await ui.press({ key: TURN_ON })
  await clock.advance(5_000)
  await clock.advance(1)
  settings.refuses = 'config.json does not follow its format'
  await ui.press({ key: `set:${PROPOSE}:1` })
  await clock.advance(5_000)
  await clock.advance(1)

  expect(await settingLines(ui, PROPOSE)).toEqual([
    'Sessions hand in proposals',
    'What sessions.propose does.',
    EVERY_MACHINE,
    AT_ITS_START,
    'not changed: config.json does not follow its format',
    '● on [off]',
  ])
  expect(settings.changedWith).toEqual([OUTSIDE_A_SESSION, OUTSIDE_A_SESSION, INSIDE_A_SESSION])
  await ui.unmount()
})

test('undo, and leaving the settings, take the press on the value that turns handing in on back: nothing is handed to m2b', async ($, on) => {
  // Covers: B199
  const { fake, settings } = world()
  const { clock } = await start($, on, fake)
  const ui = await openView($, clock)

  await ui.press({ key: TURN_ON })
  await ui.press({ key: 'settings:undo' })
  await clock.advance(10_000)
  expect(await valuesLine(ui, PROPOSE)).toBe('[on] ● off')

  await ui.press({ key: TURN_ON })
  await pressTab(ui, 'overview')
  await clock.advance(10_000)

  expect(settings.changedWith).toEqual([])
  expect(fake.settingCalls()).toEqual([LIST])
  await ui.unmount()
})

test('in the mobile app the value that turns handing in on is dim text and no button, and the setting names the command for a terminal', async ($, on) => {
  // Covers: B199
  const { fake, settings } = world()
  const { clock } = await start($, on, fake)
  const ui = await openView($, clock, 80, 'mobile')

  expect(await texts(ui)).toContain(IN_YOUR_OWN_TERMINAL)
  expect((await lookOf(ui, IN_YOUR_OWN_TERMINAL))?.dimColor).toBeUndefined()
  expect(await texts(ui)).not.toContain(BY_YOUR_PRESS)
  expect(await texts(ui)).toContain(EVERY_MACHINE)
  // The command stands where the other surfaces say that a press turns it on: above the values.
  expect(await settingLines(ui, PROPOSE)).toEqual(['Sessions hand in proposals', 'What sessions.propose does.', EVERY_MACHINE, IN_YOUR_OWN_TERMINAL, 'on ● off'])
  expect(await shownValues(ui, PROPOSE)).toEqual([
    { label: 'on', is: 'stepped back', key: null },
    { label: 'off', is: 'in force', key: null },
  ])
  expect(await buttonsAt(ui, `setting:${PROPOSE}`)).toEqual([])
  // Every other switch is offered there as anywhere.
  expect(await valueKeys(ui)).toEqual(BUTTONS.slice(0, -1).filter(key => key !== TURN_ON))
  await ui.unmount()

  // Turned on already, it is turned off from anywhere, as a change made inside a session: that way no session gains anything.
  Object.assign(settings.entries[PROPOSE] ?? {}, { value: true, shows: 'on' })
  const whereOn = await openView($, clock, 80, 'mobile')
  expect(await shownValues(whereOn, PROPOSE)).toEqual([
    { label: 'on', is: 'in force', key: null },
    { label: 'off', is: 'to press', key: `set:${PROPOSE}:1` },
  ])
  expect(await texts(whereOn)).not.toContain(IN_YOUR_OWN_TERMINAL)
  expect(await texts(whereOn)).toContain(AT_ITS_START)
  await whereOn.press({ key: `set:${PROPOSE}:1` })
  await clock.advance(5_000)
  await clock.advance(1)

  expect(fake.settingCalls().filter(call => call[1] === 'set')).toEqual([['settings', 'set', '--', 'sessions.propose', 'false']])
  expect(settings.changedWith).toEqual([INSIDE_A_SESSION])
  expect(await valuesLine(whereOn, PROPOSE)).toBe('on ● off')
  await whereOn.unmount()
})

test('the surface is the one the press came from, not the one the value was drawn on', async ($, on) => {
  // Covers: B199
  const { fake, settings } = world()
  // A value drawn for the terminal, pressed from a client that names itself the mobile app: what the press says counts.
  on('ui.press', { plugin: 'm2b', element: TURN_ON }, (_, e, next) => next({ ...e, surface: 'mobile' }))
  const { clock } = await start($, on, fake)
  const ui = await openView($, clock)
  expect(await viewButtons(ui)).toContain(TURN_ON)

  await ui.press({ key: TURN_ON })

  expect(await viewButtons(ui)).not.toContain('settings:undo')
  await clock.advance(10_000)
  expect(settings.changedWith).toEqual([])
  expect(await valuesLine(ui, PROPOSE)).toBe('[on] ● off')
  await ui.unmount()
})

test('while another change is being written, the setting of handing in still says how it is turned on, and offers nothing', async ($, on) => {
  // Covers: B199
  const { fake } = world()
  fake.delayMs = args => (args[0] === 'settings' && args[1] === 'set' ? 3_000 : 0)
  const { clock } = await start($, on, fake)
  const ui = await openView($, clock)

  await ui.press({ key: `set:${PAUSED}:0` })
  await clock.advance(5_000)

  expect(await settingLines(ui, PROPOSE)).toEqual(['Sessions hand in proposals', 'What sessions.propose does.', EVERY_MACHINE, BY_YOUR_PRESS, 'on ● off'])
  expect((await settingLines(ui, PAUSED))?.at(-1)).toBe('turning on…')
  expect(await buttonsAt(ui, `setting:${PROPOSE}`)).toEqual([])
  expect(await viewButtons(ui)).toEqual([ABOUT_ROW_WRITING])
  await clock.advance(3_001)
  await clock.advance(1)
  expect(await viewButtons(ui)).toContain(TURN_ON)
  await ui.unmount()
})

test('a core that spells on and off as texts is read the same: on is on, and the value that turns it on is the one the command takes', async ($, on) => {
  // Covers: B199
  const { fake, settings } = world()
  const { clock } = await start($, on, fake)
  const asTexts = (value: string): Partial<FakeSetting> => ({ value, shows: value === 'true' ? 'on' : 'off', choices: ['true', 'false'] })

  Object.assign(settings.entries[PROPOSE] ?? {}, asTexts('true'))
  const whereOn = await openView($, clock)
  expect(await texts(whereOn)).toContain(AT_ITS_START)
  expect(await texts(whereOn)).not.toContain(BY_YOUR_PRESS)
  expect(await valuesLine(whereOn, PROPOSE)).toBe('● true [false]')
  await whereOn.unmount()

  Object.assign(settings.entries[PROPOSE] ?? {}, asTexts('false'))
  const whereOff = await openView($, clock)
  expect(await texts(whereOff)).toContain(BY_YOUR_PRESS)
  expect(await valuesLine(whereOff, PROPOSE)).toBe('[true] ● false')
  await whereOff.press({ key: TURN_ON })
  await clock.advance(5_000)
  await clock.advance(1)
  expect(settings.changedWith).toEqual([OUTSIDE_A_SESSION])
  await whereOff.unmount()

  Object.assign(settings.entries[PROPOSE] ?? {}, asTexts('false'))
  const inTheApp = await openView($, clock, 80, 'mobile')
  expect(await valuesLine(inTheApp, PROPOSE)).toBe('true ● false')
  expect(await buttonsAt(inTheApp, `setting:${PROPOSE}`)).toEqual([])
  expect(await texts(inTheApp)).toContain(IN_YOUR_OWN_TERMINAL)
  await inTheApp.unmount()
})

test('in a pane 24 columns wide the setting of handing in wraps its lines and keeps its button below them', async ($, on) => {
  // Covers: B199
  const { fake } = world()
  const { clock } = await start($, on, fake)
  const ui = await openView($, clock, 24)

  for (const line of [EVERY_MACHINE, BY_YOUR_PRESS]) {
    expect((await ui.findAll({ type: 'Text', text: line }))[0]?.props['wrap']).toBe('wrap')
  }
  const drawn = await orderAt(ui, `setting:${PROPOSE}`)
  expect(drawn.slice(-3)).toEqual([BY_YOUR_PRESS, `[${TURN_ON}]`, '● off'])
  // A terminal draws a button as `[ label ]`: four cells more than its label.
  const label = String((await ui.find({ key: TURN_ON }))?.props['label'])
  expect(label).toBe('on')
  expect(label.length + 4).toBeLessThanOrEqual(24)
  await ui.unmount()
})

test('a setting of that name that is no switch of this machine, or was not read, says nothing about turning it on', async ($, on) => {
  // Covers: B199
  const { fake, settings } = world()
  const { clock } = await start($, on, fake)
  const ABOUT_TURNING_ON = [BY_YOUR_PRESS, IN_YOUR_OWN_TERMINAL, EVERY_MACHINE, AT_ITS_START]

  for (const other of [IN_STORE, { kind: 'shown' }, { read: false }, { ...OF_OWNER, value: true, shows: 'on' }]) {
    settings.entries[PROPOSE] = fakeSetting('sessions.propose', 'Sessions hand in proposals', 'reads', 1, { ...onOff('sessions.propose', false), ...other })
    const ui = await openView($, clock)

    expect(await texts(ui)).toContain('Sessions hand in proposals')
    for (const line of ABOUT_TURNING_ON) {
      expect(await texts(ui)).not.toContain(line)
    }
    expect(await viewButtons(ui)).not.toContain(TURN_ON)
    await ui.unmount()
  }
})

test('no other press and no command is handed to m2b as made outside a session', async ($, on) => {
  // Covers: B199
  const { fake, settings } = world()
  // A core that spells the switch otherwise, and one that lists a setting of that name for the store.
  Object.assign(settings.entries[PROPOSE] ?? {}, { value: 'off', shows: 'off', choices: ['on', 'off'] })
  settings.entries.push(fakeSetting('sessions.propose', 'Handing in, of the store', 'reads', 3, { ...IN_STORE, ...onOff('sessions.propose', false) }))
  const [IN_WORDS, OF_THE_STORE] = [PROPOSE, settings.entries.length - 1]
  const { clock } = await start($, on, fake)

  // The command with words behind it writes nothing at all.
  await typed($, 'm2b-settings', 'sessions.propose true')
  await clock.advance(10_000)
  expect(settings.changedWith).toEqual([])

  const ui = await $.ui.mount({ ...pane(PANE), surface: 'terminal' })
  // Another switch, pressed in the terminal.
  await ui.press({ key: `set:${PAUSED}:0` })
  await clock.advance(5_000)
  await clock.advance(1)
  // A value that is not the one the command takes to turn handing in on: the core decides, as for a session.
  expect(await valuesLine(ui, IN_WORDS)).toBe('[on] ● off')
  await ui.press({ key: `set:${IN_WORDS}:0` })
  await clock.advance(5_000)
  await clock.advance(1)
  // A setting of that name in another file is not this machine's switch: nothing turns it on.
  expect(await valuesLine(ui, OF_THE_STORE)).toBe('on ● off')
  expect(await buttonsAt(ui, `setting:${OF_THE_STORE}`)).toEqual([])

  expect(fake.settingCalls().filter(call => call[1] === 'set')).toEqual([
    ['settings', 'set', '--', 'curation.paused', 'true'],
    ['settings', 'set', '--', 'sessions.propose', 'on'],
  ])
  expect(settings.changedWith).toEqual([INSIDE_A_SESSION, INSIDE_A_SESSION])
  await ui.unmount()
})

test('while one change is written, no value of any setting is a button, and its own setting says what is under way', async ($, on) => {
  // Covers: B198
  const { fake } = world()
  fake.delayMs = args => (args[0] === 'settings' && args[1] === 'set' ? 3_000 : 0)
  const { clock } = await start($, on, fake)
  const ui = await openView($, clock)

  await ui.press({ key: `set:${MODEL}:1` })
  await clock.advance(5_000)

  // Being written: undo is gone, and the setting says what is under way where its values stood.
  // The one button left sets nothing: it turns the view to the settings that only inform.
  expect(await viewButtons(ui)).toEqual([ABOUT_ROW_WRITING])
  expect(await settingLines(ui, MODEL)).toEqual(['Model of curation', 'What curation.model does.', 'changing to sonnet…'])
  expect(await valuesLine(ui, PAUSED)).toBe('on ● off')
  expect(await texts(ui)).toContain('changing to sonnet…')

  await clock.advance(3_000)
  await clock.advance(1)
  expect(await valuesLine(ui, MODEL)).toBe('[haiku] ● sonnet')
  expect(await texts(ui)).not.toContain('changing to sonnet…')
  expect(await valuesLine(ui, PAUSED)).toBe('[on] ● off')
  await ui.unmount()
})

test('a press on the row of a folded group while a press on a value waits takes that press back: nothing is written when its five seconds are over', async ($, on) => {
  // Covers: B198
  const { fake, settings } = world()
  const { clock } = await start($, on, fake)
  const ui = await openView($, clock)

  await ui.press({ key: `set:${PAUSED}:0` })
  await clock.advance(2_000)
  expect(await viewButtons(ui)).toEqual(['settings:undo', ABOUT_ROW_WAITING])
  await ui.press({ key: ABOUT_ROW_WAITING })

  // The view left the values: from the group nobody could take the press back, so it does not wait any more.
  expect(await shownTab(ui)).toBe('aside')
  expect(await partLines(ui, 'about')).toContain(`Store folder: ${NOTES}`)
  expect(await viewButtons(ui)).toEqual([])
  await clock.advance(10_000)

  expect(fake.settingCalls()).toEqual([LIST])
  expect(settings.changedWith).toEqual([])
  // Back at the choices, which are read anew, the switch is as it was and every value is to press.
  await ui.press({ key: BACK_TO_THE_CHOICES })
  await clock.advance(10_000)
  expect(fake.settingCalls()).toEqual([LIST, LIST])
  expect(settings.changedWith).toEqual([])
  expect(await valuesLine(ui, PAUSED)).toBe('[on] ● off')
  expect(await viewButtons(ui)).toEqual(BUTTONS)
  await ui.unmount()
})

test('a change being written goes on when the view is turned to a folded group: the group holds nothing to press, and the write ends as it would', async ($, on) => {
  // Covers: B198
  const { fake, settings } = world()
  fake.delayMs = args => (args[0] === 'settings' && args[1] === 'set' ? 3_000 : 0)
  const { clock } = await start($, on, fake)
  const ui = await openView($, clock)
  await ui.press({ key: `set:${MODEL}:1` })
  await clock.advance(5_000)

  await ui.press({ key: ABOUT_ROW_WRITING })

  expect(await shownTab(ui)).toBe('aside')
  expect(await viewButtons(ui)).toEqual([])
  await clock.advance(3_000)
  await clock.advance(1)

  // Written once, and the list read again for the opening the group belongs to: the group stays shown.
  expect(fake.settingCalls()).toEqual([LIST, ['settings', 'set', '--', 'curation.model', 'sonnet'], LIST])
  expect(settings.changedWith).toEqual([INSIDE_A_SESSION])
  expect(await shownTab(ui)).toBe('aside')
  expect(await partLines(ui, 'about')).toContain(`Store folder: ${NOTES}`)
  await ui.press({ key: BACK_TO_THE_CHOICES })
  await clock.advance(1)
  expect(await valuesLine(ui, MODEL)).toBe('[haiku] ● sonnet')
  await ui.unmount()
})

test('a change being written goes on when the settings are left, and a view opened meanwhile waits for it', async ($, on) => {
  // Covers: B198
  const { fake } = world()
  fake.delayMs = args => (args[0] === 'settings' && args[1] === 'set' ? 3_000 : 0)
  const { clock } = await start($, on, fake)
  const ui = await openView($, clock)
  await ui.press({ key: `set:${MODEL}:1` })
  await clock.advance(5_000)

  await pressTab(ui, 'overview')
  await pressTab(ui, 'settings')
  await clock.advance(1)

  // The list of the new opening was read while the write was under way: it says so, and offers no value.
  expect((await settingLines(ui, MODEL))?.at(-1)).toBe('changing to sonnet…')
  expect(await valuesLine(ui, PAUSED)).toBe('on ● off')
  expect(await viewButtons(ui)).toEqual([ABOUT_ROW_WRITING])

  await clock.advance(3_000)
  await clock.advance(1)

  // The write ended: the view that is open now reads again and offers its values.
  expect(fake.settingCalls().filter(call => call[1] === 'set')).toEqual([['settings', 'set', '--', 'curation.model', 'sonnet']])
  expect(await valuesLine(ui, PAUSED)).toBe('[on] ● off')
  expect(await valuesLine(ui, MODEL)).toBe('[haiku] ● sonnet')
  await ui.unmount()
})

test('what the command refused after the view was opened anew stands with the setting there', async ($, on) => {
  // Covers: B198, B207
  const { fake, settings } = world()
  fake.delayMs = args => (args[0] === 'settings' && args[1] === 'set' ? 3_000 : 0)
  settings.refuses = 'the store cannot be reached'
  const { clock } = await start($, on, fake)
  const ui = await openView($, clock)
  await ui.press({ key: `set:${LANGUAGE}:0` })
  await clock.advance(5_000)

  await typed($, 'm2b-settings')
  await clock.advance(3_001)

  expect(await settingLines(ui, LANGUAGE)).toEqual(['Language', 'What language does.', 'not changed: the store cannot be reached', '[de] ● en'])
  await ui.unmount()
})

test('a list that cannot be read again after a change stays as it was read, with the trouble above it', async ($, on) => {
  // Covers: B197
  const { fake, settings } = world()
  const { clock } = await start($, on, fake)
  const ui = await openView($, clock)
  await ui.press({ key: `set:${PAUSED}:0` })
  settings.listFails = 'the store cannot be reached'

  await clock.advance(5_000)
  await clock.advance(1)

  // The view keeps its parts, and says above them that what they show is from before.
  const trouble = 'm2b could not read its settings again: the store cannot be reached'
  expect((await texts(ui))[0]).toBe(trouble)
  expect((await lookOf(ui, trouble))?.color).toBe('error')
  expect(await valuesLine(ui, PAUSED)).toBe('[on] ● off')
  expect(await viewButtons(ui)).toEqual(BUTTONS)
  expect((await shownParts(ui)).map(part => part.key)).toEqual(['shows', 'reads', 'curation', 'about'])
  // The tabs above it lead on.
  expect((await shownTabs(ui)).map(tab => tab.label)).toEqual(['Overview', 'Proposals', 'Review', 'Tasks', 'Settings'])
  // Read again, the trouble is over and the view shows what is true.
  settings.listFails = null
  await typed($, 'm2b-settings')
  await clock.advance(1)
  expect(await texts(ui)).not.toContain(trouble)
  expect(await valuesLine(ui, PAUSED)).toBe('● on [off]')
  await ui.unmount()
})

test('a list read again with fewer settings is drawn as it is then: a setting it no longer has is gone, and so is the part of a group left without one', async ($, on) => {
  // Covers: B197
  const { fake, settings } = world()
  const { clock } = await start($, on, fake)
  const ui = await openView($, clock)
  await ui.press({ key: `set:${LANGUAGE}:0` })
  // The core that answers next lists fewer settings, as after an update of m2b in another session.
  settings.entries = settings.entries.slice(0, PROPOSE)

  await clock.advance(5_000)
  await clock.advance(1)

  expect(fake.settingCalls().slice(1)).toEqual([['settings', 'set', '--', 'language', 'de'], LIST])
  expect((await shownParts(ui)).map(part => part.key)).toEqual(['shows', 'curation', 'about'])
  expect(await partLines(ui, 'curation')).toEqual([
    'Model of curation',
    'What curation.model does.',
    '● haiku [sonnet]',
    'Curation paused',
    'What curation.paused does.',
    '[on] ● off',
  ])
  expect(await partLines(ui, 'about')).toEqual([`[2 settings] ${FOLDED}`])
  expect(await viewButtons(ui)).toEqual([`set:${DUE}:0`, `set:${DUE}:2`, `set:${MODEL}:1`, `set:${PAUSED}:0`, ABOUT_ROW])
  await ui.unmount()
})

test('a press the list no longer offers when its five seconds are over is dropped, and the view shows what is true', async ($, on) => {
  // Covers: B198
  const { fake, settings } = world()
  let isListSlow = false
  fake.delayMs = args => (isListSlow && args[0] === 'settings' && args[1] === '--json' ? 4_000 : 0)
  const { clock } = await start($, on, fake)
  const ui = await openView($, clock)
  await ui.press({ key: `set:${MODEL}:1` })
  // Another session pauses the curation meanwhile; the list read after the change is slow to answer.
  Object.assign(settings.entries[PAUSED] ?? {}, { value: true, shows: 'on' })
  isListSlow = true
  await clock.advance(5_000)

  // The change is over in the view at once, before the list has answered.
  expect((await texts(ui)).some(shown => shown.includes('changing to'))).toBe(false)
  // The view still shows the list from before, and takes the press.
  expect(await valuesLine(ui, PAUSED)).toBe('[on] ● off')
  await ui.press({ key: `set:${PAUSED}:0` })
  expect(await viewButtons(ui)).toContain('settings:undo')
  await clock.advance(5_001)
  await clock.advance(1)

  expect(await valuesLine(ui, PAUSED)).toBe('● on [off]')
  expect(await viewButtons(ui)).not.toContain('settings:undo')
  expect(fake.settingCalls().filter(call => call[1] === 'set')).toEqual([['settings', 'set', '--', 'curation.model', 'sonnet']])
  await ui.unmount()
})

test('the change is handed to m2b as one made inside a session, whatever the mod itself inherited', async ($, on) => {
  // Covers: B198
  const { fake, settings } = world()
  const { clock } = await start($, on, fake)
  const ui = await openView($, clock)

  await ui.press({ key: `set:${PAUSED}:0` })
  await clock.advance(5_000)

  expect(settings.changedWith).toEqual([INSIDE_A_SESSION])
  await ui.unmount()
})

test('leaving the settings within the five seconds takes the press back', async ($, on) => {
  // Covers: B198
  const { fake } = world()
  const { clock } = await start($, on, fake)
  const ui = await openView($, clock)

  await ui.press({ key: `set:${PAUSED}:0` })
  await pressTab(ui, 'overview')
  await clock.advance(10_000)

  expect(await texts(ui)).toContain('Waits for you')
  expect(fake.settingCalls()).toEqual([LIST])
  await ui.unmount()
})

for (const [to, label] of [
  ['overview', 'Overview'],
  ['proposals', 'Proposals'],
  ['review', 'Review'],
  ['tasks', 'Tasks'],
] as const) {
  test(`the tab ${label} pressed within the five seconds takes the press back: nothing is written`, async ($, on) => {
    // Covers: B198
    const { fake } = world()
    const { clock } = await start($, on, fake)
    const ui = await openView($, clock)

    await ui.press({ key: `set:${PAUSED}:0` })
    expect(await viewButtons(ui)).toContain(SETTINGS_UNDO)
    await pressTab(ui, to)
    await clock.advance(10_000)

    expect(await shownTab(ui)).toBe(to)
    expect(fake.settingCalls()).toEqual([LIST])
    // Opened again, the settings are read anew and the switch is as it was.
    await pressTab(ui, 'settings')
    await clock.advance(1)
    expect(await valuesLine(ui, PAUSED)).toBe('[on] ● off')
    expect(await viewButtons(ui)).toEqual(BUTTONS)
    expect(fake.settingCalls()).toEqual([LIST, LIST])
    await ui.unmount()
  })
}

test('a command that turns the pane to another view within the five seconds takes the press back too', async ($, on) => {
  // Covers: B198
  const { fake } = world()
  const { clock } = await start($, on, fake)
  const ui = await openView($, clock)

  await ui.press({ key: `set:${PAUSED}:0` })
  await typed($, 'm2b-review')
  await clock.advance(10_000)

  expect(fake.settingCalls()).toEqual([LIST])
  // Opened again, the settings are read anew and the switch is as it was.
  await typed($, 'm2b-settings')
  await clock.advance(1)
  expect(await valuesLine(ui, PAUSED)).toBe('[on] ● off')
  expect(await viewButtons(ui)).toEqual(BUTTONS)
  expect(fake.settingCalls()).toEqual([LIST, LIST])
  await ui.unmount()
})

test('the command typed again within the five seconds opens the view anew and takes the press back', async ($, on) => {
  // Covers: B198
  const { fake } = world()
  const { clock } = await start($, on, fake)
  const ui = await openView($, clock)

  await ui.press({ key: `set:${PAUSED}:0` })
  await typed($, 'm2b-settings')
  await clock.advance(10_000)

  expect(fake.settingCalls()).toEqual([LIST, LIST])
  expect(await valuesLine(ui, PAUSED)).toBe('[on] ● off')
  expect(await viewButtons(ui)).toEqual(BUTTONS)
  await ui.unmount()
})

test("no value reaches the session's state, which every plugin can read, or the answer of the command", async ($, on) => {
  // Covers: B197
  const { fake } = world()
  const writes = stateWrites(on)
  const { clock } = await start($, on, fake)

  const answer = await typed($, 'm2b-settings')
  await clock.advance(1)
  const ui = await $.ui.mount({ ...pane(PANE), surface: 'terminal' })
  await ui.press({ key: `set:${MODEL}:1` })
  await clock.advance(5_000)
  await clock.advance(1)
  await ui.press({ key: ABOUT_ROW })
  expect(await partLines(ui, 'about')).toContain(`Store folder: ${NOTES}`)
  await pressTab(ui, 'overview')

  const kept = writes.join('\n')
  expect(kept).toContain('"kind":"settings"')
  // Which group the view was turned to is no value: the state names it, by the name and the title the core gave the group.
  expect(kept).toContain(`"aside":${JSON.stringify(ABOUT_SHOWN)}`)
  expect(kept).toContain('"aside":null')
  for (const held of [NOTES, 'tower-1', '2 customers', '3 named', '2 folders', 'markdown', 'sonnet', 'haiku', 'Store folder', 'Customers', 'What m2b shows']) {
    expect(kept).not.toContain(held)
    expect(answer.text).not.toContain(held)
  }
  expect(answer.text).not.toContain('About this setup')
  await ui.unmount()
})

test('the command takes no value: whatever is typed after it, it only opens the view', async ($, on) => {
  // Covers: B198
  const { fake } = world()
  const { clock } = await start($, on, fake)

  const answer = await typed($, 'm2b-settings', 'curation.paused true')
  await clock.advance(10_000)

  expect(answer.text).toBe(PLACED)
  expect(fake.settingCalls()).toEqual([LIST])
})

test('where no pane can be shown, the command answers one line that names the command for a terminal, and reads nothing', async ($, on) => {
  // Covers: B197
  const { fake } = world()
  fake.paneWaits = 'no surface is attached'
  const { clock, openPanes } = await start($, on, fake)

  const answer = await typed($, 'm2b-settings')
  await clock.advance(1)

  expect(answer.text).toBe('the m2b pane cannot be shown here: no surface is attached; m2b settings lists them in a terminal')
  expect(fake.settingCalls()).toEqual([])
  expect(openPanes.has(PANE)).toBe(false)
})

test('before m2b is set up, the command says so and opens nothing', async ($, on) => {
  // Covers: B197
  const { fake } = world()
  fake.isSetUp = false
  const { opened } = await start($, on, fake)
  const opensBefore = opened.length

  const answer = await typed($, 'm2b-settings')

  expect(answer.text).toBe('not shown: m2b is not set up on this machine; /m2b:m2b sets it up')
  expect(opened.slice(opensBefore)).toEqual([])
})

/** An answer of `m2b settings --json` with every part as the core gives it, but for `parts`. */
function answerWith(parts: Record<string, unknown>): string {
  return JSON.stringify({ settings: catalog(), groups: SETTING_GROUPS, curates: true, not_read: {}, ...parts })
}

/** The catalog with the first setting's entry changed: without the keys `without` names, and with `fields`. */
function withFirst(fields: Record<string, unknown>, ...without: string[]): Record<string, unknown>[] {
  const [first, ...rest] = catalog()
  const changed: Record<string, unknown> = { ...first, ...fields }
  for (const key of without) {
    delete changed[key]
  }
  return [changed, ...rest]
}

test('a core from before the command, one that fails and one that answers something else are each said in the view', async ($, on) => {
  // Covers: B197
  const olderCore = new FakeM2b()
  const { clock } = await start($, on, olderCore)
  const ui = await openView($, clock)
  expect(await texts(ui)).toEqual([`m2b could not read its settings: ${OLDER_CORE}`])
  expect(await viewButtons(ui)).toEqual([])
  await ui.unmount()

  expect(parseSettings('no json')).toEqual({ state: 'failed', error: OTHER_SHAPE })
  for (const other of [
    '[]',
    answerWith({ settings: 'none' }),
    answerWith({ settings: [{ key: 'x' }] }),
    answerWith({ curates: 'yes' }),
    answerWith({ settings: [] }),
    answerWith({ settings: withFirst({ read: 'yes' }) }),
    answerWith({ not_read: { 'store.json': 7 } }),
    answerWith({ not_read: [] }),
  ]) {
    expect(parseSettings(other)).toEqual({ state: 'failed', error: OTHER_SHAPE })
  }
  expect(parseSettings(answerWith({ curates: null })).state).toBe('read')
})

test('a core from before it sorted the settings into groups is said as an older core, in the view too', async ($, on) => {
  // Covers: B197
  const { fake, settings } = world()
  settings.groups = null
  const { clock } = await start($, on, fake)

  const ui = await openView($, clock)

  expect(await texts(ui)).toEqual([`m2b could not read its settings: ${OLDER_CORE}`])
  expect((await lookOf(ui, `m2b could not read its settings: ${OLDER_CORE}`))?.color).toBe('error')
  expect(await viewButtons(ui)).toEqual([])
  await ui.unmount()

  // As that core answers: no list of groups, and no setting that names one.
  const ungrouped = catalog().map(({ group: _, place: __, ...entry }) => entry)
  const older = JSON.stringify({ settings: ungrouped, curates: true, not_read: {} })
  expect(parseSettings(older)).toEqual({ state: 'failed', error: OLDER_CORE })
  // An answer that is no list of settings at all is not said as an older core, with or without groups.
  expect(parseSettings(JSON.stringify({ settings: [], curates: true, not_read: {} }))).toEqual({ state: 'failed', error: OTHER_SHAPE })
  expect(parseSettings(JSON.stringify({ curates: true, not_read: {} }))).toEqual({ state: 'failed', error: OTHER_SHAPE })
})

test('groups that are no list, a group of another shape, and a setting without its group, without its place or in a group that is not listed are no settings', () => {
  // Covers: B197
  const [shows, ...others] = SETTING_GROUPS
  const otherShapes = [
    answerWith({ groups: null }),
    answerWith({ groups: 'shows, reads, curation, about' }),
    answerWith({ groups: { shows: 'What m2b shows' } }),
    answerWith({ groups: 4 }),
    // A group of another shape: no group at all, one without a name, a title or the word on whether it is folded.
    answerWith({ groups: [...SETTING_GROUPS, 'more'] }),
    answerWith({ groups: [...SETTING_GROUPS, null] }),
    answerWith({ groups: [{ title: 'What m2b shows', folded: false }, ...others] }),
    answerWith({ groups: [{ name: 'shows', folded: false }, ...others] }),
    answerWith({ groups: [{ name: 'shows', title: 'What m2b shows' }, ...others] }),
    answerWith({ groups: [{ ...shows, folded: 'no' }, ...others] }),
    answerWith({ groups: [{ ...shows, name: 1 }, ...others] }),
    // A setting without its group or its place, or with one of another kind.
    answerWith({ settings: withFirst({}, 'group') }),
    answerWith({ settings: withFirst({}, 'place') }),
    answerWith({ settings: withFirst({ group: 4 }) }),
    answerWith({ settings: withFirst({ place: '2' }) }),
    answerWith({ settings: withFirst({ place: null }) }),
    // A setting in a group the list of groups does not have.
    answerWith({ settings: withFirst({ group: 'elsewhere' }) }),
    answerWith({ groups: others }),
    answerWith({ groups: [] }),
  ]

  for (const other of otherShapes) {
    expect(parseSettings(other)).toEqual({ state: 'failed', error: OTHER_SHAPE })
  }
})

test('a list that is read names its groups in the order of the core, each with whether it is folded, and every setting with its group and its place', () => {
  // Covers: B197
  const look = parseSettings(answerWith({}))

  expect(look.state).toBe('read')
  if (look.state !== 'read') {
    return
  }
  expect(look.catalog.groups).toEqual([
    { name: 'shows', title: 'What m2b shows', isFolded: false },
    { name: 'reads', title: 'What m2b reads', isFolded: false },
    { name: 'curation', title: 'Curation', isFolded: false },
    { name: 'about', title: 'About this setup', isFolded: true },
  ])
  // The settings stay in the order of the list, which a press names its setting by.
  expect(look.catalog.settings.map(setting => [setting.key, setting.group, setting.place])).toEqual(
    catalog().map(entry => [entry.key, entry.group, entry.place]),
  )
  // A group that holds no setting is a list all the same.
  const more = [...SETTING_GROUPS, { name: 'more', title: 'More', folded: true }]
  expect(parseSettings(answerWith({ groups: more })).state).toBe('read')
})

test('a list that could not be read says why in the words of the command, and nothing else', async ($, on) => {
  // Covers: B197
  const { fake, settings } = world()
  settings.listFails = 'not set up: no machine config'
  const { clock } = await start($, on, fake)

  const ui = await openView($, clock)

  const said = 'm2b could not read its settings: not set up: no machine config'
  expect(await texts(ui)).toEqual([said])
  expect((await lookOf(ui, said))?.color).toBe('error')
  expect(await shownParts(ui)).toEqual([])
  expect(await viewButtons(ui)).toEqual([])
  await ui.unmount()
})

/** The list as the module holds it once m2b answered, for the tests of what the module keeps. */
function readLook(entries: FakeSetting[] = catalog()) {
  return parseSettings(JSON.stringify({ settings: entries, groups: SETTING_GROUPS, curates: true, not_read: {} }))
}

/** Fills the look of an opening as the answer to a read just started for it. */
function fill(press: string, look: ReturnType<typeof parseSettings>): boolean {
  return fillSettings(press, look, askSettings(press) ?? -1)
}

function settingsOf(entries: FakeSetting[] = catalog()): Setting[] {
  const look = readLook(entries)
  return look.state === 'read' ? look.catalog.settings : []
}

// A test cannot make the person's close: the kit's engine has no call that raises one. What the
// close hook asks is held here on the functions it asks: whether the view is the one the pane
// starts in, and, on the way back, what the module that keeps the settings drops.
test("the person's close on the settings leads to the start view in one step, from a folded group under its own tab too, and takes a press that waits back", () => {
  // Covers: B187
  const choices: PaneView = { kind: 'settings', press: 'open', aside: null, drawn: 3 }
  const group: PaneView = { ...choices, aside: ABOUT_SHOWN, drawn: 4 }

  // All the hook asks of the view is whether it is the one the pane starts in.
  const isOnStartView = (view: PaneView | null): boolean => view === null

  // The choices stand under the tab Settings, a folded group under a sixth tab of its own.
  expect(shownOf(choices)).toBe('settings')
  expect(shownOf(group)).toBe('aside')
  for (const view of [choices, group]) {
    // Off the start view the close is no close and leads back, wherever the pane sits: the group
    // stands no step below the choices, and the close does not lead from it to them.
    for (const isBesideChat of [true, false]) {
      expect(closeAnswer('person', isOnStartView(view), isBesideChat, false)).toBe('back')
    }
  }
  // On the start view, right after that close, the same key again does not close the pane.
  expect(closeAnswer('person', isOnStartView(null), true, true)).toBe('back')

  // The way back turns the pane to the start view, which is the one way its view changes: the
  // module then keeps nothing, and a press that waited is not written.
  beginSettings('open')
  fill('open', readLook())
  expect(beginChange('open', PAUSED, 0, 't-1', 'terminal')).toBe(true)
  // The group is a view of the same opening: what is kept for it stays.
  forgetSettingsUnless(group)
  expect(holdsSettings()).toBe(true)
  expect(waits('t-1')).toBe(true)
  forgetSettingsUnless(null)
  expect(holdsSettings()).toBe(false)
  expect(waits('t-1')).toBe(false)
  expect(startWriting('t-1')).toBeNull()
  expect(heldSettings('open').change).toBeNull()
})

test('a reload of the mod, which starts the session again, leaves the pane on its start view', async ($, on) => {
  // Covers: B197
  const { fake } = world()
  const { clock } = await start($, on, fake)
  const ui = await openView($, clock)
  await ui.press({ key: ABOUT_ROW })
  expect(await partLines(ui, 'about')).toContain(`Store folder: ${NOTES}`)

  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await clock.advance(1)

  const shown = await texts(ui)
  expect(shown).toContain('Waits for you')
  expect(shown).not.toContain(`Store folder: ${NOTES}`)
  expect(await shownTab(ui)).toBe('overview')
  await ui.unmount()
})

test('what the module keeps is for one opening of the view: another opening neither fills nor keeps it', () => {
  // Covers: B197
  beginSettings('first')

  expect(fill('second', readLook())).toBe(false)
  // Nor under the number of a read the first opening started.
  expect(fillSettings('second', readLook(), askSettings('first') ?? -1)).toBe(false)
  expect(heldSettings('first').look).toEqual({ state: 'reading' })
  expect(fill('first', readLook())).toBe(true)
  expect(heldSettings('second').look).toEqual({ state: 'reading' })
  expect(openSettings()).toBe('first')

  // The view turned to a folded group is the same opening: what is kept stays.
  forgetSettingsUnless({ kind: 'settings', press: 'first', aside: ABOUT_SHOWN, drawn: 1 })
  expect(holdsSettings()).toBe(true)
  forgetSettingsUnless({ kind: 'settings', press: 'second', aside: null, drawn: 0 })
  expect(holdsSettings()).toBe(false)
  expect(openSettings()).toBeNull()
})

test('a first read that fails is could not read; a later one keeps the list and says the trouble', () => {
  // Covers: B197
  beginSettings('open')
  fill('open', { state: 'failed', error: 'no store' })
  expect(heldSettings('open')).toMatchObject({ look: { state: 'failed', error: 'no store' }, trouble: null })

  fill('open', readLook())
  fill('open', { state: 'failed', error: 'no store' })
  expect(heldSettings('open')).toMatchObject({ look: { state: 'read' }, trouble: 'no store' })
  // Read again, the trouble is over.
  fill('open', readLook())
  expect(heldSettings('open').trouble).toBeNull()

  // Two reads under way: the answer to the one started first is dropped when it comes last.
  const [first, second] = [askSettings('open') ?? -1, askSettings('open') ?? -1]
  expect(fillSettings('open', { state: 'failed', error: 'the later read' }, second)).toBe(true)
  expect(fillSettings('open', { state: 'failed', error: 'the earlier read' }, first)).toBe(false)
  expect(heldSettings('open').trouble).toBe('the later read')
  expect(askSettings('other')).toBeNull()
  forgetSettingsUnless(null)
})

test('the view offers every value of a switch but the one set, and the one that turns handing in on only where the client names itself the terminal, the desktop app or VS Code', () => {
  // Covers: B198, B199
  const settings = settingsOf()
  /** The places offered for each setting of the list, with what a surface is offered for handing in. */
  const places = (handingIn: number[]): number[][] => [[], [], [0, 2], [1], [0], handingIn, [], [], [], [], [], [0], []]

  for (const surface of OFFERED_THE_TURN_ON) {
    expect(settings.map(setting => offered(setting, surface))).toEqual(places([0]))
  }
  // The mobile app, and a surface the mod does not know.
  for (const surface of ['mobile', 'watch']) {
    expect(settings.map(setting => offered(setting, surface))).toEqual(places([]))
    // However a core spells the value that turns it on.
    expect(offered({ ...(settings[PROPOSE] as Setting), choices: ['true', 'false'], value: 'false' }, surface)).toEqual([])
    expect(offered({ ...(settings[PROPOSE] as Setting), value: true }, surface)).toEqual([1])
  }
  expect(offered({ ...(settings[PROPOSE] as Setting), choices: ['true', 'false'], value: 'false' }, 'terminal')).toEqual([0])
  // A setting of that name in the store's file or the owner's is not this machine's switch.
  expect(offered({ ...(settings[PROPOSE] as Setting), scope: 'store' }, 'terminal')).toEqual([])
  expect(offered({ ...(settings[PAUSED] as Setting), kind: 'shown' }, 'terminal')).toEqual([])
  expect(offered({ ...(settings[PAUSED] as Setting), isRead: false }, 'terminal')).toEqual([])
  // Where a setting stands in the view is nothing a press is offered by: its group and its place change none of it.
  expect(offered({ ...(settings[PAUSED] as Setting), group: 'about', place: 9 }, 'terminal')).toEqual([0])
  expect(offered({ ...(settings[PROPOSE] as Setting), group: 'about', place: 9 }, 'mobile')).toEqual([])
})

test('a press turns handing in on only for this machine, with the value the command takes for it, where it names one of the three surfaces', () => {
  // Covers: B199
  const settings = settingsOf()
  const propose = settings[PROPOSE] as Setting

  for (const surface of OFFERED_THE_TURN_ON) {
    expect(pressTurnsHandingInOn(propose, true, surface)).toBe(true)
    // As the command would be handed it, however the core spells it.
    expect(pressTurnsHandingInOn(propose, 'true', surface)).toBe(true)
  }
  // The mobile app, a surface the mod does not know, and names that only look like one it knows.
  for (const surface of ['mobile', 'watch', '', 'Terminal', 'terminal ', 'desktop\n']) {
    expect(pressTurnsHandingInOn(propose, true, surface)).toBe(false)
  }
  for (const choice of [false, 'on', ' true', 'TRUE', 'True', 1, 'false']) {
    expect(pressTurnsHandingInOn(propose, choice, 'terminal')).toBe(false)
  }
  expect(pressTurnsHandingInOn({ ...propose, scope: 'store' }, true, 'terminal')).toBe(false)
  expect(pressTurnsHandingInOn({ ...propose, scope: 'owner' }, true, 'terminal')).toBe(false)
  expect(pressTurnsHandingInOn({ ...propose, key: 'sessions.propose ' }, true, 'terminal')).toBe(false)
  expect(pressTurnsHandingInOn({ ...propose, key: 'sessions' }, true, 'terminal')).toBe(false)
  expect(pressTurnsHandingInOn(settings[PAUSED] as Setting, true, 'terminal')).toBe(false)
})

test('a press is marked as the one that turns handing in on when it is made, by the surface it named, and only that one is', () => {
  // Covers: B199
  beginSettings('open')
  fill('open', readLook())

  expect(beginChange('open', PROPOSE, 0, 't-0', 'mobile')).toBe(false)
  expect(beginChange('open', PROPOSE, 0, 't-0', 'watch')).toBe(false)
  expect(heldSettings('open').change).toBeNull()
  expect(beginChange('open', PROPOSE, 0, 't-1', 'desktop')).toBe(true)
  expect(startWriting('t-1')).toEqual({ key: 'sessions.propose', argument: 'true', isTurningHandingInOn: true })
  endChange('t-1', null)

  // Any other switch, pressed in the terminal or in the mobile app, is written as a session's change.
  for (const [token, surface] of [
    ['t-2', 'terminal'],
    ['t-3', 'mobile'],
  ] as const) {
    expect(beginChange('open', PAUSED, 0, token, surface)).toBe(true)
    expect(startWriting(token)).toEqual({ key: 'curation.paused', argument: 'true', isTurningHandingInOn: false })
    endChange(token, null)
  }

  // Turning it off is a session's change too.
  const turnedOn = catalog()
  Object.assign(turnedOn[PROPOSE] ?? {}, { value: true, shows: 'on' })
  fill('open', readLook(turnedOn))
  expect(beginChange('open', PROPOSE, 1, 't-4', 'terminal')).toBe(true)
  expect(startWriting('t-4')).toEqual({ key: 'sessions.propose', argument: 'false', isTurningHandingInOn: false })
  endChange('t-4', null)

  // The list read again meanwhile no longer names it for this machine: the press is dropped, not written.
  fill('open', readLook())
  expect(beginChange('open', PROPOSE, 0, 't-5', 'terminal')).toBe(true)
  const moved = catalog()
  Object.assign(moved[PROPOSE] ?? {}, IN_STORE)
  fill('open', readLook(moved))
  expect(startWriting('t-5')).toBeNull()
  expect(heldSettings('open').change).toBeNull()
  forgetSettingsUnless(null)
})

test('a press is noted only where the view offers it, one at a time, and written as the setting and the value it named', () => {
  // Covers: B198
  beginSettings('open')
  fill('open', readLook())

  // The value that is set, turning handing in on in the mobile app, a place the list does not have, another opening.
  expect(beginChange('open', PAUSED, 1, 't-0', 'terminal')).toBe(false)
  expect(beginChange('open', PROPOSE, 0, 't-0', 'mobile')).toBe(false)
  expect(beginChange('open', 99, 0, 't-0', 'terminal')).toBe(false)
  expect(beginChange('other', PAUSED, 0, 't-0', 'terminal')).toBe(false)
  // A setting that is no switch, in a group of choices and in one kept behind a row.
  expect(beginChange('open', CURATING, 0, 't-0', 'terminal')).toBe(false)
  expect(beginChange('open', PATH, 0, 't-0', 'terminal')).toBe(false)
  expect(heldSettings('open').change).toBeNull()

  expect(beginChange('open', PAUSED, 0, 't-1', 'terminal')).toBe(true)
  expect(heldSettings('open').change).toMatchObject({ scope: 'machine', key: 'curation.paused', choice: true, phase: 'waiting' })
  // One at a time.
  expect(beginChange('open', MODEL, 1, 't-2', 'terminal')).toBe(false)
  // Only the press that waits is written, under its own name; another opening does not take it back.
  expect(startWriting('t-2')).toBeNull()
  expect(undoChange('other')).toBe(false)
  // The list was read again meanwhile, in another order: the press still names its setting.
  fill('open', readLook([...catalog()].reverse()))
  expect(startWriting('t-1')).toEqual({ key: 'curation.paused', argument: 'true', isTurningHandingInOn: false })
  expect(startWriting('t-1')).toBeNull()
  // Being written, it is no longer taken back, by undo or by leaving.
  expect(undoChange('open')).toBe(false)
  dropWaitingChange()
  forgetSettingsUnless(null)
  expect(heldSettings('open').change?.phase).toBe('writing')

  // It ends under its own name, and the refusal is kept for the view that is open then.
  beginSettings('later')
  fill('later', readLook())
  expect(beginChange('later', MODEL, 1, 't-3', 'terminal')).toBe(false)
  endChange('t-3', 'not this one')
  expect(heldSettings('later').change?.phase).toBe('writing')
  endChange('t-1', 'refused')
  expect(heldSettings('later')).toMatchObject({ change: null, refusal: { scope: 'machine', key: 'curation.paused', line: 'refused' } })
  // The next press clears what the last one met.
  expect(beginChange('later', MODEL, 1, 't-4', 'terminal')).toBe(true)
  expect(heldSettings('later').refusal).toBeNull()
  forgetSettingsUnless(null)
  expect(heldSettings('later').change).toBeNull()
})

test('a press is not written when the list no longer offers its value, or the view it was made in is gone', () => {
  // Covers: B198
  const turnedOn = catalog()
  Object.assign(turnedOn[PAUSED] ?? {}, { value: true, shows: 'on' })

  beginSettings('open')
  fill('open', readLook())
  expect(beginChange('open', PAUSED, 0, 't-1', 'terminal')).toBe(true)
  // Another session turned it on meanwhile.
  fill('open', readLook(turnedOn))
  expect(startWriting('t-1')).toBeNull()
  expect(heldSettings('open').change).toBeNull()

  expect(beginChange('open', MODEL, 1, 't-2', 'terminal')).toBe(true)
  // A list that no longer names the setting.
  fill('open', readLook(catalog().filter(one => one.key !== 'curation.model')))
  expect(startWriting('t-2')).toBeNull()

  fill('open', readLook())
  expect(beginChange('open', MODEL, 1, 't-3', 'terminal')).toBe(true)
  // The view is opened anew: the press that waited in the opening before is taken back.
  beginSettings('later')
  expect(heldSettings('later').change).toBeNull()
  expect(startWriting('t-3')).toBeNull()

  // Two files can have a setting of one name: a press names the file with it.
  const twice = [fakeSetting('curation.paused', 'Paused elsewhere', 'about', 7, OF_OWNER), ...catalog()]
  fill('later', readLook(twice))
  expect(beginChange('later', PAUSED + 1, 0, 't-4', 'terminal')).toBe(true)
  expect(startWriting('t-4')).toEqual({ key: 'curation.paused', argument: 'true', isTurningHandingInOn: false })
  endChange('t-4', null)
  forgetSettingsUnless(null)
})

test('a press waits until it is taken back or its writing starts, and no other press is said to wait', () => {
  // Covers: B200
  beginSettings('open')
  fill('open', readLook())
  expect(waits('t-1')).toBe(false)

  expect(beginChange('open', PAUSED, 0, 't-1', 'terminal')).toBe(true)
  expect([waits('t-1'), waits('t-2')]).toEqual([true, false])
  expect(undoChange('open')).toBe(true)
  expect(waits('t-1')).toBe(false)

  expect(beginChange('open', PAUSED, 0, 't-3', 'terminal')).toBe(true)
  expect(waits('t-3')).toBe(true)
  expect(startWriting('t-3')).not.toBeNull()
  expect(waits('t-3')).toBe(false)
  endChange('t-3', null)
  forgetSettingsUnless(null)
})

/** The list as read with other groups than the core's four, for the tests of where the focus rests. */
function lookWith(groups: { name: string; title: string; folded: boolean }[], entries: FakeSetting[] = catalog()) {
  return parseSettings(JSON.stringify({ settings: entries, groups, curates: true, not_read: {} }))
}

test('the key of the row of a folded group names the group and the phase the view is drawn in: plain while no change is under way, another while a press waits, another while it is written', () => {
  // Covers: B200, B212
  expect(foldKey('about')).toBe('settings:fold:about')
  expect(foldKey('about', 'idle')).toBe('settings:fold:about')
  expect(foldKey('about', 'waiting')).toBe('settings:fold:about:waiting')
  expect(foldKey('about', 'writing')).toBe('settings:fold:about:writing')
  expect([foldKey('about'), foldKey('about', 'waiting'), foldKey('about', 'writing'), foldKey('worklog')]).toEqual([
    ABOUT_ROW,
    ABOUT_ROW_WAITING,
    ABOUT_ROW_WRITING,
    'settings:fold:worklog',
  ])
  // Three keys for one row: none is the key of another phase, of a value, of undo or of a tab.
  const keys = [foldKey('about'), foldKey('about', 'waiting'), foldKey('about', 'writing')]
  expect(new Set(keys).size).toBe(3)
  for (const key of keys) {
    expect(/^(set|tab):/.test(key)).toBe(false)
    expect(key).not.toBe(SETTINGS_UNDO)
  }
})

test('where the focus rests is the tab Overview until a value was pressed in the opening, and where no list is held', () => {
  // Covers: B200
  forgetSettingsUnless(null)
  expect(OFF_THE_VALUES).toBe('tab:overview:in:settings')
  // Nothing held, a list that is still read, one that could not be read, and one read with nothing pressed.
  expect(restKey()).toBe(OFF_THE_VALUES)
  beginSettings('open')
  expect(restKey()).toBe(OFF_THE_VALUES)
  fill('open', { state: 'failed', error: 'no store' })
  expect(restKey()).toBe(OFF_THE_VALUES)
  fill('open', readLook())
  expect(restKey()).toBe(OFF_THE_VALUES)

  // A press that is not one the view offers notes no setting.
  expect(beginChange('open', PAUSED, 1, 't-0', 'terminal')).toBe(false)
  expect(beginChange('open', PROPOSE, 0, 't-0', 'mobile')).toBe(false)
  expect(restKey()).toBe(OFF_THE_VALUES)

  // A press near the folded group, then a new opening: it starts without one.
  expect(beginChange('open', PAUSED, 0, 't-1', 'terminal')).toBe(true)
  expect(restKey()).toBe(ABOUT_ROW_WAITING)
  beginSettings('later')
  fill('later', readLook())
  expect(restKey()).toBe(OFF_THE_VALUES)
  forgetSettingsUnless(null)
  expect(restKey()).toBe(OFF_THE_VALUES)
})

test('the focus rests on the button that sets nothing nearest to the setting that was pressed, counted in what the view draws: the tab Overview near the top, the row of the folded group near it, and the tab where both are as near', () => {
  // Covers: B200
  // The view draws seven settings to choose and below them the row of the folded group. The tab
  // stands before the first: it is one away from the first setting, the row one from the seventh.
  const nearest: [at: number, rests: string][] = [
    [DUE, OFF_THE_VALUES],
    [PROPOSE, OFF_THE_VALUES],
    // The fourth of seven: four from the tab and four from the row.
    [MODEL, OFF_THE_VALUES],
    [PAUSED, ABOUT_ROW],
    [LANGUAGE, ABOUT_ROW],
  ]

  for (const [at, rests] of nearest) {
    beginSettings('open')
    fill('open', readLook())
    expect(beginChange('open', at, at === MODEL ? 1 : 0, 't-1', 'terminal')).toBe(true)
    expect(undoChange('open')).toBe(true)
    expect(restKey()).toBe(rests)
  }

  // The setting last pressed counts, not the first.
  beginSettings('open')
  fill('open', readLook())
  expect(beginChange('open', LANGUAGE, 0, 't-1', 'terminal')).toBe(true)
  expect(undoChange('open')).toBe(true)
  expect(restKey()).toBe(ABOUT_ROW)
  expect(beginChange('open', DUE, 0, 't-2', 'terminal')).toBe(true)
  expect(undoChange('open')).toBe(true)
  expect(restKey()).toBe(OFF_THE_VALUES)

  // The order is the view's, by group and place, not the list's: the same settings listed backwards rest alike.
  for (const [at, rests] of nearest) {
    const last = catalog().length - 1
    beginSettings('open')
    fill('open', readLook([...catalog()].reverse()))
    expect(beginChange('open', last - at, at === MODEL ? 1 : 0, 't-1', 'terminal')).toBe(true)
    expect(undoChange('open')).toBe(true)
    expect(restKey()).toBe(rests)
  }

  // A folded group that stands among the choices is near the settings on either side of it:
  // four settings of the curation run, the row, then one setting and three more.
  const aboutSecond = [SETTING_GROUPS[2], SETTING_GROUPS[3], SETTING_GROUPS[0], SETTING_GROUPS[1]].flatMap(group => (group === undefined ? [] : [group]))
  for (const [at, place, rests] of [
    [MODEL, 1, OFF_THE_VALUES],
    [PAUSED, 0, ABOUT_ROW],
    [LANGUAGE, 0, ABOUT_ROW],
    [DUE, 0, ABOUT_ROW],
    [PROPOSE, 0, ABOUT_ROW],
  ] as const) {
    beginSettings('open')
    fill('open', lookWith(aboutSecond))
    expect(beginChange('open', at, place, 't-1', 'terminal')).toBe(true)
    expect(undoChange('open')).toBe(true)
    expect(restKey()).toBe(rests)
  }
  forgetSettingsUnless(null)
})

test('the row the focus rests on is named by the key of the phase the view is in when it is asked: while the press waits, while it is written, and plain after undo and once the write ended', () => {
  // Covers: B200
  beginSettings('open')
  fill('open', readLook())

  expect(beginChange('open', PAUSED, 0, 't-1', 'terminal')).toBe(true)
  expect(restKey()).toBe(ABOUT_ROW_WAITING)
  expect(undoChange('open')).toBe(true)
  expect(restKey()).toBe(ABOUT_ROW)

  expect(beginChange('open', PAUSED, 0, 't-2', 'terminal')).toBe(true)
  expect(restKey()).toBe(ABOUT_ROW_WAITING)
  expect(startWriting('t-2')).not.toBeNull()
  expect(restKey()).toBe(ABOUT_ROW_WRITING)
  endChange('t-2', null)
  expect(restKey()).toBe(ABOUT_ROW)
  // A refusal ends the change like a write: the row has its plain key again.
  expect(beginChange('open', LANGUAGE, 0, 't-3', 'terminal')).toBe(true)
  expect(startWriting('t-3')).not.toBeNull()
  expect(restKey()).toBe(ABOUT_ROW_WRITING)
  endChange('t-3', 'the store cannot be reached')
  expect(restKey()).toBe(ABOUT_ROW)

  // A press dropped because the list no longer offers its value: no change is under way then.
  expect(beginChange('open', PAUSED, 0, 't-4', 'terminal')).toBe(true)
  const turnedOn = catalog()
  Object.assign(turnedOn[PAUSED] ?? {}, { value: true, shows: 'on' })
  fill('open', readLook(turnedOn))
  expect(startWriting('t-4')).toBeNull()
  expect(restKey()).toBe(ABOUT_ROW)

  // The tab has one key in every phase: it stands above the settings, where no value moves it.
  expect(beginChange('open', DUE, 0, 't-5', 'terminal')).toBe(true)
  expect(restKey()).toBe(OFF_THE_VALUES)
  expect(startWriting('t-5')).not.toBeNull()
  expect(restKey()).toBe(OFF_THE_VALUES)
  endChange('t-5', null)
  expect(restKey()).toBe(OFF_THE_VALUES)
  forgetSettingsUnless(null)
})

test('the focus rests on the tab Overview where no folded group holds a setting and where the list read again no longer has the setting that was pressed; it is never the key of a value', () => {
  // Covers: B200
  const isNoValue = (): void => {
    expect(/^set:/.test(restKey())).toBe(false)
    expect(restKey()).not.toBe(SETTINGS_UNDO)
  }

  // No folded group at all, and one that holds no setting.
  const choicesAlone = catalog().filter(entry => entry.group !== 'about')
  for (const look of [lookWith(SETTING_GROUPS.filter(group => !group.folded), choicesAlone), lookWith([...SETTING_GROUPS], choicesAlone)]) {
    beginSettings('open')
    fill('open', look)
    expect(look.state).toBe('read')
    // The settings of the folded group are gone from the list: the language is the seventh of seven.
    const language = choicesAlone.findIndex(entry => entry.key === 'language')
    expect(beginChange('open', language, 0, 't-1', 'terminal')).toBe(true)
    expect(restKey()).toBe(OFF_THE_VALUES)
    isNoValue()
    expect(undoChange('open')).toBe(true)
    expect(restKey()).toBe(OFF_THE_VALUES)
  }

  // The list read again without the setting that was pressed, and with it once more.
  beginSettings('open')
  fill('open', readLook())
  expect(beginChange('open', LANGUAGE, 0, 't-2', 'terminal')).toBe(true)
  expect(restKey()).toBe(ABOUT_ROW_WAITING)
  isNoValue()
  fill('open', readLook(catalog().filter(entry => entry.key !== 'language')))
  expect(startWriting('t-2')).toBeNull()
  expect(restKey()).toBe(OFF_THE_VALUES)
  fill('open', readLook())
  expect(restKey()).toBe(ABOUT_ROW)
  // A setting of that key in another file is another setting.
  const moved = catalog()
  Object.assign(moved[LANGUAGE] ?? {}, IN_STORE)
  fill('open', readLook(moved))
  expect(restKey()).toBe(OFF_THE_VALUES)
  // Sorted into the folded group, the setting that was pressed is no setting the view draws to choose.
  const folded = catalog()
  Object.assign(folded[LANGUAGE] ?? {}, { group: 'about', place: 9 })
  fill('open', readLook(folded))
  expect(restKey()).toBe(OFF_THE_VALUES)
  // A list that cannot be read again keeps the one before, and the place with it.
  fill('open', readLook())
  fill('open', { state: 'failed', error: 'no store' })
  expect(restKey()).toBe(ABOUT_ROW)

  // Whatever was pressed and whatever the phase, it is no value and not undo.
  for (const entries of [catalog(), [...catalog()].reverse()]) {
    for (const [at, entry] of entries.entries()) {
      for (const place of entry.choices.keys()) {
        beginSettings('open')
        fill('open', readLook(entries))
        if (beginChange('open', at, place, 't-3', 'terminal')) {
          isNoValue()
          expect(startWriting('t-3')).not.toBeNull()
          isNoValue()
          endChange('t-3', null)
          isNoValue()
        }
      }
    }
  }
  forgetSettingsUnless(null)
})

test('the title of a folded group is known for the opening that holds it, cleaned; a group of choices, one without a setting, a name the list does not have, another opening and a list not read have none', () => {
  // Covers: B212
  forgetSettingsUnless(null)
  expect(foldedTitle('open', 'about')).toBeNull()
  beginSettings('open')
  // While m2b reads, and where it could not.
  expect(foldedTitle('open', 'about')).toBeNull()
  fill('open', { state: 'failed', error: 'no store' })
  expect(foldedTitle('open', 'about')).toBeNull()

  fill('open', readLook())
  expect(foldedTitle('open', 'about')).toBe('About this setup')
  expect(foldedTitle('other', 'about')).toBeNull()
  for (const name of ['shows', 'reads', 'curation', 'elsewhere', '', 'About this setup', 'ABOUT']) {
    expect(foldedTitle('open', name)).toBeNull()
  }
  // A second folded group has its own, and one that holds no setting has none.
  const more = [...SETTING_GROUPS, { name: 'worklog', title: 'Worklog', folded: true }, { name: 'empty', title: 'Nothing here', folded: true }]
  const withWorklog = catalog()
  Object.assign(withWorklog.find(entry => entry.key === 'customers') ?? {}, { group: 'worklog', place: 1 })
  fill('open', lookWith(more, withWorklog))
  expect([foldedTitle('open', 'about'), foldedTitle('open', 'worklog'), foldedTitle('open', 'empty')]).toEqual(['About this setup', 'Worklog', null])
  // The list read again without a setting in the group, and with the group as one of choices.
  fill('open', readLook(catalog().filter(entry => entry.group !== 'about')))
  expect(foldedTitle('open', 'about')).toBeNull()
  fill('open', lookWith(SETTING_GROUPS.map(group => ({ ...group, folded: false }))))
  expect(foldedTitle('open', 'about')).toBeNull()
  // A title of the core is one plain line.
  const escape = String.fromCharCode(0x1b)
  fill('open', lookWith(SETTING_GROUPS.map(group => ({ ...group, title: `Ab${escape}[2Jout\nthis setup` }))))
  expect(foldedTitle('open', 'about')).toBe('About this setup')
  // A later read that failed keeps the list, and the group with it.
  fill('open', { state: 'failed', error: 'no store' })
  expect(foldedTitle('open', 'about')).toBe('About this setup')
  forgetSettingsUnless(null)
  expect(foldedTitle('open', 'about')).toBeNull()
})

const PROBE = 'settings-alone'

test('each button hands its action what it names: a value the place of its setting in the list, its own place among the choices and the surface of the press, the row of a folded group the name of its group', async ($, on) => {
  // Covers: B198, B212
  // The view drawn by a hook of the test's own, with actions that only note what they are handed.
  const handed: string[] = []
  const noting: SettingsActions = {
    choose: async (at: number, place: number, surface: string) => void handed.push(`choose ${at} ${place} on ${surface}`),
    undo: async () => void handed.push('undo'),
    showGroup: async (group: string) => void handed.push(`show the group ${group}`),
  }
  on('ui.render', { component: 'Pane', requestId: PROBE }, ($, e) => {
    const view = { kind: 'settings', press: 'open', aside: null, drawn: 0 } as const
    return settingsPane($, e, view, heldSettings('open'), noting, e.props.bodyColumns)
  })
  // A press says its own surface, whatever the drawing was made for.
  on('ui.press', { plugin: 'test', element: `set:${LANGUAGE}:0` }, (_, e, next) => next({ ...e, surface: 'mobile' }))
  beginSettings('open')
  fill('open', readLook())

  for (const columns of [80, 24]) {
    handed.length = 0
    const read = await $.ui.mount({ ...pane(PROBE, columns), plugin: 'test', surface: 'desktop' })
    for (const key of [`set:${DUE}:0`, `set:${DUE}:2`, TURN_ON, `set:${MODEL}:1`, `set:${PAUSED}:0`, `set:${LANGUAGE}:0`, ABOUT_ROW]) {
      await read.press({ key })
    }
    await read.unmount()
    // While a press waits and while it is written the row has the key of that phase, and names the same group.
    expect(beginChange('open', PAUSED, 0, 't-1', 'desktop')).toBe(true)
    const waiting = await $.ui.mount({ ...pane(PROBE, columns), plugin: 'test', surface: 'desktop' })
    await waiting.press({ key: SETTINGS_UNDO })
    await waiting.press({ key: ABOUT_ROW_WAITING })
    await waiting.unmount()
    expect(startWriting('t-1')).not.toBeNull()
    const writing = await $.ui.mount({ ...pane(PROBE, columns), plugin: 'test', surface: 'desktop' })
    await writing.press({ key: ABOUT_ROW_WRITING })
    await writing.unmount()
    endChange('t-1', null)

    expect(handed).toEqual([
      `choose ${DUE} 0 on desktop`,
      `choose ${DUE} 2 on desktop`,
      `choose ${PROPOSE} 0 on desktop`,
      `choose ${MODEL} 1 on desktop`,
      `choose ${PAUSED} 0 on desktop`,
      `choose ${LANGUAGE} 0 on mobile`,
      'show the group about',
      'undo',
      'show the group about',
      'show the group about',
    ])
  }
  forgetSettingsUnless(null)
})
