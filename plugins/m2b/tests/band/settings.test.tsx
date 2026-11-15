import { expect, test } from 'claude-code/testing'
import type { CommandRunResult, ProcessRunResult } from 'claude-code'
import type { Engine } from 'claude-code/testing'

import {
  afterBack,
  askSettings,
  beginChange,
  beginSettings,
  dropWaitingChange,
  endChange,
  fillSettings,
  forgetSettingsUnless,
  heldSettings,
  holdsSettings,
  listOf,
  offered,
  openSettings,
  parseSettings,
  showsCard,
  startWriting,
  undoChange,
} from '../../hooks/settings'
import type { Setting } from '../../hooks/settings'
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
async function openList($: Engine, clock: Clock, columns = 80) {
  await typed($, 'm2b-settings')
  await clock.advance(1)
  return $.ui.mount({ ...pane(PANE, columns), surface: 'terminal' })
}

/** The card of the setting at `at`, opened from the list. */
async function openCard($: Engine, clock: Clock, at: number, columns = 80) {
  const ui = await openList($, clock, columns)
  await ui.press({ key: `setting:${at}` })
  return ui
}

type Mounted = Awaited<ReturnType<typeof openList>>

async function buttons(ui: Mounted): Promise<string[]> {
  return (await ui.findAll({ type: 'Button' })).map(button => String(button.key))
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
  await typed($, 'm2b')
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
  expect(await buttons(ui)).toEqual(['settings:previous', 'settings:next', 'settings:list', `set:${PAUSED}:0`])
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

  expect(await buttons(ui)).toEqual(['settings:next', 'settings:list'])
  for (let at = 0; at < catalog().length; at += 1) {
    walked.push((await texts(ui))[2] ?? '')
    if (at < catalog().length - 1) {
      await ui.press({ key: 'settings:next' })
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
  expect(await buttons(ui)).toEqual(['settings:previous', 'settings:list'])
  await ui.press({ key: 'settings:previous' })
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
  expect(await buttons(ui)).toEqual(['settings:previous', 'settings:next', 'settings:list', 'settings:undo'])
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
  await ui.press({ key: 'settings:previous' })
  expect((await texts(ui)).some(text => text.startsWith('not changed'))).toBe(false)
  await ui.press({ key: 'settings:next' })
  expect(await texts(ui)).toContain(`not changed: ${settings.refuses}`)
  // The next press on the card is another try; what the last one met is gone.
  settings.refuses = null
  await ui.press({ key: `set:${LANGUAGE}:0` })
  expect((await texts(ui)).some(text => text.startsWith('not changed'))).toBe(false)
  await ui.unmount()
})

test('the switch that lets sessions hand in is not turned on from the pane: its card names the command', async ($, on) => {
  // Covers: B197
  const { fake, settings } = world()
  const { clock } = await start($, on, fake)
  const ui = await openCard($, clock, PROPOSE)

  expect(await texts(ui)).toContain(IN_YOUR_OWN_TERMINAL)
  expect(await buttons(ui)).toEqual(['settings:previous', 'settings:next', 'settings:list'])
  await ui.unmount()

  // Turned on already, it can be turned off here: that way no session gains anything.
  Object.assign(settings.entries[PROPOSE] ?? {}, { value: true, shows: 'on' })
  const on2 = await openCard($, clock, PROPOSE)
  expect(await labels(on2)).toEqual(['previous', 'next', 'list', 'turn off'])
  expect(await texts(on2)).not.toContain(IN_YOUR_OWN_TERMINAL)
  await on2.unmount()
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
  expect(await buttons(ui)).toEqual(['settings:previous', 'settings:next', 'settings:list'])
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
  await ui.press({ key: 'settings:next' })
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
  expect(await buttons(ui)).toEqual(['settings:previous', 'settings:next', 'settings:list'])
  expect(await texts(ui)).toContain('setting curation.model to sonnet…')
  await ui.press({ key: 'settings:next' })
  expect(await texts(ui)).toContain('A change of curation.model is under way.')
  expect(await buttons(ui)).toEqual(['settings:previous', 'settings:next', 'settings:list'])
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

  for (const leave of ['settings:next', 'settings:previous', 'settings:list']) {
    await ui.press({ key: `set:${PAUSED}:0` })
    expect(await buttons(ui)).toContain('settings:undo')
    await ui.press({ key: leave })
    // Nothing waits where nobody could take it back: no card and no list says a change is under way.
    expect((await texts(ui)).some(text => text.includes('under way') || text.includes('turning'))).toBe(false)
    await clock.advance(10_000)
    await ui.press({ key: leave === 'settings:list' ? `setting:${PAUSED}` : leave === 'settings:next' ? 'settings:previous' : 'settings:next' })
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
  expect(await buttons(ui)).toEqual(['settings:previous', 'settings:next', 'settings:list'])

  settings.refuses = null
  await clock.advance(3_000)
  await clock.advance(1)

  // The write ended: the view that is open now reads again and offers its switches.
  expect(fake.settingCalls().filter(call => call[1] === 'set')).toEqual([['settings', 'set', '--', 'curation.model', 'sonnet']])
  expect(await labels(ui)).toEqual(['previous', 'next', 'list', 'turn on'])
  await ui.press({ key: 'settings:previous' })
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
  expect(await buttons(ui)).toEqual(['settings:previous', 'settings:next', 'settings:list', `set:${PAUSED}:0`])
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
  await ui.press({ key: 'settings:next' })
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

  expect(settings.changedWith).toEqual([{ CLAUDECODE: '1' }])
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
  await ui.press({ key: 'settings:next' })
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
  expect(await buttons(ui)).toEqual(['settings:previous', 'settings:next', 'settings:list'])
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

test('a card offers every value of its switch but the one set, and never the one that turns handing in on', () => {
  // Covers: B198
  const settings = settingsOf()

  expect(settings.map(offered)).toEqual([[], [], [1], [0], [], [], [], [], [0], []])
  expect(offered({ ...(settings[PAUSED] as Setting), kind: 'shown' })).toEqual([])
  expect(offered({ ...(settings[PAUSED] as Setting), isRead: false })).toEqual([])
  // However a core spells the value that turns it on.
  expect(offered({ ...(settings[PROPOSE] as Setting), choices: ['true', 'false'], value: 'false' })).toEqual([])
  expect(offered({ ...(settings[PROPOSE] as Setting), value: true })).toEqual([1])
})

test('a press is noted only where the card offers it, one at a time, and written as the setting and the value it named', () => {
  // Covers: B198
  beginSettings('open')
  fill('open', readLook())

  // The value that is set, turning handing in on, a place the list does not have, another opening.
  expect(beginChange('open', PAUSED, 1, 't-0')).toBe(false)
  expect(beginChange('open', PROPOSE, 0, 't-0')).toBe(false)
  expect(beginChange('open', 99, 0, 't-0')).toBe(false)
  expect(beginChange('other', PAUSED, 0, 't-0')).toBe(false)
  expect(heldSettings('open').change).toBeNull()

  expect(beginChange('open', PAUSED, 0, 't-1')).toBe(true)
  expect(heldSettings('open').change).toMatchObject({ scope: 'machine', key: 'curation.paused', choice: true, phase: 'waiting' })
  // One at a time.
  expect(beginChange('open', MODEL, 1, 't-2')).toBe(false)
  // Only the press that waits is written, under its own name; another opening does not take it back.
  expect(startWriting('t-2')).toBeNull()
  expect(undoChange('other')).toBe(false)
  // The list was read again meanwhile, in another order: the press still names its setting.
  fill('open', readLook([...catalog()].reverse()))
  expect(startWriting('t-1')).toEqual({ key: 'curation.paused', argument: 'true' })
  expect(startWriting('t-1')).toBeNull()
  // Being written, it is no longer taken back, by undo or by leaving.
  expect(undoChange('open')).toBe(false)
  dropWaitingChange()
  forgetSettingsUnless(null)
  expect(heldSettings('open').change?.phase).toBe('writing')

  // It ends under its own name, and the refusal is kept for the view that is open then.
  beginSettings('later')
  fill('later', readLook())
  expect(beginChange('later', MODEL, 1, 't-3')).toBe(false)
  endChange('t-3', 'not this one')
  expect(heldSettings('later').change?.phase).toBe('writing')
  endChange('t-1', 'refused')
  expect(heldSettings('later')).toMatchObject({ change: null, refusal: { scope: 'machine', key: 'curation.paused', line: 'refused' } })
  // The next press clears what the last one met.
  expect(beginChange('later', MODEL, 1, 't-4')).toBe(true)
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
  expect(beginChange('open', PAUSED, 0, 't-1')).toBe(true)
  // Another session turned it on meanwhile.
  fill('open', readLook(turnedOn))
  expect(startWriting('t-1')).toBeNull()
  expect(heldSettings('open').change).toBeNull()

  expect(beginChange('open', MODEL, 1, 't-2')).toBe(true)
  // A list that no longer names the setting.
  fill('open', readLook(catalog().filter(one => one.key !== 'curation.model')))
  expect(startWriting('t-2')).toBeNull()

  fill('open', readLook())
  expect(beginChange('open', MODEL, 1, 't-3')).toBe(true)
  // The view is opened anew: the press that waited in the opening before is taken back.
  beginSettings('later')
  expect(heldSettings('later').change).toBeNull()
  expect(startWriting('t-3')).toBeNull()

  // Two files can have a setting of one name: a press names the file with it.
  const twice = [entry('curation.paused', 'Paused elsewhere', { ...ofOwner, kind: 'shown' }), ...catalog()]
  fill('later', readLook(twice))
  expect(beginChange('later', PAUSED + 1, 0, 't-4')).toBe(true)
  expect(startWriting('t-4')).toEqual({ key: 'curation.paused', argument: 'true' })
  endChange('t-4', null)
  forgetSettingsUnless(null)
})
