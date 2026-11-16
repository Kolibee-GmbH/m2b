import { expect, test } from 'claude-code/testing'
import type { CommandRunResult } from 'claude-code'
import type { Engine } from 'claude-code/testing'

import { beginTopic, fillTopic, forgetTopicUnless, heldTopic, holdsTopic, parseTopic, topicPane } from '../../hooks/topic'
import type { TopicLook } from '../../hooks/topic'
import {
  FakeM2b,
  HOME,
  SESSION_ID,
  inView,
  insetsAt,
  lookOf,
  pane,
  partLines,
  partLook,
  piecesAt,
  pressTab,
  shownParts,
  shownTab,
  shownTabs,
  start,
  texts,
  viewButtons,
} from './harness'
import type { Files, ShownPiece } from './harness'

const PANE = 'm2b'
const AS_A_DIALOG = { id: PANE, title: 'm2b', closeOnEscape: true, focus: true }
const NEXT_SESSION = '7c9e6679-7425-40de-944b-e07fc1f90ae7'
const AS_IT_IS_NOW = 'As the distillate holds it now, which may differ from what this session was given.'
const READING = 'm2b is reading the topic…'
const NO_TOPIC = 'The distillate holds no topic of this name now.'
const NO_LINES = 'The topic holds no lines now.'
const KIM = "Kim Lee leads Acme's IT"
const PAYS = 'Acme pays within 30 days'
const AUDIT = 'Export audit under way (since 2026-11-02)'
const READ_ACME = ['distillate', 'topic', '--json', '--', 'Acme Ltd']

function typed($: Engine, command: string, args = ''): Promise<CommandRunResult> {
  return $.command.run({ command, args, origin: { kind: 'composer' }, presentation: { isFullscreen: false, columns: 100 } })
}

async function startView($: Engine) {
  await typed($, 'm2b-pane')
  return $.ui.mount({ ...pane(PANE), surface: 'terminal' })
}

/** A session that was given two topics, the first with facts and a current item in the distillate now. */
function givenAcme(): FakeM2b {
  const fake = new FakeM2b()
  fake.given = {
    topics: [
      { name: 'Acme Ltd', facts: 2, current: 1 },
      { name: 'Riverside Choir', facts: 1, current: 0 },
    ],
    atStart: 'whole',
    offUnder: null,
  }
  fake.topicLines = {
    'Acme Ltd': { facts: [KIM, PAYS], current: [AUDIT] },
    'Riverside Choir': { facts: ['The choir meets on Wednesdays'], current: [] },
  }
  return fake
}

test('a press on a topic shows its lines as the distillate holds them now, and says that they are of now', async ($, on) => {
  // Covers: B190
  const fake = givenAcme()
  const { clock, opened } = await start($, on, fake)
  const ui = await startView($)
  await clock.advance(1)
  const [opensBefore, callsBefore] = [opened.length, fake.calls.length]

  await ui.press({ key: 'topic:0' })
  await clock.advance(1)

  // The one call: the band holds nothing a topic's lines change, and is not read again.
  expect(fake.calls.slice(callsBefore)).toEqual([READ_ACME])
  expect(await texts(ui)).toEqual(['Acme Ltd', AS_IT_IS_NOW, KIM, PAYS, 'Current', AUDIT])
  // Opened anew as a dialog, so Escape leads back to the view the pane starts in.
  expect(opened.slice(opensBefore)).toEqual([AS_A_DIALOG])
  // The lines are read, never pressed: the tabs above them are the one way on, the topic's own beside the four.
  expect(await viewButtons(ui)).toEqual([])
  expect((await shownTabs(ui)).at(-1)).toEqual({ label: 'Acme Ltd', key: null })
  await ui.unmount()
})

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

test("the session's state, which every plugin can read, names the topic and never holds a line of it", async ($, on) => {
  // Covers: B190
  const fake = givenAcme()
  const writes = stateWrites(on)
  await start($, on, fake)
  const ui = await startView($)

  await ui.press({ key: 'topic:0' })
  expect(await texts(ui)).toContain(KIM)
  await pressTab(ui, 'overview')

  const kept = writes.join('\n')
  expect(kept).toContain('"name":"Acme Ltd"')
  expect(kept).toContain('"isRead":true')
  for (const line of [KIM, PAYS, AUDIT]) {
    expect(kept).not.toContain(line)
  }
  await ui.unmount()
})

