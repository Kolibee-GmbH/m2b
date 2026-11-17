import { expect, test } from 'claude-code/testing'
import type { CommandRunResult } from 'claude-code'
import type { Engine } from 'claude-code/testing'

import {
  AFTER_ANSWERS_CALL,
  CURATE_NOW,
  CURATE_NOW_CALL,
  CURATE_NOW_LINE,
  FakeM2b,
  RUN_UNDER_WAY,
  STATUS,
  STATUS_ELSEWHERE,
  UNDO_CURATE,
  buttonsAt,
  fail,
  lookOf,
  pane,
  partLines,
  pressTab,
  runStart,
  start,
  viewButtons,
} from './harness'

const PANE = 'm2b'
const UNDO_MS = 5_000
const LOOK_AFTER_A_START_MS = 3_000
const DANA = 'a1a1a1a1a1a1'
const LADDER = 'b2b2b2b2b2b2'
const ROW = 'row:curate'

const NONE_WAITS = 'No proposal waits for an answer.'
const ONE_ANSWER_WAITS = '1 answer waits for the next curation run, which files what you kept'
const TWO_ANSWERS_WAIT = '2 answers wait for the next curation run, which files what you kept'
const ONE_WAITS_ELSEWHERE = '1 answer waits for the next curation run on tower-2, which files what you kept'
const FILING = 'A curation run is under way: it files what you kept.'
const UNDER_WAY = 'A curation run is under way.'
const WAITS_FOR_UNDO = '[undo] starting a curation run'
const NOT_STARTED = 'No curation run started: '
const CURATED = '2 in inbox · curated 18:02'
const ONE_ANSWER_OF_YOURS = 'Waiting for the next curation run: 1 answer of yours.'
const TWO_ANSWERS_OF_YOURS = 'Waiting for the next curation run: 2 answers of yours.'

const DIM = { color: undefined, dimColor: true, wrap: 'wrap' }
const TROUBLE = { color: 'error', dimColor: undefined, wrap: 'wrap' }

const RUNNING = { ...STATUS, run: { state: 'running' } }

function typed($: Engine, command: string): Promise<CommandRunResult> {
  return $.command.run({ command, args: '', origin: { kind: 'composer' }, presentation: { isFullscreen: false, columns: 100 } })
}

/** Two proposals that wait: a person and a commitment. */
function proposedFake(): FakeM2b {
  return new FakeM2b()
    .proposal(DANA, 'Dana is head of IT at Northwind.', 'Dana runs IT at Northwind')
    .proposal(LADDER, 'Call Sam about the ladder.', 'I still have to call Sam', { kind: 'commitment' })
}

/** The pane on the tab of the proposals. */
async function proposalsView($: Engine) {
  await typed($, 'm2b-proposals')
  return $.ui.mount({ ...pane(PANE), surface: 'terminal' })
}

/** The calls that read the band's answer. */
function looks(fake: FakeM2b): string[][] {
  return fake.calls.filter(call => call[0] === 'band' && !call.includes('--session-only'))
}

