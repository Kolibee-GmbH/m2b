import { expect, test } from 'claude-code/testing'
import type { CommandRunResult } from 'claude-code'
import type { Engine } from 'claude-code/testing'

import { focusKeyAfterTab, tabKeyAfterTurn } from '../../hooks/pane-tabs'
import type { Shown, TabId } from '../../hooks/pane-tabs'
import { topicShowKey } from '../../hooks/session-view'
import type { SessionModel } from '../../hooks/session-view'
import type { BandSession } from '../../types'
import {
  CURATE_NOW,
  FakeM2b,
  FakeSettings,
  NOTES,
  SESSION_ID,
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
const TURN_ENDED = { answer: 'done', durationMs: 5, isAborted: false, reason: 'answer' } as const

/** The tabs that stay, in the order drawn. */
const TABS: readonly TabId[] = ['overview', 'proposals', 'review', 'tasks', 'settings']
const LABELS: Readonly<Record<TabId, string>> = {
  overview: 'Overview',
  proposals: 'Proposals',
  review: 'Review',
  tasks: 'Tasks',
  settings: 'Settings',
}

/** Every view of the pane: the five under their tabs, and the three under a sixth tab, a folded group of the settings, a topic's lines and a search. */
type View = TabId | 'group' | 'topic' | 'search'
const VIEWS: readonly View[] = ['overview', 'proposals', 'review', 'tasks', 'settings', 'group', 'topic', 'search']
/** The views that stand under a sixth tab. */
const UNDER_A_SIXTH_TAB = ['group', 'topic', 'search'] as const
/** The button of the row the settings keep their folded group behind, which turns the pane to that group. */
const SHOW_GROUP = 'settings:fold:about'
/** Which tab the row marks above each view. */
const SHOWN: Readonly<Record<View, Shown>> = {
  overview: 'overview',
  proposals: 'proposals',
  review: 'review',
  tasks: 'tasks',
  settings: 'settings',
  group: 'aside',
  topic: 'aside',
  search: 'aside',
}
/** The label of the sixth tab above the three views that have one. */
const ASIDE: Readonly<Partial<Record<View, string>>> = { group: 'About this setup', topic: 'Northwind', search: 'Search' }
/** A line each view draws and no other does: the review has a part "Waits for you" too, so the overview is told by its part "Today". */
const SAYS: Readonly<Record<View, string>> = {
  overview: 'Today',
  proposals: 'said on 2026-03-12: "Dana runs IT at Northwind"',
  review: 'lint: broken link in a.md',
  tasks: LADDER_TASK,
  settings: 'that only inform or are changed by a command',
  group: `Store folder: ${NOTES}`,
  topic: KIM,
  search: 'memory/dana.md:3',
}
/** The command that turns the pane to each view, or to the view a press leads on from: the tasks have no command, only their tab. */
const COMMANDS: Readonly<Record<View, string>> = {
  overview: 'm2b-pane',
  proposals: 'm2b-proposals',
  review: 'm2b-review',
  tasks: 'm2b-pane',
  settings: 'm2b-settings',
  group: 'm2b-settings',
  topic: 'm2b-pane',
  search: 'm2b-search',
}

function typed($: Engine, command: string, args = ''): Promise<CommandRunResult> {
  return $.command.run({ command, args, origin: { kind: 'composer' }, presentation: { isFullscreen: false, columns: 100 } })
}

/**
 * A session with something under every tab: two topics, a candidate, a question and the review,
 * three proposals, an open task, a hit to search for, and three settings, two to choose and one
 * behind a row.
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

/** Turns the pane to `view` from wherever it is: by the view's command and, for the tasks, a folded group and a topic, the press that shows it. */
async function arrive($: Engine, clock: Clock, ui: Pane, view: View): Promise<void> {
  await typed($, COMMANDS[view], view === 'search' ? 'tea' : '')
  await clock.advance(1)
  if (view === 'tasks') {
    await pressTab(ui, 'tasks')
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
    key: id === shown ? null : `tab:${id}:in:${shown}`,
  }))
  return aside === undefined ? staying : [...staying, { label: aside, key: null }]
}

