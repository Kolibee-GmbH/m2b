import { expect, test } from 'claude-code/testing'
import { opening } from '../../hooks/look'
import { topicFactKey } from '../../hooks/topic'
import type { CommandRunResult } from 'claude-code'
import type { Engine } from 'claude-code/testing'

import { BACK_TO_THE_TOPIC_KEY, backTabKey, focusKeyAfterTab } from '../../hooks/pane-tabs'
import type { Shown, TabId } from '../../hooks/pane-tabs'
import {
  CURATE_NOW,
  FakeM2b,
  FakeSettings,
  NOTES,
  buttonsAt,
  fakeSetting,
  inView,
  lookOf,
  onOff,
  pane,
  partLines,
  pressTab,
  shownTab,
  shownTabs,
  start,
  texts,
  viewButtons,
} from './harness'
import type { ShownTab } from './harness'

const PANE = 'm2b'
const UNDO_MS = 5_000
const DANA = 'a1a1a1a1a1a1'
const LADDER = 'b2b2b2b2b2b2'
const SHED = 'c3c3c3c3c3c3'
const KIM = "Kim Lee leads Northwind's IT"
/** A topic's name of 25 characters, and the 20 its tab and its button show of it. */
const LONG_NAME = 'Riverside Community Choir'
const LONG_NAME_CUT = 'Riverside Community…'
const LIST = ['settings', '--json']
const TODOS = ['todos', '--json']
const LADDER_TASK = 'Return the ladder to Sam'
const DANA_FACT = 'Dana: my sister, birthday on 3 March'
const DANA_LINE = 'My sister. Birthday on 3 March.'
const DANA_NOTE = '20261012T081500Z-claude-3f2a.md'
const NOTE_WORDS = 'She starts at Northwind in April.'
const FACTS = ['distillate', 'topics', '--json']

/** The tabs that stay, in the order drawn. */
const TABS: readonly TabId[] = ['overview', 'proposals', 'review', 'tasks', 'facts', 'settings']
const LABELS: Readonly<Record<TabId, string>> = {
  overview: 'Overview',
  proposals: 'Proposals',
  review: 'Review',
  tasks: 'Tasks',
  facts: 'Facts',
  settings: 'Settings',
}

/**
 * Every view of the pane: the six under their tabs, the four under a seventh tab, a folded group
 * of the settings, a topic's lines, a fact's file and a search, and a source a fact rests on under
 * an eighth.
 */
type View = TabId | 'group' | 'topic' | 'fact' | 'search' | 'source'
const VIEWS: readonly View[] = ['overview', 'proposals', 'review', 'tasks', 'facts', 'settings', 'group', 'topic', 'fact', 'search', 'source']
// A test that walks every view and every tab grows with both, and a shared runner takes several
// times a laptop's time for it: one such walk ran past the kit's five seconds there.
const WALK = { timeoutMs: 20_000 }
/** The views that stand under a tab beside the six: a seventh, and for a source an eighth. */
const BESIDE_THE_SIX = ['group', 'topic', 'fact', 'search', 'source'] as const
/** The button of the row the settings keep their folded group behind, which turns the pane to that group. */
const SHOW_GROUP = 'settings:fold:about'
/** Which tab the row marks above each view. */
const SHOWN: Readonly<Record<View, Shown>> = {
  overview: 'overview',
  proposals: 'proposals',
  review: 'review',
  tasks: 'tasks',
  facts: 'facts',
  settings: 'settings',
  group: 'aside',
  topic: 'aside',
  fact: 'aside',
  search: 'aside',
  source: 'aside',
}
/** The label of the tab that marks a view beside the six: the seventh, or above a source the eighth. */
const ASIDE: Readonly<Partial<Record<View, string>>> = { group: 'About this setup', topic: 'Northwind', fact: 'dana', search: 'Search', source: 'note 2026-10-12' }
/** The seventh tab above a source: its fact file, a button that leads back to it. */
const BACK_TO_DANA: ShownTab = { label: 'dana', key: 'tab:fact:in:source' }
const DANA_SHOWN: ShownTab = { label: 'dana', key: 'tab:fact:shown' }
/** A line each view draws and no other does: the review has a part "Waits for you" too, so the overview is told by its part "Today". */
const SAYS: Readonly<Record<View, string>> = {
  overview: 'Today',
  proposals: 'said on 2026-03-12: "Dana runs IT at Northwind"',
  review: 'lint: broken link in a.md',
  tasks: LADDER_TASK,
  // A fact that names its file is drawn as the row that opens it.
  facts: opening(DANA_FACT),
  settings: 'that only inform or are changed by a command',
  group: `Store folder: ${NOTES}`,
  topic: KIM,
  fact: DANA_LINE,
  search: 'memory/dana.md:3',
  source: NOTE_WORDS,
}
/** The command that turns the pane to each view, or to the view a press leads on from: the tasks and the facts have no command, only their tab. */
const COMMANDS: Readonly<Record<View, string>> = {
  overview: 'm2b-pane',
  proposals: 'm2b-proposals',
  review: 'm2b-review',
  tasks: 'm2b-pane',
  facts: 'm2b-pane',
  settings: 'm2b-settings',
  group: 'm2b-settings',
  topic: 'm2b-pane',
  fact: 'm2b-pane',
  search: 'm2b-search',
  source: 'm2b-pane',
}

