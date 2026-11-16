import { expect, test } from 'claude-code/testing'
import type { CommandRunResult } from 'claude-code'
import type { Engine } from 'claude-code/testing'

import {
  BAND,
  ENGINES_OWN_DRAWING,
  FakeM2b,
  HOME,
  NOW,
  OPEN,
  answerKeys,
  buttonsAt,
  everyText,
  insetsAt,
  linesAt,
  lookOf,
  pane,
  partLines,
  partLook,
  pressTab,
  rowSaying,
  sentenceOfM2b,
  shownBand,
  shownParts,
  shownTabs,
  start,
  startView,
  texts,
  viewButtons,
} from './harness'
import type { Files } from './harness'

const PANE = 'm2b'
const UNDO_MS = 5_000
const DANA = 'a1a1a1a1a1a1'
const LADDER = 'b2b2b2b2b2b2'
const SHED = 'c3c3c3c3c3c3'
const CACHE = `${HOME}/.local/state/m2b/band-answer.json`
const NO_TASKS = { candidates: [], review: null, error: null }
const NOT_LOOKED = 'm2b has not looked yet.'
/** Not looked, as a text says it, which has no pane to wait in. */
const NOT_LOOKED_SAYS_HOW = 'm2b has not looked for proposals yet; m2b proposals lists them in a shell'
const FROM_YOUR_SESSIONS = 'Proposals from your sessions'
const NONE_WAITS = 'No proposal waits for an answer.'
const LIST_AND_ANSWER =
  'list with: m2b proposals; keep with: m2b proposals keep <id>... (or keep --all); drop with: m2b proposals drop <id>...'
const FILED_BY_THE_NEXT_RUN = 'for the next curation run, which files what you kept'

/** How a line to be read, one that may be skipped and one in the color of trouble are drawn. */
const PLAIN = { color: undefined, dimColor: undefined, wrap: 'wrap' }
const DIM = { color: undefined, dimColor: true, wrap: 'wrap' }
const TROUBLE = { color: 'error', dimColor: undefined, wrap: 'wrap' }
/** How far the words a proposal stands on are indented under it. */
const INDENT = 2

function typed($: Engine, command: string): Promise<CommandRunResult> {
  return $.command.run({
    command,
    args: '',
    origin: { kind: 'composer' },
    presentation: { isFullscreen: false, columns: 100 },
  })
}

function proposedFake(): FakeM2b {
  return new FakeM2b()
    .proposal(DANA, 'Dana is head of IT at Northwind.', 'Dana runs IT at Northwind', { topic: 'Northwind', day: '2026-03-04' })
    .proposal(LADDER, 'Call Sam about the ladder.', 'I still have to call Sam', {
      kind: 'commitment',
      due: '2026-03-06',
      day: '2026-03-04',
    })
    .proposal(SHED, 'The spare key is in the shed.', 'the spare key is in the shed', { kind: 'personal', day: '2026-03-05' })
}

/** The buttons of the view itself: the tabs, which stand above every view, are left out. */
const buttons = viewButtons

/** The lines of the overview's part "Waits for you", below its title. */
function waits(ui: Parameters<typeof partLines>[0]): Promise<string[] | null> {
  return partLines(ui, 'waits')
}

/** The view of the proposals as its one part: the count beside its title, and the lines below. */
function oneProposalsPart(count: string | null, lines: string[]) {
  return [{ key: 'proposals', title: FROM_YOUR_SESSIONS, count, lines }]
}

test('while proposals wait the band counts each, and the pane has one row with their number that names their tab, and counts them on that tab, whatever the number', async ($, on) => {
  // Covers: B127
  const fake = proposedFake()
  const { clock } = await start($, on, fake)
  const band = await $.ui.mount({ ...BAND, surface: 'terminal' })
  const ui = await startView($)

  expect(await shownBand(band)).toEqual(rowSaying('3 wait for you'))
  // One row for all of them, never one per proposal, and nothing to press: their tab leads to them.
  expect(await waits(ui)).toEqual(['3 proposals from your sessions', 'in the tab Proposals'])
  expect(await buttons(ui)).toEqual([])
  expect((await shownTabs(ui)).map(tab => tab.label)).toEqual(['Overview', 'Proposals 3', 'Review', 'Settings'])

  fake.proposals = fake.proposals?.slice(0, 1) ?? null
  await clock.advance(60_000)
  expect(await shownBand(band)).toEqual(rowSaying('1 waits for you'))
  expect(await waits(ui)).toEqual(['1 proposal from your sessions', 'in the tab Proposals'])
  expect(await buttons(ui)).toEqual([])
  expect((await shownTabs(ui)).map(tab => tab.label)).toEqual(['Overview', 'Proposals 1', 'Review', 'Settings'])
  await ui.unmount()
  await band.unmount()
})

test('with no proposal waiting the band counts none, the pane has no line for them and their tab says no number', async ($, on) => {
  // Covers: B127
  const fake = proposedFake()
  for (const proposed of fake.proposals ?? []) {
    proposed.answer = 'keep'
  }
  await start($, on, fake)
  const band = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await everyText(band)).toEqual([ENGINES_OWN_DRAWING])
  await band.unmount()

  const ui = await startView($)
  expect(await texts(ui)).toContain('Nothing waits for you.')
  expect(await buttons(ui)).toEqual([])
  expect((await shownTabs(ui)).map(tab => tab.label)).toEqual(['Overview', 'Proposals', 'Review', 'Settings'])
  await ui.unmount()
})

