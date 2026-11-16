import { expect, test } from 'claude-code/testing'
import type { CommandRunResult } from 'claude-code'
import type { Engine } from 'claude-code/testing'

import { CURATE_NOW as NOW_KEY, CURATE_PRESS, UNDO_CURATE as UNDO_KEY, sessionLines } from '../../hooks/session-view'
import type { SessionModel } from '../../hooks/session-view'
import type { BandHealth } from '../../types'
import {
  BAND,
  CURATES_ELSEWHERE,
  CURATE_NOW,
  CURATE_NOW_CALL,
  CURATE_NOW_LINE,
  FakeM2b,
  HOME,
  NOW,
  RUN_STARTED,
  RUN_UNDER_WAY,
  SHOWN_WITHOUT_ENTRY,
  STATUS,
  STATUS_ELSEWHERE,
  UNDO_CURATE,
  buttonsAt,
  fail,
  linesAt,
  lookOf,
  ok,
  partLines,
  rowSaying,
  runStart,
  shownBand,
  start,
  startView,
  viewButtons,
} from './harness'
import type { Files } from './harness'

const UNDO_MS = 5_000
const LOOK_AFTER_A_START_MS = 3_000
const CURATED = '2 in inbox · curated 18:02'
const CURATING = 'curating'
const ROW = 'row:curate'
const WAITS_FOR_UNDO = '[undo] starting a curation run'
const BEING_STARTED = 'starting a curation run…'
const ELSEWHERE = 'Curation runs on tower-2.'
const NOT_STARTED = 'No curation run started: '
const SHARED_ANSWER = `${HOME}/.local/state/m2b/band-answer.json`

const DIM = { color: undefined, dimColor: true, wrap: 'wrap' }
const TROUBLE = { color: 'error', dimColor: undefined, wrap: 'wrap' }
const THE_BUTTON = { key: CURATE_NOW, label: 'curate now', variant: undefined, dimColor: false }

const RUNNING = { ...STATUS, run: { state: 'running' } }

/** The calls that read the band's answer, without the looks at what the session was given. */
function looks(fake: FakeM2b): string[][] {
  return fake.calls.filter(call => call[0] === 'band')
}

function typed($: Engine, command: string): Promise<CommandRunResult> {
  return $.command.run({ command, args: '', origin: { kind: 'composer' }, presentation: { isFullscreen: false, columns: 100 } })
}

test('the keys of the button and of its undo are the ones the view draws', () => {
  // Covers: B216
  expect(NOW_KEY).toBe(CURATE_NOW)
  expect(UNDO_KEY).toBe(UNDO_CURATE)
  expect(CURATE_PRESS).toBe('curate')
})

test('on the machine that curates the store, the part "m2b" has the button curate now below the line that says how curation stands', async ($, on) => {
  // Covers: B216
  const fake = new FakeM2b()
  await start($, on, fake)

  const ui = await startView($)

  expect(await partLines(ui, 'm2b')).toEqual([CURATED, CURATE_NOW_LINE])
  expect(await linesAt(ui, ROW)).toEqual([CURATED, CURATE_NOW_LINE])
  // The line may be skipped; the button is one beside others, and says nothing of what a run costs.
  expect(await lookOf(ui, CURATED)).toEqual(DIM)
  expect(await buttonsAt(ui, ROW)).toEqual([THE_BUTTON])
  // Drawing it starts nothing.
  expect(fake.curateCalls()).toEqual([])
  await ui.unmount()
})

test('on a machine that does not curate the part says which machine does, stepped back, and has no button', async ($, on) => {
  // Covers: B216
  const fake = new FakeM2b()
  fake.status = STATUS_ELSEWHERE
  const { clock } = await start($, on, fake)

  const ui = await startView($)

  expect(await partLines(ui, 'm2b')).toEqual([CURATED, ELSEWHERE])
  expect(await lookOf(ui, ELSEWHERE)).toEqual(DIM)
  expect(await ui.find({ key: ROW })).toBeUndefined()
  expect(await viewButtons(ui)).toEqual([])

  // With nothing to say of curation the part still names the machine.
  fake.status = { ...STATUS_ELSEWHERE, inbox: { count: 0, evicted: 0 }, run: { state: 'succeeded' } }
  await clock.advance(60_000)
  expect(await partLines(ui, 'm2b')).toEqual([ELSEWHERE])
  expect(await viewButtons(ui)).toEqual([])
  await ui.unmount()
})

test('the name of the curating machine is drawn as one plain line', async ($, on) => {
  // Covers: B216
  const fake = new FakeM2b()
  fake.status = { ...STATUS_ELSEWHERE, curating_machine: 'tower\u001b[31m-2\nand more' }
  await start($, on, fake)

  const ui = await startView($)

  expect(await partLines(ui, 'm2b')).toEqual([CURATED, 'Curation runs on tower-2 and more.'])
  await ui.unmount()
})

const MACHINE_NOT_KNOWN: [string, Record<string, unknown>, string[]][] = [
  ['the answer names no curating machine', { curating_machine: null, this_machine_curates: false }, [CURATED]],
  [
    'm2b could not read store.json',
    { curating_machine: null, this_machine_curates: false, store_error: 'bad json in line 3' },
    ['m2b could not read store.json: bad json in line 3', CURATED],
  ],
  ['the answer says this machine curates and names none', { curating_machine: null, this_machine_curates: true }, [CURATED]],
  ['the name of the curating machine is empty', { curating_machine: '', this_machine_curates: true }, [CURATED]],
]