test('a reload of the mod, which starts the session again, leaves the pane on its start view', async ($, on) => {
  // Covers: B190
  const fake = givenAcme()
  const { clock } = await start($, on, fake)
  const ui = await startView($)
  await ui.press({ key: 'topic:0' })
  expect(await texts(ui)).toContain(KIM)

  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await clock.advance(1)

  const shown = await texts(ui)
  expect(shown).toContain('Waits for you')
  expect(shown).not.toContain(KIM)
  await ui.unmount()
})

test('each topic has its own button, and a topic without current items shows none', async ($, on) => {
  // Covers: B190
  const fake = givenAcme()
  await start($, on, fake)
  const ui = await startView($)

  await ui.press({ key: 'topic:1' })

  expect(fake.topicCalls()).toEqual([['distillate', 'topic', '--json', '--', 'Riverside Choir']])
  expect(await texts(ui)).toEqual(['Riverside Choir', AS_IT_IS_NOW, 'The choir meets on Wednesdays'])
  await ui.unmount()
})

test('the tab Overview forgets the lines, and the next press reads them again', async ($, on) => {
  // Covers: B190
  const fake = givenAcme()
  await start($, on, fake)
  const ui = await startView($)
  await ui.press({ key: 'topic:0' })

  await pressTab(ui, 'overview')

  const shown = await texts(ui)
  expect(shown).toContain('Waits for you')
  expect(await partLines(ui, 'session')).toContain('[Acme Ltd] 2 facts, 1 current')
  expect(shown).not.toContain(KIM)

  fake.topicLines = { 'Acme Ltd': { facts: ['Kim Lee left Acme'], current: [] } }
  await ui.press({ key: 'topic:0' })
  expect(fake.topicCalls()).toEqual([READ_ACME, READ_ACME])
  expect(await texts(ui)).toEqual(['Acme Ltd', AS_IT_IS_NOW, 'Kim Lee left Acme'])
  await ui.unmount()
})

for (const [to, label] of [
  ['proposals', 'Proposals'],
  ['review', 'Review'],
  ['settings', 'Settings'],
] as const) {
  test(`the tab ${label} forgets the lines too: back on the start view, the next press reads them again`, async ($, on) => {
    // Covers: B190
    const fake = givenAcme()
    await start($, on, fake)
    const ui = await startView($)
    await ui.press({ key: 'topic:0' })
    expect(await texts(ui)).toContain(KIM)

    await pressTab(ui, to)

    expect(await shownTab(ui)).toBe(to)
    expect(await texts(ui)).not.toContain(KIM)
    await pressTab(ui, 'overview')
    expect(await texts(ui)).not.toContain(KIM)

    fake.topicLines = { 'Acme Ltd': { facts: ['Kim Lee left Acme'], current: [] } }
    await ui.press({ key: 'topic:0' })
    expect(fake.topicCalls()).toEqual([READ_ACME, READ_ACME])
    expect(await texts(ui)).toEqual(['Acme Ltd', AS_IT_IS_NOW, 'Kim Lee left Acme'])
    await ui.unmount()
  })
}

test('no line of a topic reaches a text for the conversation or a file the sessions share', async ($, on) => {
  // Covers: B190
  const fake = givenAcme()
  fake.review('r1', ['lint: broken link in a.md'])
  fake.proposal('a1a1a1a1a1a1', 'Dana is head of IT at Northwind.', 'Dana runs IT at Northwind')
  const files: Files = new Map()
  const { clock } = await start($, on, fake, {}, files)
  const ui = await startView($)
  await ui.press({ key: 'topic:0' })
  expect(await texts(ui)).toContain(KIM)

  // No surface draws the pane any more: every command answers with its lines as text.
  fake.paneWaits = 'no surface attached places panes'
  const answers = [
    (await typed($, 'm2b-pane')).text ?? '',
    (await typed($, 'm2b-review')).text ?? '',
    (await typed($, 'm2b-proposals')).text ?? '',
  ]
  await clock.advance(60_000)

  for (const said of [...answers, ...files.values()]) {
    expect(said).not.toContain(KIM)
    expect(said).not.toContain(PAYS)
    expect(said).not.toContain(AUDIT)
  }
  expect(files.get(`${HOME}/.local/state/m2b/band-answer.json`) ?? '').not.toBe('')
  await ui.unmount()
})

test('a command that turns the pane to another view leaves no line of the topic behind', async ($, on) => {
  // Covers: B190
  const fake = givenAcme()
  fake.review('r1', ['lint: broken link in a.md'])
  await start($, on, fake)
  const ui = await startView($)
  await ui.press({ key: 'topic:0' })

  await typed($, 'm2b-review')
  expect(await texts(ui)).not.toContain(KIM)

  await pressTab(ui, 'overview')
  expect(await shownTab(ui)).toBe('overview')
  expect(await texts(ui)).toContain('Waits for you')
  expect(await texts(ui)).not.toContain(KIM)
  await ui.unmount()
})