test('the answer that leaves no proposal waiting, with one kept, starts one run: the view says in the place of the answers that it runs, and the band is read again three seconds later', async ($, on) => {
  // Covers: B238
  const fake = proposedFake()
  const { clock } = await start($, on, fake)
  const ui = await proposalsView($)

  await ui.press({ key: `keep:${DANA}` })
  await clock.advance(UNDO_MS)
  // One proposal still waits: m2b is not asked for a run.
  expect(fake.answers()).toEqual([['proposals', 'keep', DANA]])
  expect(fake.curateCalls()).toEqual([])
  expect((await partLines(ui, 'proposals'))?.slice(-2)).toEqual([ONE_ANSWER_WAITS, CURATE_NOW_LINE])

  await ui.press({ key: `drop:${LADDER}` })
  await clock.advance(UNDO_MS - 1)
  // Until the answer is written nothing is started: the press can still be taken back.
  expect(fake.curateCalls()).toEqual([])
  await clock.advance(1)

  expect(fake.answers()).toEqual([['proposals', 'keep', DANA], ['proposals', 'drop', LADDER]])
  expect(fake.curateCalls()).toEqual([AFTER_ANSWERS_CALL])
  expect(await partLines(ui, 'proposals')).toEqual([NONE_WAITS, FILING])
  expect(await lookOf(ui, FILING)).toEqual(DIM)
  expect(await viewButtons(ui)).toEqual([])

  // By then the run has written that it is under way.
  const looksBefore = looks(fake).length
  fake.status = RUNNING
  await clock.advance(LOOK_AFTER_A_START_MS - 1)
  expect(looks(fake)).toHaveLength(looksBefore)
  await clock.advance(1)
  expect(looks(fake)).toHaveLength(looksBefore + 1)
  expect(await partLines(ui, 'proposals')).toEqual([NONE_WAITS, FILING])
  expect(fake.curateCalls()).toHaveLength(1)
  await ui.unmount()
})

test('keep all that leaves no proposal waiting starts the run with one call', async ($, on) => {
  // Covers: B238
  const fake = proposedFake()
  const { clock } = await start($, on, fake)
  const ui = await proposalsView($)

  await ui.press({ key: 'keep-all' })
  await clock.advance(UNDO_MS)

  expect(fake.answers()).toEqual([['proposals', 'keep', DANA, LADDER]])
  expect(fake.curateCalls()).toEqual([AFTER_ANSWERS_CALL])
  expect(await partLines(ui, 'proposals')).toEqual([NONE_WAITS, FILING])
  await ui.unmount()
})

test('an answer m2b could not write leaves its proposal waiting, so nothing is asked for', async ($, on) => {
  // Covers: B238
  const fake = new FakeM2b().proposal(DANA, 'Dana is head of IT at Northwind.')
  fake.answerFails = 'the store cannot be written'
  const { clock } = await start($, on, fake)
  const ui = await proposalsView($)

  await ui.press({ key: `keep:${DANA}` })
  await clock.advance(UNDO_MS)

  expect(fake.answers()).toEqual([['proposals', 'keep', DANA]])
  expect(fake.curateCalls()).toEqual([])
  await ui.unmount()
})

test('an answer m2b refused because another one stands leaves no proposal waiting: the run is asked for, and what m2b said to the answer stands', async ($, on) => {
  // Covers: B238
  const fake = proposedFake()
  const { clock } = await start($, on, fake)
  const ui = await proposalsView($)
  await ui.press({ key: `keep:${LADDER}` })
  await clock.advance(UNDO_MS)
  expect(fake.curateCalls()).toEqual([])
  // Another machine drops the proposal this session still shows.
  const dana = (fake.proposals ?? []).find(proposed => proposed.id === DANA)
  if (dana !== undefined) {
    dana.answer = 'drop'
  }

  await ui.press({ key: `keep:${DANA}` })
  await clock.advance(UNDO_MS)

  expect(fake.curateCalls()).toEqual([AFTER_ANSWERS_CALL])
  const refused = `m2b could not keep "Dana is head of IT at Northwind.": ${DANA} is answered with drop already; that answer stands`
  expect(await partLines(ui, 'proposals')).toEqual([refused, NONE_WAITS, FILING])
  await ui.unmount()
})

test('while a press on curate now waits, the answer that leaves no proposal waiting asks for no run: the press starts it, or undo leaves the answers waiting', async ($, on) => {
  // Covers: B238
  const fake = proposedFake()
  const { clock } = await start($, on, fake)
  const ui = await proposalsView($)
  await ui.press({ key: `keep:${DANA}` })
  await clock.advance(UNDO_MS)

  await ui.press({ key: `keep:${LADDER}` })
  await clock.advance(2_000)
  await ui.press({ key: CURATE_NOW })
  await clock.advance(UNDO_MS - 2_000)

  // The answer is written, the press on curate now still waits: nothing was started yet.
  expect(fake.answers()).toHaveLength(2)
  expect(fake.curateCalls()).toEqual([])
  expect(await partLines(ui, 'proposals')).toEqual([NONE_WAITS, TWO_ANSWERS_WAIT, WAITS_FOR_UNDO])

  await clock.advance(2_000)
  expect(fake.curateCalls()).toEqual([CURATE_NOW_CALL])
  expect(await partLines(ui, 'proposals')).toEqual([NONE_WAITS, FILING])
  await ui.unmount()
})