test('the task that tells a phone proposals wait is not counted in the band and is no row in the pane', async ($, on) => {
  // Covers: B127
  const fake = proposedFake().candidate('c1', 'Remember? Acme moved')
  fake.tasks.push({
    id: 't-proposals',
    title: 'm2b: proposals from your sessions',
    notes: 'm2b:proposals\n\n3 proposals from your sessions wait for your answer',
    completed: false,
    dropped: false,
    marker: 'proposals',
  })
  await start($, on, fake)
  const band = await $.ui.mount({ ...BAND, surface: 'terminal' })
  // The three proposals and the candidate.
  expect(await shownBand(band)).toEqual(rowSaying('4 wait for you'))
  await band.unmount()

  const ui = await startView($)
  expect(await waits(ui)).toEqual(['3 proposals from your sessions', 'in the tab Proposals', 'Remember? Acme moved', '[keep] [drop]'])
  expect(await buttons(ui)).toEqual(['keep:c1', 'drop:c1'])
  await ui.unmount()
})

test('open in the band, then the tab Proposals, lead to every proposal: its kind, the text, the words, the day, keep and drop, and keep all', async ($, on) => {
  // Covers: B127
  const fake = proposedFake()
  const { opened } = await start($, on, fake)
  const band = await $.ui.mount({ ...BAND, surface: 'terminal' })

  await band.press({ key: OPEN })
  await band.unmount()

  expect(opened.map(one => one.id)).toEqual([PANE])
  const ui = await $.ui.mount({ ...pane(PANE), surface: 'terminal' })
  expect(await texts(ui)).toContain('Waits for you')
  await pressTab(ui, 'proposals')
  expect(await shownParts(ui)).toEqual(
    oneProposalsPart('3', [
      '[keep all]',
      'Dana is head of IT at Northwind.',
      '[keep] [drop] person, topic Northwind',
      'said on 2026-03-04: "Dana runs IT at Northwind"',
      'Call Sam about the ladder.',
      '[keep] [drop] commitment, due 2026-03-06',
      'said on 2026-03-04: "I still have to call Sam"',
      'The spare key is in the shed.',
      '[keep] [drop] personal',
      'said on 2026-03-05: "the spare key is in the shed"',
    ]),
  )
  expect(await buttons(ui)).toEqual([
    'keep-all',
    `keep:${DANA}`,
    `drop:${DANA}`,
    `keep:${LADDER}`,
    `drop:${LADDER}`,
    `keep:${SHED}`,
    `drop:${SHED}`,
  ])
  await ui.unmount()
})

test('a proposal that stands on pasted text says pasted, one from a source the band does not know names it, and the others say said', async ($, on) => {
  // Covers: B172
  const fake = new FakeM2b()
    .proposal(DANA, 'Dana is head of IT at Northwind.', 'Dana runs IT at Northwind', { day: '2026-03-04', source: 'pasted' })
    .proposal(LADDER, 'Call Sam about the ladder.', 'I still have to call Sam', { day: '2026-03-04', source: 'typed' })
    .proposal(SHED, 'The spare key is in the shed.', 'the spare key is in the shed', { day: '2026-03-05', source: 'letter' })
    .proposal('d4d4d4d4d4d4', 'Kim moved to Globex.', 'Kim moved to Globex', { day: '2026-03-05' })
  await start($, on, fake)
  await typed($, 'm2b-proposals')

  const ui = await $.ui.mount({ ...pane(PANE), surface: 'terminal' })
  const said = (await texts(ui)).filter(line => line.includes(' on 2026-03-0'))
  expect(said).toEqual([
    'pasted on 2026-03-04: "Dana runs IT at Northwind"',
    'said on 2026-03-04: "I still have to call Sam"',
    'from letter on 2026-03-05: "the spare key is in the shed"',
    'said on 2026-03-05: "Kim moved to Globex"',
  ])
  await ui.unmount()
})

test('a proposal a session handed in says so, and its line names the tool of a result or Claude for an answer', async ($, on) => {
  // Covers: B179
  const handedIn = { day: '2026-03-04', by: 'session' }
  const fake = new FakeM2b()
    .proposal(DANA, 'Dana is head of IT at Northwind.', 'Dana runs IT at Northwind', {
      ...handedIn,
      source: 'tool',
      tool: 'mcp__mail__get_message',
    })
    .proposal(LADDER, 'Call Sam about the ladder.', 'I still have to call Sam', { ...handedIn, source: 'agent', tool: null })
    .proposal(SHED, 'The spare key is in the shed.', 'the spare key is in the shed', { ...handedIn, source: 'tool', tool: null })
    .proposal('d4d4d4d4d4d4', 'Kim moved to Globex.', 'Kim moved to Globex', { ...handedIn, source: 'typed' })
    .proposal('e5e5e5e5e5e5', 'Riley signs the orders.', 'Riley signs the orders', { day: '2026-03-04', by: null, tool: null })
  await start($, on, fake)
  await typed($, 'm2b-proposals')

  const ui = await $.ui.mount({ ...pane(PANE), surface: 'terminal' })
  const drawn = await texts(ui)
  expect(drawn.filter(line => line.includes(' on 2026-03-0'))).toEqual([
    'in a result of mcp__mail__get_message on 2026-03-04: "Dana runs IT at Northwind"',
    'Claude wrote on 2026-03-04: "I still have to call Sam"',
    'in a result of a tool on 2026-03-04: "the spare key is in the shed"',
    'said on 2026-03-04: "Kim moved to Globex"',
    'said on 2026-03-04: "Riley signs the orders"',
  ])
  // Each handed-in proposal says so in its heading, typed words too; the one a reading found does not.
  expect(drawn.filter(line => line.endsWith('handed in by a session'))).toEqual(Array(4).fill('person, handed in by a session'))
  expect(drawn.filter(line => line === 'person')).toEqual(['person'])
  await ui.unmount()
})