/** The key of every button the pane draws, the tabs among them. */
async function everyButton(ui: Pane): Promise<string[]> {
  return (await ui.findAll({ type: 'Button' })).map(button => String(button.key))
}

test('above the view the pane starts in stand Overview, Proposals with the number that wait, Review, Tasks and Settings: Overview as a text, the others as buttons', async ($, on) => {
  // Covers: B204
  await start($, on, fullFake())

  const ui = await mounted($)

  expect(await shownTabs(ui)).toEqual([
    { label: 'Overview', key: null },
    { label: 'Proposals 3', key: 'tab:proposals:in:overview' },
    { label: 'Review', key: 'tab:review:in:overview' },
    { label: 'Tasks', key: 'tab:tasks:in:overview' },
    { label: 'Settings', key: 'tab:settings:in:overview' },
  ])
  // The row is the first thing drawn: the view stands below it.
  expect((await ui.findAll({ type: 'Text' }))[0]?.text).toBe('Overview')
  expect((await texts(ui))[0]).toBe('Waits for you')
  await ui.unmount()
})

test('the five tabs stand above every view in the same order: the one whose view is shown is a text and no button, every other a button', async ($, on) => {
  // Covers: B204
  const { clock } = await start($, on, fullFake())
  const ui = await mounted($)

  for (const view of VIEWS) {
    await arrive($, clock, ui, view)

    expect(await texts(ui)).toContain(SAYS[view])
    expect(await shownTabs(ui)).toEqual(rowAbove(SHOWN[view], ASIDE[view]))
    // No tab is drawn twice: once as the text that is shown, or once as a button.
    expect((await everyButton(ui)).filter(key => key.startsWith('tab:'))).toHaveLength(5 - (ASIDE[view] === undefined ? 1 : 0))
  }
  await ui.unmount()
})