test('a press on curate now that waits keeps its undo below the proposals whatever a look reads meanwhile', async ($, on) => {
  // Covers: B239, B94
  const fake = new FakeM2b().proposal(DANA, 'Dana is head of IT at Northwind.')
  fake.afterAnswersAnswer = runStart('off', 'no curation run starts after your answers on this machine')
  const { clock } = await start($, on, fake)
  const ui = await proposalsView($)
  await ui.press({ key: `keep:${DANA}` })
  await clock.advance(UNDO_MS)
  await ui.press({ key: CURATE_NOW })
  await clock.advance(1_000)

  for (const status of [STATUS_ELSEWHERE, { ...STATUS, curating_machine: null, this_machine_curates: false }, RUNNING]) {
    fake.status = status
    await $.turn.complete({ answer: 'done', durationMs: 5, isAborted: false, turnId: 't1', reason: 'answer' })
    await clock.advance(1)
    expect(await partLines(ui, 'proposals')).toEqual([NONE_WAITS, ONE_ANSWER_WAITS, WAITS_FOR_UNDO])
    expect((await buttonsAt(ui, ROW)).map(button => button.key)).toEqual([UNDO_CURATE])
  }

  await ui.press({ key: UNDO_CURATE })
  await clock.advance(UNDO_MS * 2)
  expect(fake.curateCalls()).toEqual([AFTER_ANSWERS_CALL])
  await ui.unmount()
})

/** What the command answers where the answers call for no run now, and nothing is wrong. */
const NO_RUN_IS_DUE: [string, string][] = [
  ['the setting is off', 'off'],
  ['curation is paused', 'paused'],
  ['a proposal another session sees still waits', 'proposals-wait'],
  ['nothing is kept', 'nothing-kept'],
  ['a run is under way that this session had not read of', 'running'],
  ['another machine curates and this session had not read of it', 'not-curating'],
]

for (const [situation, kind] of NO_RUN_IS_DUE) {
  test(`where ${situation}, no run starts and nothing is said of it: the answers wait, with curate now below them`, async ($, on) => {
    // Covers: B238, B239
    const fake = new FakeM2b().proposal(DANA, 'Dana is head of IT at Northwind.')
    fake.afterAnswersAnswer = runStart(kind, `the sentence of the command for ${kind}, on tower-1`)
    const { clock } = await start($, on, fake)
    const ui = await proposalsView($)

    await ui.press({ key: `keep:${DANA}` })
    await clock.advance(UNDO_MS)

    expect(fake.curateCalls()).toEqual([AFTER_ANSWERS_CALL])
    expect(await partLines(ui, 'proposals')).toEqual([NONE_WAITS, ONE_ANSWER_WAITS, CURATE_NOW_LINE])
    expect(await lookOf(ui, ONE_ANSWER_WAITS)).toEqual(DIM)
    expect((await buttonsAt(ui, ROW)).map(button => button.key)).toEqual([CURATE_NOW])
    await ui.unmount()
  })
}

test('drops alone ask m2b, which starts no run: the answer waits, and nothing is said of a run', async ($, on) => {
  // Covers: B238
  const fake = new FakeM2b().proposal(DANA, 'Dana is head of IT at Northwind.')
  const { clock } = await start($, on, fake)
  const ui = await proposalsView($)

  await ui.press({ key: `drop:${DANA}` })
  await clock.advance(UNDO_MS)

  expect(fake.curateCalls()).toEqual([AFTER_ANSWERS_CALL])
  expect(await partLines(ui, 'proposals')).toEqual([NONE_WAITS, ONE_ANSWER_WAITS, CURATE_NOW_LINE])
  await ui.unmount()
})