function typed($: Engine, command: string, args = ''): Promise<CommandRunResult> {
  return $.command.run({ command, args, origin: { kind: 'composer' }, presentation: { isFullscreen: false, columns: 100 } })
}

/**
 * A session with something under every tab: two topics, a candidate, a question and the review,
 * three proposals, an open task, a fact every session starts with, its file and the note it rests
 * on, a hit to search for, and three settings, two to choose and one behind a row.
 */
function fullFake(): FakeM2b {
  const fake = new FakeM2b()
  fake.given = {
    topics: [
      { name: 'Northwind', facts: 1, current: 0 },
      { name: LONG_NAME, facts: 1, current: 0 },
    ],
    atStart: 'whole',
    offUnder: null,
  }
  fake.topicLines = { Northwind: { facts: [KIM], current: [] }, [LONG_NAME]: { facts: ['The choir meets on Wednesdays'], current: [] } }
  fake.candidate('c1', 'Remember? Dana prefers tea')
  fake.question('q1', 'Still current? Planning the trip to Porto')
  fake.review('r1', ['lint: broken link in a.md'])
  fake
    .proposal(DANA, 'Dana is head of IT at Northwind.', 'Dana runs IT at Northwind')
    .proposal(LADDER, 'Call Sam about the ladder.')
    .proposal(SHED, 'The spare key is in the shed.')
  fake.todo('later', 't1', LADDER_TASK, '2026-04-02')
  fake.distillate = { facts: [{ statement: DANA_FACT, file: 'dana.md' }], current: [], topics: [{ name: 'Northwind', facts: 1, current: 0 }] }
  const evidence = { name: DANA_NOTE, state: 'read', day: '2026-10-12', kind: 'note', original_name: null, first_line: 'Dana, my sister.', path: `corpus/2026/10/${DANA_NOTE}`, fetch: null, reason: null }
  fake.sourceAnswer = { name: 'dana.md', kind: 'fact file', path: 'memory/dana.md', title: 'Dana', until: null, lines: [DANA_LINE], earlier: [], evidence: [evidence] }
  fake.viewerAnswers = {
    [DANA_NOTE]: {
      name: DANA_NOTE,
      kind: 'note',
      path: `corpus/2026/10/${DANA_NOTE}`,
      day: '2026-10-12',
      captured: `Dana, my sister.\n${NOTE_WORDS}`,
      added: [],
      original_name: null,
      outline: [],
      original: null,
      original_here: null,
      opens: false,
      not_opened: null,
      file: null,
    },
  }
  fake.searchHits = [{ path: 'memory/dana.md', line: 3, text: 'Dana prefers tea' }]
  fake.onSettings = new FakeSettings([
    fakeSetting('curation.paused', 'Curation paused', 'curation', 1, onOff('curation.paused', false)),
    fakeSetting('sessions.propose', 'Sessions hand in proposals', 'reads', 1, onOff('sessions.propose', false)),
    fakeSetting('store.path', 'Store folder', 'about', 1, { value: NOTES, shows: NOTES }),
  ]).handle
  return fake
}

function mounted($: Engine, columns = 80) {
  return $.ui.mount({ ...pane(PANE, columns), surface: 'terminal' })
}

type Pane = Awaited<ReturnType<typeof mounted>>
type Clock = Awaited<ReturnType<typeof start>>['clock']