test("the tab shown is bold and underlined in the color of m2b's name, and every other tab is a dim button", async ($, on) => {
  // Covers: B204
  const { clock } = await start($, on, fullFake())
  const ui = await mounted($)

  for (const view of ['overview', 'review', 'tasks', 'topic', 'group'] as const) {
    await arrive($, clock, ui, view)
    const row = await shownTabs(ui)
    const marked = row.find(tab => tab.key === null)

    // The row's one text is the first text the pane draws.
    const [text] = await ui.findAll({ type: 'Text' })
    expect(text?.text).toBe(marked?.label)
    expect(text?.props).toMatchObject({ color: 'remember', weight: 'bold', underline: true })
    for (const tab of row.filter(one => one.key !== null)) {
      const button = await ui.find({ key: tab.key ?? '' })
      expect(button?.type).toBe('Button')
      expect(button?.props['dimColor']).toBe(true)
      expect(button?.props['variant']).toBeUndefined()
    }
  }
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

test("a topic's lines stand under a sixth tab with the topic's name, cut to 20 characters, and a search under one named Search", async ($, on) => {
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

test('the sixth tab stands there only while its view is shown: a press on any of the five takes it away', async ($, on) => {
  // Covers: B204
  const { clock } = await start($, on, fullFake())
  const ui = await mounted($)

  for (const view of UNDER_A_SIXTH_TAB) {
    for (const to of TABS) {
      await arrive($, clock, ui, view)
      // All five tabs that stay are buttons there, `Settings` above a folded group of the settings too.
      expect(await shownTabs(ui)).toEqual(rowAbove('aside', ASIDE[view]))
      expect(await shownTabs(ui)).toHaveLength(6)

      await pressTab(ui, to)

      expect(await shownTabs(ui)).toEqual(rowAbove(to))
      expect(await texts(ui)).not.toContain(SAYS[view])
    }
  }
  await ui.unmount()
})

test("no view has a button labelled back, settings or show: a topic's button on the overview is labelled with the topic's name", async ($, on) => {
  // Covers: B204, B190
  const { clock } = await start($, on, fullFake())
  const ui = await mounted($)

  for (const view of VIEWS) {
    await arrive($, clock, ui, view)
    const drawn = await inView(ui, 'Button')
    const labels = drawn.map(button => String(button.props['label']).toLowerCase())

    expect(labels).not.toContain('back')
    expect(labels).not.toContain('settings')
    expect(labels).not.toContain('show')
    const topics = drawn.filter(button => (button.key ?? '').startsWith('topic:')).map(button => [button.key, button.props['label']])
    expect(topics).toEqual(
      view === 'overview'
        ? [
            ['topic:0', 'Northwind'],
            ['topic:1', LONG_NAME_CUT],
          ]
        : [],
    )
    // Whatever its label, no button is keyed as one that leads back or shows another view.
    expect((await everyButton(ui)).filter(key => key === 'back' || key.startsWith('show:'))).toEqual([])
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

test('a press on each tab turns the pane to its view, from every other view, and reads what that view shows', async ($, on) => {
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

      await pressTab(ui, to)
      await clock.advance(1)

      expect(await shownTabs(ui)).toEqual(rowAbove(to))
      const shown = await texts(ui)
      expect(shown).toContain(SAYS[to])
      expect(shown).not.toContain(SAYS[from])
      // The settings and the open tasks are each read for each opening of their view, and by no other tab.
      expect(fake.settingCalls().slice(listsBefore)).toEqual(to === 'settings' ? [LIST] : [])
      expect(fake.todosCalls().slice(todosBefore)).toEqual(to === 'tasks' ? [TODOS] : [])
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
    expect(await shownTabs(ui)).toEqual(rowAbove(SHOWN[view], ASIDE[view]))
    expect(await texts(ui)).toContain(SAYS[view])
    await ui.unmount()
  })
}

test('a command typed on any view turns the pane to its own, and the row marks that tab', async ($, on) => {
  // Covers: B204
  const { clock } = await start($, on, fullFake())
  const ui = await mounted($)

  for (const from of VIEWS) {
    for (const to of ['overview', 'proposals', 'review', 'settings', 'search'] as const) {
      await arrive($, clock, ui, from)
      await arrive($, clock, ui, to)

      expect(await shownTabs(ui)).toEqual(rowAbove(SHOWN[to], ASIDE[to]))
      expect(await texts(ui)).toContain(SAYS[to])
    }
  }
  await ui.unmount()
})

test('in a pane as narrow as a dock gets the row holds the same tabs and breaks between them', async ($, on) => {
  // Covers: B204
  const { clock } = await start($, on, fullFake())
  const ui = await mounted($, 24)

  for (const view of ['overview', 'tasks', 'topic', 'group'] as const) {
    await arrive($, clock, ui, view)
    expect(await shownTabs(ui)).toEqual(rowAbove(SHOWN[view], ASIDE[view]))
    expect((await ui.find({ key: 'tabs' }))?.props).toMatchObject({ flexDirection: 'row', flexWrap: 'wrap' })
  }
  await ui.unmount()
})

// What the kit shows of the focus: a move the mod asks for fails in the kit and reaches no hook of
// a test. So the rule is held in two parts: which key the mod's function names for a press, and,
// on the views as drawn, that this key is a button of the view turned to and was none of the view
// that was left. Claude Code looks a key up in what is drawn when the focus is asked for and waits
// only for one that is not drawn yet: a key the view before drew too would be found there.

/** Which tab's view a second press on the same key shows: the one that was left, or what stands in for a sixth tab. */
function leadsBackTo(left: Shown, to: TabId): TabId {
  if (left !== 'aside') {
    return left
  }
  return to === 'overview' ? 'proposals' : 'overview'
}

test('after a press on a tab the focus is asked for the tab that leads back to the view that was left; Overview stands in for a sixth tab, and Proposals on the overview itself', () => {
  // Covers: B201
  const every: readonly Shown[] = [...TABS, 'aside']
  const asked = Object.fromEntries(every.map(left => [left, every.map(to => tabKeyAfterTurn(left, to))]))

  // Each row: the view that was left; each column: the view turned to, in the order of the tabs, the sixth last.
  expect(asked).toEqual({
    overview: [
      'tab:proposals:in:overview',
      'tab:overview:in:proposals',
      'tab:overview:in:review',
      'tab:overview:in:tasks',
      'tab:overview:in:settings',
      'tab:overview:in:aside',
    ],
    proposals: [
      'tab:proposals:in:overview',
      'tab:overview:in:proposals',
      'tab:proposals:in:review',
      'tab:proposals:in:tasks',
      'tab:proposals:in:settings',
      'tab:proposals:in:aside',
    ],
    review: [
      'tab:review:in:overview',
      'tab:review:in:proposals',
      'tab:overview:in:review',
      'tab:review:in:tasks',
      'tab:review:in:settings',
      'tab:review:in:aside',
    ],
    tasks: [
      'tab:tasks:in:overview',
      'tab:tasks:in:proposals',
      'tab:tasks:in:review',
      'tab:overview:in:tasks',
      'tab:tasks:in:settings',
      'tab:tasks:in:aside',
    ],
    settings: [
      'tab:settings:in:overview',
      'tab:settings:in:proposals',
      'tab:settings:in:review',
      'tab:settings:in:tasks',
      'tab:overview:in:settings',
      'tab:settings:in:aside',
    ],
    aside: [
      'tab:proposals:in:overview',
      'tab:overview:in:proposals',
      'tab:overview:in:review',
      'tab:overview:in:tasks',
      'tab:overview:in:settings',
      'tab:overview:in:aside',
    ],
  })
  // The key never names the tab of the view turned to, which is drawn as a text and takes no focus.
  for (const left of every) {
    for (const to of every) {
      expect(tabKeyAfterTurn(left, to).startsWith(`tab:${to}:`)).toBe(false)
      expect(tabKeyAfterTurn(left, to).endsWith(`:in:${to}`)).toBe(true)
    }
  }
})

test('for every view left and every tab pressed, the key the focus is asked for is a tab drawn above the view turned to, was no button of the view that was left, and leads back', async ($, on) => {
  // Covers: B201
  const { clock } = await start($, on, fullFake())
  const ui = await mounted($)

  for (const from of VIEWS) {
    for (const to of TABS.filter(tab => tab !== SHOWN[from])) {
      await arrive($, clock, ui, from)
      const before = await everyButton(ui)

      await pressTab(ui, to)
      await clock.advance(1)

      const key = tabKeyAfterTurn(SHOWN[from], to)
      expect((await shownTabs(ui)).map(tab => tab.key)).toContain(key)
      expect(before).not.toContain(key)
      // The same key pressed again returns to the tab that was left.
      await ui.press({ key })
      expect(await shownTab(ui)).toBe(leadsBackTo(SHOWN[from], to))
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

  const key = tabKeyAfterTurn('overview', 'aside')
  expect(key).toBe('tab:overview:in:aside')
  expect((await shownTabs(ui)).map(tab => tab.key)).toContain(key)
  expect(before).not.toContain(key)
  await ui.press({ key })
  expect(await shownTab(ui)).toBe('overview')
  await ui.unmount()
})

const GIVEN_TWO: BandSession = {
  id: SESSION_ID,
  known: true,
  topics: [
    { name: 'Northwind', facts: 3, current: 1 },
    { name: 'Acme Ltd', facts: 1, current: 0 },
  ],
  atStart: 'whole',
  offUnder: null,
  error: null,
}

/** What the start view draws from, with what a test sets and nothing else. */
function modelWith(parts: Partial<SessionModel>): SessionModel {
  return {
    given: null,
    notes: 0,
    rowNotice: null,
    folderNotice: null,
    curateNotice: null,
    snapshot: null,
    proposals: null,
    presses: {},
    health: null,
    curatingMachine: null,
    versionLine: null,
    ...parts,
  }
}

test('a topic left for the overview has the key of its button there, by its place among the topics, and none where the start view draws no such row', () => {
  // Covers: B201
  const full = modelWith({ given: GIVEN_TWO })

  expect(topicShowKey(full, 'Northwind')).toBe('topic:0')
  expect(topicShowKey(full, 'Acme Ltd')).toBe('topic:1')
  // A topic the session is no longer given, a session given none, one m2b has not looked at, and one it could not look at.
  expect(topicShowKey(full, 'Lumen')).toBeNull()
  expect(topicShowKey(modelWith({ given: { ...GIVEN_TWO, topics: [] } }), 'Northwind')).toBeNull()
  expect(topicShowKey(modelWith({}), 'Northwind')).toBeNull()
  expect(topicShowKey(modelWith({ given: { ...GIVEN_TWO, error: 'the machine state cannot be read' } }), 'Northwind')).toBeNull()
  // Then the tab's own rule holds: the sixth tab is gone, and on the overview Proposals stands in for it.
  expect(tabKeyAfterTurn('aside', 'overview')).toBe('tab:proposals:in:overview')
})

test("a topic left by Overview gets its own button before the tabs' rule; left by another tab, or with no such row, the tabs' rule holds", () => {
  // Covers: B201
  const full = modelWith({ given: GIVEN_TWO })
  const acme = { kind: 'topic', name: 'Acme Ltd', press: 'p1', isRead: true } as const

  expect(focusKeyAfterTab(acme, 'overview', full)).toBe('topic:1')
  expect(focusKeyAfterTab(acme, 'review', full)).toBe('tab:overview:in:review')
  expect(focusKeyAfterTab(acme, 'overview', modelWith({}))).toBe('tab:proposals:in:overview')
  // No other view has a row on the start view: the tab that leads back to it.
  expect(focusKeyAfterTab({ kind: 'review' }, 'overview', full)).toBe('tab:review:in:overview')
  expect(focusKeyAfterTab({ kind: 'tasks', press: 'p1', drawn: 1 }, 'overview', full)).toBe('tab:tasks:in:overview')
  expect(focusKeyAfterTab(null, 'settings', full)).toBe('tab:overview:in:settings')
  // A folded group of the settings stands under a sixth tab, which is gone once it is left: the
  // tabs' rule for the sixth tab holds, whichever tab is pressed above it, `Settings` among them.
  const choices = { kind: 'settings', press: 'p1', aside: null, drawn: 0 } as const
  const group = { ...choices, aside: { name: 'about', title: 'About this setup' }, drawn: 1 } as const
  expect(focusKeyAfterTab(group, 'overview', full)).toBe('tab:proposals:in:overview')
  expect(focusKeyAfterTab(group, 'proposals', full)).toBe('tab:overview:in:proposals')
  expect(focusKeyAfterTab(group, 'review', full)).toBe('tab:overview:in:review')
  expect(focusKeyAfterTab(group, 'tasks', full)).toBe('tab:overview:in:tasks')
  expect(focusKeyAfterTab(group, 'settings', full)).toBe('tab:overview:in:settings')
  // The choices stand under `Settings`, which leads back to them.
  expect(focusKeyAfterTab(choices, 'review', full)).toBe('tab:settings:in:review')
})

test("the button of the topic that was left is a button of the start view and was none above the topic's lines", async ($, on) => {
  // Covers: B201
  const { clock } = await start($, on, fullFake())
  const ui = await mounted($)

  for (const at of [0, 1]) {
    await arrive($, clock, ui, 'overview')
    await ui.press({ key: `topic:${at}` })
    const before = await everyButton(ui)

    await pressTab(ui, 'overview')

    expect(await viewButtons(ui)).toContain(`topic:${at}`)
    expect(before).not.toContain(`topic:${at}`)
    // The same key pressed again returns to the topic that was left.
    const heading = at === 0 ? 'Northwind' : LONG_NAME
    await ui.press({ key: `topic:${at}` })
    expect((await texts(ui))[0]).toBe(heading)
  }
  await ui.unmount()
})

test('where the start view no longer draws the row of the topic that was left, the tab Proposals is drawn there and was none above the lines', async ($, on) => {
  // Covers: B201
  const fake = fullFake()
  const { clock } = await start($, on, fake)
  const ui = await mounted($)
  await arrive($, clock, ui, 'topic')
  // The session is given no topic any more, as m2b says when it is asked after a turn.
  fake.given = { topics: [], atStart: 'whole', offUnder: null }
  await $.turn.complete({ ...TURN_ENDED, turnId: 't1' })
  await clock.advance(1)
  expect(await texts(ui)).toContain(KIM)
  const before = await everyButton(ui)

  await pressTab(ui, 'overview')

  expect(await partLines(ui, 'session')).toEqual(['The distillate was printed whole at the start.'])
  expect(await viewButtons(ui)).not.toContain('topic:0')
  const key = tabKeyAfterTurn('aside', 'overview')
  expect((await shownTabs(ui)).map(tab => tab.key)).toContain(key)
  expect(before).not.toContain(key)
  await ui.unmount()
})