for (const [situation, answer, words] of [
  ['the command fails', fail('the proposals file cannot be read'), 'the proposals file cannot be read'],
  ['store.json is not on this machine', runStart('not-downloaded', 'store.json is not downloaded'), 'store.json is not downloaded on this machine'],
] as const) {
  test(`where ${situation}, the view says above the answers that no run started and why, in the color of trouble, and keeps curate now`, async ($, on) => {
    // Covers: B238, B239
    const fake = new FakeM2b().proposal(DANA, 'Dana is head of IT at Northwind.')
    fake.afterAnswersAnswer = answer
    const { clock } = await start($, on, fake)
    const ui = await proposalsView($)

    await ui.press({ key: `keep:${DANA}` })
    await clock.advance(UNDO_MS)

    const notice = `${NOT_STARTED}${words}`
    expect(await partLines(ui, 'proposals')).toEqual([NONE_WAITS, notice, ONE_ANSWER_WAITS, CURATE_NOW_LINE])
    expect(await lookOf(ui, notice)).toEqual(TROUBLE)
    // The overview says the same where it says how curation stands.
    await pressTab(ui, 'overview')
    expect(await partLines(ui, 'm2b')).toEqual([notice, CURATED, ONE_ANSWER_OF_YOURS, CURATE_NOW_LINE])
    await ui.unmount()
  })
}

test('on a machine that does not curate m2b is not asked for a run: the view names the machine whose run the answers wait for, and has no button', async ($, on) => {
  // Covers: B238, B239
  const fake = new FakeM2b().proposal(DANA, 'Dana is head of IT at Northwind.')
  fake.status = STATUS_ELSEWHERE
  const { clock } = await start($, on, fake)
  const ui = await proposalsView($)

  await ui.press({ key: `keep:${DANA}` })
  await clock.advance(UNDO_MS)

  expect(fake.answers()).toEqual([['proposals', 'keep', DANA]])
  expect(fake.curateCalls()).toEqual([])
  expect(await partLines(ui, 'proposals')).toEqual([NONE_WAITS, ONE_WAITS_ELSEWHERE])
  expect(await lookOf(ui, ONE_WAITS_ELSEWHERE)).toEqual(DIM)
  expect(await viewButtons(ui)).toEqual([])
  await ui.unmount()
})

test('while a run is under way an answer asks for none: the view says that it runs, and once it is over the answers that still wait have curate now below them', async ($, on) => {
  // Covers: B238, B239
  const fake = new FakeM2b().proposal(DANA, 'Dana is head of IT at Northwind.')
  fake.status = RUNNING
  const { clock } = await start($, on, fake)
  const ui = await proposalsView($)
  // No answer waits yet: the view says only that a run is under way.
  expect((await partLines(ui, 'proposals'))?.at(-1)).toBe(UNDER_WAY)

  await ui.press({ key: `keep:${DANA}` })
  await clock.advance(UNDO_MS)

  expect(fake.curateCalls()).toEqual([])
  expect(await partLines(ui, 'proposals')).toEqual([NONE_WAITS, FILING])
  expect(await viewButtons(ui)).toEqual([])

  // The run had read the answers before this one: it is over, and the answer still waits.
  fake.status = STATUS
  await clock.advance(60_000)
  expect(await partLines(ui, 'proposals')).toEqual([NONE_WAITS, ONE_ANSWER_WAITS, CURATE_NOW_LINE])
  await ui.unmount()
})