test('the proposals command opens the same pane, also while nothing waits', async ($, on) => {
  // Covers: B127
  const fake = new FakeM2b()
  const { opened, commands } = await start($, on, fake)

  const answer = await typed($, 'm2b-proposals')

  expect(commands.find(command => command.name === 'm2b-proposals')?.immediate).toBe(true)
  expect(answer.text).toBe('the proposals from your sessions are in the m2b pane')
  expect(opened.map(one => one.id)).toEqual([PANE])
  const ui = await $.ui.mount({ ...pane(PANE), surface: 'terminal' })
  expect(await shownParts(ui)).toEqual(oneProposalsPart(null, [NONE_WAITS]))
  expect(await lookOf(ui, NONE_WAITS)).toEqual(DIM)
  expect(await buttons(ui)).toEqual([])
  await ui.unmount()
})

test('where no pane can be shown the command answers with the proposals and how to answer them', async ($, on) => {
  // Covers: B127
  const fake = proposedFake()
  fake.paneWaits = 'no terminal is attached'
  await start($, on, fake)

  const answer = await typed($, 'm2b-proposals')

  expect(answer.text?.split('\n')).toEqual([
    'the m2b pane cannot be shown here: no terminal is attached',
    '3 proposals from your sessions',
    LIST_AND_ANSWER,
    `${DANA}  person, topic Northwind`,
    '  Dana is head of IT at Northwind.',
    '  said on 2026-03-04: "Dana runs IT at Northwind"',
    `${LADDER}  commitment, due 2026-03-06`,
    '  Call Sam about the ladder.',
    '  said on 2026-03-04: "I still have to call Sam"',
    `${SHED}  personal`,
    '  The spare key is in the shed.',
    '  said on 2026-03-05: "the spare key is in the shed"',
  ])
})

test('a text answer too long to give whole still says how to list and answer, before the proposals it has room for', async ($, on) => {
  // Covers: B127
  const fake = new FakeM2b()
  for (const n of [1, 2, 3, 4, 5, 6, 7]) {
    fake.proposal(`${n}`.repeat(12), `Dana prefers tea ${n}.`)
  }
  const kept = fake.proposals?.[0]
  if (kept !== undefined) {
    kept.answer = 'keep'
  }
  fake.proposal('8'.repeat(12), 'Dana prefers tea 8.')
  fake.paneWaits = 'no terminal is attached'
  await start($, on, fake)

  const lines = (await typed($, 'm2b-proposals')).text?.split('\n') ?? []

  expect(lines.slice(0, 5)).toEqual([
    'the m2b pane cannot be shown here: no terminal is attached',
    '7 proposals from your sessions',
    LIST_AND_ANSWER,
    `1 answer waits ${FILED_BY_THE_NEXT_RUN}`,
    `${'2'.repeat(12)}  person`,
  ])
  expect(lines).toHaveLength(22)
  expect(lines.at(-1)).toBe('and 4 more lines')
})

test('before the band could look, the pane and the text answer say so and never that nothing waits', async ($, on) => {
  // Covers: B127
  const fake = proposedFake()
  fake.statusFails = true
  await start($, on, fake)

  await typed($, 'm2b-proposals')
  const ui = await $.ui.mount({ ...pane(PANE), surface: 'terminal' })
  // Not known is no count and not the color of what waits, and it is not "none waits".
  expect(await shownParts(ui)).toEqual(oneProposalsPart(null, [NOT_LOOKED]))
  expect(await lookOf(ui, NOT_LOOKED)).toEqual(DIM)
  expect(await buttons(ui)).toEqual([])
  await ui.unmount()

  fake.paneWaits = 'no terminal is attached'
  const answer = await typed($, 'm2b-proposals')
  expect(answer.text?.split('\n')).toEqual(['the m2b pane cannot be shown here: no terminal is attached', NOT_LOOKED_SAYS_HOW])
})

test('open on a surface without panes says so in the band, and names the command that answers with the lines', async ($, on) => {
  // Covers: B127
  const fake = proposedFake()
  fake.paneWaits = 'no terminal is attached'
  const { openPanes } = await start($, on, fake)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })

  await ui.press({ key: OPEN })

  expect(await shownBand(ui)).toEqual(
    rowSaying('the m2b pane cannot be shown here: no terminal is attached; /m2b-pane answers with the lines'),
  )
  expect(openPanes.has(PANE)).toBe(false)
  const answer = await typed($, 'm2b-pane')
  expect(answer.text?.split('\n')).toContain('  3 proposals from your sessions: /m2b-proposals')
  await ui.unmount()
})