/** Turns the pane to `view` from wherever it is: by the view's command and, for the tasks, the facts, a fact's file and its source, a folded group and a topic, the press that shows it. */
async function arrive($: Engine, clock: Clock, ui: Pane, view: View): Promise<void> {
  await typed($, COMMANDS[view], view === 'search' ? 'tea' : '')
  await clock.advance(1)
  if (view === 'tasks') {
    await pressTab(ui, 'tasks')
  }
  if (view === 'facts' || view === 'fact' || view === 'source') {
    await pressTab(ui, 'facts')
  }
  if (view === 'fact' || view === 'source') {
    await ui.press({ key: 'details:0' })
  }
  if (view === 'source') {
    await ui.press({ key: 'show:0' })
  }
  if (view === 'group') {
    await ui.press({ key: SHOW_GROUP })
  }
  if (view === 'topic') {
    await ui.press({ key: 'topic:0' })
  }
}

/** The row of tabs as drawn above the view `shown`: a tab's key names the tab and the view it stands above. */
function rowAbove(shown: Shown, aside?: string, proposals = 'Proposals 3'): ShownTab[] {
  const staying = TABS.map(id => ({
    label: id === 'proposals' ? proposals : LABELS[id],
    key: `tab:${id}:in:${shown}`,
  }))
  return aside === undefined ? staying : [...staying, { label: aside, key: null }]
}

/**
 * The row of tabs above `view` while three proposals wait: above a source the tab of its fact file
 * stands before its own; a fact file's tab, shown, is a button that reads it again.
 */
function rowOver(view: View): ShownTab[] {
  const row = rowAbove(SHOWN[view], ASIDE[view])
  if (view === 'fact') {
    return [...row.slice(0, -1), DANA_SHOWN]
  }
  return view === 'source' ? [...row.slice(0, -1), BACK_TO_DANA, ...row.slice(-1)] : row
}

/** The key of every button the pane draws, the tabs among them. */
async function everyButton(ui: Pane): Promise<string[]> {
  return (await ui.findAll({ type: 'Button' })).map(button => String(button.key))
}

test('above the view the pane starts in stand Overview, Proposals with the number that wait, Review, Tasks, Facts and Settings, each a button', async ($, on) => {
  // Covers: B204
  await start($, on, fullFake())

  const ui = await mounted($)

  expect(await shownTabs(ui)).toEqual([
    { label: 'Overview', key: 'tab:overview:in:overview' },
    { label: 'Proposals 3', key: 'tab:proposals:in:overview' },
    { label: 'Review', key: 'tab:review:in:overview' },
    { label: 'Tasks', key: 'tab:tasks:in:overview' },
    { label: 'Facts', key: 'tab:facts:in:overview' },
    { label: 'Settings', key: 'tab:settings:in:overview' },
  ])
  // The row is the first thing drawn: the view stands below it.
  expect((await ui.findAll({ type: 'Button' }))[0]?.key).toBe('tab:overview:in:overview')
  expect(await shownTab(ui)).toBe('overview')
  expect((await texts(ui))[0]).toBe('Waits for you')
  await ui.unmount()
})

test("the six tabs stand above every view in the same order, each a button; a tab beside them is a text while its view is shown, but a fact file's, a button that reads it again", async ($, on) => {
  // Covers: B204
  const { clock } = await start($, on, fullFake())
  const ui = await mounted($)

  for (const view of VIEWS) {
    await arrive($, clock, ui, view)

    expect(await texts(ui)).toContain(SAYS[view])
    expect(await shownTabs(ui)).toEqual(rowOver(view))
    // No tab is drawn twice: the six are buttons, above a source or its own view the tab of a fact file too.
    expect((await everyButton(ui)).filter(key => key.startsWith('tab:'))).toHaveLength(6 + (view === 'source' || view === 'fact' ? 1 : 0))
  }
  await ui.unmount()
})