for (const [situation, fields, lines] of MACHINE_NOT_KNOWN) {
  test(`where ${situation}, the part has neither the button nor a word on where curation runs`, async ($, on) => {
    // Covers: B216
    const fake = new FakeM2b()
    fake.status = { ...STATUS, ...fields }
    await start($, on, fake)

    const ui = await startView($)

    expect(await partLines(ui, 'm2b')).toEqual(lines)
    expect(await ui.find({ key: ROW })).toBeUndefined()
    expect(await viewButtons(ui)).toEqual([])
    await ui.unmount()
  })
}

test('while a run is under way the part says curating and has no button, and the button is back once the run is over', async ($, on) => {
  // Covers: B216
  const fake = new FakeM2b()
  fake.status = RUNNING
  const { clock } = await start($, on, fake)

  const ui = await startView($)

  expect(await partLines(ui, 'm2b')).toEqual([CURATING])
  expect(await ui.find({ key: ROW })).toBeUndefined()
  expect(await viewButtons(ui)).toEqual([])

  fake.status = STATUS
  await clock.advance(60_000)
  expect(await partLines(ui, 'm2b')).toEqual([CURATED, CURATE_NOW_LINE])
  await ui.unmount()
})

test('the part is drawn on the machine that curates also where there is nothing to say of curation: the button alone', async ($, on) => {
  // Covers: B216
  const fake = new FakeM2b()
  // An empty inbox and a last run without a time.
  fake.status = { ...STATUS, inbox: { count: 0, evicted: 0 }, run: { state: 'succeeded' } }
  const { clock } = await start($, on, fake)

  const ui = await startView($)

  expect(await partLines(ui, 'm2b')).toEqual([CURATE_NOW_LINE])
  expect(await linesAt(ui, ROW)).toEqual([CURATE_NOW_LINE])

  await ui.press({ key: CURATE_NOW })
  expect(await partLines(ui, 'm2b')).toEqual([WAITS_FOR_UNDO])
  await clock.advance(UNDO_MS)
  expect(fake.curateCalls()).toEqual([CURATE_NOW_CALL])
  expect(await partLines(ui, 'm2b')).toEqual([CURATING])
  await ui.unmount()
})

test('a press calls nothing for five seconds: the row offers undo beside "starting a curation run", and undo takes the press back for good', async ($, on) => {
  // Covers: B216, B94
  const fake = new FakeM2b()
  const { clock } = await start($, on, fake)
  const ui = await startView($)
  const callsBefore = fake.calls.length

  await ui.press({ key: CURATE_NOW })

  expect(await linesAt(ui, ROW)).toEqual([CURATED, WAITS_FOR_UNDO])
  expect((await buttonsAt(ui, ROW)).map(button => button.key)).toEqual([UNDO_CURATE])
  await clock.advance(UNDO_MS - 1)
  expect(fake.calls).toHaveLength(callsBefore)
  expect(await linesAt(ui, ROW)).toEqual([CURATED, WAITS_FOR_UNDO])

  await ui.press({ key: UNDO_CURATE })

  expect(await linesAt(ui, ROW)).toEqual([CURATED, CURATE_NOW_LINE])
  await clock.advance(UNDO_MS * 4)
  expect(fake.curateCalls()).toEqual([])
  expect(await linesAt(ui, ROW)).toEqual([CURATED, CURATE_NOW_LINE])
  await ui.unmount()
})

test('undo of the press is a button the view draws once the press waits, and was none before: the key the focus is asked on is never one drawn earlier', async ($, on) => {
  // Covers: B216, B201
  const fake = new FakeM2b().candidate('c1', 'Remember? Dana prefers tea')
  await start($, on, fake)
  const ui = await startView($)
  const drawn = async (): Promise<string[]> => (await ui.findAll({ type: 'Button' })).map(button => String(button.key))
  const before = await drawn()
  expect(before).toContain(CURATE_NOW)
  expect(before).not.toContain(UNDO_CURATE)

  await ui.press({ key: CURATE_NOW })

  const waiting = await drawn()
  expect(waiting.filter(key => key === UNDO_CURATE)).toHaveLength(1)
  expect(waiting).not.toContain(CURATE_NOW)
  // The other rows are as they were.
  expect(waiting.filter(key => key !== UNDO_CURATE)).toEqual(before.filter(key => key !== CURATE_NOW))
  await ui.unmount()
})

test('after five seconds the mod starts one run with one call; where it started, the part says curating and has no button before any new look, and one look follows three seconds later', async ($, on) => {
  // Covers: B216
  const fake = new FakeM2b()
  const { clock } = await start($, on, fake)
  const ui = await startView($)
  const looksBefore = looks(fake).length

  await ui.press({ key: CURATE_NOW })
  await clock.advance(UNDO_MS)

  expect(fake.curateCalls()).toEqual([CURATE_NOW_CALL])
  // Said from the command's answer alone: m2b was not asked how it stands.
  expect(looks(fake)).toHaveLength(looksBefore)
  expect(await partLines(ui, 'm2b')).toEqual([CURATING])
  expect(await lookOf(ui, CURATING)).toEqual(DIM)
  expect(await ui.find({ key: ROW })).toBeUndefined()
  expect(await viewButtons(ui)).toEqual([])

  // By then the run has written that it is under way.
  fake.status = RUNNING
  await clock.advance(LOOK_AFTER_A_START_MS - 1)
  expect(looks(fake)).toHaveLength(looksBefore)
  await clock.advance(1)
  expect(looks(fake)).toHaveLength(looksBefore + 1)
  expect(await partLines(ui, 'm2b')).toEqual([CURATING])
  expect(await viewButtons(ui)).toEqual([])

  // The run is over at a later look: the button is back, and nothing was started twice.
  fake.status = STATUS
  await clock.advance(60_000)
  expect(await partLines(ui, 'm2b')).toEqual([CURATED, CURATE_NOW_LINE])
  expect(fake.curateCalls()).toHaveLength(1)
  expect(fake.writes()).toEqual([])
  await ui.unmount()
})