test('after /clear the topic of the conversation that ended is no longer shown', async ($, on) => {
  // Covers: B190
  const fake = givenAcme()
  const { clock } = await start($, on, fake)
  const ui = await startView($)
  await ui.press({ key: 'topic:0' })
  expect(await texts(ui)).toContain(KIM)

  await $.session.end({ reason: 'clear', sessionId: SESSION_ID, resume: { id: SESSION_ID } })
  fake.sessionId = NEXT_SESSION
  fake.given = { topics: [], atStart: 'whole', offUnder: null }
  await clock.advance(1_000)

  const shown = await texts(ui)
  expect(shown).toContain('Waits for you')
  expect(shown).not.toContain(KIM)
  await ui.unmount()
})

test('while m2b reads, the view says so, and an answer that comes after the tab Overview is dropped', async ($, on) => {
  // Covers: B190
  const fake = givenAcme()
  fake.delayMs = args => (args[1] === 'topic' ? 2_000 : 0)
  const { clock } = await start($, on, fake)
  const ui = await startView($)

  const pressed = ui.press({ key: 'topic:0' })
  await clock.advance(1)
  expect(await texts(ui)).toEqual(['Acme Ltd', AS_IT_IS_NOW, READING])

  await pressTab(ui, 'overview')
  await clock.advance(2_000)
  await pressed

  const shown = await texts(ui)
  expect(shown).toContain('Waits for you')
  expect(shown).not.toContain(KIM)
  await ui.unmount()
})

test('an answer that comes after another tab was pressed is dropped too, and draws no fifth tab again', async ($, on) => {
  // Covers: B190
  const fake = givenAcme()
  fake.delayMs = args => (args[1] === 'topic' ? 2_000 : 0)
  const { clock } = await start($, on, fake)
  const ui = await startView($)

  const pressed = ui.press({ key: 'topic:0' })
  await clock.advance(1)
  expect(await texts(ui)).toEqual(['Acme Ltd', AS_IT_IS_NOW, READING])

  await pressTab(ui, 'review')
  await clock.advance(2_000)
  await pressed

  expect(await shownTab(ui)).toBe('review')
  expect(await shownTabs(ui)).toHaveLength(4)
  expect(await texts(ui)).not.toContain(KIM)
  await pressTab(ui, 'overview')
  expect(await texts(ui)).not.toContain(KIM)
  await ui.unmount()
})

test('an answer that comes after another topic was opened does not fill that one', async ($, on) => {
  // Covers: B190
  const fake = givenAcme()
  fake.delayMs = args => (args.at(-1) === 'Acme Ltd' ? 2_000 : args[1] === 'topic' ? 5_000 : 0)
  const { clock } = await start($, on, fake)
  const ui = await startView($)

  const first = ui.press({ key: 'topic:0' })
  await clock.advance(1)
  await pressTab(ui, 'overview')
  const second = ui.press({ key: 'topic:1' })
  await clock.advance(2_000)
  await first

  // The first topic's answer is here, and the view still waits for the second one's.
  expect(await texts(ui)).toEqual(['Riverside Choir', AS_IT_IS_NOW, READING])
  await clock.advance(5_000)
  await second
  expect(await texts(ui)).toEqual(['Riverside Choir', AS_IT_IS_NOW, 'The choir meets on Wednesdays'])
  await ui.unmount()
})

test('an answer to an earlier press on the same topic does not fill the view of a later one', async ($, on) => {
  // Covers: B190
  const fake = givenAcme()
  let reads = 0
  fake.delayMs = args => (args[1] !== 'topic' ? 0 : (reads += 1) === 1 ? 2_000 : 5_000)
  const { clock } = await start($, on, fake)
  const ui = await startView($)

  const first = ui.press({ key: 'topic:0' })
  await clock.advance(1)
  await pressTab(ui, 'overview')
  // The distillate changed between the two presses: the later answer is the one to show.
  fake.topicLines = { 'Acme Ltd': { facts: ['Kim Lee left Acme'], current: [] } }
  const second = ui.press({ key: 'topic:0' })
  await clock.advance(2_000)
  await first

  expect(await texts(ui)).toEqual(['Acme Ltd', AS_IT_IS_NOW, READING])
  await clock.advance(5_000)
  await second
  expect(await texts(ui)).toEqual(['Acme Ltd', AS_IT_IS_NOW, 'Kim Lee left Acme'])
  await ui.unmount()
})