test('keep is written once the undo window is over, and the pane and the band follow without a curation run', async ($, on) => {
  // Covers: B127
  const fake = proposedFake()
  const { clock } = await start($, on, fake)
  await typed($, 'm2b-proposals')
  const ui = await $.ui.mount({ ...pane(PANE), surface: 'terminal' })
  const band = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await shownBand(band)).toEqual(rowSaying('3 wait for you'))

  await ui.press({ key: `keep:${DANA}` })
  expect(await linesAt(ui, `row:${DANA}`)).toEqual(['Dana is head of IT at Northwind.', '[undo] keeping'])
  expect(await buttons(ui)).toContain(`undo:${DANA}`)
  await clock.advance(UNDO_MS - 1)
  expect(fake.answers()).toEqual([])
  await clock.advance(1)

  expect(fake.answers()).toEqual([['proposals', 'keep', DANA]])
  const [shown] = await shownParts(ui)
  expect(shown?.count).toBe('2')
  expect(await linesAt(ui, `proposal:${DANA}`)).toBeNull()
  expect(shown?.lines).not.toContain('Dana is head of IT at Northwind.')
  expect(shown?.lines.at(-1)).toBe(`1 answer waits ${FILED_BY_THE_NEXT_RUN}`)
  expect(await lookOf(ui, `1 answer waits ${FILED_BY_THE_NEXT_RUN}`)).toEqual(DIM)
  expect(await shownBand(band)).toEqual(rowSaying('2 wait for you'))
  await band.unmount()
  await ui.unmount()
})

test('drop, then undo within the window, answers nothing', async ($, on) => {
  // Covers: B127
  const fake = proposedFake()
  const { clock } = await start($, on, fake)
  await typed($, 'm2b-proposals')
  const ui = await $.ui.mount({ ...pane(PANE), surface: 'terminal' })

  await ui.press({ key: `drop:${LADDER}` })
  expect(await linesAt(ui, `row:${LADDER}`)).toEqual(['Call Sam about the ladder.', '[undo] dropping'])
  await ui.press({ key: `undo:${LADDER}` })
  await ui.press({ key: `drop:${SHED}` })
  await clock.advance(UNDO_MS)

  expect(fake.answers()).toEqual([['proposals', 'drop', SHED]])
  expect((await texts(ui)).at(-1)).toBe(`1 answer waits ${FILED_BY_THE_NEXT_RUN}`)
  await ui.unmount()
})

test('keep all keeps the proposals the pane showed, in one call, and can be undone until then', async ($, on) => {
  // Covers: B127
  const fake = proposedFake()
  const { clock } = await start($, on, fake)
  await typed($, 'm2b-proposals')
  const ui = await $.ui.mount({ ...pane(PANE), surface: 'terminal' })

  await ui.press({ key: 'keep-all' })
  expect(await buttons(ui)).toEqual(['undo:all'])
  expect(await linesAt(ui, 'row:keep-all')).toEqual(['[undo] keeping all 3 proposals'])
  await ui.press({ key: 'undo:all' })
  await clock.advance(UNDO_MS)
  expect(fake.answers()).toEqual([])

  // One the pane did not show, as a curation run on another machine adds it meanwhile.
  await ui.press({ key: 'keep-all' })
  fake.proposal('d4d4d4d4d4d4', 'Robin moved to Lisbon.')
  await clock.advance(UNDO_MS)

  expect(fake.answers()).toEqual([['proposals', 'keep', DANA, LADDER, SHED]])
  expect(await shownParts(ui)).toEqual(
    oneProposalsPart('1', [
      'Robin moved to Lisbon.',
      '[keep] [drop] person',
      'said on 2026-03-12: "Robin moved to Lisbon."',
      `3 answers wait ${FILED_BY_THE_NEXT_RUN}`,
    ]),
  )
  expect(await buttons(ui)).toEqual(['keep:d4d4d4d4d4d4', 'drop:d4d4d4d4d4d4'])
  await ui.unmount()
})

test('keep all leaves what a session handed in, which is kept or dropped on its own', async ($, on) => {
  // Covers: B179
  const fake = new FakeM2b()
    .proposal(DANA, 'Dana is head of IT at Northwind.')
    .proposal(LADDER, 'Call Sam about the ladder.')
    .proposal(SHED, 'The spare key is in the shed.', 'the spare key is in the shed', { source: 'tool', tool: 'Read', by: 'session' })
  const { clock } = await start($, on, fake)
  await typed($, 'm2b-proposals')

  const ui = await $.ui.mount({ ...pane(PANE), surface: 'terminal' })
  await ui.press({ key: 'keep-all' })
  await clock.advance(6_000)

  expect(fake.answers()).toEqual([['proposals', 'keep', DANA, LADDER]])
  expect((fake.proposals ?? []).map(proposal => proposal.answer)).toEqual(['keep', 'keep', undefined])
  await ui.unmount()
})

test('keep all leaves out a proposal pressed on its own, which keeps its own answer', async ($, on) => {
  // Covers: B127
  const fake = proposedFake()
  const { clock } = await start($, on, fake)
  await typed($, 'm2b-proposals')
  const ui = await $.ui.mount({ ...pane(PANE), surface: 'terminal' })

  await ui.press({ key: `drop:${LADDER}` })
  await ui.press({ key: 'keep-all' })
  expect(await buttons(ui)).toEqual(['undo:all', `undo:${LADDER}`])
  await clock.advance(UNDO_MS)

  expect(fake.answers()).toEqual([
    ['proposals', 'drop', LADDER],
    ['proposals', 'keep', DANA, SHED],
  ])
  expect(fake.proposals?.map(proposed => proposed.answer)).toEqual(['keep', 'drop', 'keep'])
  await ui.unmount()
})

