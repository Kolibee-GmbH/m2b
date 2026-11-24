import { expect, test } from 'claude-code/testing'
import type { CommandRunResult } from 'claude-code'
import type { Engine } from 'claude-code/testing'

import { currentItemOf, currentNoteKey, noteLabels } from '../../hooks/current-item'
import { opening } from '../../hooks/look'
import { BACK_TO_THE_FACT_FILE_KEY } from '../../hooks/pane-tabs'
import { holdsSource } from '../../hooks/source-view'
import { beginTopic, forgetTopicUnless, topicOriginOf } from '../../hooks/topic'
import { FakeM2b, NOW, pane, partLines, pressTab, shownTabs, start, viewButtons } from './harness'

const PANE = 'm2b'
const NOTE = '20261117T104540Z-cli-a1b2.md'
const OTHER_NOTE = '20261102T070000Z-phone-c3d4.md'
const WITH_A_NOTE = `Alex builds the shed with Sam, the roof is next [[${NOTE}]] (since 2026-11-17)`
const WITH_TWO_NOTES = `The offer for Acme is out, an answer is due in December [[${OTHER_NOTE}]] [[${NOTE}]] (since 2026-11-02)`
const WITHOUT_A_NOTE = 'Dana is on leave until spring (since 2026-10-01)'
const DOCUMENT = '20261020T090000Z-cli-5e6f.pdf'

const SHED = 'Alex builds the shed with Sam, the roof is next (since 2026-11-17)'
const OFFER = 'The offer for Acme is out, an answer is due in December (since 2026-11-02)'

const START_PART = 'facts:start'
const READ_NOTE = ['source', '--json', '--viewer', '--', NOTE]

function typed($: Engine, command: string): Promise<CommandRunResult> {
  return $.command.run({ command, args: '', origin: { kind: 'composer' }, presentation: { isFullscreen: false, columns: 100 } })
}

/** The note as `m2b source --json --viewer` answers for one without a file. */
function noteAnswer(name: string, day: string, words: string): Record<string, unknown> {
  return {
    name,
    kind: 'note',
    path: `corpus/2026/11/${name}`,
    day,
    captured: `${words}\n`,
    added: [],
    original_name: null,
    outline: [],
    original: null,
    original_here: null,
    opens: false,
    not_opened: null,
    file: null,
  }
}

/** A distillate with three current items outside any topic, one topic that holds the first of them, and the two notes. */
function world(): FakeM2b {
  const fake = new FakeM2b()
  fake.distillate = { facts: [], current: [WITH_A_NOTE, WITH_TWO_NOTES, WITHOUT_A_NOTE], topics: [{ name: 'Shed', facts: 1, current: 1 }] }
  fake.topicLines = { Shed: { facts: ['The shed stands behind the house.'], current: [WITH_A_NOTE] } }
  fake.viewerAnswers = {
    [NOTE]: noteAnswer(NOTE, '2026-11-17', 'The roof of the shed is next.'),
    [OTHER_NOTE]: noteAnswer(OTHER_NOTE, '2026-11-02', 'The offer for Acme went out.'),
  }
  return fake
}

/** The pane on the tab Facts. */
async function factsView($: Engine) {
  await typed($, 'm2b-pane')
  const ui = await $.ui.mount({ ...pane(PANE, 80), surface: 'terminal' })
  await pressTab(ui, 'facts')
  return ui
}

type On = Parameters<typeof start>[1]

/** Every write to the session's state, as JSON: that state is one every plugin can read. */
function stateWrites(on: On): string[] {
  const writes: string[] = []
  on('state.set', (_, e, next) => {
    writes.push(JSON.stringify(e))
    return next(e)
  })
  return writes
}

test('a current item is its words and since when, without the links to its notes; a link that names no note stays in the words', () => {
  // Covers: B242
  expect(currentItemOf(WITH_A_NOTE)).toEqual({ words: SHED, notes: [NOTE] })
  expect(currentItemOf(WITH_TWO_NOTES)).toEqual({ words: OFFER, notes: [OTHER_NOTE, NOTE] })
  expect(currentItemOf(WITHOUT_A_NOTE)).toEqual({ words: WITHOUT_A_NOTE, notes: [] })
  // A link at the end, before a full stop, and one in the middle of the words.
  expect(currentItemOf(`The roof is next [[${NOTE}]].`)).toEqual({ words: 'The roof is next.', notes: [NOTE] })
  expect(currentItemOf(`The roof [[${NOTE}]] is next`)).toEqual({ words: 'The roof is next', notes: [NOTE] })
  // A link at the very start, one before a bracket, and a line that is a link alone.
  expect(currentItemOf(`[[${NOTE}]] The roof is next`)).toEqual({ words: 'The roof is next', notes: [NOTE] })
  expect(currentItemOf(`The roof (with Sam [[${NOTE}]]) is next`)).toEqual({ words: 'The roof (with Sam) is next', notes: [NOTE] })
  expect(currentItemOf(`[[${NOTE}]]`)).toEqual({ words: '', notes: [NOTE] })
  // A document or a picture of the archive is named with its own ending.
  expect(currentItemOf(`The handbook is in [[${DOCUMENT}]] (since 2026-10-20)`)).toEqual({ words: 'The handbook is in (since 2026-10-20)', notes: [DOCUMENT] })
  // A fact file, a name with a folder, one without an ending, one with a space, one without the four signs and one in capitals
  // are no names of the archive: they are drawn as written.
  for (const other of [
    '[[dana.md]]',
    '[[../20261117T104540Z-cli-a1b2.md]]',
    '[[20261117T104540Z-cli-a1b2]]',
    '[[20261117T104540Z cli.md]]',
    '[[20261117T104540Z-Acme.md]]',
    '[[20261117T104540Z-CLI-A1B2.md]]',
  ]) {
    expect(currentItemOf(`Seen ${other} today`)).toEqual({ words: `Seen ${other} today`, notes: [] })
  }
})