test('while the run is being started the row offers nothing to press, so a second press cannot be made', async ($, on) => {
  // Covers: B216
  const fake = new FakeM2b()
  fake.delayMs = args => (args[0] === 'curate' ? 2_000 : 0)
  const { clock } = await start($, on, fake)
  const ui = await startView($)

  await ui.press({ key: CURATE_NOW })
  await clock.advance(UNDO_MS + 1)

  expect(await linesAt(ui, ROW)).toEqual([CURATED, BEING_STARTED])
  expect(await lookOf(ui, BEING_STARTED)).toEqual(DIM)
  expect(await buttonsAt(ui, ROW)).toEqual([])
  expect(await viewButtons(ui)).toEqual([])

  await clock.advance(2_000)
  expect(await partLines(ui, 'm2b')).toEqual([CURATING])
  expect(await viewButtons(ui)).toEqual([])
  expect(fake.curateCalls()).toEqual([CURATE_NOW_CALL])
  await ui.unmount()
})

test('why no run started is said in the pane alone: the band above the prompt keeps counting', async ($, on) => {
  // Covers: B216, B207
  const fake = new FakeM2b().candidate('c1', 'Remember? Dana prefers tea')
  fake.curateAnswer = runStart('running', RUN_UNDER_WAY)
  const { clock } = await start($, on, fake)
  const band = await $.ui.mount({ ...BAND, surface: 'terminal' })
  const ui = await startView($)

  await ui.press({ key: CURATE_NOW })
  await clock.advance(UNDO_MS)

  expect((await partLines(ui, 'm2b'))?.[0]).toBe(`${NOT_STARTED}${RUN_UNDER_WAY}`)
  expect(await shownBand(band)).toEqual(rowSaying('1 waits for you'))
  await ui.unmount()
  await band.unmount()
})

/** The band's own words for the reasons the command names. */
const ALREADY_RUNNING = 'a curation run is already running on this machine'
const ANOTHER_CURATES = 'another machine curates the store'
const NOT_DOWNLOADED = 'store.json is not downloaded on this machine'
const NO_SUCH_ANSWER = 'm2b answered something that is not the start of a run'

/**
 * Ways a press starts no run: what the command answers, the words the part says after `No curation
 * run started: `, which refusal the session's state holds, and words of the command's answer that
 * must not reach the state: a machine, a folder, its sentence.
 */
const NO_RUN_STARTED: [string, FakeM2b['curateAnswer'], string, string, string[]][] = [
  ['a run is already under way', runStart('running', RUN_UNDER_WAY), ALREADY_RUNNING, 'running', ['already running']],
  [
    'a run is under way and the command words it with the machine',
    runStart('running', 'tower-1 holds the lock in /home/alex/.local/state/m2b since 18:02'),
    ALREADY_RUNNING,
    'running',
    ['holds the lock', '.local/state/m2b/curate', 'since 18:02'],
  ],
  ['another machine curates', runStart('not-curating', CURATES_ELSEWHERE), ANOTHER_CURATES, 'not-curating', ['tower-2', 'is not the curating machine']],
  [
    'store.json is not on this machine',
    runStart('not-downloaded', 'store.json is not downloaded; run: m2b fetch /home/alex/Notes/store.json'),
    NOT_DOWNLOADED,
    'not-downloaded',
    ['/home/alex/Notes', 'm2b fetch'],
  ],
  [
    'the command answers a kind this band does not know',
    runStart('queued', 'a run is queued behind the one of tower-2'),
    'a run is queued behind the one of tower-2',
    'failed',
    ['queued', 'tower-2'],
  ],
  ['the command answers no JSON', ok('a curation run started in /home/alex/Notes\n'), NO_SUCH_ANSWER, 'failed', ['/home/alex/Notes', 'started in']],
  ['the command answers JSON of another shape', ok('["started", "tower-2"]'), NO_SUCH_ANSWER, 'failed', ['tower-2']],
  [
    'the command fails',
    fail('the machine config /home/alex/.config/m2b/config.json cannot be read'),
    'the machine config /home/alex/.config/m2b/config.json cannot be read',
    'failed',
    ['.config/m2b', 'cannot be read'],
  ],
]