test('a topic the distillate no longer holds is said, apart from one without lines', async ($, on) => {
  // Covers: B190
  const fake = givenAcme()
  fake.topicLines = { 'Riverside Choir': { facts: [], current: [] } }
  await start($, on, fake)
  const ui = await startView($)

  await ui.press({ key: 'topic:0' })
  expect(await texts(ui)).toEqual(['Acme Ltd', AS_IT_IS_NOW, 'The distillate holds no topic of this name now.'])

  await pressTab(ui, 'overview')
  await ui.press({ key: 'topic:1' })
  expect(await texts(ui)).toEqual(['Riverside Choir', AS_IT_IS_NOW, 'The topic holds no lines now.'])
  await ui.unmount()
})

test('a distillate m2b cannot read is could not read, never a topic without lines', async ($, on) => {
  // Covers: B190
  const fake = givenAcme()
  fake.topicFails = 'memory/MEMORY.md is not downloaded to this machine; run: m2b fetch memory/MEMORY.md'
  await start($, on, fake)
  const ui = await startView($)

  await ui.press({ key: 'topic:0' })

  expect(await texts(ui)).toEqual([
    'Acme Ltd',
    AS_IT_IS_NOW,
    'm2b could not read the topic: memory/MEMORY.md is not downloaded to this machine; run: m2b fetch memory/MEMORY.md',
  ])
  await ui.unmount()
})

test('an installed m2b from before the command, and an answer of another shape, each say could not read', async ($, on) => {
  // Covers: B190
  const fake = givenAcme()
  fake.knowsTopics = false
  await start($, on, fake)
  const ui = await startView($)

  await ui.press({ key: 'topic:0' })
  expect(await texts(ui)).toContain(
    'm2b could not read the topic: the installed m2b is older than this band; update m2b, then run /reload-plugins',
  )
  await ui.unmount()

  expect(parseTopic('{"name": "Acme Ltd", "found": true, "facts": "all of them", "current": []}')).toEqual({
    state: 'failed',
    error: 'm2b answered something other than a topic',
  })
  expect(parseTopic('not JSON')).toEqual({ state: 'failed', error: 'm2b answered something other than a topic' })
  expect(parseTopic('{"name": "Acme Ltd", "found": false, "facts": [], "current": []}')).toEqual({ state: 'missing' })
})

test('the lines are drawn without what a terminal would run, and wrap in a narrow pane', async ($, on) => {
  // Covers: B190
  const fake = givenAcme()
  fake.given = { topics: [{ name: 'Ac\u001b[31mme Ltd', facts: 1, current: 1 }], atStart: 'whole', offUnder: null }
  fake.topicLines = { 'Ac\u001b[31mme Ltd': { facts: ['Kim\u001b[2J leads\nIT'], current: ['Audit\u0007 under way'] } }
  await start($, on, fake)
  await typed($, 'm2b-pane')
  const ui = await $.ui.mount({ ...pane(PANE, 24), surface: 'terminal' })

  await ui.press({ key: 'topic:0' })

  // Asked for under the name as m2b gave it.
  expect(fake.topicCalls()).toEqual([['distillate', 'topic', '--json', '--', 'Ac\u001b[31mme Ltd']])
  expect(await texts(ui)).toEqual(['Acme Ltd', AS_IT_IS_NOW, 'Kim leads IT', 'Current', 'Audit under way'])
  const wraps = (await inView(ui, 'Text')).map(found => found.props['wrap'])
  expect(wraps).not.toEqual([])
  expect(wraps.every(wrap => wrap === 'wrap')).toBe(true)
  await ui.unmount()
})

test('a launcher that cannot be started says could not read', async ($, on) => {
  // Covers: B190
  const fake = givenAcme()
  await start($, on, fake)
  const ui = await startView($)
  fake.runFails = 'timed out'

  await ui.press({ key: 'topic:0' })

  expect((await texts(ui)).some(line => line.startsWith('m2b could not read the topic: could not run '))).toBe(true)
  await ui.unmount()
})

