import { expect, test } from 'claude-code/testing'
import type { CommandRunResult } from 'claude-code'
import type { Engine } from 'claude-code/testing'

import { BAND, FakeM2b, HOME, NOW, pane, start, texts } from './harness'
import type { Files } from './harness'

const PANE = 'm2b'
const UNDO_MS = 5_000
const DANA = 'a1a1a1a1a1a1'
const LADDER = 'b2b2b2b2b2b2'
const SHED = 'c3c3c3c3c3c3'
const CACHE = `${HOME}/.local/state/m2b/band-view.json`
const NO_TASKS = { candidates: [], review: null, error: null }
const NOT_LOOKED = 'm2b has not looked for proposals yet; m2b proposals lists them in a shell'
const LIST_AND_ANSWER =
  'list with: m2b proposals; keep with: m2b proposals keep <id>... (or keep --all); drop with: m2b proposals drop <id>...'
const FILED_BY_THE_NEXT_RUN = 'for the next curation run, which files what you kept'

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

async function buttons(ui: { findAll: (q: { type: string }) => Promise<{ key?: string }[]> }): Promise<(string | undefined)[]> {
  return (await ui.findAll({ type: 'Button' })).map(button => button.key)
}

test('while proposals wait the band shows one row with their number, whatever the number', async ($, on) => {
  // Covers: B127
  const fake = proposedFake()
  const { clock } = await start($, on, fake)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })

  expect(await texts(ui)).toEqual(['3 proposals from your sessions'])
  expect(await buttons(ui)).toEqual(['show:proposals'])

  fake.proposals = fake.proposals?.slice(0, 1) ?? null
  await clock.advance(60_000)
  expect(await texts(ui)).toEqual(['1 proposal from your sessions'])
  await ui.unmount()
})

test('with no proposal waiting the band has no row for them', async ($, on) => {
  // Covers: B127
  const fake = proposedFake()
  for (const proposed of fake.proposals ?? []) {
    proposed.answer = 'keep'
  }
  await start($, on, fake)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })

  expect(await texts(ui)).toEqual(['engine'])
  await ui.unmount()
})

test('the task that tells a phone proposals wait is no row beside the one of the band', async ($, on) => {
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
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })

  expect(await texts(ui)).toEqual(['Remember? Acme moved', '3 proposals from your sessions'])
  expect(await buttons(ui)).toEqual(['keep:c1', 'drop:c1', 'show:proposals'])
  await ui.unmount()
})

