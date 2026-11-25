import { expect, test } from 'claude-code/testing'
import type { CommandRunResult } from 'claude-code'
import type { Engine } from 'claude-code/testing'

import { beginFactFile, forgetFactsUnless, topicOfFactFile } from '../../hooks/facts-tab'
import { opening } from '../../hooks/look'
import { BACK_TO_THE_FACT_FILE_KEY, BACK_TO_THE_TOPIC_KEY } from '../../hooks/pane-tabs'
import { beginTopic, fillTopic, forgetTopicUnless, holdsTopic, parseTopic, topicFactKey } from '../../hooks/topic'
import { FakeM2b, pane, partLines, pressTab, shownTabs, start, texts, viewButtons } from './harness'

const PANE = 'm2b'
const AS_IT_IS_NOW = 'As the distillate holds it now, which may differ from what this session was given.'
const KIM = "Kim Lee leads Acme's IT"
const PAYS = 'Acme pays within 30 days'
const SIGNED = 'The framework contract is signed'
const AUDIT = 'Export audit under way (since 2026-11-02)'
const READ_ACME = ['distillate', 'topic', '--json', '--', 'Acme Ltd']
const READ_PAYS = ['source', '--json', '--viewer', '--', 'acme.md']
const OTHER_SHAPE = 'm2b answered something other than a topic'
const EVIDENCE = '20261012T081500Z-claude-3f2a.md'
const SIX = ['overview', 'proposals', 'review', 'tasks', 'facts', 'settings'] as const
const LABELS = ['Overview', 'Proposals', 'Review', 'Tasks', 'Facts', 'Settings']

function typed($: Engine, command: string): Promise<CommandRunResult> {
  return $.command.run({ command, args: '', origin: { kind: 'composer' }, presentation: { isFullscreen: false, columns: 100 } })
}

/** Acme's fact file: one line and one note it rests on. */
function acmeFile(): Record<string, unknown> {
  return {
    name: 'acme.md',
    kind: 'fact file',
    path: 'memory/acme.md',
    title: 'Acme Ltd',
    until: null,
    lines: ['Pays within 30 days.'],
    earlier: [],
    evidence: [
      { name: EVIDENCE, state: 'read', day: '2026-10-12', kind: 'note', original_name: null, first_line: 'Acme pays in 30 days.', path: `corpus/2026/10/${EVIDENCE}`, fetch: null, reason: null },
    ],
  }
}

/**
 * A session given the topic Acme Ltd: three facts, the first and the second naming a fact file and
 * the third none, and a current item.
 */