test('an answer m2b refuses stands in the view of the proposals until the next prompt, the band keeps counting, and the rows are read again', async ($, on) => {
  // Covers: B127, B207
  on('prompt.submit', (_, e) => ({ text: e.text, context: e.context }))
  const fake = proposedFake()
  const { clock } = await start($, on, fake)
  await typed($, 'm2b-proposals')
  const ui = await $.ui.mount({ ...pane(PANE), surface: 'terminal' })

  await ui.press({ key: `keep:${DANA}` })
  // Another machine drops it while the press waits.
  const dana = fake.proposals?.find(proposed => proposed.id === DANA)
  if (dana !== undefined) {
    dana.answer = 'drop'
  }
  await clock.advance(UNDO_MS)

  const refused = `m2b could not keep "Dana is head of IT at Northwind.": ${DANA} is answered with drop already; that answer stands`
  // Said where it was pressed, in the color of trouble: above keep all and the proposals that still wait.
  expect(await shownParts(ui)).toEqual(
    oneProposalsPart('2', [
      refused,
      '[keep all]',
      'Call Sam about the ladder.',
      '[keep] [drop] commitment, due 2026-03-06',
      'said on 2026-03-04: "I still have to call Sam"',
      'The spare key is in the shed.',
      '[keep] [drop] personal',
      'said on 2026-03-05: "the spare key is in the shed"',
      `1 answer waits ${FILED_BY_THE_NEXT_RUN}`,
    ]),
  )
  expect(await lookOf(ui, refused)).toEqual(TROUBLE)
  expect(await buttons(ui)).not.toContain(`keep:${DANA}`)
  const band = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await shownBand(band)).toEqual(rowSaying('2 wait for you'))

  await $.prompt.submit({ text: 'what is on today?', context: [], wait: false, origin: { kind: 'composer' } })
  expect(await texts(ui)).not.toContain(refused)
  expect((await shownParts(ui))[0]?.count).toBe('2')
  expect(await shownBand(band)).toEqual(rowSaying('2 wait for you'))
  await band.unmount()
  await ui.unmount()
})

test('a keep or drop m2b cannot run stands in the pane too, and the proposal stays to answer', async ($, on) => {
  // Covers: B127
  const fake = proposedFake()
  fake.answerFails = 'the store /home/alex/Notes is read-only on this machine'
  const { clock } = await start($, on, fake)
  await typed($, 'm2b-proposals')
  const ui = await $.ui.mount({ ...pane(PANE), surface: 'terminal' })

  await ui.press({ key: `drop:${SHED}` })
  await clock.advance(UNDO_MS)

  expect(await texts(ui)).toContain(
    'm2b could not drop "The spare key is in the shed.": the store /home/alex/Notes is read-only on this machine',
  )
  expect(await buttons(ui)).toContain(`drop:${SHED}`)
  await ui.unmount()
})

test('control characters and marks that reorder or hide text in a proposal are written out, never drawn', async ($, on) => {
  // Covers: B128
  const fake = new FakeM2b().proposal(
    DANA,
    'Dana\u001b]0;kept unseen\u0007 runs\r\n  IT\u009b2J\ufeffand\u00adon',
    '\n \u202egnitirw\u202c in \u200bone\tline\ufeff \t',
    { topic: 'North\u0007wind\ufe0f\u{e0041}', kind: 'per\u001bson', day: '2026-03-04\u001b[2J' },
  )
  await start($, on, fake)
  await typed($, 'm2b-proposals')
  const ui = await $.ui.mount({ ...pane(PANE), surface: 'terminal' })

  expect(await shownParts(ui)).toEqual(
    oneProposalsPart('1', [
      'Dana\\x1b]0;kept unseen\\x07 runs IT\\x9b2J\\ufeffand\\xadon',
      '[keep] [drop] per\\x1bson, topic North\\x07wind\\ufe0f\\u{e0041}',
      'said on 2026-03-04\\x1b[2J: "\\u202egnitirw\\u202c in \\u200bone line\\ufeff"',
    ]),
  )
  await ui.press({ key: `keep:${DANA}` })
  expect(await linesAt(ui, `row:${DANA}`)).toEqual(['Dana\\x1b]0;kept unseen\\x07 runs IT\\x9b2J\\ufeffand\\xadon', '[undo] keeping'])
  await ui.unmount()
})

test('proposals m2b could not look at say so in the band and the pane, beside the tasks it could read', async ($, on) => {
  // Covers: B127
  const fake = proposedFake().candidate('c1', 'Remember? Acme moved')
  fake.proposalsError =
    'state/core/proposal-answers is not downloaded to this machine; run: m2b store fetch state/core/proposal-answers'
  await start($, on, fake)
  const band = await $.ui.mount({ ...BAND, surface: 'terminal' })

  const line = `m2b could not look for proposals: ${fake.proposalsError}`
  expect(await shownBand(band)).toEqual(sentenceOfM2b(line))
  await band.unmount()

  const first = await startView($)
  expect(await waits(first)).toEqual([line, 'Remember? Acme moved', '[keep] [drop]'])
  expect(await buttons(first)).toEqual(['keep:c1', 'drop:c1'])
  await first.unmount()

  await typed($, 'm2b-proposals')
  const ui = await $.ui.mount({ ...pane(PANE), surface: 'terminal' })
  // Could not look is the one line of the part, in the color of trouble: no count, and never "none waits".
  expect(await shownParts(ui)).toEqual(oneProposalsPart(null, [line]))
  expect(await lookOf(ui, line)).toEqual(TROUBLE)
  await ui.unmount()
})