test('show opens the pane with every proposal: its kind, the text, the words, the day, keep and drop, and keep all', async ($, on) => {
  // Covers: B127
  const fake = proposedFake()
  const { opened } = await start($, on, fake)
  const band = await $.ui.mount({ ...BAND, surface: 'terminal' })

  await band.press({ key: 'show:proposals' })
  await band.unmount()

  expect(opened.map(one => one.id)).toEqual([PANE])
  const ui = await $.ui.mount({ ...pane(PANE), surface: 'terminal' })
  expect(await texts(ui)).toEqual([
    '3 proposals from your sessions',
    'Dana is head of IT at Northwind.',
    'person, topic Northwind',
    'said on 2026-03-04: "Dana runs IT at Northwind"',
    'Call Sam about the ladder.',
    'commitment, due 2026-03-06',
    'said on 2026-03-04: "I still have to call Sam"',
    'The spare key is in the shed.',
    'personal',
    'said on 2026-03-05: "the spare key is in the shed"',
  ])
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

test('the proposals command opens the same pane, also while nothing waits', async ($, on) => {
  // Covers: B127
  const fake = new FakeM2b()
  const { opened, commands } = await start($, on, fake)

  const answer = await typed($, 'm2b-proposals')

  expect(commands.find(command => command.name === 'm2b-proposals')?.immediate).toBe(true)
  expect(answer.text).toBe('the proposals from your sessions are in the m2b pane')
  expect(opened.map(one => one.id)).toEqual([PANE])
  const ui = await $.ui.mount({ ...pane(PANE), surface: 'terminal' })
  expect(await texts(ui)).toEqual(['No proposal waits for an answer.'])
  expect(await buttons(ui)).toEqual([])
  await ui.unmount()
})

test('where no pane can be shown the command answers with the proposals and how to answer them', async ($, on) => {
  // Covers: B127
  const fake = proposedFake()
  fake.paneWaits = 'no terminal is attached'
  await start($, on, fake)

  const answer = await typed($, 'm2b-proposals')

  expect(answer.text.split('\n')).toEqual([
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

  const lines = (await typed($, 'm2b-proposals')).text.split('\n')

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
  expect(await texts(ui)).toEqual([NOT_LOOKED])
  expect(await buttons(ui)).toEqual([])
  await ui.unmount()

  fake.paneWaits = 'no terminal is attached'
  const answer = await typed($, 'm2b-proposals')
  expect(answer.text.split('\n')).toEqual(['the m2b pane cannot be shown here: no terminal is attached', NOT_LOOKED])
})

test('show on a surface without panes says so in the band', async ($, on) => {
  // Covers: B127
  const fake = proposedFake()
  fake.paneWaits = 'no terminal is attached'
  await start($, on, fake)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })

  await ui.press({ key: 'show:proposals' })

  expect(await texts(ui)).toContain(
    'the m2b pane cannot be shown here: no terminal is attached; m2b proposals lists them in a shell',
  )
  await ui.unmount()
})

test('keep is written once the undo window is over, and the pane and the band follow without a curation run', async ($, on) => {
  // Covers: B127
  const fake = proposedFake()
  const { clock } = await start($, on, fake)
  await typed($, 'm2b-proposals')
  const ui = await $.ui.mount({ ...pane(PANE), surface: 'terminal' })

  await ui.press({ key: `keep:${DANA}` })
  expect(await texts(ui)).toContain('keeping: Dana is head of IT at Northwind.')
  expect(await buttons(ui)).toContain(`undo:${DANA}`)
  await clock.advance(UNDO_MS - 1)
  expect(fake.answers()).toEqual([])
  await clock.advance(1)

  expect(fake.answers()).toEqual([['proposals', 'keep', DANA]])
  const shown = await texts(ui)
  expect(shown[0]).toBe('2 proposals from your sessions')
  expect(shown).not.toContain('Dana is head of IT at Northwind.')
  expect(shown.at(-1)).toBe(`1 answer waits ${FILED_BY_THE_NEXT_RUN}`)
  await ui.unmount()
  const band = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await texts(band)).toEqual(['2 proposals from your sessions'])
  await band.unmount()
})

test('drop, then undo within the window, answers nothing', async ($, on) => {
  // Covers: B127
  const fake = proposedFake()
  const { clock } = await start($, on, fake)
  await typed($, 'm2b-proposals')
  const ui = await $.ui.mount({ ...pane(PANE), surface: 'terminal' })

  await ui.press({ key: `drop:${LADDER}` })
  expect(await texts(ui)).toContain('dropping: Call Sam about the ladder.')
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
  expect(await texts(ui)).toContain('keeping all 3 proposals')
  await ui.press({ key: 'undo:all' })
  await clock.advance(UNDO_MS)
  expect(fake.answers()).toEqual([])

  // One the pane did not show, as a curation run on another machine adds it meanwhile.
  await ui.press({ key: 'keep-all' })
  fake.proposal('d4d4d4d4d4d4', 'Robin moved to Lisbon.')
  await clock.advance(UNDO_MS)

  expect(fake.answers()).toEqual([['proposals', 'keep', DANA, LADDER, SHED]])
  const shown = await texts(ui)
  expect(shown[0]).toBe('1 proposal from your sessions')
  expect(shown).toContain('Robin moved to Lisbon.')
  expect(shown.at(-1)).toBe(`3 answers wait ${FILED_BY_THE_NEXT_RUN}`)
  expect(await buttons(ui)).toEqual(['keep:d4d4d4d4d4d4', 'drop:d4d4d4d4d4d4'])
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

test('an answer m2b refuses stands in the pane and in the band until the next prompt, and the rows are read again', async ($, on) => {
  // Covers: B127
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
  const shown = await texts(ui)
  expect(shown).toContain(refused)
  expect(shown[0]).toBe('2 proposals from your sessions')
  expect(await buttons(ui)).not.toContain(`keep:${DANA}`)
  await ui.unmount()
  const band = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await texts(band)).toContain(refused)

  await $.prompt.submit({ text: 'what is on today?', context: [] })
  expect(await texts(band)).toEqual(['2 proposals from your sessions'])
  await band.unmount()
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

  const shown = await texts(ui)
  expect(shown).toEqual([
    '1 proposal from your sessions',
    'Dana\\x1b]0;kept unseen\\x07 runs IT\\x9b2J\\ufeffand\\xadon',
    'per\\x1bson, topic North\\x07wind\\ufe0f\\u{e0041}',
    'said on 2026-03-04\\x1b[2J: "\\u202egnitirw\\u202c in \\u200bone line\\ufeff"',
  ])
  await ui.press({ key: `keep:${DANA}` })
  expect(await texts(ui)).toContain('keeping: Dana\\x1b]0;kept unseen\\x07 runs IT\\x9b2J\\ufeffand\\xadon')
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
  expect(await texts(band)).toEqual(['Remember? Acme moved', line])
  expect(await buttons(band)).toEqual(['keep:c1', 'drop:c1'])
  await band.unmount()

  await typed($, 'm2b-proposals')
  const ui = await $.ui.mount({ ...pane(PANE), surface: 'terminal' })
  expect(await texts(ui)).toEqual([line])
  await ui.unmount()
})

test('with the task list out of reach too, the band keeps to that one error line', async ($, on) => {
  // Covers: B127
  const fake = new FakeM2b()
  fake.isStoreMissing = true
  fake.proposalsError = 'not set up: no store.json in the store /home/alex/Notes. Run /m2b:m2b setup in Claude Code.'
  await start($, on, fake)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })

  expect(await texts(ui)).toEqual([
    'm2b could not read the tasks: not set up: no store.json in the store /home/alex/Notes. Run /m2b:m2b setup in Claude Code.',
  ])
  await ui.unmount()
})