test("one of the six shown is a button in the accent, as is a fact file's tab shown, any other tab beside them shown is bold and underlined in the color of m2b's name, and every other tab is a dim button", async ($, on) => {
  // Covers: B204
  const { clock } = await start($, on, fullFake())
  const ui = await mounted($)

  for (const view of ['overview', 'review', 'tasks', 'facts', 'topic', 'fact', 'group', 'source'] as const) {
    await arrive($, clock, ui, view)
    const shown = SHOWN[view]
    const row = await shownTabs(ui)

    if (view === 'fact') {
      const marked = await ui.find({ key: DANA_SHOWN.key ?? '' })
      expect(marked?.props).toMatchObject({ label: ASIDE.fact, variant: 'primary' })
    } else if (shown === 'aside') {
      // The row's one text is the first text the pane draws.
      const [text] = await ui.findAll({ type: 'Text' })
      expect(text?.text).toBe(ASIDE[view])
      expect(text?.props).toMatchObject({ color: 'remember', weight: 'bold', underline: true })
    } else {
      const marked = await ui.find({ key: `tab:${shown}:in:${shown}` })
      expect(marked?.props).toMatchObject({ label: LABELS[shown], variant: 'primary' })
      expect(marked?.props['dimColor']).toBeUndefined()
    }
    for (const tab of row.filter(one => one.key !== null && one.key !== `tab:${shown}:in:${shown}` && one.key !== DANA_SHOWN.key)) {
      const button = await ui.find({ key: tab.key ?? '' })
      expect(button?.type).toBe('Button')
      expect(button?.props['dimColor']).toBe(true)
      expect(button?.props['variant']).toBeUndefined()
    }
  }
  await ui.unmount()
})

const HOTKEYS: Readonly<Record<TabId, string>> = { overview: 'o', proposals: 'p', review: 'r', tasks: 't', facts: 'f', settings: 's' }

test('each of the six tabs has its first letter as its key above every view, a tab beside them none, and no other button of the pane has a key', async ($, on) => {
  // Covers: B315
  const fake = fullFake()
  // The topic's fact names its file, so a fact file opened from the topic has a tab that leads back to it.
  fake.topicLines = { ...fake.topicLines, Northwind: { facts: [KIM], current: [], files: ['dana.md'] } }
  const { clock } = await start($, on, fake)
  const ui = await mounted($)
  const fromTheTopic = async () => {
    await arrive($, clock, ui, 'topic')
    await ui.press({ key: topicFactKey(0) })
  }

  for (const reach of [...VIEWS.map(view => () => arrive($, clock, ui, view)), fromTheTopic]) {
    await reach()
    const [six, beside] = [elementsOfTheRow(await ui.findAll({ type: 'Button' })).slice(0, 6), elementsOfTheRow(await ui.findAll({ type: 'Button' })).slice(6)]

    expect(six.map(button => button.props['hotkey'])).toEqual(TABS.map(id => HOTKEYS[id]))
    // A tab beside the six that leads back, to a fact file above a source or to a topic above its fact file, has no letter.
    expect(beside.map(button => button.props['hotkey'])).toEqual(beside.map(() => undefined))
    expect((await inView(ui, 'Button')).filter(button => button.props['hotkey'] !== undefined).map(button => button.key)).toEqual([])
  }
  // The last view reached is the fact file opened from the topic, under the topic's tab.
  expect((await ui.find({ key: BACK_TO_THE_TOPIC_KEY }))?.props['hotkey']).toBeUndefined()
  await ui.unmount()
})

/** The buttons of the row of tabs, the six and any beside them, in the order drawn. */
function elementsOfTheRow<T extends { key?: string | undefined }>(buttons: T[]): T[] {
  return buttons.filter(button => (button.key ?? '').startsWith('tab:'))
}

test('a press on the tab shown, as Enter on it or its letter does, reads its view again and leaves the pane there', async ($, on) => {
  // Covers: B204, B315
  const fake = fullFake()
  const { clock } = await start($, on, fake)
  const ui = await mounted($)

  for (const to of ['tasks', 'facts', 'settings'] as const) {
    await pressTab(ui, to)
    await clock.advance(1)
    const [lists, todos, facts] = [fake.settingCalls().length, fake.todosCalls().length, fake.factsCalls().length]

    await ui.press({ key: `tab:${to}:in:${to}` })
    await clock.advance(1)

    expect(await shownTab(ui)).toBe(to)
    expect(await texts(ui)).toContain(SAYS[to])
    expect(fake.settingCalls().length - lists).toBe(to === 'settings' ? 1 : 0)
    expect(fake.todosCalls().length - todos).toBe(to === 'tasks' ? 1 : 0)
    expect(fake.factsCalls().length - facts).toBe(to === 'facts' ? 1 : 0)
  }
  // Overview asks again what the session was given, and stays on the overview.
  await pressTab(ui, 'overview')
  await clock.advance(1)
  const asked = fake.looks.length
  await ui.press({ key: 'tab:overview:in:overview' })
  await clock.advance(1)
  expect(await shownTab(ui)).toBe('overview')
  expect(fake.looks.length).toBeGreaterThan(asked)
  await ui.unmount()
})