test('with the task list out of reach too, the band keeps to that one error line', async ($, on) => {
  // Covers: B127
  const fake = new FakeM2b()
  fake.isStoreMissing = true
  fake.proposalsError = 'not set up: no store.json in the store /home/alex/Notes. Run /m2b:m2b setup in Claude Code; without Claude Code, m2b setup apply (https://github.com/Kolibee-GmbH/m2b/blob/main/docs/getting-started.md).'
  await start($, on, fake)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })

  expect(await shownBand(ui)).toEqual(
    sentenceOfM2b(
      'm2b could not read the tasks: not set up: no store.json in the store /home/alex/Notes. Run /m2b:m2b setup in Claude Code; without Claude Code, m2b setup apply (https://github.com/Kolibee-GmbH/m2b/blob/main/docs/getting-started.md).',
    ),
  )
  await ui.unmount()
})

test('a core that does not know proposals leaves the band counting none and the pane without a row for them', async ($, on) => {
  // Covers: B127
  const fake = new FakeM2b().candidate('c1', 'Remember? Acme moved')
  fake.proposals = null
  await start($, on, fake)
  const band = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await shownBand(band)).toEqual(rowSaying('1 waits for you'))
  await band.unmount()

  const ui = await startView($)
  expect(await waits(ui)).toEqual(['Remember? Acme moved', '[keep] [drop]'])
  expect(await buttons(ui)).toEqual(['keep:c1', 'drop:c1'])
  await ui.unmount()
})

test('a proposals part of another shape, or an id that is none, is could not look and never a row to press', async ($, on) => {
  // Covers: B127
  const fake = new FakeM2b()
  fake.proposalsPart = {
    proposals: [{ id: '--all', kind: 'person', text: 'Dana', quote: 'Dana', day: '2026-03-04', topic: null, due: null }],
    answered: 0,
  }
  const { clock } = await start($, on, fake)
  const band = await $.ui.mount({ ...BAND, surface: 'terminal' })
  const ui = await startView($)

  const line = 'm2b could not look for proposals: m2b answered something other than the proposals that wait'
  expect(await shownBand(band)).toEqual(sentenceOfM2b(line))
  expect(await waits(ui)).toEqual([line])
  expect(await buttons(ui)).toEqual([])

  fake.proposalsPart = ['not', 'an', 'object']
  await clock.advance(60_000)
  expect(await shownBand(band)).toEqual(sentenceOfM2b(line))
  expect(await waits(ui)).toEqual([line])
  expect(await buttons(ui)).toEqual([])
  await ui.unmount()
  await band.unmount()
})

test('while keep all is being written its rows offer nothing, and it still says how many it keeps', async ($, on) => {
  // Covers: B127
  const fake = proposedFake()
  fake.delayMs = args => (args[0] === 'proposals' ? 2_000 : 0)
  const { clock } = await start($, on, fake)
  await typed($, 'm2b-proposals')
  const ui = await $.ui.mount({ ...pane(PANE), surface: 'terminal' })

  await ui.press({ key: 'keep-all' })
  await clock.advance(UNDO_MS + 1_000)

  expect(await buttons(ui)).toEqual([])
  expect(await partLines(ui, 'proposals')).toEqual([
    'keeping all 3 proposals…',
    'keeping: Dana is head of IT at Northwind.',
    'said on 2026-03-04: "Dana runs IT at Northwind"',
    'keeping: Call Sam about the ladder.',
    'said on 2026-03-04: "I still have to call Sam"',
    'keeping: The spare key is in the shed.',
    'said on 2026-03-05: "the spare key is in the shed"',
  ])
  await clock.advance(1_000)
  expect(await shownParts(ui)).toEqual(oneProposalsPart(null, [NONE_WAITS, `3 answers wait ${FILED_BY_THE_NEXT_RUN}`]))
  await ui.unmount()
})

test('once m2b is no longer set up on this machine the count of the proposals goes with the band', async ($, on) => {
  // Covers: B127
  const fake = proposedFake()
  const { clock } = await start($, on, fake)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await shownBand(ui)).toEqual(rowSaying('3 wait for you'))

  fake.isSetUp = false
  await clock.advance(60_000)

  expect(await everyText(ui)).toEqual([ENGINES_OWN_DRAWING])
  await ui.unmount()
})

test('a shared answer whose proposals are of another shape is loaded again instead of drawn', async ($, on) => {
  // Covers: B127
  const fake = proposedFake()
  const proposals = { waiting: [{ id: '--all', kind: 'person', text: 'Dana', quote: 'Dana', day: '2026-03-04', topic: null, due: null }], answered: 0, error: null }
  const stored = { writtenAtMs: NOW - 1_000, value: { snapshot: NO_TASKS, status: null, version: '0.3.0', proposals } }
  const files: Files = new Map([[CACHE, JSON.stringify(stored)]])
  await start($, on, fake, {}, files)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })

  expect(fake.calls).toEqual([['band', '--json']])
  expect(await shownBand(ui)).toEqual(rowSaying('3 wait for you'))
  await ui.unmount()
})

test('a shared answer of a band that does not know proposals says nothing about them, and the next own look does', async ($, on) => {
  // Covers: B127
  const fake = proposedFake()
  const stored = { writtenAtMs: NOW - 1_000, value: { snapshot: NO_TASKS, status: null, version: '0.3.0' } }
  const files: Files = new Map([[CACHE, JSON.stringify(stored)]])
  const { clock } = await start($, on, fake, {}, files)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })

  expect(fake.calls).toEqual([])
  expect(await everyText(ui)).toEqual([ENGINES_OWN_DRAWING])

  await clock.advance(60_000)
  expect(await shownBand(ui)).toEqual(rowSaying('3 wait for you'))
  await ui.unmount()
})

