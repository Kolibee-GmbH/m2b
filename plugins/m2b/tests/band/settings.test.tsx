import { expect, test } from 'claude-code/testing'
import type { CommandRunResult, ProcessRunResult } from 'claude-code'
import type { Engine } from 'claude-code/testing'

import {
  SETTINGS_UNDO,
  afterBack,
  askSettings,
  beginChange,
  beginSettings,
  dropWaitingChange,
  endChange,
  fillSettings,
  focusKeyOfCard,
  focusKeyOfHeldCard,
  forgetSettingsUnless,
  heldSettings,
  holdsSettings,
  listOf,
  offered,
  openSettings,
  parseSettings,
  pressTurnsHandingInOn,
  rowKey,
  settingsPane,
  showsCard,
  startWriting,
  undoChange,
  waits,
} from '../../hooks/settings'
import type { Reached, Setting, SettingsActions } from '../../hooks/settings'
import type { PaneView } from '../../types'
import { FakeM2b, fail, ok, pane, start, texts } from './harness'

const PANE = 'm2b'
const AS_A_DIALOG = { id: PANE, title: 'm2b', closeOnEscape: true, focus: true }
const PLACED = 'every setting of m2b is in the m2b pane'
const READING = 'm2b is reading its settings…'
const NOTES = '/home/alex/Notes'
const DOES_NOT_CURATE = 'This machine does not curate: the settings of the curation run do nothing here.'
const IN_YOUR_OWN_TERMINAL = 'Turned on in a terminal of your own: m2b settings set sessions.propose true'
const LIST = ['settings', '--json']
const BY_YOUR_PRESS = 'Your press here turns it on, as a terminal of your own does.'
const EVERY_MACHINE = 'Every machine that shares the store needs an m2b that knows handing in.'
const AT_ITS_START =
  'A session gets the tool when it starts or its plugins are reloaded: until then, one that ran before this was turned on does not have it.'
/** The surfaces whose card offers to turn handing in on; `mobile` is how the mobile app names itself. */
const OFFERED_THE_TURN_ON = ['terminal', 'desktop', 'vscode'] as const
type Surface = (typeof OFFERED_THE_TURN_ON)[number] | 'mobile'
/** What the core says to a session that turns handing in on, in short. */
const NO_SESSION_TURNS_IT_ON = 'sessions.propose is turned on in a terminal of your own, outside Claude Code'
/** What a call of `m2b settings set` is handed: the core takes an empty `CLAUDECODE` as a terminal of the owner's own. */
const OUTSIDE_A_SESSION = { CLAUDECODE: '' }
const INSIDE_A_SESSION = { CLAUDECODE: '1' }

type Entry = {
  key: string
  file: string
  scope: string
  kind: string
  title: string
  does: string
  read: boolean
  value: unknown
  shows: string | null
  default: unknown
  choices: unknown[]
  changed_by: string
  change: string | null
  curation: boolean
}

function entry(key: string, title: string, fields: Partial<Entry>): Entry {
  return {
    key,
    file: 'config.json',
    scope: 'machine',
    kind: 'shown',
    title,
    does: `What ${key} does.`,
    read: true,
    value: null,
    shows: 'not set',
    default: null,
    choices: [],
    changed_by: 'command',
    change: `m2b config set ${key} <value>`,
    curation: false,
    ...fields,
  }
}

const onOff = (key: string, isOn: boolean): Partial<Entry> => ({
  kind: 'switch',
  value: isOn,
  shows: isOn ? 'on' : 'off',
  default: false,
  choices: [true, false],
  change: `m2b settings set ${key} true|false`,
})
const inStore: Partial<Entry> = { file: 'store.json', scope: 'store' }
const ofOwner: Partial<Entry> = { file: 'profile.json', scope: 'owner' }

const [MACHINE_ID, PATH, MODEL, PAUSED, PROPOSE, EXECUTABLES, BACKEND, TIMEOUT, LANGUAGE, CUSTOMERS] = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
/** The button that turns handing in on: the first of its switch's two values, on its card. */
const TURN_ON = `set:${PROPOSE}:0`
/** The keys of a card's `previous` and `next`, which name the card they are drawn on. */
const previousOf = (at: number): string => `settings:previous:${at}`
const nextOf = (at: number): string => `settings:next:${at}`
/** The buttons that lead on from a card that is neither the first nor the last. */
const walk = (at: number): string[] => [previousOf(at), nextOf(at), 'settings:list']

/** Ten settings as `m2b settings --json` lists them: each kind, each file, each way a setting changes. */
function catalog(): Entry[] {
  return [
    entry('machine_id', "This machine's name", { value: 'tower-1', shows: 'tower-1', changed_by: 'never by hand', change: null }),
    entry('store.path', 'Store folder', { value: NOTES, shows: NOTES, change: 'm2b config set store.path <folder>' }),
    entry('curation.model', 'Model of curation', {
      kind: 'switch',
      value: 'haiku',
      shows: 'haiku',
      default: 'haiku',
      choices: ['haiku', 'sonnet'],
      change: 'm2b settings set curation.model haiku|sonnet',
      curation: true,
    }),
    entry('curation.paused', 'Curation paused', { ...onOff('curation.paused', false), curation: true }),
    entry('sessions.propose', 'Sessions hand in proposals', onOff('sessions.propose', false)),
    entry('executables', 'Programs m2b starts', { kind: 'named', shows: '3 named', change: 'm2b config set executables.<program> <path>' }),
    entry('tasks.backend', 'Task list', { ...inStore, value: 'markdown', shows: 'markdown', changed_by: 'setup', change: '/m2b:setup' }),
    entry('tasks.timeout_seconds', 'Time limit of a tasks call', {
      ...inStore,
      value: 20,
      shows: '20',
      default: 20,
      changed_by: 'by hand',
      change: 'edit tasks.timeout_seconds in store.json, in the store folder',
    }),
    entry('language', 'Language', {
      ...ofOwner,
      kind: 'switch',
      value: 'en',
      shows: 'en',
      default: 'en',
      choices: ['de', 'en'],
      change: 'm2b settings set language de|en',
    }),
    entry('customers', 'Customers', { ...ofOwner, kind: 'named', shows: '2 customers', changed_by: 'setup', change: '/m2b:worklog-setup' }),
  ]
}

/** The core's two commands, answered from memory. */
class FakeSettings {
  entries = catalog()
  curates: boolean | null = true
  notRead: Record<string, string> = {}
  /** When set, `m2b settings set` refuses with this line and changes nothing. */
  refuses: string | null = null
  /** When set, `m2b settings` fails with this as its message. */
  listFails: string | null = null
  /** When set, `m2b settings --json` answers this instead, whatever its shape. */
  part: unknown = undefined
  /** The variables each `m2b settings set` was handed, one entry per call. */
  readonly changedWith: (Record<string, string> | undefined)[] = []

  handle = (args: readonly string[], env?: Record<string, string>): ProcessRunResult => {
    if (args[0] !== 'set') {
      const answer = this.part ?? { curates: this.curates, not_read: this.notRead, settings: this.entries }
      return this.listFails === null ? ok(JSON.stringify(answer)) : fail(this.listFails)
    }
    this.changedWith.push(env)
    const [key, value] = args[1] === '--' ? args.slice(2) : args.slice(1)
    // As the core: no call that carries a `CLAUDECODE` with a value turns handing in on.
    if (key === 'sessions.propose' && value === 'true' && env?.['CLAUDECODE']) {
      return { ...fail(NO_SESSION_TURNS_IT_ON), exitCode: 2 }
    }
    const found = this.entries.find(one => one.key === key && one.kind === 'switch')
    if (this.refuses !== null || found === undefined) {
      return { ...fail(this.refuses ?? `${key} is no switch`), exitCode: 2 }
    }
    found.value = value === 'true' ? true : value === 'false' ? false : value
    found.shows = found.value === true ? 'on' : found.value === false ? 'off' : String(found.value)
    return ok('')
  }
}