test('a core that does not know proposals leaves the band without a row for them', async ($, on) => {
  // Covers: B127
  const fake = new FakeM2b().candidate('c1', 'Remember? Acme moved')
  fake.proposals = null
  await start($, on, fake)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })

  expect(await texts(ui)).toEqual(['Remember? Acme moved'])
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
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })

  const line = 'm2b could not look for proposals: m2b answered something other than the proposals that wait'
  expect(await texts(ui)).toEqual([line])
  expect(await buttons(ui)).toEqual([])

  fake.proposalsPart = ['not', 'an', 'object']
  await clock.advance(60_000)
  expect(await texts(ui)).toEqual([line])
  await ui.unmount()
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
  expect(await texts(ui)).toContain('keeping all 3 proposals')
  await clock.advance(1_000)
  expect(await texts(ui)).toEqual(['No proposal waits for an answer.', `3 answers wait ${FILED_BY_THE_NEXT_RUN}`])
  await ui.unmount()
})

test('once m2b is no longer set up on this machine the row for the proposals goes with the band', async ($, on) => {
  // Covers: B127
  const fake = proposedFake()
  const { clock } = await start($, on, fake)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await texts(ui)).toEqual(['3 proposals from your sessions'])

  fake.isSetUp = false
  await clock.advance(60_000)

  expect(await texts(ui)).toEqual(['engine'])
  await ui.unmount()
})

test('a shared answer whose proposals are of another shape is loaded again instead of drawn', async ($, on) => {
  // Covers: B127
  const fake = proposedFake()
  const proposals = { waiting: [{ id: '--all', kind: 'person', text: 'Dana', quote: 'Dana', day: '2026-03-04', topic: null, due: null }], answered: 0, error: null }
  const stored = { writtenAtMs: NOW - 1_000, value: { snapshot: NO_TASKS, status: '7 in inbox', version: '0.3.0', proposals } }
  const files: Files = new Map([[CACHE, JSON.stringify(stored)]])
  await start($, on, fake, {}, files)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })

  expect(fake.calls).toEqual([['band', '--json']])
  expect(await texts(ui)).toEqual(['3 proposals from your sessions'])
  await ui.unmount()
})

test('a shared answer of a band that does not know proposals says nothing about them, and the next own look does', async ($, on) => {
  // Covers: B127
  const fake = proposedFake()
  const stored = { writtenAtMs: NOW - 1_000, value: { snapshot: NO_TASKS, status: '7 in inbox', version: '0.3.0' } }
  const files: Files = new Map([[CACHE, JSON.stringify(stored)]])
  const { clock } = await start($, on, fake, {}, files)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })

  expect(fake.calls).toEqual([])
  expect(await texts(ui)).toEqual(['engine'])

  await clock.advance(60_000)
  expect(await texts(ui)).toEqual(['3 proposals from your sessions'])
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
  expect(await texts(ui)).toEqual([
    'No proposal waits for an answer.',
    'keep all: "Call Sam about the ladder." is answered with drop already; that answer stands',
    `3 answers wait ${FILED_BY_THE_NEXT_RUN}`,
  ])
  await ui.unmount()
})

test('what the band says about a candidate is not drawn in the proposals pane as if an answer were refused', async ($, on) => {
  // Covers: B127
  const fake = proposedFake().candidate('c1', 'Remember? Acme moved')
  const { clock } = await start($, on, fake)
  const band = await $.ui.mount({ ...BAND, surface: 'terminal' })
  await band.press({ key: 'drop:c1' })
  const task = fake.tasks[0]
  if (task !== undefined) {
    task.completed = true
  }
  await clock.advance(UNDO_MS)
  expect(await texts(band)).toContain('Already settled in another session, nothing written: Remember? Acme moved')
  await band.unmount()

  await typed($, 'm2b-proposals')
  const ui = await $.ui.mount({ ...pane(PANE), surface: 'terminal' })
  expect((await texts(ui)).join('\n')).not.toContain('Already settled')
  await ui.unmount()
})