test('keep all that m2b refuses for one proposal names that one, not all of them', async ($, on) => {
  // Covers: B127
  const fake = proposedFake()
  const { clock } = await start($, on, fake)
  await typed($, 'm2b-proposals')
  const ui = await $.ui.mount({ ...pane(PANE), surface: 'terminal' })

  await ui.press({ key: 'keep-all' })
  // Another machine drops one of them while the press waits.
  const ladder = fake.proposals?.find(proposed => proposed.id === LADDER)
  if (ladder !== undefined) {
    ladder.answer = 'drop'
  }
  await clock.advance(UNDO_MS)

  expect(fake.proposals?.map(proposed => proposed.answer)).toEqual(['keep', 'drop', 'keep'])
  // What m2b said stands first, where keep all was pressed.
  expect(await shownParts(ui)).toEqual(
    oneProposalsPart(null, [
      'keep all: "Call Sam about the ladder." is answered with drop already; that answer stands',
      NONE_WAITS,
      `3 answers wait ${FILED_BY_THE_NEXT_RUN}`,
    ]),
  )
  await ui.unmount()
})

test('what m2b said to a press on a candidate stands in the overview, and is not drawn in the view of the proposals as if an answer were refused', async ($, on) => {
  // Covers: B127, B207
  const fake = proposedFake().candidate('c1', 'Remember? Acme moved')
  const { clock } = await start($, on, fake)
  const band = await $.ui.mount({ ...BAND, surface: 'terminal' })
  const first = await startView($)
  await first.press({ key: 'drop:c1' })
  const task = fake.tasks[0]
  if (task !== undefined) {
    task.completed = true
  }
  await clock.advance(UNDO_MS)
  expect(fake.writes()).toEqual([])
  expect(await waits(first)).toEqual([
    'Already settled in another session, nothing written: Remember? Acme moved',
    '3 proposals from your sessions',
    'in the tab Proposals',
  ])
  expect(await shownBand(band)).toEqual(rowSaying('3 wait for you'))
  expect(await answerKeys(first)).toEqual([])
  await first.unmount()
  await band.unmount()

  await typed($, 'm2b-proposals')
  const ui = await $.ui.mount({ ...pane(PANE), surface: 'terminal' })
  expect((await texts(ui)).join('\n')).not.toContain('Already settled')
  await ui.unmount()
})

test('a proposal is its text, then keep, drop and what it is on one line, then the words it stands on, indented whole and stepped back, whatever their source', async ($, on) => {
  // Covers: B127
  const KIM = 'd4d4d4d4d4d4'
  const fake = new FakeM2b()
    .proposal(DANA, 'Dana is head of IT at Northwind.', 'Dana runs IT at Northwind', { topic: 'Northwind', day: '2026-03-04' })
    .proposal(LADDER, 'Call Sam about the ladder.', 'I still have to call Sam', {
      kind: 'commitment',
      due: '2026-03-06',
      topic: 'Northwind',
      day: '2026-03-01',
      source: 'pasted',
    })
    .proposal(SHED, 'The spare key is in the shed.', 'the spare key is in the shed', {
      kind: 'personal',
      day: '2026-03-05',
      source: 'tool',
      tool: 'Read',
      by: 'session',
    })
    .proposal(KIM, 'Kim moved to Acme.', 'Kim moved to Acme', { day: '2026-03-05', source: 'agent', by: 'session' })
  await start($, on, fake)
  await typed($, 'm2b-proposals')
  const ui = await $.ui.mount({ ...pane(PANE), surface: 'terminal' })

  const drawn: [id: string, text: string, what: string, words: string][] = [
    [DANA, 'Dana is head of IT at Northwind.', 'person, topic Northwind', 'said on 2026-03-04: "Dana runs IT at Northwind"'],
    [LADDER, 'Call Sam about the ladder.', 'commitment, due 2026-03-06, topic Northwind', 'pasted on 2026-03-01: "I still have to call Sam"'],
    [SHED, 'The spare key is in the shed.', 'personal, handed in by a session', 'in a result of Read on 2026-03-05: "the spare key is in the shed"'],
    [KIM, 'Kim moved to Acme.', 'person, handed in by a session', 'Claude wrote on 2026-03-05: "Kim moved to Acme"'],
  ]
  for (const [id, text, what, words] of drawn) {
    expect(await linesAt(ui, `proposal:${id}`)).toEqual([text, `[keep] [drop] ${what}`, words])
    // The row is the text and its one line of buttons; the words stand under it, outside the row.
    expect(await linesAt(ui, `row:${id}`)).toEqual([text, `[keep] [drop] ${what}`])
    expect(await buttonsAt(ui, `row:${id}`)).toEqual([
      { key: `keep:${id}`, label: 'keep', variant: 'primary', dimColor: undefined },
      { key: `drop:${id}`, label: 'drop', variant: undefined, dimColor: true },
    ])
    expect(await lookOf(ui, text)).toEqual(PLAIN)
    expect(await lookOf(ui, what)).toEqual(DIM)
    expect(await lookOf(ui, words)).toEqual(DIM)
    // Indented by a box, not by spaces in the text: where the words wrap, their further lines stand in as well.
    expect(await insetsAt(ui, `proposal:${id}`)).toEqual([{ paddingLeft: INDENT, lines: [words] }])
    expect(await insetsAt(ui, `row:${id}`)).toEqual([])
  }
  await ui.unmount()
})