// What the module keeps cannot be read from outside it, and the engine loads the mod's modules
// apart from a test's own import. So the keeping is tested here on the module itself; the tests
// above hold what it comes to in the pane and in the session's state.
test('the lines are kept for the press that asked, and turning the pane away drops them', () => {
  // Covers: B190
  const lines: TopicLook = { state: 'read', facts: [KIM], current: [] }
  beginTopic('p1')
  expect(heldTopic('p1')).toEqual({ state: 'reading' })
  expect(fillTopic('p1', lines)).toBe(true)
  expect(heldTopic('p1')).toEqual(lines)

  // The view of that very press keeps them; a redraw or a second write of the view changes nothing.
  forgetTopicUnless({ kind: 'topic', name: 'Acme Ltd', press: 'p1', isRead: true })
  expect(heldTopic('p1')).toEqual(lines)

  for (const other of [null, { kind: 'review' }, { kind: 'proposals' }, { kind: 'topic', name: 'Acme Ltd', press: 'p2', isRead: false }] as const) {
    beginTopic('p1')
    fillTopic('p1', lines)
    forgetTopicUnless(other)
    expect(holdsTopic()).toBe(false)
    expect(heldTopic('p1')).toEqual({ state: 'reading' })
  }
})

test('an answer for a press the pane turned away from is not kept', () => {
  // Covers: B190
  const lines: TopicLook = { state: 'read', facts: [KIM], current: [] }
  beginTopic('p1')
  forgetTopicUnless(null)
  expect(fillTopic('p1', lines)).toBe(false)
  expect(holdsTopic()).toBe(false)

  // Nor for an earlier press on the same topic, once a later one asked.
  beginTopic('p1')
  beginTopic('p2')
  expect(fillTopic('p1', lines)).toBe(false)
  expect(heldTopic('p2')).toEqual({ state: 'reading' })
  expect(heldTopic('p1')).toEqual({ state: 'reading' })
  forgetTopicUnless(null)
})

/** A piece of text as drawn where a test names nothing else: to be read, in no color. */
function piece(text: string, look: Partial<ShownPiece> = {}): ShownPiece {
  return { text, color: undefined, dimColor: undefined, weight: undefined, strikethrough: undefined, ...look }
}

const DIM = { dimColor: true }
const NOT_READ = 'm2b could not read the topic: memory/MEMORY.md is not downloaded to this machine'

/** A look at a topic, and what the view draws of it below the line that says it is of now. */
const LOOKS: [what: string, look: TopicLook, below: ShownPiece[]][] = [
  ['while m2b reads', { state: 'reading' }, [piece(READING, DIM)]],
  [
    'a topic with facts and current items',
    { state: 'read', facts: [KIM, PAYS], current: [AUDIT] },
    [piece(KIM), piece(PAYS), piece('Current', { weight: 'bold' }), piece(AUDIT)],
  ],
  ['a topic without current items', { state: 'read', facts: [KIM], current: [] }, [piece(KIM)]],
  ['a topic with current items alone', { state: 'read', facts: [], current: [AUDIT] }, [piece('Current', { weight: 'bold' }), piece(AUDIT)]],
  ['a topic without lines', { state: 'read', facts: [], current: [] }, [piece(NO_LINES, DIM)]],
  ['a topic the distillate no longer holds', { state: 'missing' }, [piece(NO_TOPIC, DIM)]],
  [
    'a topic m2b could not read',
    { state: 'failed', error: 'memory/MEMORY.md is not downloaded to this machine' },
    [piece(NOT_READ, { color: 'error' })],
  ],
]

for (const [what, look, below] of LOOKS) {
  test(`the view of a topic is one part under the topic's name, whole: ${what}`, async ($, on) => {
    // Covers: B190, B208
    const name = 'Riverside Community Choir'
    on('ui.render', { component: 'Pane', requestId: 'topic-alone' }, (engine, e) => topicPane(engine, e, name, look, e.props.bodyColumns))

    const ui = await $.ui.mount({ ...pane('topic-alone'), plugin: 'test', surface: 'terminal' })

    expect(await shownParts(ui)).toEqual([{ key: 'topic', title: name, count: null, lines: [AS_IT_IS_NOW, ...below.map(drawn => drawn.text)] }])
    // The name is the part's title, in m2b's color, and stands nowhere else; that the lines are of now steps back.
    expect(await piecesAt(ui, 'part:topic')).toEqual([piece(name, { color: 'remember', weight: 'bold' }), piece(AS_IT_IS_NOW, DIM), ...below])
    // A topic is read, not answered: no count, never the color of what waits, and nothing stands in.
    expect(await partLook(ui, 'topic')).toEqual({
      borderStyle: 'round',
      borderColor: 'subtle',
      paddingX: 1,
      titleColor: 'remember',
      titleWeight: 'bold',
      countColor: undefined,
    })
    expect(await insetsAt(ui, 'part:topic')).toEqual([])
    // A name longer than its tab stands whole in the title, which wraps where the pane is narrow.
    expect(await lookOf(ui, name)).toEqual({ color: 'remember', dimColor: undefined, wrap: 'wrap' })
    expect(await viewButtons(ui)).toEqual([])
    await ui.unmount()
  })
}