test('Proposals counts the proposals that wait, as a button and as the tab shown, and says no zero', async ($, on) => {
  // Covers: B204
  const fake = fullFake()
  const { clock } = await start($, on, fake)
  const ui = await mounted($)
  const proposals = async (): Promise<string | undefined> => (await shownTabs(ui))[1]?.label
  expect(await proposals()).toBe('Proposals 3')

  await pressTab(ui, 'proposals')
  expect(await shownTabs(ui)).toEqual(rowAbove('proposals'))
  await ui.press({ key: `keep:${DANA}` })
  await clock.advance(UNDO_MS)
  expect(fake.answers()).toEqual([['proposals', 'keep', DANA]])
  expect(await shownTabs(ui)).toEqual(rowAbove('proposals', undefined, 'Proposals 2'))

  await pressTab(ui, 'overview')
  expect(await proposals()).toBe('Proposals 2')
  await ui.press({ key: 'topic:0' })
  expect(await proposals()).toBe('Proposals 2')

  for (const proposed of fake.proposals ?? []) {
    proposed.answer ??= 'drop'
  }
  await clock.advance(60_000)
  expect(await proposals()).toBe('Proposals')
  await pressTab(ui, 'proposals')
  expect(await shownTabs(ui)).toEqual(rowAbove('proposals', undefined, 'Proposals'))
  await ui.unmount()
})

test('where m2b could not look for proposals the tab says Proposals without a number, until it could', async ($, on) => {
  // Covers: B204
  const fake = fullFake()
  fake.proposalsError = 'the store at /home/alex/Notes cannot be read'
  const { clock } = await start($, on, fake)
  const ui = await mounted($)
  expect(await shownTabs(ui)).toEqual(rowAbove('overview', undefined, 'Proposals'))

  fake.proposalsError = null
  await clock.advance(60_000)
  expect(await shownTabs(ui)).toEqual(rowAbove('overview'))
  await ui.unmount()
})

test('with a core that does not know proposals the tab says Proposals without a number', async ($, on) => {
  // Covers: B204
  const fake = fullFake()
  fake.proposals = null
  await start($, on, fake)

  const ui = await mounted($)

  expect(await shownTabs(ui)).toEqual(rowAbove('overview', undefined, 'Proposals'))
  await ui.unmount()
})

test("a topic's lines stand under a seventh tab with the topic's name, cut to 20 characters, and a search under one named Search", async ($, on) => {
  // Covers: B204
  const fake = fullFake()
  // A name of exactly 20 characters is shown whole, and one m2b gave with what a terminal would run is cleaned.
  fake.given = {
    topics: [...(fake.given?.topics ?? []), { name: 'Northwind Trading Co', facts: 1, current: 0 }, { name: 'Ac\u001b[31mme Ltd', facts: 1, current: 0 }],
    atStart: 'whole',
    offUnder: null,
  }
  const { clock } = await start($, on, fake)
  const ui = await mounted($)

  for (const [at, label] of ['Northwind', LONG_NAME_CUT, 'Northwind Trading Co', 'Acme Ltd'].entries()) {
    await arrive($, clock, ui, 'overview')
    // The topic's button on the overview is labelled as its tab will be.
    expect((await ui.find({ key: `topic:${at}` }))?.props['label']).toBe(label)
    await ui.press({ key: `topic:${at}` })
    expect(await shownTabs(ui)).toEqual(rowAbove('aside', label))
  }
  expect(Array.from(LONG_NAME_CUT)).toHaveLength(20)
  // The view names the topic whole in its heading.
  await arrive($, clock, ui, 'overview')
  await ui.press({ key: 'topic:1' })
  expect((await texts(ui))[0]).toBe(LONG_NAME)

  await arrive($, clock, ui, 'search')
  expect(await shownTabs(ui)).toEqual(rowAbove('aside', 'Search'))
  await ui.unmount()
})

test('the seventh tab, and the eighth above a source, stand there only while their view is shown: a press on any of the six takes them away', async ($, on) => {
  // Covers: B204
  const { clock } = await start($, on, fullFake())
  const ui = await mounted($)

  for (const view of BESIDE_THE_SIX) {
    for (const to of TABS) {
      await arrive($, clock, ui, view)
      // All six tabs that stay are buttons there, `Settings` above a folded group of the settings and `Facts` above a fact's file and its source too.
      expect(await shownTabs(ui)).toEqual(rowOver(view))
      expect(await shownTabs(ui)).toHaveLength(view === 'source' ? 8 : 7)

      await pressTab(ui, to)

      expect(await shownTabs(ui)).toEqual(rowAbove(to))
      expect(await texts(ui)).not.toContain(SAYS[view])
    }
  }
  await ui.unmount()
})