for (const [situation, answer, words, refusal, ofTheCommand] of NO_RUN_STARTED) {
  test(`where ${situation}, the part says that no run started and why, in the color of trouble, the button is there again, the session's state holds the refusal alone, and the next press takes the sentence away`, async ($, on) => {
    // Covers: B216, B207
    const writes = stateWrites(on)
    const fake = new FakeM2b()
    fake.curateAnswer = answer
    const { clock } = await start($, on, fake)
    const ui = await startView($)

    await ui.press({ key: CURATE_NOW })
    await clock.advance(UNDO_MS)

    const notice = `${NOT_STARTED}${words}`
    expect(fake.curateCalls()).toEqual([CURATE_NOW_CALL])
    // Above the row, and the row as it was: nothing says a run is under way.
    expect(await partLines(ui, 'm2b')).toEqual([notice, CURATED, CURATE_NOW_LINE])
    expect(await lookOf(ui, notice)).toEqual(TROUBLE)
    expect(await buttonsAt(ui, ROW)).toEqual([THE_BUTTON])
    // It stays through a look.
    await clock.advance(60_000)
    expect(await partLines(ui, 'm2b')).toEqual([notice, CURATED, CURATE_NOW_LINE])
    // What every plugin can read says which refusal it was: no sentence, the band's or the command's.
    expect(keptUnder(writes, 'curateNotice').filter(kept => kept !== null)).toEqual([refusal])
    const state = writes.join('\n')
    for (const held of [...ofTheCommand, words, NOT_STARTED.trim()]) {
      expect(state).not.toContain(held)
    }

    await ui.press({ key: CURATE_NOW })

    expect(await partLines(ui, 'm2b')).toEqual([CURATED, WAITS_FOR_UNDO])
    expect(keptUnder(writes, 'curateNotice').at(-1)).toBeNull()
    await ui.press({ key: UNDO_CURATE })
    expect(await partLines(ui, 'm2b')).toEqual([CURATED, CURATE_NOW_LINE])
    expect(fake.curateCalls()).toHaveLength(1)
    await ui.unmount()
  })
}

test('why no run started goes with the next prompt', async ($, on) => {
  // Covers: B216, B207
  on('prompt.submit', (_, e) => ({ text: e.text }))
  const fake = new FakeM2b()
  fake.curateAnswer = runStart('running', RUN_UNDER_WAY)
  const { clock } = await start($, on, fake)
  const ui = await startView($)
  await ui.press({ key: CURATE_NOW })
  await clock.advance(UNDO_MS)
  expect((await partLines(ui, 'm2b'))?.[0]).toBe(`${NOT_STARTED}${RUN_UNDER_WAY}`)

  await $.prompt.submit({ text: 'go on', origin: { kind: 'composer' }, wait: false })

  expect(await partLines(ui, 'm2b')).toEqual([CURATED, CURATE_NOW_LINE])
  await ui.unmount()
})

for (const [what, answer] of [
  ['a sentence of the command', runStart('queued', 'a run\nis queued\u001b[2J behind another')],
  ['an error of the command', fail('a run\u001b[31m is queued behind another')],
] as const) {
  test(`${what} is drawn as one plain line`, async ($, on) => {
    // Covers: B216
    const fake = new FakeM2b()
    fake.curateAnswer = answer
    const { clock } = await start($, on, fake)
    const ui = await startView($)

    await ui.press({ key: CURATE_NOW })
    await clock.advance(UNDO_MS)

    expect((await partLines(ui, 'm2b'))?.[0]).toBe(`${NOT_STARTED}a run is queued behind another`)
    await ui.unmount()
  })
}

test('a start that failed is said in the command\'s words though the session\'s state holds only that it failed; the words go with the next prompt, and a later refusal says nothing of them', async ($, on) => {
  // Covers: B216, B207
  on('prompt.submit', (_, e) => ({ text: e.text }))
  const writes = stateWrites(on)
  const fake = new FakeM2b()
  const reason = 'the lock in /home/alex/.local/state/m2b cannot be written on tower-1'
  fake.curateAnswer = fail(reason)
  const { clock } = await start($, on, fake)
  const ui = await startView($)

  await ui.press({ key: CURATE_NOW })
  await clock.advance(UNDO_MS)

  expect(await partLines(ui, 'm2b')).toEqual([`${NOT_STARTED}${reason}`, CURATED, CURATE_NOW_LINE])
  expect(keptUnder(writes, 'curateNotice').filter(kept => kept !== null)).toEqual(['failed'])
  expect(writes.join('\n')).not.toContain('cannot be written')
  expect(writes.join('\n')).not.toContain('tower-1')

  await $.prompt.submit({ text: 'go on', origin: { kind: 'composer' }, wait: false })
  expect(await partLines(ui, 'm2b')).toEqual([CURATED, CURATE_NOW_LINE])

  // The next press is refused for a reason the band has words for: none of the failure's are left.
  fake.curateAnswer = runStart('not-curating', CURATES_ELSEWHERE)
  await ui.press({ key: CURATE_NOW })
  await clock.advance(UNDO_MS)
  expect(await partLines(ui, 'm2b')).toEqual([`${NOT_STARTED}${ANOTHER_CURATES}`, CURATED, CURATE_NOW_LINE])

  // And a failure that says nothing after one that did: its own words, which are none of the earlier.
  fake.curateAnswer = { ...fail(''), stderr: '', exitCode: 3 }
  await ui.press({ key: CURATE_NOW })
  await clock.advance(UNDO_MS)
  const said = (await partLines(ui, 'm2b'))?.[0] ?? ''
  expect(said).toStartWith(NOT_STARTED)
  expect(said).not.toContain('cannot be written')
  expect(said).not.toContain('tower-2')
  expect(keptUnder(writes, 'curateNotice').filter(kept => kept !== null)).toEqual(['failed', 'not-curating', 'failed'])
  await ui.unmount()
})

test('a press that starts a run after one that started none says curating, and no word of the earlier press', async ($, on) => {
  // Covers: B216
  const fake = new FakeM2b()
  fake.curateAnswer = fail('the machine config cannot be read')
  const { clock } = await start($, on, fake)
  const ui = await startView($)
  await ui.press({ key: CURATE_NOW })
  await clock.advance(UNDO_MS)
  expect((await partLines(ui, 'm2b'))?.[0]).toBe(`${NOT_STARTED}the machine config cannot be read`)

  fake.curateAnswer = runStart('started', RUN_STARTED)
  await ui.press({ key: CURATE_NOW })
  await clock.advance(UNDO_MS)

  expect(fake.curateCalls()).toEqual([CURATE_NOW_CALL, CURATE_NOW_CALL])
  expect(await partLines(ui, 'm2b')).toEqual([CURATING])
  await ui.unmount()
})