function world(): { fake: FakeM2b; settings: FakeSettings } {
  const [fake, settings] = [new FakeM2b(), new FakeSettings()]
  fake.onSettings = settings.handle
  return { fake, settings }
}

function typed($: Engine, command: string, args = ''): Promise<CommandRunResult> {
  return $.command.run({ command, args, origin: { kind: 'composer' }, presentation: { isFullscreen: false, columns: 100 } })
}

type Clock = Awaited<ReturnType<typeof start>>['clock']

/** The list, opened with the command and read. */
async function openList($: Engine, clock: Clock, columns = 80, surface: Surface = 'terminal') {
  await typed($, 'm2b-settings')
  await clock.advance(1)
  return $.ui.mount({ ...pane(PANE, columns), surface })
}

/** The card of the setting at `at`, opened from the list. */
async function openCard($: Engine, clock: Clock, at: number, columns = 80, surface: Surface = 'terminal') {
  const ui = await openList($, clock, columns, surface)
  await ui.press({ key: `setting:${at}` })
  return ui
}

/** A drawing of the pane, on whatever surface it was mounted. */
type Mounted = Pick<Awaited<ReturnType<typeof openList>>, 'findAll'>

async function buttons(ui: Mounted): Promise<string[]> {
  return (await ui.findAll({ type: 'Button' })).map(button => String(button.key))
}

/** What the pane draws, in the order of its tree: a button as `[key]`, a text as it reads. */
async function inOrder(ui: Mounted): Promise<string[]> {
  return (await ui.findAll({}))
    .filter(found => found.type === 'Button' || found.type === 'Text')
    .map(found => (found.type === 'Button' ? `[${String(found.key)}]` : found.text.trim()))
}