test("no view has a button labelled back or settings, no evidence entry one labelled show, and only a fact's file one keyed show: a topic's button on the overview is labelled with the topic's name", async ($, on) => {
  // Covers: B204, B190, B230
  const { clock } = await start($, on, fullFake())
  const ui = await mounted($)

  for (const view of VIEWS) {
    await arrive($, clock, ui, view)
    const drawn = await inView(ui, 'Button')
    const labels = drawn.map(button => String(button.props['label']).toLowerCase())

    expect(labels).not.toContain('back')
    expect(labels).not.toContain('settings')
    // The one entry of the fact file that was read is the row that leads down to its source; this fixture has no current item with a note, whose button says show (B242).
    expect(labels.filter(label => label === 'show')).toEqual([])
    const topics = drawn.filter(button => (button.key ?? '').startsWith('topic:')).map(button => [button.key, button.props['label']])
    expect(topics).toEqual(
      view === 'overview'
        ? [
            ['topic:0', 'Northwind'],
            ['topic:1', LONG_NAME_CUT],
          ]
        : [],
    )
    // Whatever its label, no button is keyed as one that leads back, and only that entry's as one that shows another view.
    expect((await everyButton(ui)).filter(key => key === 'back' || key.startsWith('show:'))).toEqual(view === 'fact' ? ['show:0'] : [])
  }
  await ui.unmount()
})

test('the start view says under which tab the proposals and the whole review are, as lines with nothing to press', async ($, on) => {
  // Covers: B204
  await start($, on, fullFake())
  const ui = await mounted($)

  const lines = (await partLines(ui, 'waits')) ?? []

  expect(lines.slice(0, 2)).toEqual(['3 proposals from your sessions', 'in the tab Proposals'])
  expect(lines.at(-1)).toBe('The whole review is in the tab Review.')
  expect(await buttonsAt(ui, 'row:proposals')).toEqual([])
  // Both may be skipped: the count stands above the one, the review's own row above the other.
  for (const line of ['in the tab Proposals', 'The whole review is in the tab Review.']) {
    expect((await lookOf(ui, line))?.dimColor).toBe(true)
  }
  expect(await viewButtons(ui)).toEqual(['keep:c1', 'drop:c1', 'keep:q1', 'drop:q1', 'ok:r1', 'topic:0', 'topic:1', CURATE_NOW])
  await ui.unmount()
})

test('a press on each tab turns the pane to its view, from every other view, and reads what that view shows', WALK, async ($, on) => {
  // Covers: B204
  const fake = fullFake()
  const { clock } = await start($, on, fake)
  const ui = await mounted($)

  for (const from of VIEWS) {
    for (const to of TABS.filter(tab => tab !== SHOWN[from])) {
      await arrive($, clock, ui, from)
      expect(await texts(ui)).toContain(SAYS[from])
      const listsBefore = fake.settingCalls().length
      const todosBefore = fake.todosCalls().length
      const factsBefore = fake.factsCalls().length
      const viewerBefore = fake.viewerCalls().length

      await pressTab(ui, to)
      await clock.advance(1)

      expect(await shownTabs(ui)).toEqual(rowAbove(to))
      const shown = await texts(ui)
      expect(shown).toContain(SAYS[to])
      expect(shown).not.toContain(SAYS[from])
      // The settings, the open tasks and the facts are each read for each opening of their view, and by no other tab.
      expect(fake.settingCalls().slice(listsBefore)).toEqual(to === 'settings' ? [LIST] : [])
      expect(fake.todosCalls().slice(todosBefore)).toEqual(to === 'tasks' ? [TODOS] : [])
      expect(fake.factsCalls().slice(factsBefore)).toEqual(to === 'facts' ? [FACTS] : [])
      expect(fake.viewerCalls().slice(viewerBefore)).toEqual([])
    }
  }
  // Nothing a tab does answers a row or changes a setting.
  expect(fake.writes()).toEqual([])
  expect(fake.answers()).toEqual([])
  expect(fake.folderCalls()).toEqual([])
  await ui.unmount()
})