test('while curation is paused the button is there, and the press makes the same call', async ($, on) => {
  // Covers: B216
  const fake = new FakeM2b()
  fake.status = { ...STATUS, paused: true }
  const { clock } = await start($, on, fake)
  const ui = await startView($)
  const paused = `${CURATED} · curation paused`
  expect(await partLines(ui, 'm2b')).toEqual([paused, CURATE_NOW_LINE])
  expect(await buttonsAt(ui, ROW)).toEqual([THE_BUTTON])

  await ui.press({ key: CURATE_NOW })
  expect(await linesAt(ui, ROW)).toEqual([paused, WAITS_FOR_UNDO])
  await clock.advance(UNDO_MS)

  expect(fake.curateCalls()).toEqual([CURATE_NOW_CALL])
  expect(await viewButtons(ui)).toEqual([])
  await ui.unmount()
})

test('beside what is wrong with m2b the button stands last, below the line about curation', async ($, on) => {
  // Covers: B216, B206
  const fake = new FakeM2b()
  fake.status = { ...STATUS, run: { state: 'failed', message: 'the ingest step failed' } }
  fake.version = '0.4.0'
  fake.curateAnswer = runStart('running', RUN_UNDER_WAY)
  const { clock } = await start($, on, fake)
  const ui = await startView($)
  const failed = 'The last curation run failed: the ingest step failed'
  const older = 'This session runs m2b 0.3.0 and m2b 0.4.0 is installed: run /reload-plugins.'
  expect(await partLines(ui, 'm2b')).toEqual([failed, older, '2 in inbox', CURATE_NOW_LINE])

  await ui.press({ key: CURATE_NOW })
  await clock.advance(UNDO_MS)

  // What is wrong, the older m2b, why no run started, then the row.
  expect(await partLines(ui, 'm2b')).toEqual([failed, older, `${NOT_STARTED}${RUN_UNDER_WAY}`, '2 in inbox', CURATE_NOW_LINE])
  await ui.unmount()
})

/** A shared answer of a second ago with nothing waiting, this health and, where one is named, this curating machine. */
function sharedWith(health: unknown, named: { curatingMachine?: unknown } = {}): Files {
  const snapshot = { candidates: [], review: null, error: null, due: [], shows: SHOWN_WITHOUT_ENTRY }
  const value = { snapshot, status: null, version: '0.3.0', health, ...named }
  return new Map([[SHARED_ANSWER, JSON.stringify({ writtenAtMs: NOW - 1_000, value })]])
}

const ELSEWHERE_HEALTH: BandHealth = { curation: '5 in inbox', troubles: [], curates: false, isCurating: false }

const ANSWER_BEFORE_THE_BUTTON: [string, Record<string, unknown>, { curatingMachine?: unknown }][] = [
  ['says neither whether this machine curates nor whether a run is under way', { curation: CURATED, troubles: [] }, {}],
  ['does not say whether this machine curates', { curation: CURATED, troubles: [], isCurating: false }, { curatingMachine: 'tower-2' }],
  ['does not say whether a run is under way', { curation: CURATED, troubles: [], curates: false }, { curatingMachine: 'tower-2' }],
  ['says whether this machine curates in a word', { curation: CURATED, troubles: [], curates: 'no', isCurating: false }, { curatingMachine: 'tower-2' }],
  ['names the curating machine by something that is no name', { ...ELSEWHERE_HEALTH }, { curatingMachine: 7 }],
]

for (const [situation, health, named] of ANSWER_BEFORE_THE_BUTTON) {
  test(`a shared answer that ${situation} is not taken: m2b is asked, and the part is drawn from its own answer`, async ($, on) => {
    // Covers: B216
    const fake = new FakeM2b()
    await start($, on, fake, {}, sharedWith(health, named))

    const ui = await startView($)

    expect(looks(fake)).toEqual([['band', '--json']])
    expect(await partLines(ui, 'm2b')).toEqual([CURATED, CURATE_NOW_LINE])
    await ui.unmount()
  })
}

test('a shared answer that says another machine curates and names it is taken without asking m2b: the part names that machine and has no button, and the name stays out of the session\'s state', async ($, on) => {
  // Covers: B216, B197
  const writes = stateWrites(on)
  const fake = new FakeM2b()
  await start($, on, fake, {}, sharedWith(ELSEWHERE_HEALTH, { curatingMachine: 'tower-2' }))

  const ui = await startView($)

  expect(looks(fake)).toEqual([])
  expect(await partLines(ui, 'm2b')).toEqual(['5 in inbox', ELSEWHERE])
  expect(await viewButtons(ui)).toEqual([])
  // How m2b stands went into the state as it was shared, the name beside it did not.
  const kept = writes.join('\n')
  expect(kept).toContain('"curates":false')
  expect(kept).not.toContain('tower-2')
  await ui.unmount()
})