function givenAcme(): FakeM2b {
  const fake = new FakeM2b()
  fake.given = { topics: [{ name: 'Acme Ltd', facts: 3, current: 1 }], atStart: 'whole', offUnder: null }
  fake.topicLines = { 'Acme Ltd': { facts: [KIM, PAYS, SIGNED], current: [AUDIT], files: ['kim-lee.md', 'acme.md', null] } }
  fake.sourceAnswer = acmeFile()
  fake.viewerAnswers = {
    [EVIDENCE]: {
      name: EVIDENCE,
      kind: 'note',
      path: `corpus/2026/10/${EVIDENCE}`,
      day: '2026-10-12',
      captured: 'Acme pays in 30 days.\n',
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
  return fake
}

/** The pane on the topic's view, opened from the start view. */
async function topicView($: Engine) {
  await typed($, 'm2b-pane')
  const ui = await $.ui.mount({ ...pane(PANE, 80), surface: 'terminal' })
  await ui.press({ key: 'topic:0' })
  return ui
}

/** The tabs above a fact file opened from the topic Acme Ltd. */
function tabsAboveTheFile(): { label: string; key: string | null }[] {
  return [
    ...SIX.map((id, at) => ({ label: LABELS[at] ?? '', key: `tab:${id}:in:aside` })),
    { label: 'Acme Ltd', key: BACK_TO_THE_TOPIC_KEY },
    { label: 'acme', key: 'tab:fact:shown' },
  ]
}

test('m2b names each fact of a topic with its fact file in a key of its own; a core before it names none, and a key of another shape is could not read', () => {
  // Covers: B190, B313
  const answer = { name: 'Acme Ltd', found: true, facts: [KIM, SIGNED], current: [] }
  const withFiles = [
    { statement: KIM, file: 'kim-lee.md' },
    { statement: SIGNED, file: null },
  ]
  expect(parseTopic(JSON.stringify({ ...answer, facts_with_files: withFiles }))).toEqual({ state: 'read', facts: withFiles, current: [] })
  expect(parseTopic(JSON.stringify(answer))).toEqual({
    state: 'read',
    facts: [
      { statement: KIM, file: null },
      { statement: SIGNED, file: null },
    ],
    current: [],
  })
  for (const other of [
    [{ statement: KIM, file: 'kim-lee.md' }],
    [{ statement: SIGNED, file: 'kim-lee.md' }, { statement: KIM, file: null }],
    [{ statement: KIM, file: 3 }, { statement: SIGNED, file: null }],
    [KIM, SIGNED],
    'kim-lee.md',
    null,
  ]) {
    expect(parseTopic(JSON.stringify({ ...answer, facts_with_files: other }))).toEqual({ state: 'failed', error: OTHER_SHAPE })
  }
})

test("in a topic's view a fact that names its fact file is a row that opens it, and one that names none is its words", async ($, on) => {
  // Covers: B190
  await start($, on, givenAcme())

  const ui = await topicView($)

  expect(await partLines(ui, 'topic')).toEqual([AS_IT_IS_NOW, opening(KIM), opening(PAYS), SIGNED, 'Current', AUDIT])
  expect(await viewButtons(ui)).toEqual([topicFactKey(0), topicFactKey(1)])
  await ui.unmount()
})

test("a core before the files names none: the topic's facts are its words, and nothing opens", async ($, on) => {
  // Covers: B190
  const fake = givenAcme()
  fake.namesFactFiles = false
  await start($, on, fake)

  const ui = await topicView($)

  expect(await partLines(ui, 'topic')).toEqual([AS_IT_IS_NOW, KIM, PAYS, SIGNED, 'Current', AUDIT])
  expect(await viewButtons(ui)).toEqual([])
  await ui.unmount()
})

test("a fact's row opens its file under the tab beside the topic's, which bears the topic's name and leads back, and the focus is asked for that tab", async ($, on) => {
  // Covers: B190, B204, B227
  const fake = givenAcme()
  await start($, on, fake)
  const ui = await topicView($)
  const before = (await ui.findAll({ type: 'Button' })).map(button => String(button.key))
  const callsBefore = fake.calls.length

  await ui.press({ key: topicFactKey(1) })

  expect(fake.calls.slice(callsBefore).filter(call => call[0] === 'source' || call[0] === 'distillate')).toEqual([READ_PAYS])
  expect(await partLines(ui, 'fact')).toEqual(['[correct] [edit]', 'Pays within 30 days.'])
  expect(await shownTabs(ui)).toEqual(tabsAboveTheFile())
  // The key the focus is asked for is drawn above the file and was drawn by no view before: Claude Code finds it there.
  expect(before).not.toContain(BACK_TO_THE_TOPIC_KEY)
  await ui.unmount()
})

test("the topic's tab leads back to the lines as they were drawn, without reading them again, and the focus is asked for the fact's row", async ($, on) => {
  // Covers: B190, B204
  const fake = givenAcme()
  await start($, on, fake)
  const ui = await topicView($)
  const drawn = await partLines(ui, 'topic')
  await ui.press({ key: topicFactKey(1) })
  // The distillate changed meanwhile: the way back shows the topic as it was read.
  fake.topicLines = { 'Acme Ltd': { facts: ['Acme moved to Basel'], current: [] } }
  const before = (await ui.findAll({ type: 'Button' })).map(button => String(button.key))

  await ui.press({ key: BACK_TO_THE_TOPIC_KEY })

  expect(await partLines(ui, 'topic')).toEqual(drawn)
  expect(fake.topicCalls()).toEqual([READ_ACME])
  expect((await shownTabs(ui)).at(-1)).toEqual({ label: 'Acme Ltd', key: null })
  // The key the focus is asked for is the row of the fact the file was opened from: drawn now, and by no button of the file.
  expect(await viewButtons(ui)).toContain(topicFactKey(1))
  expect(before).not.toContain(topicFactKey(1))
  // From there the row opens the file again, read anew.
  await ui.press({ key: topicFactKey(1) })
  expect(fake.sourceCalls()).toEqual([READ_PAYS, READ_PAYS])
  await ui.unmount()
})

test("a source of a fact file opened from a topic stands beside the file's tab, and the way back leads to the file and from there to the topic", async ($, on) => {
  // Covers: B190, B204, B230, B232
  const fake = givenAcme()
  await start($, on, fake)
  const ui = await topicView($)
  await ui.press({ key: topicFactKey(1) })

  await ui.press({ key: 'show:0' })

  const tabs = await shownTabs(ui)
  expect(tabs.slice(6)).toEqual([
    { label: 'acme', key: BACK_TO_THE_FACT_FILE_KEY },
    { label: 'note 2026-10-12', key: null },
  ])
  expect((await partLines(ui, 'source'))?.join('\n')).toContain('Acme pays in 30 days.')

  await ui.press({ key: BACK_TO_THE_FACT_FILE_KEY })
  expect(await shownTabs(ui)).toEqual(tabsAboveTheFile())
  await ui.press({ key: BACK_TO_THE_TOPIC_KEY })
  expect(await texts(ui)).toContain(opening(PAYS))
  expect(fake.topicCalls()).toEqual([READ_ACME])
  await ui.unmount()
})

test('one of the six tabs leads out of the fact file, and the topic is no longer one to go back to', async ($, on) => {
  // Covers: B190, B204
  const fake = givenAcme()
  await start($, on, fake)
  const ui = await topicView($)
  await ui.press({ key: topicFactKey(0) })

  await pressTab(ui, 'facts')

  expect((await shownTabs(ui)).map(tab => tab.label)).toEqual(LABELS)
  expect((await shownTabs(ui)).map(tab => tab.key)).not.toContain(BACK_TO_THE_TOPIC_KEY)
  await ui.unmount()
})

type On = Parameters<typeof start>[1]

test("the session's state, which every plugin can read, holds neither a fact of the topic nor the name of its fact file", async ($, on: On) => {
  // Covers: B190, B224
  const writes: string[] = []
  on('state.set', (_, e, next) => {
    writes.push(JSON.stringify(e))
    return next(e)
  })
  await start($, on, givenAcme())
  const ui = await topicView($)

  await ui.press({ key: topicFactKey(1) })
  await ui.press({ key: 'show:0' })
  await ui.press({ key: BACK_TO_THE_FACT_FILE_KEY })
  await ui.press({ key: BACK_TO_THE_TOPIC_KEY })

  const kept = writes.join('\n')
  expect(kept).toContain('"kind":"fact"')
  for (const line of [KIM, PAYS, 'acme.md', 'kim-lee', EVIDENCE, 'Pays within 30 days.']) {
    expect(kept).not.toContain(line)
  }
  await ui.unmount()
})

// What the modules keep cannot be read from outside them, and the engine loads the mod's modules
// apart from a test's own import. So the keeping is tested here on the modules themselves.
test("a topic's lines stay while a fact file opened from it, or a source of that file, is shown; any other view drops them", () => {
  // Covers: B190
  beginTopic('t1', 'Acme Ltd')
  fillTopic('t1', { state: 'read', facts: [{ statement: PAYS, file: 'acme.md' }], current: [] })
  beginFactFile('f1', 'acme.md', { press: 't1', index: 0 })
  expect(topicOfFactFile('f1')).toEqual({ press: 't1', index: 0 })
  expect(topicOfFactFile('f2')).toBeNull()

  forgetTopicUnless({ kind: 'fact', press: 'f1', drawn: 0 }, 't1')
  expect(holdsTopic()).toBe(true)
  forgetTopicUnless({ kind: 'source', press: 's1', from: 'f1', drawn: 0 }, 't1')
  expect(holdsTopic()).toBe(true)
  forgetTopicUnless({ kind: 'fact', press: 'f3', drawn: 0 }, 'another topic')
  expect(holdsTopic()).toBe(false)

  // A fact file opened from the tab Facts names no topic.
  beginFactFile('f4', 'acme.md')
  expect(topicOfFactFile('f4')).toBeNull()
  forgetFactsUnless(null)
  expect(topicOfFactFile('f4')).toBeNull()
})