test('the part of the proposals is in the color of what waits and counts them while any wait, and is framed as any other part without a count once none does', async ($, on) => {
  // Covers: B208
  const fake = proposedFake()
  const { clock } = await start($, on, fake)
  await typed($, 'm2b-proposals')
  const ui = await $.ui.mount({ ...pane(PANE), surface: 'terminal' })
  const framed = { borderStyle: 'round', paddingX: 1, titleWeight: 'bold' }

  expect((await shownParts(ui)).map(part => [part.title, part.count])).toEqual([[FROM_YOUR_SESSIONS, '3']])
  expect(await partLook(ui, 'proposals')).toEqual({ ...framed, borderColor: 'warning', titleColor: 'warning', countColor: 'warning' })
  // The count stands beside the title, never in a heading of its own.
  expect((await texts(ui)).join('\n')).not.toContain('3 proposals from your sessions')

  for (const proposed of fake.proposals ?? []) {
    proposed.answer = 'keep'
  }
  await clock.advance(60_000)

  expect((await shownParts(ui)).map(part => [part.title, part.count])).toEqual([[FROM_YOUR_SESSIONS, null]])
  expect(await partLook(ui, 'proposals')).toEqual({ ...framed, borderColor: 'subtle', titleColor: 'remember', countColor: undefined })
  await ui.unmount()
})

test('keep all is a button above the proposals while two or more can be pressed; pressed, it is undo beside how many it keeps, and while it is written that line alone', async ($, on) => {
  // Covers: B127
  const fake = new FakeM2b().proposal(DANA, 'Dana is head of IT at Northwind.')
  fake.delayMs = args => (args[0] === 'proposals' ? 2_000 : 0)
  const { clock } = await start($, on, fake)
  await typed($, 'm2b-proposals')
  const ui = await $.ui.mount({ ...pane(PANE), surface: 'terminal' })
  const stepsBack = 'keeping all 3 proposals'

  // One proposal is kept by its own button.
  expect(await buttons(ui)).toEqual([`keep:${DANA}`, `drop:${DANA}`])

  fake.proposal(LADDER, 'Call Sam about the ladder.').proposal(SHED, 'The spare key is in the shed.')
  await clock.advance(60_000)
  expect((await partLines(ui, 'proposals'))?.[0]).toBe('[keep all]')
  expect((await buttonsAt(ui, 'part:proposals'))[0]).toEqual({ key: 'keep-all', label: 'keep all', variant: undefined, dimColor: false })

  await ui.press({ key: 'keep-all' })
  expect((await partLines(ui, 'proposals'))?.[0]).toBe(`[undo] ${stepsBack}`)
  expect(await linesAt(ui, 'row:keep-all')).toEqual([`[undo] ${stepsBack}`])
  expect(await buttonsAt(ui, 'row:keep-all')).toEqual([{ key: 'undo:all', label: 'undo', variant: undefined, dimColor: false }])
  expect(await lookOf(ui, stepsBack)).toEqual(DIM)
  // While it waits no proposal can be answered on its own.
  expect(await buttons(ui)).toEqual(['undo:all'])
  expect(fake.answers()).toEqual([])

  await clock.advance(UNDO_MS + 1_000)
  expect(fake.answers()).toEqual([['proposals', 'keep', DANA, LADDER, SHED]])
  expect(await linesAt(ui, 'row:keep-all')).toBeNull()
  expect((await partLines(ui, 'proposals'))?.[0]).toBe(`${stepsBack}…`)
  expect(await lookOf(ui, `${stepsBack}…`)).toEqual(DIM)
  expect(await buttons(ui)).toEqual([])
  await clock.advance(1_000)
  await ui.unmount()
})

for (const [next, nextPress] of [
  ['a press on another proposal', `drop:${SHED}`],
  ['a press on keep all', 'keep-all'],
] as const) {
  test(`what m2b said to an answer it refused goes with ${next}, before that press is written`, async ($, on) => {
    // Covers: B207
    const fake = proposedFake()
    const { clock } = await start($, on, fake)
    await typed($, 'm2b-proposals')
    const ui = await $.ui.mount({ ...pane(PANE), surface: 'terminal' })
    await ui.press({ key: `keep:${DANA}` })
    // Another machine drops it while the press waits.
    const dana = fake.proposals?.find(proposed => proposed.id === DANA)
    if (dana !== undefined) {
      dana.answer = 'drop'
    }
    await clock.advance(UNDO_MS)
    const refused = `m2b could not keep "Dana is head of IT at Northwind.": ${DANA} is answered with drop already; that answer stands`
    expect((await partLines(ui, 'proposals'))?.[0]).toBe(refused)
    const refusedCall = ['proposals', 'keep', DANA]
    expect(fake.answers()).toEqual([refusedCall])

    await ui.press({ key: nextPress })

    // Gone at the press, while its undo still waits and nothing more is written.
    expect(await texts(ui)).not.toContain(refused)
    await clock.advance(UNDO_MS - 1)
    expect(fake.answers()).toEqual([refusedCall])
    expect(await texts(ui)).not.toContain(refused)
    await clock.advance(1)
    expect(fake.answers()).toEqual([refusedCall, nextPress === 'keep-all' ? ['proposals', 'keep', LADDER, SHED] : ['proposals', 'drop', SHED]])
    expect(await texts(ui)).not.toContain(refused)
    await ui.unmount()
  })
}