for (const [situation, named] of [
  ['names no curating machine', {}],
  ['says that none is known', { curatingMachine: null }],
] as const) {
  test(`a shared answer that says another machine curates and ${situation} is taken, and the part has neither the button nor a word on where curation runs`, async ($, on) => {
    // Covers: B216
    const fake = new FakeM2b()
    await start($, on, fake, {}, sharedWith(ELSEWHERE_HEALTH, named))

    const ui = await startView($)

    expect(looks(fake)).toEqual([])
    expect(await partLines(ui, 'm2b')).toEqual(['5 in inbox'])
    expect(await viewButtons(ui)).toEqual([])
    await ui.unmount()
  })
}

test('what this band shares says whether this machine curates and whether a run is under way, and names the curating machine beside that, not in it', async ($, on) => {
  // Covers: B216
  const files: Files = new Map()
  const fake = new FakeM2b()
  fake.status = RUNNING
  await start($, on, fake, {}, files)

  const { health, curatingMachine } = JSON.parse(files.get(SHARED_ANSWER) ?? '{}').value
  expect(health).toEqual({ curation: CURATING, troubles: [], curates: true, isCurating: true })
  expect(curatingMachine).toBe('tower-1')
})

test('on a machine that does not curate, what this band shares names the machine that does: what another session takes and draws', async ($, on) => {
  // Covers: B216
  const files: Files = new Map()
  const fake = new FakeM2b()
  fake.status = STATUS_ELSEWHERE
  await start($, on, fake, {}, files)

  const { health, curatingMachine } = JSON.parse(files.get(SHARED_ANSWER) ?? '{}').value
  expect(health).toEqual({ curation: CURATED, troubles: [], curates: false, isCurating: false })
  expect(curatingMachine).toBe('tower-2')
})

/** What the state writes put under a key of m2b, in the order written. */
function keptUnder(writes: readonly string[], key: string): unknown[] {
  return writes.map(write => JSON.parse(write) as { key?: unknown; value?: unknown }).filter(write => write.key === key).map(write => write.value)
}

const STOPS_CURATING: [string, Record<string, unknown>, string[], string[]][] = [
  ['another machine curates the store', STATUS_ELSEWHERE, [CURATED, WAITS_FOR_UNDO, ELSEWHERE], [CURATED, ELSEWHERE]],
  ['m2b can no longer tell which machine curates', { ...STATUS, curating_machine: null, this_machine_curates: false }, [CURATED, WAITS_FOR_UNDO], [CURATED]],
]

for (const [situation, status, whileWaiting, afterUndo] of STOPS_CURATING) {
  test(`a look that reads that ${situation} while a press waits leaves the row with its undo, and undo takes the press back so that nothing is called`, async ($, on) => {
    // Covers: B216, B94
    const fake = new FakeM2b()
    const { clock } = await start($, on, fake)
    const ui = await startView($)
    await ui.press({ key: CURATE_NOW })
    await clock.advance(1_000)

    fake.status = status
    await $.turn.complete({ answer: 'done', durationMs: 5, isAborted: false, turnId: 't1', reason: 'answer' })
    await clock.advance(1)

    expect(await partLines(ui, 'm2b')).toEqual(whileWaiting)
    expect(await linesAt(ui, ROW)).toEqual([CURATED, WAITS_FOR_UNDO])
    expect((await buttonsAt(ui, ROW)).map(button => button.key)).toEqual([UNDO_CURATE])

    await ui.press({ key: UNDO_CURATE })

    // With the press the row is gone: this machine has nothing to start.
    expect(await partLines(ui, 'm2b')).toEqual(afterUndo)
    expect(await ui.find({ key: ROW })).toBeUndefined()
    expect(await viewButtons(ui)).toEqual([])
    await clock.advance(UNDO_MS * 4)
    expect(fake.curateCalls()).toEqual([])
    await ui.unmount()
  })
}

test('a look asked for while the run is being started waits for the command to answer: the row stays as it is, and what the look reads is drawn after it', async ($, on) => {
  // Covers: B216
  const fake = new FakeM2b()
  fake.delayMs = args => (args[0] === 'curate' ? 2_000 : 0)
  fake.curateAnswer = runStart('not-curating', CURATES_ELSEWHERE)
  const { clock } = await start($, on, fake)
  const ui = await startView($)
  await ui.press({ key: CURATE_NOW })
  await clock.advance(UNDO_MS + 1)
  expect(await linesAt(ui, ROW)).toEqual([CURATED, BEING_STARTED])

  fake.status = STATUS_ELSEWHERE
  await $.turn.complete({ answer: 'done', durationMs: 5, isAborted: false, turnId: 't1', reason: 'answer' })
  await clock.advance(1)

  // The band's reads and writes go one after another: the look stands behind the start.
  expect(await partLines(ui, 'm2b')).toEqual([CURATED, BEING_STARTED])
  expect(await viewButtons(ui)).toEqual([])

  // The command's answer lands, then the look: no run, in the band's own words, and no row on a machine that does not curate.
  await clock.advance(2_000)
  expect(await partLines(ui, 'm2b')).toEqual([`${NOT_STARTED}${ANOTHER_CURATES}`, CURATED, ELSEWHERE])
  expect(await ui.find({ key: ROW })).toBeUndefined()
  expect(fake.curateCalls()).toEqual([CURATE_NOW_CALL])
  await ui.unmount()
})

/** Every write to the session's state, as text: what every plugin can read. */
function stateWrites(on: Parameters<typeof start>[1]): string[] {
  const writes: string[] = []
  on('state.set', (_, e, next) => {
    writes.push(JSON.stringify(e))
    return next(e)
  })
  return writes
}