test('curate now below the answers that wait is the press of the overview: undo for five seconds, then one run, and the view says that it runs', async ($, on) => {
  // Covers: B239, B216
  const fake = proposedFake()
  fake.afterAnswersAnswer = runStart('off', 'no curation run starts after your answers on this machine')
  const { clock } = await start($, on, fake)
  const ui = await proposalsView($)
  await ui.press({ key: 'keep-all' })
  await clock.advance(UNDO_MS)
  expect(await partLines(ui, 'proposals')).toEqual([NONE_WAITS, TWO_ANSWERS_WAIT, CURATE_NOW_LINE])

  await ui.press({ key: CURATE_NOW })

  expect(await partLines(ui, 'proposals')).toEqual([NONE_WAITS, TWO_ANSWERS_WAIT, WAITS_FOR_UNDO])
  expect((await buttonsAt(ui, ROW)).map(button => button.key)).toEqual([UNDO_CURATE])
  await clock.advance(UNDO_MS)

  expect(fake.curateCalls()).toEqual([AFTER_ANSWERS_CALL, CURATE_NOW_CALL])
  expect(await partLines(ui, 'proposals')).toEqual([NONE_WAITS, FILING])
  expect(await viewButtons(ui)).toEqual([])
  await ui.unmount()
})

test('a press on curate now that started no run says why above the answers, and the next start that works takes the sentence away', async ($, on) => {
  // Covers: B239, B207
  const fake = new FakeM2b().proposal(DANA, 'Dana is head of IT at Northwind.')
  fake.afterAnswersAnswer = runStart('paused', 'curation is paused')
  fake.curateAnswer = runStart('running', RUN_UNDER_WAY)
  const { clock } = await start($, on, fake)
  const ui = await proposalsView($)
  await ui.press({ key: `keep:${DANA}` })
  await clock.advance(UNDO_MS)

  await ui.press({ key: CURATE_NOW })
  await clock.advance(UNDO_MS)
  expect(await partLines(ui, 'proposals')).toEqual([NONE_WAITS, `${NOT_STARTED}${RUN_UNDER_WAY}`, ONE_ANSWER_WAITS, CURATE_NOW_LINE])

  fake.curateAnswer = runStart('started', 'a curation run started in the background')
  await ui.press({ key: CURATE_NOW })
  await clock.advance(UNDO_MS)
  expect(await partLines(ui, 'proposals')).toEqual([NONE_WAITS, FILING])
  await ui.unmount()
})

test('the overview says how many answers wait for a run between the line about curation and curate now, and nothing of them while a run is under way', async ($, on) => {
  // Covers: B239
  const fake = proposedFake()
  fake.afterAnswersAnswer = runStart('off', 'no curation run starts after your answers on this machine')
  const { clock } = await start($, on, fake)
  const ui = await proposalsView($)
  await ui.press({ key: 'keep-all' })
  await clock.advance(UNDO_MS)

  await pressTab(ui, 'overview')
  expect(await partLines(ui, 'm2b')).toEqual([CURATED, TWO_ANSWERS_OF_YOURS, CURATE_NOW_LINE])
  expect(await lookOf(ui, TWO_ANSWERS_OF_YOURS)).toEqual(DIM)

  fake.status = RUNNING
  await clock.advance(60_000)
  expect(await partLines(ui, 'm2b')).toEqual(['curating'])
  await ui.unmount()
})

test('on a machine that does not curate the overview says how many answers wait above the line that names the machine that curates', async ($, on) => {
  // Covers: B239
  const fake = new FakeM2b().proposal(DANA, 'Dana is head of IT at Northwind.')
  fake.status = STATUS_ELSEWHERE
  const { clock } = await start($, on, fake)
  const ui = await proposalsView($)
  await ui.press({ key: `keep:${DANA}` })
  await clock.advance(UNDO_MS)

  await pressTab(ui, 'overview')
  expect(await partLines(ui, 'm2b')).toEqual([CURATED, ONE_ANSWER_OF_YOURS, 'Curation runs on tower-2.'])
  expect(await viewButtons(ui)).toEqual([])
  await ui.unmount()
})