test('nothing of a line but its links is changed: spaces before a mark, two spaces and a dot after a space stay as written', () => {
  // Covers: B242
  for (const line of ['Dana keeps the keys in .env files (since 2026-10-01)', 'Ratio 3 : 1 for the paint', 'Two  spaces, and a tab\there']) {
    expect(currentItemOf(line)).toEqual({ words: line, notes: [] })
  }
  expect(currentItemOf(`Dana keeps the keys in .env files [[${NOTE}]] (since 2026-10-01)`).words).toBe('Dana keeps the keys in .env files (since 2026-10-01)')
})

test('a topic keeps the tab it was opened from, which is where a note opened in it leads back; the overview where nothing says otherwise', () => {
  // Covers: B242
  beginTopic('t1', 'Shed', 'facts')
  expect(topicOriginOf('t1')).toBe('facts')
  expect(topicOriginOf('another press')).toBe('overview')
  beginTopic('t2', 'Shed')
  expect(topicOriginOf('t2')).toBe('overview')
  forgetTopicUnless(null)
  expect(topicOriginOf('t2')).toBe('overview')
})

// Zurich, an hour ahead of UTC in winter and two in summer; New York, five hours behind in winter.
const ZURICH = (ms: number) => (ms >= Date.UTC(2026, 2, 29, 1) && ms < Date.UTC(2026, 9, 25, 1) ? 120 : 60)
const NEW_YORK = () => -300

test("a note's button bears the day it was captured in the owner's time zone, the year where it is not this one, and the time where two fall on one day", () => {
  // Covers: B314
  const at = (moment: string) => `${moment}-cli-a1b2.md`
  expect(noteLabels([at('20261117T104540Z'), at('20261102T070000Z')], NOW, ZURICH)).toEqual(['17 Nov', '2 Nov'])
  // Two on one day: each with its time, on the owner's clock.
  expect(noteLabels([at('20261117T104540Z'), at('20261117T170000Z')], NOW, ZURICH)).toEqual(['17 Nov 11:45', '17 Nov 18:00'])
  // A day is the owner's: late in the evening in UTC is the next morning in Zurich, and the same day in New York.
  expect(noteLabels([at('20261117T233000Z'), at('20261117T100000Z')], NOW, ZURICH)).toEqual(['18 Nov', '17 Nov'])
  expect(noteLabels([at('20261118T030000Z'), at('20261117T100000Z')], NOW, NEW_YORK)).toEqual(['17 Nov 22:00', '17 Nov 05:00'])
  // Summer time is the offset of the note's moment, not of now.
  expect(noteLabels([at('20260701T221500Z'), at('20260701T080000Z')], NOW, ZURICH)).toEqual(['2 Jul', '1 Jul'])
  // A day of another year than now's bears its year; two such on one day their times too.
  expect(noteLabels([at('20251201T120000Z'), at('20261201T120000Z')], NOW, ZURICH)).toEqual(['1 Dec 2025', '1 Dec'])
  expect(noteLabels([at('20251201T120000Z'), at('20251201T150000Z')], NOW, ZURICH)).toEqual(['1 Dec 2025 13:00', '1 Dec 2025 16:00'])
  // Two in one minute: with their seconds, so each button tells its note.
  expect(noteLabels([at('20261117T104540Z'), at('20261117T104512Z'), at('20261117T170000Z')], NOW, ZURICH)).toEqual([
    '17 Nov 11:45:40',
    '17 Nov 11:45:12',
    '17 Nov 18:00',
  ])
  // A name that says no moment that can be is labelled by its place.
  expect(noteLabels([at('20261131T120000Z'), at('20261117T104540Z')], NOW, ZURICH)).toEqual(['note 1', '17 Nov'])
})

test('under Current in the tab Facts no line holds a file name: an item with one note is its own row that opens it, one with two notes has a button with the day of each, one without a note no button', async ($, on) => {
  // Covers: B242, B226, B314
  await start($, on, world())

  const ui = await factsView($)

  const [other, note] = noteLabels([OTHER_NOTE, NOTE], NOW)
  expect(await partLines(ui, START_PART)).toEqual(['Current', opening(SHED), OFFER, `[${other}] [${note}]`, WITHOUT_A_NOTE])
  const drawn = (await partLines(ui, START_PART))?.join('\n') ?? ''
  expect(drawn).not.toContain('[[')
  expect(drawn).not.toContain('.md')
  expect((await viewButtons(ui)).filter(key => key.startsWith('current-note:'))).toEqual([
    currentNoteKey(0, 0),
    currentNoteKey(1, 0),
    currentNoteKey(1, 1),
  ])
  await ui.unmount()
})