for (const [where, status, machine, lines] of [
  ['on the machine that curates', STATUS, 'tower-1', [CURATED, CURATE_NOW_LINE]],
  ['on a machine that does not curate, whose part names the one that does', STATUS_ELSEWHERE, 'tower-2', [CURATED, ELSEWHERE]],
] as const) {
  test(`no name of a machine is in the session's state ${where}: not after a look, a press, a start or a turn`, async ($, on) => {
    // Covers: B216, B197
    on('prompt.submit', (_, e) => ({ text: e.text }))
    const writes = stateWrites(on)
    const fake = new FakeM2b().candidate('c1', 'Remember? Dana prefers tea')
    fake.status = status
    const { clock } = await start($, on, fake)
    const ui = await startView($)
    expect(await partLines(ui, 'm2b')).toEqual([...lines])

    await clock.advance(60_000)
    if (status === STATUS) {
      await ui.press({ key: CURATE_NOW })
      await clock.advance(UNDO_MS + LOOK_AFTER_A_START_MS)
      expect(fake.curateCalls()).toEqual([CURATE_NOW_CALL])
    }
    await $.prompt.submit({ text: 'go on', origin: { kind: 'composer' }, wait: false })
    await $.turn.complete({ answer: 'done', durationMs: 5, isAborted: false, turnId: 't1', reason: 'answer' })
    await clock.advance(60_000)

    // The state was written, and holds how m2b stands without the name.
    const kept = writes.join('\n')
    expect(kept).toContain('"key":"bandHealth"')
    expect(kept).toContain(`"curates":${status === STATUS}`)
    expect(kept).not.toContain(machine)
    expect(kept).not.toContain('tower-')
    expect(await partLines(ui, 'm2b')).toEqual([...lines])
    await ui.unmount()
  })
}

test('a look that reads a run while a press waits leaves the row with its undo, and undo still takes the press back', async ($, on) => {
  // Covers: B216, B94
  const fake = new FakeM2b()
  const { clock } = await start($, on, fake)
  const ui = await startView($)
  await ui.press({ key: CURATE_NOW })
  await clock.advance(1_000)

  // A run another session started, read by the look after this session's turn.
  fake.status = RUNNING
  await $.turn.complete({ answer: 'done', durationMs: 5, isAborted: false, turnId: 't1', reason: 'answer' })
  await clock.advance(1)

  expect(await linesAt(ui, ROW)).toEqual([CURATING, WAITS_FOR_UNDO])
  expect((await buttonsAt(ui, ROW)).map(button => button.key)).toEqual([UNDO_CURATE])

  await ui.press({ key: UNDO_CURATE })

  // The row is gone with the press: a run is under way, and there is nothing to start.
  expect(await partLines(ui, 'm2b')).toEqual([CURATING])
  expect(await ui.find({ key: ROW })).toBeUndefined()
  await clock.advance(UNDO_MS * 4)
  expect(fake.curateCalls()).toEqual([])
  await ui.unmount()
})

test('a press left to fire while a run is under way says that none started, and the look that follows at once takes the button away while the sentence stands', async ($, on) => {
  // Covers: B216, B207
  const fake = new FakeM2b()
  fake.curateAnswer = runStart('running', RUN_UNDER_WAY)
  const { clock } = await start($, on, fake)
  const ui = await startView($)
  // The run started elsewhere a moment ago: this session has not read of it, and offers the button.
  fake.status = RUNNING
  const looksBefore = looks(fake).length

  await ui.press({ key: CURATE_NOW })
  await clock.advance(UNDO_MS)
  await clock.advance(1)

  expect(fake.curateCalls()).toEqual([CURATE_NOW_CALL])
  expect(looks(fake)).toHaveLength(looksBefore + 1)
  const notice = `${NOT_STARTED}${RUN_UNDER_WAY}`
  expect(await partLines(ui, 'm2b')).toEqual([notice, CURATING])
  expect(await lookOf(ui, notice)).toEqual(TROUBLE)
  expect(await ui.find({ key: ROW })).toBeUndefined()
  expect(await viewButtons(ui)).toEqual([])

  // The sentence stays until the next prompt; the button is back once the run is over.
  fake.status = STATUS
  await clock.advance(60_000)
  expect(await partLines(ui, 'm2b')).toEqual([notice, CURATED, CURATE_NOW_LINE])
  await ui.unmount()
})

test('a look follows at once after every press that started no run, and none before three seconds after one that did', async ($, on) => {
  // Covers: B216
  const fake = new FakeM2b()
  fake.curateAnswer = fail('the machine config cannot be read')
  const { clock } = await start($, on, fake)
  const ui = await startView($)
  const looksBefore = looks(fake).length

  await ui.press({ key: CURATE_NOW })
  await clock.advance(UNDO_MS)
  await clock.advance(1)
  expect(looks(fake)).toHaveLength(looksBefore + 1)

  fake.curateAnswer = runStart('started', RUN_STARTED)
  await ui.press({ key: CURATE_NOW })
  await clock.advance(UNDO_MS + LOOK_AFTER_A_START_MS - 1)
  expect(looks(fake)).toHaveLength(looksBefore + 1)
  await clock.advance(1)
  expect(looks(fake)).toHaveLength(looksBefore + 2)
  await ui.unmount()
})