for (const [command, view] of [
  ['m2b-pane', 'overview'],
  ['m2b-proposals', 'proposals'],
  ['m2b-review', 'review'],
  ['m2b-settings', 'settings'],
  ['m2b-search', 'search'],
] as const) {
  test(`/${command} opens the pane with ${ASIDE[view] ?? LABELS[SHOWN[view] as TabId]} as the tab shown`, async ($, on) => {
    // Covers: B204
    const { clock, opened } = await start($, on, fullFake())

    await typed($, command, view === 'search' ? 'tea' : '')
    await clock.advance(1)

    expect(opened.map(one => one.id)).toEqual([PANE])
    const ui = await mounted($)
    expect(await shownTabs(ui)).toEqual(rowOver(view))
    expect(await texts(ui)).toContain(SAYS[view])
    await ui.unmount()
  })
}

test('a command typed on any view turns the pane to its own, and the row marks that tab', WALK, async ($, on) => {
  // Covers: B204
  const { clock } = await start($, on, fullFake())
  const ui = await mounted($)

  for (const from of VIEWS) {
    for (const to of ['overview', 'proposals', 'review', 'settings', 'search'] as const) {
      await arrive($, clock, ui, from)
      await arrive($, clock, ui, to)

      expect(await shownTabs(ui)).toEqual(rowOver(to))
      expect(await texts(ui)).toContain(SAYS[to])
    }
  }
  await ui.unmount()
})

test('in a pane as narrow as a dock gets the row holds the same tabs and breaks between them', async ($, on) => {
  // Covers: B204
  const { clock } = await start($, on, fullFake())
  const ui = await mounted($, 24)

  for (const view of ['overview', 'tasks', 'facts', 'topic', 'fact', 'group', 'source'] as const) {
    await arrive($, clock, ui, view)
    expect(await shownTabs(ui)).toEqual(rowOver(view))
    expect((await ui.find({ key: 'tabs' }))?.props).toMatchObject({ flexDirection: 'row', flexWrap: 'wrap' })
  }
  await ui.unmount()
})

// What the kit shows of the focus: a move the mod asks for fails in the kit and reaches no hook of
// a test. So the rule is held in two parts: which key the mod's function names for a press, and,
// on the views as drawn, that this key is a button of the view turned to and was none of the view
// that was left. Claude Code looks a key up in what is drawn when the focus is asked for and waits
// only for one that is not drawn yet: a key the view before drew too would be found there.

test('after a press on a tab the focus is asked for that tab, drawn as the one shown; after a press that opens a view beside the six, for the tab of the view it was opened from', () => {
  // Covers: B201
  for (const to of TABS) {
    expect(focusKeyAfterTab(to)).toBe(`tab:${to}:in:${to}`)
    expect(backTabKey(to)).toBe(`tab:${to}:in:aside`)
  }
})

test('for every view left and every tab pressed, the key the focus is asked for is that tab drawn as the one shown, was no button of the view that was left, and pressed again stays', WALK, async ($, on) => {
  // Covers: B201
  const { clock } = await start($, on, fullFake())
  const ui = await mounted($)

  for (const from of VIEWS) {
    for (const to of TABS.filter(tab => tab !== SHOWN[from])) {
      await arrive($, clock, ui, from)
      const before = await everyButton(ui)

      await pressTab(ui, to)
      await clock.advance(1)

      const key = focusKeyAfterTab(to)
      expect((await shownTabs(ui)).map(tab => tab.key)).toContain(key)
      expect(await shownTab(ui)).toBe(to)
      expect(before).not.toContain(key)
      // The same key pressed again reads the view again and stays there.
      await ui.press({ key })
      expect(await shownTab(ui)).toBe(to)
    }
  }
  await ui.unmount()
})

test("after a press on a topic's button the focus is asked for Overview above the lines, which the start view did not draw", async ($, on) => {
  // Covers: B201
  const { clock } = await start($, on, fullFake())
  const ui = await mounted($)
  await arrive($, clock, ui, 'overview')
  const before = await everyButton(ui)

  await ui.press({ key: 'topic:0' })

  const key = backTabKey('overview')
  expect(key).toBe('tab:overview:in:aside')
  expect((await shownTabs(ui)).map(tab => tab.key)).toContain(key)
  expect(before).not.toContain(key)
  await ui.press({ key })
  expect(await shownTab(ui)).toBe('overview')
  await ui.unmount()
})