test("an item's row opens its note under a seventh tab as a source of a fact file opens: m2b reads that note alone, the tab says note and its day, no tab of a fact file stands above it, and the tab Facts leads back", async ($, on) => {
  // Covers: B242, B230
  const fake = world()
  await start($, on, fake)
  const ui = await factsView($)
  const callsBefore = fake.calls.length

  await ui.press({ key: currentNoteKey(0, 0) })

  expect(fake.calls.slice(callsBefore).filter(call => call[0] === 'source')).toEqual([READ_NOTE])
  const tabs = await shownTabs(ui)
  expect(tabs).toHaveLength(7)
  expect(tabs.at(-1)).toEqual({ label: 'note 2026-11-17', key: null })
  expect(tabs.map(tab => tab.key)).not.toContain(BACK_TO_THE_FACT_FILE_KEY)
  // The tab Facts stands above the note as a button: the way back.
  expect(tabs.map(tab => tab.key)).toContain('tab:facts:in:aside')
  expect((await partLines(ui, 'source'))?.join('\n')).toContain('The roof of the shed is next.')

  // The six tabs lead out; Facts leads back to the items, read anew.
  await pressTab(ui, 'facts')
  expect((await partLines(ui, START_PART))?.slice(0, 2)).toEqual(['Current', opening(SHED)])
  expect(holdsSource()).toBe(false)
  await ui.unmount()
})

test('the second button of an item with two notes opens the second note it names', async ($, on) => {
  // Covers: B242
  const fake = world()
  await start($, on, fake)
  const ui = await factsView($)

  await ui.press({ key: currentNoteKey(1, 0) })
  expect((await shownTabs(ui)).at(-1)).toEqual({ label: 'note 2026-11-02', key: null })
  await pressTab(ui, 'facts')
  await ui.press({ key: currentNoteKey(1, 1) })

  expect((await shownTabs(ui)).at(-1)).toEqual({ label: 'note 2026-11-17', key: null })
  expect(fake.calls.filter(call => call[0] === 'source').map(call => call.at(-1))).toEqual([OTHER_NOTE, NOTE])
  await ui.unmount()
})

test('a note that is not on this machine says so with the command that fetches it: m2b is asked once, and nothing fetches it', async ($, on) => {
  // Covers: B242, B230
  const fake = world()
  fake.viewerAnswers = { [NOTE]: { name: NOTE, kind: 'not read', fetch: 'm2b store fetch corpus/2026/11', reason: null } }
  await start($, on, fake)
  const ui = await factsView($)

  const callsBefore = fake.calls.length

  await ui.press({ key: currentNoteKey(0, 0) })

  expect(fake.calls.slice(callsBefore).filter(call => call[0] === 'source' || call[0] === 'store')).toEqual([READ_NOTE])
  expect((await partLines(ui, 'source'))?.join('\n')).toContain('not downloaded to this machine; m2b store fetch corpus/2026/11 fetches it')
  // Its tab keeps the word it had while it was read: nothing says what the note is.
  expect((await shownTabs(ui)).at(-1)).toEqual({ label: 'note', key: null })
  await ui.unmount()
})

test("a topic's current items are drawn the same way, and an item's row opens its note under the seventh tab in place of the topic's", async ($, on) => {
  // Covers: B242, B190
  const fake = world()
  await start($, on, fake)
  const ui = await factsView($)
  await ui.press({ key: 'facts-topic:0' })

  const topic = (await partLines(ui, 'topic')) ?? []
  expect(topic.slice(-2)).toEqual(['Current', opening(SHED)])
  expect(topic.join('\n')).not.toContain('[[')

  await ui.press({ key: currentNoteKey(0, 0) })

  expect((await shownTabs(ui)).at(-1)).toEqual({ label: 'note 2026-11-17', key: null })
  expect((await partLines(ui, 'source'))?.join('\n')).toContain('The roof of the shed is next.')
  await ui.unmount()
})

test("the name of a note a current item names never reaches the session's state: not while the item is drawn, not while the note is shown", async ($, on) => {
  // Covers: B242, B224
  const writes = stateWrites(on)
  await start($, on, world())
  const ui = await factsView($)

  await ui.press({ key: currentNoteKey(0, 0) })
  await pressTab(ui, 'facts')
  await ui.press({ key: 'facts-topic:0' })
  await ui.press({ key: currentNoteKey(0, 0) })

  const kept = writes.join('\n')
  expect(kept).toContain('"kind":"source"')
  expect(kept).not.toContain(NOTE)
  expect(kept).not.toContain(OTHER_NOTE)
  // Nor the words of the item or of the note.
  expect(kept).not.toContain('roof')
  await ui.unmount()
})