test('a run that started is said as one where the command leaves its sentence out', async ($, on) => {
  // Covers: B216
  const fake = new FakeM2b()
  fake.curateAnswer = ok('{"kind":"started"}\n')
  const { clock } = await start($, on, fake)
  const ui = await startView($)

  await ui.press({ key: CURATE_NOW })
  await clock.advance(UNDO_MS)

  expect(await partLines(ui, 'm2b')).toEqual([CURATING])
  expect(await viewButtons(ui)).toEqual([])

  // Where none started, a kind the band knows needs no sentence, and one it does not know stands for the sentence it left out.
  fake.curateAnswer = ok('{"kind":"running"}\n')
  fake.status = STATUS
  await clock.advance(60_000)
  await ui.press({ key: CURATE_NOW })
  await clock.advance(UNDO_MS)
  expect((await partLines(ui, 'm2b'))?.[0]).toBe(`${NOT_STARTED}${ALREADY_RUNNING}`)

  fake.curateAnswer = ok('{"kind":"queued"}\n')
  await ui.press({ key: CURATE_NOW })
  await clock.advance(UNDO_MS)
  expect((await partLines(ui, 'm2b'))?.[0]).toBe(`${NOT_STARTED}queued`)
  await ui.unmount()
})

test('once m2b is no longer set up on this machine the button goes with the part, and why no run started with it', async ($, on) => {
  // Covers: B216
  const fake = new FakeM2b()
  fake.curateAnswer = runStart('running', RUN_UNDER_WAY)
  const { clock } = await start($, on, fake)
  const ui = await startView($)
  await ui.press({ key: CURATE_NOW })
  await clock.advance(UNDO_MS)
  expect((await partLines(ui, 'm2b'))?.[0]).toBe(`${NOT_STARTED}${RUN_UNDER_WAY}`)

  fake.isSetUp = false
  await clock.advance(60_000)
  expect(await partLines(ui, 'm2b')).toBeNull()
  expect(await viewButtons(ui)).toEqual([])

  fake.isSetUp = true
  await clock.advance(60_000)
  expect(await partLines(ui, 'm2b')).toEqual([CURATED, CURATE_NOW_LINE])
  await ui.unmount()
})

test('where no pane can be shown, the text names the machine that curates on a machine that does not, and nothing to press on the one that does', async ($, on) => {
  // Covers: B216, B205
  const fake = new FakeM2b()
  fake.status = STATUS_ELSEWHERE
  fake.paneWaits = 'no surface attached places panes'
  const { clock } = await start($, on, fake)

  const elsewhere = ((await typed($, 'm2b-pane')).text ?? '').split('\n')
  expect(elsewhere.slice(elsewhere.indexOf('m2b'))).toEqual(['m2b', `  ${CURATED}`, `  ${ELSEWHERE}`])

  fake.status = STATUS
  await clock.advance(60_000)
  const here = ((await typed($, 'm2b-pane')).text ?? '').split('\n')
  expect(here.slice(here.indexOf('m2b'))).toEqual(['m2b', `  ${CURATED}`])
  expect(fake.curateCalls()).toEqual([])
})

test('the text form says where curation runs below the line about curation, on a machine that does not curate alone; a press and why it started no run are of the pane', () => {
  // Covers: B216, B205
  const health = (fields: Partial<BandHealth>): BandHealth => ({ curation: CURATED, troubles: [], curates: true, isCurating: false, ...fields })
  const lines = (fields: Partial<SessionModel>): string[] => {
    const all = sessionLines({
      given: null,
      notes: 0,
      rowNotice: null,
      folderNotice: null,
      curateNotice: null,
      snapshot: { candidates: [], review: null, error: null, due: [] },
      proposals: null,
      presses: {},
      health: null,
      curatingMachine: null,
      versionLine: null,
      ...fields,
    })
    return all.includes('m2b') ? all.slice(all.indexOf('m2b')) : []
  }
  const elsewhere = { curates: false }
  const curatingMachine = 'tower-2'

  expect(lines({ health: health(elsewhere), curatingMachine })).toEqual(['m2b', `  ${CURATED}`, `  ${ELSEWHERE}`])
  expect(lines({ health: health({ ...elsewhere, curation: null }), curatingMachine })).toEqual(['m2b', `  ${ELSEWHERE}`])
  expect(lines({ health: health({ ...elsewhere, troubles: ['The last curation run failed.'] }), curatingMachine })).toEqual([
    'm2b',
    '  The last curation run failed.',
    `  ${CURATED}`,
    `  ${ELSEWHERE}`,
  ])
  expect(lines({ health: health(elsewhere), curatingMachine: 'tower\u001b[31m-2' })).toEqual(['m2b', `  ${CURATED}`, `  ${ELSEWHERE}`])
  // On the machine that curates, where the machine is not named, and where whether this one curates is not known: the line about curation alone.
  expect(lines({ health: health({}), curatingMachine: 'tower-1' })).toEqual(['m2b', `  ${CURATED}`])
  expect(lines({ health: health(elsewhere) })).toEqual(['m2b', `  ${CURATED}`])
  expect(lines({ health: health({ curates: null }), curatingMachine })).toEqual(['m2b', `  ${CURATED}`])
  expect(lines({ health: health({ isCurating: true, curation: CURATING }) })).toEqual(['m2b', `  ${CURATING}`])
  // A text has nothing to press: neither the button, nor a press that waits, nor what a press could not start.
  const pressed = { [CURATE_PRESS]: { action: 'curate' as const, phase: 'waiting' as const, token: 't1' } }
  expect(lines({ health: health({}), presses: pressed, curateNotice: `${NOT_STARTED}${RUN_UNDER_WAY}` })).toEqual(['m2b', `  ${CURATED}`])
  // Nothing to say of m2b: no part, also on the machine that curates.
  expect(lines({ health: health({ curation: null }) })).toEqual([])
})