async function labels(ui: Mounted): Promise<string[]> {
  return (await ui.findAll({ type: 'Button' })).map(button => String(button.props['label']))
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

test('/m2b-settings opens the list: every setting under its file, with its title and its value', async ($, on) => {
  // Covers: B197
  const { fake } = world()
  const { clock, commands, opened } = await start($, on, fake)
  const opensBefore = opened.length

  const answer = await typed($, 'm2b-settings')
  const reading = await $.ui.mount({ ...pane(PANE), surface: 'terminal' })
  expect(await texts(reading)).toEqual(['Settings', READING])
  await clock.advance(1)

  expect(answer.text).toBe(PLACED)
  expect(commands.find(command => command.name === 'm2b-settings')?.immediate).toBe(true)
  expect(opened.slice(opensBefore)).toEqual([AS_A_DIALOG])
  expect(fake.settingCalls()).toEqual([LIST])
  expect(await texts(reading)).toEqual([
    'Settings',
    'This machine',
    "This machine's name: tower-1",
    `Store folder: ${NOTES}`,
    'Model of curation: haiku',
    'Curation paused: off',
    'Sessions hand in proposals: off',
    'Programs m2b starts: 3 named',
    'The store, for every machine',
    'Task list: markdown',
    'Time limit of a tasks call: 20',
    'The owner, for every machine',
    'Language: en',
    'Customers: 2 customers',
  ])
  expect(await buttons(reading)).toEqual(['back', ...catalog().map((_, at) => `setting:${at}`)])
  await reading.unmount()
})

test('the button on the start view opens the list too, as a dialog that leads back', async ($, on) => {
  // Covers: B197
  const { fake } = world()
  const { clock, opened } = await start($, on, fake)
  await typed($, 'm2b-pane')
  const ui = await $.ui.mount({ ...pane(PANE), surface: 'terminal' })
  const opensBefore = opened.length

  await ui.press({ key: 'show:settings' })
  await clock.advance(1)

  expect(opened.slice(opensBefore)).toEqual([AS_A_DIALOG])
  expect(await texts(ui)).toContain('Curation paused: off')
  await ui.press({ key: 'back' })
  expect(await texts(ui)).toContain('In this session')
  await ui.unmount()
})

test('a row opens the card of its setting: what it is, where it lives, its value and what it does', async ($, on) => {
  // Covers: B197
  const { fake } = world()
  const { clock } = await start($, on, fake)

  const ui = await openCard($, clock, PAUSED)

  expect(await texts(ui)).toEqual([
    'Settings · 4 of 10',
    'Curation paused',
    'this machine · curation.paused',
    'now: off',
    'What curation.paused does.',
  ])
  expect(await buttons(ui)).toEqual([...walk(PAUSED), `set:${PAUSED}:0`])
  expect(await labels(ui)).toEqual(['previous', 'next', 'list', 'turn on'])
  // Read once: a card is drawn from what the list read.
  expect(fake.settingCalls()).toEqual([LIST])
  await ui.unmount()
})

test('next and previous walk through every setting, the shown and the counted ones among them', async ($, on) => {
  // Covers: B197
  const { fake } = world()
  const { clock } = await start($, on, fake)
  const ui = await openCard($, clock, MACHINE_ID)
  const walked: string[] = []

  expect(await buttons(ui)).toEqual([nextOf(MACHINE_ID), 'settings:list'])
  for (let at = 0; at < catalog().length; at += 1) {
    walked.push((await texts(ui))[2] ?? '')
    if (at < catalog().length - 1) {
      await ui.press({ key: nextOf(at) })
    }
  }

  expect(walked).toEqual([
    'this machine · machine_id',
    'this machine · store.path',
    'this machine · curation.model',
    'this machine · curation.paused',
    'this machine · sessions.propose',
    'this machine · executables',
    'the store, for every machine · tasks.backend',
    'the store, for every machine · tasks.timeout_seconds',
    'the owner, for every machine · language',
    'the owner, for every machine · customers',
  ])
  expect(await buttons(ui)).toEqual([previousOf(CUSTOMERS), 'settings:list'])
  await ui.press({ key: previousOf(CUSTOMERS) })
  expect((await texts(ui))[0]).toBe('Settings · 9 of 10')
  await ui.press({ key: 'settings:list' })
  expect((await texts(ui)).slice(0, 2)).toEqual(['Settings', 'This machine'])
  await ui.unmount()
})

test('a setting that is no switch says what changes it, and offers nothing to press', async ($, on) => {
  // Covers: B197
  const { fake } = world()
  const { clock } = await start($, on, fake)
  const ui = await openList($, clock)
  const last: Record<number, string> = {
    [MACHINE_ID]: 'kept by m2b, never changed by hand',
    [PATH]: 'change: m2b config set store.path <folder>',
    [EXECUTABLES]: 'change: m2b config set executables.<program> <path>',
    [BACKEND]: 'set up with /m2b:setup',
    [TIMEOUT]: 'by hand: edit tasks.timeout_seconds in store.json, in the store folder',
    [CUSTOMERS]: 'set up with /m2b:worklog-setup',
  }

  for (const [at, line] of Object.entries(last)) {
    await ui.press({ key: `setting:${at}` })
    expect((await texts(ui)).at(-1)).toBe(line)
    expect((await buttons(ui)).filter(key => key.startsWith('set:'))).toEqual([])
    await ui.press({ key: 'settings:list' })
  }
  await ui.press({ key: `setting:${CUSTOMERS}` })
  expect(await texts(ui)).toContain('now: 2 customers')
  await ui.unmount()
})

test('a press on a switch writes nothing for five seconds and offers undo, then runs m2b settings set and reads again', async ($, on) => {
  // Covers: B198
  const { fake } = world()
  const { clock } = await start($, on, fake)
  const ui = await openCard($, clock, PAUSED)
  const callsBefore = fake.calls.length

  await ui.press({ key: `set:${PAUSED}:0` })

  expect(await texts(ui)).toContain('turning curation.paused on')
  expect(await buttons(ui)).toEqual([...walk(PAUSED), 'settings:undo'])
  await clock.advance(4_999)
  expect(fake.calls.slice(callsBefore).filter(call => call[0] === 'settings')).toEqual([])

  await clock.advance(1)
  await clock.advance(1)

  // The change and the list read again come first: the band is not waited for, and is read behind them.
  expect(fake.calls.slice(callsBefore, callsBefore + 2)).toEqual([['settings', 'set', '--', 'curation.paused', 'true'], LIST])
  expect(fake.calls.slice(callsBefore + 2)).toEqual([['band', '--json']])
  expect(await texts(ui)).toContain('now: on')
  expect(await labels(ui)).toEqual(['previous', 'next', 'list', 'turn off'])
  await ui.unmount()
})

test('undo within the five seconds takes the press back: nothing is written', async ($, on) => {
  // Covers: B198
  const { fake } = world()
  const { clock } = await start($, on, fake)
  const ui = await openCard($, clock, PAUSED)

  await ui.press({ key: `set:${PAUSED}:0` })
  await clock.advance(2_000)
  await ui.press({ key: 'settings:undo' })
  // At once: the card offers its switch again.
  expect(await labels(ui)).toEqual(['previous', 'next', 'list', 'turn on'])
  await clock.advance(10_000)

  expect(fake.settingCalls()).toEqual([LIST])
  expect(await texts(ui)).toContain('now: off')
  expect(await labels(ui)).toEqual(['previous', 'next', 'list', 'turn on'])
  await ui.unmount()
})

test('a switch of a few names offers each other name, and hands the name on as it is', async ($, on) => {
  // Covers: B198
  const { fake } = world()
  const { clock } = await start($, on, fake)
  const ui = await openCard($, clock, MODEL)

  expect(await labels(ui)).toEqual(['previous', 'next', 'list', 'set to sonnet'])
  await ui.press({ key: `set:${MODEL}:1` })
  expect(await texts(ui)).toContain('setting curation.model to sonnet')
  await clock.advance(5_000)
  await clock.advance(1)

  expect(fake.settingCalls().slice(1)).toEqual([['settings', 'set', '--', 'curation.model', 'sonnet'], LIST])
  expect(await texts(ui)).toContain('now: sonnet')
  expect(await labels(ui)).toEqual(['previous', 'next', 'list', 'set to haiku'])
  await ui.unmount()
})

test('a value that is none of the switch values is shown as it is, with every value to choose', async ($, on) => {
  // Covers: B197
  const { fake, settings } = world()
  Object.assign(settings.entries[MODEL] ?? {}, { value: 'opus', shows: 'opus' })
  Object.assign(settings.entries[LANGUAGE] ?? {}, { value: 'fr', shows: 'fr' })
  const { clock } = await start($, on, fake)

  const ui = await openCard($, clock, MODEL)

  expect(await texts(ui)).toContain('now: opus')
  expect(await texts(ui)).toContain('default: haiku')
  expect(await labels(ui)).toEqual(['previous', 'next', 'list', 'set to haiku', 'set to sonnet'])
  await ui.press({ key: 'settings:list' })
  await ui.press({ key: `setting:${LANGUAGE}` })
  expect(await labels(ui)).toEqual(['previous', 'next', 'list', 'set to de', 'set to en'])
  await ui.unmount()
})

test('what the command refuses stands on the card in its own words, and the value is as it was', async ($, on) => {
  // Covers: B198
  const { fake, settings } = world()
  const { clock } = await start($, on, fake)
  const ui = await openCard($, clock, LANGUAGE)
  const bandReads = fake.calls.filter(call => call[0] === 'band').length
  settings.refuses = 'profile.json in the store does not follow its format; m2b profile get says where'

  await ui.press({ key: `set:${LANGUAGE}:0` })
  await clock.advance(5_000)
  await clock.advance(1)

  expect(await texts(ui)).toContain(`not changed: ${settings.refuses}`)
  expect(await texts(ui)).toContain('now: en')
  expect(await labels(ui)).toEqual(['previous', 'next', 'list', 'set to de'])
  // Nothing was written, so the band holds nothing new and is not read.
  expect(fake.calls.filter(call => call[0] === 'band').length).toBe(bandReads)
  // It stands on the card of the setting it was about, and on no other.
  await ui.press({ key: previousOf(LANGUAGE) })
  expect((await texts(ui)).some(text => text.startsWith('not changed'))).toBe(false)
  await ui.press({ key: nextOf(TIMEOUT) })
  expect(await texts(ui)).toContain(`not changed: ${settings.refuses}`)
  // The next press on the card is another try; what the last one met is gone.
  settings.refuses = null
  await ui.press({ key: `set:${LANGUAGE}:0` })
  expect((await texts(ui)).some(text => text.startsWith('not changed'))).toBe(false)
  await ui.unmount()
})

test('in a terminal, the desktop app and VS Code the card of handing in offers turn on: on the card alone, below the buttons that lead on and the line that says how, under no key of its own', async ($, on) => {
  // Covers: B199
  const { fake } = world()
  const { clock } = await start($, on, fake)

  for (const surface of OFFERED_THE_TURN_ON) {
    const ui = await openList($, clock, 80, surface)
    // The list has rows to open and the way back, never a switch.
    expect(await buttons(ui)).toContain(`setting:${PROPOSE}`)
    expect((await buttons(ui)).every(key => key === 'back' || key.startsWith('setting:'))).toBe(true)
    await ui.press({ key: `setting:${PROPOSE}` })

    expect(await buttons(ui)).toEqual([...walk(PROPOSE), TURN_ON])
    expect(await labels(ui)).toEqual(['previous', 'next', 'list', 'turn on'])
    const turnOn = await ui.find({ key: TURN_ON })
    for (const reach of ['hotkey', 'action', 'autoFocus', 'variant', 'role']) {
      expect(turnOn?.props[reach]).toBeUndefined()
    }
    expect(await texts(ui)).not.toContain(IN_YOUR_OWN_TERMINAL)
    // What it needs, then how it is turned on, then the button: the last thing on the card.
    const drawn = await inOrder(ui)
    expect(drawn.indexOf(EVERY_MACHINE)).toBeGreaterThan(drawn.indexOf('[settings:list]'))
    expect(drawn.slice(drawn.indexOf(EVERY_MACHINE) + 1)).toEqual([BY_YOUR_PRESS, `[${TURN_ON}]`])
    expect(drawn).not.toContain(AT_ITS_START)
    await ui.unmount()
  }
})

test('the press on turn on waits five seconds with undo, is then the one call handed to m2b as made outside a session, and the card says what it reaches', async ($, on) => {
  // Covers: B199
  const { fake, settings } = world()
  const { clock } = await start($, on, fake)

  for (const [turn, surface] of OFFERED_THE_TURN_ON.entries()) {
    Object.assign(settings.entries[PROPOSE] ?? {}, onOff('sessions.propose', false))
    const ui = await openCard($, clock, PROPOSE, 80, surface)

    await ui.press({ key: TURN_ON })

    expect(await texts(ui)).toContain('turning sessions.propose on')
    expect(await buttons(ui)).toEqual([...walk(PROPOSE), 'settings:undo'])
    await clock.advance(4_999)
    expect(settings.changedWith).toHaveLength(turn)
    await clock.advance(1)
    await clock.advance(1)

    expect(settings.changedWith).toHaveLength(turn + 1)
    expect((await texts(ui)).some(shown => shown.startsWith('not changed'))).toBe(false)
    expect(await texts(ui)).toContain('now: on')
    expect(await texts(ui)).toContain(AT_ITS_START)
    expect(await texts(ui)).toContain(EVERY_MACHINE)
    expect(await texts(ui)).not.toContain(BY_YOUR_PRESS)
    expect(await labels(ui)).toEqual(['previous', 'next', 'list', 'turn off'])
    await ui.unmount()
  }

  const written = fake.settingCalls().filter(call => call[1] === 'set')
  expect(written).toEqual(OFFERED_THE_TURN_ON.map(() => ['settings', 'set', '--', 'sessions.propose', 'true']))
  expect(settings.changedWith).toEqual(OFFERED_THE_TURN_ON.map(() => OUTSIDE_A_SESSION))
})

test('undo, and leaving the card, take the press on turn on back: nothing is handed to m2b', async ($, on) => {
  // Covers: B199
  const { fake, settings } = world()
  const { clock } = await start($, on, fake)
  const ui = await openCard($, clock, PROPOSE)

  await ui.press({ key: TURN_ON })
  await ui.press({ key: 'settings:undo' })
  await clock.advance(10_000)
  expect(await labels(ui)).toEqual(['previous', 'next', 'list', 'turn on'])

  await ui.press({ key: TURN_ON })
  await ui.press({ key: nextOf(PROPOSE) })
  await clock.advance(10_000)

  expect(settings.changedWith).toEqual([])
  expect(fake.settingCalls()).toEqual([LIST])
  await ui.unmount()
})

test('in the mobile app the card of handing in names the command for a terminal and offers nothing that turns it on', async ($, on) => {
  // Covers: B199
  const { fake, settings } = world()
  const { clock } = await start($, on, fake)
  const ui = await openCard($, clock, PROPOSE, 80, 'mobile')

  expect(await texts(ui)).toContain(IN_YOUR_OWN_TERMINAL)
  expect(await texts(ui)).not.toContain(BY_YOUR_PRESS)
  expect(await texts(ui)).toContain(EVERY_MACHINE)
  expect(await buttons(ui)).toEqual([...walk(PROPOSE)])
  await ui.unmount()

  // Turned on already, it is turned off from anywhere, as a change made inside a session: that way no session gains anything.
  Object.assign(settings.entries[PROPOSE] ?? {}, { value: true, shows: 'on' })
  const whereOn = await openCard($, clock, PROPOSE, 80, 'mobile')
  expect(await labels(whereOn)).toEqual(['previous', 'next', 'list', 'turn off'])
  expect(await texts(whereOn)).not.toContain(IN_YOUR_OWN_TERMINAL)
  expect(await texts(whereOn)).toContain(AT_ITS_START)
  await whereOn.press({ key: `set:${PROPOSE}:1` })
  await clock.advance(5_000)
  await clock.advance(1)

  expect(fake.settingCalls().filter(call => call[1] === 'set')).toEqual([['settings', 'set', '--', 'sessions.propose', 'false']])
  expect(settings.changedWith).toEqual([INSIDE_A_SESSION])
  expect(await texts(whereOn)).toContain('now: off')
  await whereOn.unmount()
})

test('the surface is the one the press came from, not the one the card was drawn on', async ($, on) => {
  // Covers: B199
  const { fake, settings } = world()
  // A card drawn for the terminal, pressed from a client that names itself the mobile app: what the press says counts.
  on('ui.press', { plugin: 'm2b', element: TURN_ON }, (_, e, next) => next({ ...e, surface: 'mobile' }))
  const { clock } = await start($, on, fake)
  const ui = await openCard($, clock, PROPOSE)
  expect(await buttons(ui)).toContain(TURN_ON)

  await ui.press({ key: TURN_ON })

  expect(await buttons(ui)).not.toContain('settings:undo')
  await clock.advance(10_000)
  expect(settings.changedWith).toEqual([])
  expect(await texts(ui)).toContain('now: off')
  await ui.unmount()
})

test('while another change is being written, the card of handing in still says how it is turned on, and offers nothing', async ($, on) => {
  // Covers: B199
  const { fake } = world()
  fake.delayMs = args => (args[0] === 'settings' && args[1] === 'set' ? 3_000 : 0)
  const { clock } = await start($, on, fake)
  const ui = await openCard($, clock, PAUSED)

  await ui.press({ key: `set:${PAUSED}:0` })
  await clock.advance(5_000)
  await ui.press({ key: nextOf(PAUSED) })

  expect(await texts(ui)).toContain('Sessions hand in proposals')
  expect(await texts(ui)).toContain(BY_YOUR_PRESS)
  expect(await texts(ui)).toContain('A change of curation.paused is under way.')
  expect(await buttons(ui)).toEqual([...walk(PROPOSE)])
  await clock.advance(3_001)
  await clock.advance(1)
  expect(await buttons(ui)).toContain(TURN_ON)
  await ui.unmount()
})

test('a core that spells on and off as texts is read the same: on is on, and the value that turns it on is the one the command takes', async ($, on) => {
  // Covers: B199
  const { fake, settings } = world()
  const { clock } = await start($, on, fake)
  const asTexts = (value: string): Partial<Entry> => ({ value, shows: value === 'true' ? 'on' : 'off', choices: ['true', 'false'] })

  Object.assign(settings.entries[PROPOSE] ?? {}, asTexts('true'))
  const whereOn = await openCard($, clock, PROPOSE)
  expect(await texts(whereOn)).toContain(AT_ITS_START)
  expect(await texts(whereOn)).not.toContain(BY_YOUR_PRESS)
  expect(await labels(whereOn)).toEqual(['previous', 'next', 'list', 'set to false'])
  await whereOn.unmount()

  Object.assign(settings.entries[PROPOSE] ?? {}, asTexts('false'))
  const whereOff = await openCard($, clock, PROPOSE)
  expect(await texts(whereOff)).toContain(BY_YOUR_PRESS)
  expect(await labels(whereOff)).toEqual(['previous', 'next', 'list', 'set to true'])
  await whereOff.press({ key: TURN_ON })
  await clock.advance(5_000)
  await clock.advance(1)
  expect(settings.changedWith).toEqual([OUTSIDE_A_SESSION])
  await whereOff.unmount()

  Object.assign(settings.entries[PROPOSE] ?? {}, asTexts('false'))
  const inTheApp = await openCard($, clock, PROPOSE, 80, 'mobile')
  expect(await labels(inTheApp)).toEqual(['previous', 'next', 'list'])
  expect(await texts(inTheApp)).toContain(IN_YOUR_OWN_TERMINAL)
  await inTheApp.unmount()
})

test('in a pane 24 columns wide the card of handing in wraps its lines and keeps its button below them', async ($, on) => {
  // Covers: B199
  const { fake } = world()
  const { clock } = await start($, on, fake)
  const ui = await openCard($, clock, PROPOSE, 24)

  for (const line of [EVERY_MACHINE, BY_YOUR_PRESS]) {
    expect((await ui.findAll({ type: 'Text', text: line }))[0]?.props['wrap']).toBe('wrap')
  }
  const drawn = await inOrder(ui)
  expect(drawn.slice(-2)).toEqual([BY_YOUR_PRESS, `[${TURN_ON}]`])
  // A terminal draws a button as `[ label ]`: four cells more than its label.
  const label = String((await ui.find({ key: TURN_ON }))?.props['label'])
  expect(label).toBe('turn on')
  expect(label.length + 4).toBeLessThanOrEqual(24)
  await ui.unmount()
})

test('a setting of that name that is no switch of this machine, or was not read, says nothing about turning it on', async ($, on) => {
  // Covers: B199
  const { fake, settings } = world()
  const { clock } = await start($, on, fake)
  const ABOUT_TURNING_ON = [BY_YOUR_PRESS, IN_YOUR_OWN_TERMINAL, EVERY_MACHINE, AT_ITS_START]

  for (const other of [inStore, { kind: 'shown' }, { read: false }, { ...ofOwner, value: true, shows: 'on' }]) {
    settings.entries[PROPOSE] = entry('sessions.propose', 'Sessions hand in proposals', { ...onOff('sessions.propose', false), ...other })
    const ui = await openCard($, clock, PROPOSE)

    expect(await texts(ui)).toContain('Sessions hand in proposals')
    for (const line of ABOUT_TURNING_ON) {
      expect(await texts(ui)).not.toContain(line)
    }
    expect(await buttons(ui)).not.toContain(TURN_ON)
    await ui.unmount()
  }
})

test('no other press and no command is handed to m2b as made outside a session', async ($, on) => {
  // Covers: B199
  const { fake, settings } = world()
  // A core that spells the switch otherwise, and one that lists a setting of that name for the store.
  Object.assign(settings.entries[PROPOSE] ?? {}, { value: 'off', shows: 'off', choices: ['on', 'off'] })
  settings.entries.push(entry('sessions.propose', 'Handing in, of the store', { ...inStore, ...onOff('sessions.propose', false) }))
  const [IN_WORDS, OF_THE_STORE] = [PROPOSE, settings.entries.length - 1]
  const { clock } = await start($, on, fake)

  // The command with words behind it writes nothing at all.
  await typed($, 'm2b-settings', 'sessions.propose true')
  await clock.advance(10_000)
  expect(settings.changedWith).toEqual([])

  const ui = await $.ui.mount({ ...pane(PANE), surface: 'terminal' })
  // Another switch, pressed in the terminal.
  await ui.press({ key: `setting:${PAUSED}` })
  await ui.press({ key: `set:${PAUSED}:0` })
  await clock.advance(5_000)
  await clock.advance(1)
  // A value that is not the one the command takes to turn handing in on: the core decides, as for a session.
  await ui.press({ key: 'settings:list' })
  await ui.press({ key: `setting:${IN_WORDS}` })
  expect(await labels(ui)).toEqual(['previous', 'next', 'list', 'set to on'])
  await ui.press({ key: `set:${IN_WORDS}:0` })
  await clock.advance(5_000)
  await clock.advance(1)
  // A setting of that name in another file is not this machine's switch: nothing turns it on.
  await ui.press({ key: 'settings:list' })
  await ui.press({ key: `setting:${OF_THE_STORE}` })
  expect(await labels(ui)).toEqual(['previous', 'list'])

  expect(fake.settingCalls().filter(call => call[1] === 'set')).toEqual([
    ['settings', 'set', '--', 'curation.paused', 'true'],
    ['settings', 'set', '--', 'sessions.propose', 'on'],
  ])
  expect(settings.changedWith).toEqual([INSIDE_A_SESSION, INSIDE_A_SESSION])
  await ui.unmount()
})

test('the settings of a file that could not be read are listed as not read, with why, and nothing to press', async ($, on) => {
  // Covers: B197
  const { fake, settings } = world()
  settings.notRead = { 'profile.json': 'no profile.json in the store yet' }
  settings.curates = null
  for (const at of [LANGUAGE, CUSTOMERS]) {
    Object.assign(settings.entries[at] ?? {}, { read: false, value: null, shows: null })
  }
  const { clock } = await start($, on, fake)

  const ui = await openList($, clock)

  const shown = await texts(ui)
  // Whether this machine curates is not known without the store: nothing says that it does not.
  expect(shown).not.toContain(DOES_NOT_CURATE)
  expect(shown.slice(shown.indexOf('The owner, for every machine'))).toEqual([
    'The owner, for every machine',
    'not read: no profile.json in the store yet',
    'Language: not read',
    'Customers: not read',
  ])
  await ui.press({ key: `setting:${LANGUAGE}` })
  expect(await texts(ui)).toContain('now: not read')
  expect(await texts(ui)).toContain('not read: no profile.json in the store yet')
  expect(await buttons(ui)).toEqual([...walk(LANGUAGE)])
  await ui.unmount()
})

test('on a machine that does not curate, the list and the cards of the curation settings say so', async ($, on) => {
  // Covers: B197
  const { fake, settings } = world()
  settings.curates = false
  const { clock } = await start($, on, fake)

  const ui = await openList($, clock)

  expect((await texts(ui)).slice(1, 3)).toEqual(['This machine', DOES_NOT_CURATE])
  expect((await ui.findAll({ type: 'Text', text: 'Curation paused: off' }))[0]?.props['dimColor']).toBe(true)
  expect((await ui.findAll({ type: 'Text', text: 'Sessions hand in proposals: off' }))[0]?.props['dimColor']).not.toBe(true)
  await ui.press({ key: `setting:${PAUSED}` })
  expect(await texts(ui)).toContain('This machine does not curate.')
  await ui.press({ key: nextOf(PAUSED) })
  expect(await texts(ui)).not.toContain('This machine does not curate.')
  await ui.unmount()
})

test('while one change is written, no card offers a switch, and the list says what is under way', async ($, on) => {
  // Covers: B198
  const { fake } = world()
  fake.delayMs = args => (args[0] === 'settings' && args[1] === 'set' ? 3_000 : 0)
  const { clock } = await start($, on, fake)
  const ui = await openCard($, clock, MODEL)

  await ui.press({ key: `set:${MODEL}:1` })
  await clock.advance(5_000)

  // Being written: undo is gone, and the card says what is under way.
  expect(await buttons(ui)).toEqual([...walk(MODEL)])
  expect(await texts(ui)).toContain('setting curation.model to sonnet…')
  await ui.press({ key: nextOf(MODEL) })
  expect(await texts(ui)).toContain('A change of curation.model is under way.')
  expect(await buttons(ui)).toEqual([...walk(PAUSED)])
  await ui.press({ key: 'settings:list' })
  expect((await texts(ui)).slice(0, 2)).toEqual(['Settings', 'A change of curation.model is under way.'])

  await clock.advance(3_000)
  await clock.advance(1)
  expect(await texts(ui)).toContain('Model of curation: sonnet')
  expect(await texts(ui)).not.toContain('A change of curation.model is under way.')
  await ui.press({ key: `setting:${PAUSED}` })
  expect(await labels(ui)).toEqual(['previous', 'next', 'list', 'turn on'])
  await ui.unmount()
})

test('leaving the card within the five seconds takes the press back, whichever way the card is left', async ($, on) => {
  // Covers: B198
  const { fake } = world()
  const { clock } = await start($, on, fake)
  const ui = await openCard($, clock, PAUSED)

  // Each way out of the card, with the button that leads back to it.
  const ways: [string, string][] = [
    [nextOf(PAUSED), previousOf(PROPOSE)],
    [previousOf(PAUSED), nextOf(MODEL)],
    ['settings:list', `setting:${PAUSED}`],
  ]
  for (const [leave, back] of ways) {
    await ui.press({ key: `set:${PAUSED}:0` })
    expect(await buttons(ui)).toContain('settings:undo')
    await ui.press({ key: leave })
    // Nothing waits where nobody could take it back: no card and no list says a change is under way.
    expect((await texts(ui)).some(text => text.includes('under way') || text.includes('turning'))).toBe(false)
    await clock.advance(10_000)
    await ui.press({ key: back })
    expect(await labels(ui)).toEqual(['previous', 'next', 'list', 'turn on'])
  }

  expect(fake.settingCalls()).toEqual([LIST])
  await ui.unmount()
})

test('a change being written goes on when the settings are left, and a view opened meanwhile waits for it', async ($, on) => {
  // Covers: B198
  const { fake, settings } = world()
  fake.delayMs = args => (args[0] === 'settings' && args[1] === 'set' ? 3_000 : 0)
  const { clock } = await start($, on, fake)
  const ui = await openCard($, clock, MODEL)
  await ui.press({ key: `set:${MODEL}:1` })
  await clock.advance(5_000)

  await ui.press({ key: 'settings:list' })
  await ui.press({ key: 'back' })
  await ui.press({ key: 'show:settings' })
  await clock.advance(1)

  // The list of the new opening was read while the write was under way: it says so, and offers no switch.
  expect(await texts(ui)).toContain('A change of curation.model is under way.')
  await ui.press({ key: `setting:${PAUSED}` })
  expect(await buttons(ui)).toEqual([...walk(PAUSED)])

  settings.refuses = null
  await clock.advance(3_000)
  await clock.advance(1)

  // The write ended: the view that is open now reads again and offers its switches.
  expect(fake.settingCalls().filter(call => call[1] === 'set')).toEqual([['settings', 'set', '--', 'curation.model', 'sonnet']])
  expect(await labels(ui)).toEqual(['previous', 'next', 'list', 'turn on'])
  await ui.press({ key: previousOf(PAUSED) })
  expect(await texts(ui)).toContain('now: sonnet')
  await ui.unmount()
})

test('what the command refused after the view was opened anew stands on the card there', async ($, on) => {
  // Covers: B198
  const { fake, settings } = world()
  fake.delayMs = args => (args[0] === 'settings' && args[1] === 'set' ? 3_000 : 0)
  settings.refuses = 'the store cannot be reached'
  const { clock } = await start($, on, fake)
  const ui = await openCard($, clock, LANGUAGE)
  await ui.press({ key: `set:${LANGUAGE}:0` })
  await clock.advance(5_000)

  await typed($, 'm2b-settings')
  await clock.advance(3_001)
  await ui.press({ key: `setting:${LANGUAGE}` })

  expect(await texts(ui)).toContain('not changed: the store cannot be reached')
  await ui.unmount()
})

test('a list that cannot be read again after a change stays as it was read, with the trouble beside it', async ($, on) => {
  // Covers: B197
  const { fake, settings } = world()
  const { clock } = await start($, on, fake)
  const ui = await openCard($, clock, PAUSED)
  await ui.press({ key: `set:${PAUSED}:0` })
  settings.listFails = 'the store cannot be reached'

  await clock.advance(5_000)
  await clock.advance(1)

  // The card keeps its way on, and says that what it shows is from before.
  expect(await texts(ui)).toContain('m2b could not read its settings again: the store cannot be reached')
  expect(await texts(ui)).toContain('now: off')
  expect(await buttons(ui)).toEqual([...walk(PAUSED), `set:${PAUSED}:0`])
  await ui.press({ key: 'settings:list' })
  expect((await texts(ui)).slice(0, 2)).toEqual(['Settings', 'm2b could not read its settings again: the store cannot be reached'])
  expect((await buttons(ui))[0]).toBe('back')
  await ui.unmount()
})

test('a card whose place the list no longer has falls back to the list, with the way back', async ($, on) => {
  // Covers: B197
  const { fake, settings } = world()
  const { clock } = await start($, on, fake)
  const ui = await openCard($, clock, LANGUAGE)
  await ui.press({ key: `set:${LANGUAGE}:0` })
  // The core that answers next lists fewer settings, as after an update of m2b in another session.
  settings.entries = settings.entries.slice(0, PROPOSE)

  await clock.advance(5_000)
  await clock.advance(1)

  expect((await texts(ui)).slice(0, 2)).toEqual(['Settings', 'This machine'])
  expect(await buttons(ui)).toEqual(['back', 'setting:0', 'setting:1', 'setting:2', 'setting:3'])
  await ui.unmount()
})

test('a press the list no longer offers when its five seconds are over is dropped, and the card shows what is true', async ($, on) => {
  // Covers: B198
  const { fake, settings } = world()
  let isListSlow = false
  fake.delayMs = args => (isListSlow && args[0] === 'settings' && args[1] === '--json' ? 4_000 : 0)
  const { clock } = await start($, on, fake)
  const ui = await openCard($, clock, MODEL)
  await ui.press({ key: `set:${MODEL}:1` })
  // Another session pauses the curation meanwhile; the list read after the change is slow to answer.
  Object.assign(settings.entries[PAUSED] ?? {}, { value: true, shows: 'on' })
  isListSlow = true
  await clock.advance(5_000)

  // The change is over in the view at once, before the list has answered.
  expect((await texts(ui)).some(shown => shown.includes('setting curation.model'))).toBe(false)
  // The card still shows the list from before, and takes the press.
  await ui.press({ key: nextOf(MODEL) })
  expect(await texts(ui)).toContain('now: off')
  await ui.press({ key: `set:${PAUSED}:0` })
  expect(await buttons(ui)).toContain('settings:undo')
  await clock.advance(5_001)
  await clock.advance(1)

  expect(await texts(ui)).toContain('now: on')
  expect(await labels(ui)).toEqual(['previous', 'next', 'list', 'turn off'])
  expect(fake.settingCalls().filter(call => call[1] === 'set')).toEqual([['settings', 'set', '--', 'curation.model', 'sonnet']])
  await ui.unmount()
})

test('the change is handed to m2b as one made inside a session, whatever the mod itself inherited', async ($, on) => {
  // Covers: B198
  const { fake, settings } = world()
  const { clock } = await start($, on, fake)
  const ui = await openCard($, clock, PAUSED)

  await ui.press({ key: `set:${PAUSED}:0` })
  await clock.advance(5_000)

  expect(settings.changedWith).toEqual([INSIDE_A_SESSION])
  await ui.unmount()
})

test('leaving the settings within the five seconds takes the press back', async ($, on) => {
  // Covers: B198
  const { fake } = world()
  const { clock } = await start($, on, fake)
  const ui = await openCard($, clock, PAUSED)

  await ui.press({ key: `set:${PAUSED}:0` })
  await ui.press({ key: 'settings:list' })
  await ui.press({ key: 'back' })
  await clock.advance(10_000)

  expect(await texts(ui)).toContain('In this session')
  expect(fake.settingCalls()).toEqual([LIST])
  await ui.unmount()
})

test('a command that turns the pane to another view within the five seconds takes the press back too', async ($, on) => {
  // Covers: B198
  const { fake } = world()
  const { clock } = await start($, on, fake)
  const ui = await openCard($, clock, PAUSED)

  await ui.press({ key: `set:${PAUSED}:0` })
  await typed($, 'm2b-review')
  await clock.advance(10_000)

  expect(fake.settingCalls()).toEqual([LIST])
  // Opened again, the settings are read anew and the switch is as it was.
  await typed($, 'm2b-settings')
  await clock.advance(1)
  await ui.press({ key: `setting:${PAUSED}` })
  expect(await labels(ui)).toEqual(['previous', 'next', 'list', 'turn on'])
  expect(fake.settingCalls()).toEqual([LIST, LIST])
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
  await ui.press({ key: `setting:${PATH}` })
  expect(await texts(ui)).toContain(`now: ${NOTES}`)
  await ui.press({ key: nextOf(PATH) })
  await ui.press({ key: `set:${MODEL}:1` })
  await clock.advance(5_000)
  await clock.advance(1)
  await ui.press({ key: 'settings:list' })
  await ui.press({ key: 'back' })

  const kept = writes.join('\n')
  expect(kept).toContain('"kind":"settings"')
  for (const held of [NOTES, 'tower-1', '2 customers', '3 named', 'markdown', 'sonnet', 'haiku', 'Store folder']) {
    expect(kept).not.toContain(held)
    expect(answer.text).not.toContain(held)
  }
  await ui.unmount()
})

test('the command takes no value: whatever is typed after it, it only opens the list', async ($, on) => {
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

test('a core from before the command, one that fails and one that answers something else are each said in the list', async ($, on) => {
  // Covers: B197
  const olderCore = new FakeM2b()
  const { clock } = await start($, on, olderCore)
  const ui = await openList($, clock)
  expect(await texts(ui)).toEqual([
    'Settings',
    'm2b could not read its settings: the installed m2b is older than this band; update m2b, then run /reload-plugins',
  ])
  expect(await buttons(ui)).toEqual(['back'])
  await ui.unmount()

  expect(parseSettings('no json')).toEqual({ state: 'failed', error: 'm2b answered something other than its settings' })
  for (const other of [[], { settings: 'none' }, { settings: [{ key: 'x' }], curates: true, not_read: {} }, { settings: catalog(), curates: 'yes', not_read: {} }, { settings: [], curates: true, not_read: {} }, { settings: [{ ...catalog()[0], read: 'yes' }], curates: true, not_read: {} }, { settings: catalog(), curates: true, not_read: { 'store.json': 7 } }]) {
    expect(parseSettings(JSON.stringify(other)).state).toBe('failed')
  }
  expect(parseSettings(JSON.stringify({ settings: catalog(), curates: null, not_read: {} })).state).toBe('read')
})

test('a list that could not be read says why in the words of the command', async ($, on) => {
  // Covers: B197
  const { fake, settings } = world()
  settings.listFails = 'not set up: no machine config'
  const { clock } = await start($, on, fake)

  const ui = await openList($, clock)

  expect(await texts(ui)).toEqual(['Settings', 'm2b could not read its settings: not set up: no machine config'])
  await ui.unmount()
})

test('a close by the person leads from a card to the list, from the list to the start view, and not past the list on a key pressed twice', () => {
  // Covers: B197
  const list: PaneView = { kind: 'settings', press: 'p-1', at: null, drawn: 3 }
  const card: PaneView = { ...list, at: 4 }

  expect(listOf(card)).toEqual({ ...card, at: null })
  expect(listOf(list)).toBeNull()
  expect(listOf({ kind: 'review' })).toBeNull()
  expect(listOf(null)).toBeNull()

  expect(afterBack(card, true, false)).toBe('list')
  expect(afterBack(card, true, true)).toBe('list')
  expect(afterBack(list, false, false)).toBe('start')
  // Right after the close that led to the list, the same key again stays there.
  expect(afterBack(list, false, true)).toBe('stay')
  // A card whose place the list no longer has is drawn as the list, and is left like it.
  expect(afterBack(card, false, false)).toBe('start')
  expect(afterBack(card, false, true)).toBe('stay')
  expect(afterBack({ kind: 'review' }, false, true)).toBe('start')
  expect(afterBack(null, false, true)).toBe('start')
})

test('a reload of the mod, which starts the session again, leaves the pane on its start view', async ($, on) => {
  // Covers: B197
  const { fake } = world()
  const { clock } = await start($, on, fake)
  const ui = await openCard($, clock, PATH)
  expect(await texts(ui)).toContain(`now: ${NOTES}`)

  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await clock.advance(1)

  const shown = await texts(ui)
  expect(shown).toContain('In this session')
  expect(shown).not.toContain(`now: ${NOTES}`)
  await ui.unmount()
})

test('in a pane as narrow as a dock gets, a row is the title and below it the value, and a card wraps', async ($, on) => {
  // Covers: B197
  const { fake } = world()
  const { clock } = await start($, on, fake)

  const ui = await openList($, clock, 24)

  const shown = await texts(ui)
  expect(shown.slice(shown.indexOf('Store folder'), shown.indexOf('Store folder') + 2)).toEqual(['Store folder', NOTES])
  expect((await ui.findAll({ type: 'Text', text: NOTES }))[0]?.props['wrap']).toBe('wrap')
  await ui.press({ key: `setting:${PATH}` })
  for (const text of ['Store folder', `now: ${NOTES}`, 'What store.path does.', 'change: m2b config set store.path <folder>']) {
    expect((await ui.findAll({ type: 'Text', text }))[0]?.props['wrap']).toBe('wrap')
  }
  expect(await buttons(ui)).toEqual([...walk(PATH)])
  // Three buttons side by side are wider than 24 columns: `list` stands below the other two.
  const boxes = async (): Promise<string[]> => (await ui.findAll({ type: 'Box' })).map(box => String(box.key))
  expect(await boxes()).toContain('row:walk')
  expect(await boxes()).not.toContain('row:nav')
  await ui.unmount()
  const wide = await $.ui.mount({ ...pane(PANE, 41), surface: 'terminal' })
  expect((await wide.findAll({ type: 'Box' })).map(box => String(box.key))).toContain('row:nav')
  await wide.unmount()
})

test('a text of the core is drawn as one plain line', async ($, on) => {
  // Covers: B197
  const { fake, settings } = world()
  const escape = String.fromCharCode(0x1b)
  Object.assign(settings.entries[PATH] ?? {}, { shows: `/home/alex/No${escape}[2Jtes\nforged: on${' '.repeat(60)}Language: fr` })
  const { clock } = await start($, on, fake)

  const ui = await openCard($, clock, PATH)

  // A run of spaces would wrap into what reads as a row of its own.
  expect(await texts(ui)).toContain('now: /home/alex/Notes forged: on Language: fr')
  await ui.unmount()
})

/** The list as the module holds it once m2b answered, for the tests of what the module keeps. */
function readLook(entries: Entry[] = catalog()) {
  return parseSettings(JSON.stringify({ settings: entries, curates: true, not_read: {} }))
}

/** Fills the look of an opening as the answer to a read just started for it. */
function fill(press: string, look: ReturnType<typeof parseSettings>): boolean {
  return fillSettings(press, look, askSettings(press) ?? -1)
}

function settingsOf(entries: Entry[] = catalog()): Setting[] {
  const look = readLook(entries)
  return look.state === 'read' ? look.catalog.settings : []
}

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

  forgetSettingsUnless({ kind: 'settings', press: 'first', at: 2, drawn: 1 })
  expect(holdsSettings()).toBe(true)
  forgetSettingsUnless({ kind: 'settings', press: 'second', at: null, drawn: 0 })
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
  fill('open', readLook())

  expect(showsCard({ kind: 'settings', press: 'open', at: 3, drawn: 0 }, heldSettings('open'))).toBe(true)
  expect(showsCard({ kind: 'settings', press: 'open', at: null, drawn: 0 }, heldSettings('open'))).toBe(false)
  expect(showsCard({ kind: 'settings', press: 'open', at: 99, drawn: 0 }, heldSettings('open'))).toBe(false)
  expect(showsCard({ kind: 'settings', press: 'other', at: 3, drawn: 0 }, heldSettings('other'))).toBe(false)
  forgetSettingsUnless(null)
})

test('a card offers every value of its switch but the one set, and the one that turns handing in on only where the client names itself the terminal, the desktop app or VS Code', () => {
  // Covers: B198, B199
  const settings = settingsOf()

  for (const surface of OFFERED_THE_TURN_ON) {
    expect(settings.map(setting => offered(setting, surface))).toEqual([[], [], [1], [0], [0], [], [], [], [0], []])
  }
  for (const surface of ['mobile', 'watch']) {
    expect(settings.map(setting => offered(setting, surface))).toEqual([[], [], [1], [0], [], [], [], [], [0], []])
    // However a core spells the value that turns it on.
    expect(offered({ ...(settings[PROPOSE] as Setting), choices: ['true', 'false'], value: 'false' }, surface)).toEqual([])
    expect(offered({ ...(settings[PROPOSE] as Setting), value: true }, surface)).toEqual([1])
  }
  expect(offered({ ...(settings[PROPOSE] as Setting), choices: ['true', 'false'], value: 'false' }, 'terminal')).toEqual([0])
  // A setting of that name in the store's file or the owner's is not this machine's switch.
  expect(offered({ ...(settings[PROPOSE] as Setting), scope: 'store' }, 'terminal')).toEqual([])
  expect(offered({ ...(settings[PAUSED] as Setting), kind: 'shown' }, 'terminal')).toEqual([])
  expect(offered({ ...(settings[PAUSED] as Setting), isRead: false }, 'terminal')).toEqual([])
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
  Object.assign(moved[PROPOSE] ?? {}, inStore)
  fill('open', readLook(moved))
  expect(startWriting('t-5')).toBeNull()
  expect(heldSettings('open').change).toBeNull()
  forgetSettingsUnless(null)
})

test('a press is noted only where the card offers it, one at a time, and written as the setting and the value it named', () => {
  // Covers: B198
  beginSettings('open')
  fill('open', readLook())

  // The value that is set, turning handing in on in the mobile app, a place the list does not have, another opening.
  expect(beginChange('open', PAUSED, 1, 't-0', 'terminal')).toBe(false)
  expect(beginChange('open', PROPOSE, 0, 't-0', 'mobile')).toBe(false)
  expect(beginChange('open', 99, 0, 't-0', 'terminal')).toBe(false)
  expect(beginChange('other', PAUSED, 0, 't-0', 'terminal')).toBe(false)
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
  const twice = [entry('curation.paused', 'Paused elsewhere', { ...ofOwner, kind: 'shown' }), ...catalog()]
  fill('later', readLook(twice))
  expect(beginChange('later', PAUSED + 1, 0, 't-4', 'terminal')).toBe(true)
  expect(startWriting('t-4')).toEqual({ key: 'curation.paused', argument: 'true', isTurningHandingInOn: false })
  endChange('t-4', null)
  forgetSettingsUnless(null)
})

// What the kit shows of the focus: which button the mod asks it for, and that the button is drawn.
// A move the mod asks for is not handed to a test's hook, and fails in the kit: every test of this
// file that presses a button of the settings runs with a move that failed, as where the pane does
// not hold the keyboard.

test('the focus goes to the button that leads the way the card was reached, at either end of the list to the one that leads back, and never to a switch', () => {
  // Covers: B200
  const count = catalog().length
  const last = count - 1

  // Reached by `next`, or opened from its row of the list.
  expect(focusKeyOfCard(0, count, 'forward')).toBe(nextOf(0))
  expect(focusKeyOfCard(PAUSED, count, 'forward')).toBe(nextOf(PAUSED))
  expect(focusKeyOfCard(last - 1, count, 'forward')).toBe(nextOf(last - 1))
  expect(focusKeyOfCard(last, count, 'forward')).toBe(previousOf(last))
  // Reached by `previous`.
  expect(focusKeyOfCard(last, count, 'back')).toBe(previousOf(last))
  expect(focusKeyOfCard(PAUSED, count, 'back')).toBe(previousOf(PAUSED))
  expect(focusKeyOfCard(1, count, 'back')).toBe(previousOf(1))
  expect(focusKeyOfCard(0, count, 'back')).toBe(nextOf(0))
  // A list of two settings, and one of a single setting, whose card leads nowhere but to the list.
  expect([focusKeyOfCard(0, 2, 'forward'), focusKeyOfCard(1, 2, 'forward'), focusKeyOfCard(0, 2, 'back'), focusKeyOfCard(1, 2, 'back')]).toEqual([
    nextOf(0),
    previousOf(1),
    nextOf(0),
    previousOf(1),
  ])
  expect([focusKeyOfCard(0, 1, 'forward'), focusKeyOfCard(0, 1, 'back')]).toEqual(['settings:list', 'settings:list'])
  for (let at = 0; at < count; at += 1) {
    for (const reached of ['forward', 'back'] as const) {
      expect(focusKeyOfCard(at, count, reached).startsWith('set:')).toBe(false)
    }
  }
})

test('the focus is asked for a card of the list held for the opening, as that list is now, and for no other', () => {
  // Covers: B200
  beginSettings('open')
  // Nothing is read yet: no card is drawn that could take it.
  expect(focusKeyOfHeldCard('open', PAUSED, 'forward')).toBeNull()
  fill('open', readLook())

  expect(focusKeyOfHeldCard('open', PAUSED, 'forward')).toBe(nextOf(PAUSED))
  expect(focusKeyOfHeldCard('open', PAUSED, 'back')).toBe(previousOf(PAUSED))
  expect(focusKeyOfHeldCard('open', CUSTOMERS, 'forward')).toBe(previousOf(CUSTOMERS))
  expect(focusKeyOfHeldCard('open', MACHINE_ID, 'back')).toBe(nextOf(MACHINE_ID))
  expect(focusKeyOfHeldCard('open', catalog().length, 'forward')).toBeNull()
  expect(focusKeyOfHeldCard('other', PAUSED, 'forward')).toBeNull()
  // Read again, the list ends at this card: it is the last one now.
  fill('open', readLook(catalog().slice(0, PAUSED + 1)))
  expect(focusKeyOfHeldCard('open', PAUSED, 'forward')).toBe(previousOf(PAUSED))
  forgetSettingsUnless(null)
  expect(focusKeyOfHeldCard('open', PAUSED, 'forward')).toBeNull()
})

test('the button the focus is asked for is drawn: on every card whichever way it was reached, the row of every card on the list, and undo after a press', async ($, on) => {
  // Covers: B200
  const { fake } = world()
  const { clock } = await start($, on, fake)
  const count = catalog().length

  for (const columns of [80, 24]) {
    const ui = await openList($, clock, columns)
    const rows = await buttons(ui)
    const walked: string[] = []
    for (let at = 0; at < count; at += 1) {
      expect(rows).toContain(rowKey(at))
      if (at === 0) {
        await ui.press({ key: rowKey(0) })
      }
      const drawn = await buttons(ui)
      expect(drawn).toContain(focusKeyOfCard(at, count, 'forward'))
      expect(drawn).toContain(focusKeyOfCard(at, count, 'back'))
      walked.push(...drawn.filter(key => key.startsWith('settings:previous') || key.startsWith('settings:next')))
      if (at < count - 1) {
        await ui.press({ key: nextOf(at) })
      }
    }
    // A key of `previous` or `next` is drawn on one card alone: asked for from the card before, it is one not drawn yet.
    expect(new Set(walked).size).toBe(walked.length)
    expect(walked.length).toBe(2 * (count - 1))
    await ui.press({ key: 'settings:list' })
    await ui.press({ key: rowKey(PAUSED) })
    expect(await buttons(ui)).not.toContain(SETTINGS_UNDO)
    await ui.press({ key: `set:${PAUSED}:0` })
    expect(await buttons(ui)).toContain(SETTINGS_UNDO)
    await ui.press({ key: SETTINGS_UNDO })
    expect(await buttons(ui)).toContain(focusKeyOfCard(PAUSED, count, 'forward'))
    await ui.unmount()
  }
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

const PROBE = 'settings-alone'

test('each button that leads on says where it leads and how the card is reached: a row and next forward, previous back, list from the card it stands on', async ($, on) => {
  // Covers: B200
  // The view drawn by a hook of the test's own, with actions that only note what they are handed.
  const handed: string[] = []
  const noting: SettingsActions = {
    open: async (at: number, reached: Reached) => void handed.push(`open ${at} ${reached}`),
    toList: async (from: number) => void handed.push(`list from ${from}`),
    choose: async () => undefined,
    undo: async () => undefined,
  }
  let at: number | null = null
  on('ui.render', { component: 'Pane', requestId: PROBE }, ($, e) => {
    const view = { kind: 'settings', press: 'open', at, drawn: 0 } as const
    return settingsPane($, e, view, heldSettings('open'), noting, e.props.bodyColumns)
  })
  beginSettings('open')
  fill('open', readLook())
  const last = catalog().length - 1

  for (const columns of [80, 24]) {
    handed.length = 0
    at = null
    const list = await $.ui.mount({ ...pane(PROBE, columns), plugin: 'test', surface: 'terminal' })
    await list.press({ key: rowKey(PAUSED) })
    await list.press({ key: rowKey(last) })
    await list.unmount()
    at = PAUSED
    const card = await $.ui.mount({ ...pane(PROBE, columns), plugin: 'test', surface: 'terminal' })
    await card.press({ key: previousOf(PAUSED) })
    await card.press({ key: nextOf(PAUSED) })
    await card.press({ key: 'settings:list' })
    await card.unmount()

    expect(handed).toEqual([
      `open ${PAUSED} forward`,
      `open ${last} forward`,
      `open ${PAUSED - 1} back`,
      `open ${PAUSED + 1} forward`,
      `list from ${PAUSED}`,
    ])
  }
  forgetSettingsUnless(null)
})
