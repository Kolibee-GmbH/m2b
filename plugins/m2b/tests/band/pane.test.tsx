import { expect, test } from 'claude-code/testing'
import type { CommandRunResult } from 'claude-code'
import type { Engine } from 'claude-code/testing'

import { BAND, FakeM2b, HOME, NOW, STATUS, pane, start, texts } from './harness'
import type { Files } from './harness'

const PANE = 'm2b'
const UNDO_MS = 5_000
const LONG_FINDING =
  'ingest: eleven captures were not filed because their photos are not downloaded; a copy of the run log is at /home/alex/.local/state/m2b/runs/20260314T170200Z.jsonl'

function typed($: Engine, command: string, args = ''): Promise<CommandRunResult> {
  return $.command.run({
    command,
    args,
    origin: { kind: 'composer' },
    presentation: { isFullscreen: false, columns: 100 },
  })
}

function reviewedFake(): FakeM2b {
  const fake = new FakeM2b()
  for (const n of [1, 2, 3, 4]) {
    fake.candidate(`c${n}`, `Remember? Dana prefers tea ${n}`)
  }
  fake.question('q1', 'Still current? Planning the trip to Porto')
  fake.review('r1', ['lint: broken link in a.md', 'lint: broken link in b.md', 'ingest: x', LONG_FINDING])
  fake.status = {
    ...STATUS,
    run: {
      state: 'succeeded',
      started_at: '2026-03-14T18:00:05+01:00',
      finished_at: '2026-03-14T18:02:10+01:00',
      last_succeeded_at: '2026-03-14T18:02:10+01:00',
    },
  }
  return fake
}

test('the review command opens the pane with every finding whole, every candidate and the run', async ($, on) => {
  // Covers: B101
  const fake = reviewedFake()
  const { opened } = await start($, on, fake)

  const answer = await typed($, 'm2b-review')

  expect(opened.map(one => one.id)).toContain(PANE)
  expect(answer.text).toBe('the last curation run is in the m2b pane')
  const ui = await $.ui.mount({ ...pane(PANE), surface: 'terminal' })
  const shown = (await texts(ui)).join('\n')
  expect(shown).toContain('Last curation run: succeeded, 2026-03-14 18:00 to 18:02')
  expect(shown).toContain(LONG_FINDING)
  expect(shown).toContain('ingest: x')
  for (const n of [1, 2, 3, 4]) {
    expect(shown).toContain(`Remember? Dana prefers tea ${n}`)
  }
  expect(shown).toContain('Still current? Planning the trip to Porto')
  expect(await ui.findAll({ type: 'Button' })).toHaveLength(11) // with ok on the review
  await ui.unmount()
})

test('drop in the pane waits for undo like the band, and undo writes nothing', async ($, on) => {
  // Covers: B101
  const fake = reviewedFake()
  const { clock } = await start($, on, fake)
  await typed($, 'm2b-review')
  const ui = await $.ui.mount({ ...pane(PANE), surface: 'terminal' })

  await ui.press({ key: 'drop:c4' })
  expect(await texts(ui)).toContain('dropping: Remember? Dana prefers tea 4')
  await ui.press({ key: 'undo:c4' })
  await ui.press({ key: 'keep:q1' })
  await clock.advance(UNDO_MS)

  expect(fake.writes()).toEqual([['tasks', 'complete', '--', 'q1']])
  await ui.unmount()
  const band = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await texts(band)).not.toContain('Still current? Planning the trip to Porto')
  await band.unmount()
})

test('a run that has not happened yet, and one that failed, say so', async ($, on) => {
  // Covers: B101
  const fake = new FakeM2b()
  fake.status = { ...STATUS, run: { state: 'none' } }
  const { clock } = await start($, on, fake)
  await typed($, 'm2b-review')
  const ui = await $.ui.mount({ ...pane(PANE), surface: 'terminal' })
  expect(await texts(ui)).toContain('No curation run yet.')

  fake.status = {
    ...STATUS,
    run: { state: 'failed', started_at: '2026-03-14T18:00:05+01:00', message: 'ingest \u001b[31mfailed\u001b[0m' },
  }
  await clock.advance(60_000)
  const shown = (await texts(ui)).join('\n')
  expect(shown).toContain('Last curation run: failed, started 2026-03-14 18:00')
  expect(shown).toContain('ingest failed')
  expect(shown).toContain('Nothing to keep or drop.')
  await ui.unmount()
})

test('the search command shows each hit with its file and line, without the model', async ($, on) => {
  // Covers: B101
  const fake = new FakeM2b()
  fake.searchHits = [
    { path: 'korpus/2026/03/20260312-sam.md', line: 4, text: 'Sam brings the \u001b[1mplywood\u001b[0m on Saturday' },
    { path: 'memory/people/sam.md', line: 2, text: 'Sam: neighbour, has a van' },
  ]
  fake.searchEvicted = ['korpus/2026/01/20260105-old.md']
  await start($, on, fake)

  const answer = await typed($, 'm2b-search', '-plywood "Sam"')

  expect(fake.calls.filter(call => call[0] === 'search')).toEqual([['search', '--json', '--', '-plywood "Sam"']])
  expect(answer.text).toBe('2 hits for -plywood "Sam" in the m2b pane')
  const ui = await $.ui.mount({ ...pane(PANE), surface: 'terminal' })
  const shown = await texts(ui)
  expect(shown).toContain('korpus/2026/03/20260312-sam.md:4')
  expect(shown).toContain('Sam brings the plywood on Saturday')
  expect(shown).toContain('memory/people/sam.md:2')
  expect(shown).toContain('1 file not downloaded, not searched')
  await ui.unmount()
})

test('--word in front of the text searches whole words only', async ($, on) => {
  // Covers: B101
  const fake = new FakeM2b()
  fake.searchHits = [{ path: 'inbox/20261111-velo.md', line: 5, text: 'I service the Velo on Friday.' }]
  const { commands } = await start($, on, fake)

  const answer = await typed($, 'm2b-search', '--word  Velo ')

  expect(fake.calls.filter(call => call[0] === 'search')).toEqual([['search', '--json', '--word', '--', 'Velo']])
  expect(answer.text).toBe('1 hit for Velo, whole words only, in the m2b pane')
  expect(commands.find(command => command.name === 'm2b-search')).toMatchObject({ argumentHint: '[--word] <text>' })
})

test('--word without a text searches nothing, and a dash elsewhere stays part of the text', async ($, on) => {
  // Covers: B101
  const fake = new FakeM2b()
  await start($, on, fake)
  expect((await typed($, 'm2b-search', '--word')).text).toBe(
    'nothing searched: write what to look for after the command, as in /m2b-search plywood',
  )
  await typed($, 'm2b-search', '--wordy plywood')
  expect(fake.calls.filter(call => call[0] === 'search')).toEqual([['search', '--json', '--', '--wordy plywood']])
})

test('a search without hits, without text, or that fails is one clear line', async ($, on) => {
  // Covers: B101
  const fake = new FakeM2b()
  await start($, on, fake)

  expect((await typed($, 'm2b-search', '  ')).text).toBe(
    'nothing searched: write what to look for after the command, as in /m2b-search plywood',
  )
  expect(fake.calls.filter(call => call[0] === 'search')).toEqual([])

  expect((await typed($, 'm2b-search', 'plywood')).text).toBe('no hits for plywood')

  fake.searchHits = [{ path: 'memory/people/sam.md', line: 2, text: 'plywood' }]
  fake.searchCut = true
  expect((await typed($, 'm2b-search', 'plywood')).text).toBe(
    'too many hits for plywood to show; search for something narrower',
  )
  fake.searchCut = false

  fake.searchFails = 'the store at /home/alex/Notes cannot be read'
  expect((await typed($, 'm2b-search', 'plywood')).text).toBe(
    'could not search: the store at /home/alex/Notes cannot be read',
  )
})

test('showing the review and a search, drawn and left alone, asks m2b only band and search', async ($, on) => {
  // Covers: B101
  const fake = reviewedFake()
  fake.searchHits = [{ path: 'memory/people/sam.md', line: 2, text: 'Sam: neighbour' }]
  const { clock } = await start($, on, fake)
  await typed($, 'm2b-review')
  const review = await $.ui.mount({ ...pane(PANE), surface: 'terminal' })
  await clock.advance(60_000)
  await review.unmount()
  await typed($, 'm2b-search', 'Sam')
  const search = await $.ui.mount({ ...pane(PANE), surface: 'terminal' })
  await clock.advance(60_000)
  await search.unmount()
  expect(fake.writes()).toEqual([])
  expect(fake.calls.map(call => call[0]).every(verb => verb === 'band' || verb === 'search')).toBe(true)
})

test('an answer an older session shared, without the run, leaves the run line as it was', async ($, on) => {
  // Covers: B101
  const files: Files = new Map()
  const fake = reviewedFake()
  const { clock } = await start($, on, fake, {}, files)
  await typed($, 'm2b-review')
  // The refresh the command starts lands first; the older session writes after it.
  await clock.advance(1)
  const ui = await $.ui.mount({ ...pane(PANE), surface: 'terminal' })
  const older = { snapshot: { candidates: [], review: null, error: null }, status: '2 in inbox', version: '0.3.0' }
  files.set(`${HOME}/.local/state/m2b/band-view.json`, JSON.stringify({ writtenAtMs: NOW + 59_500, value: older }))
  await clock.advance(60_000)
  expect(await texts(ui)).toContain('Last curation run: succeeded, 2026-03-14 18:00 to 18:02')
  await ui.unmount()
})

test('a shared answer whose run has the wrong shape is loaded again', async ($, on) => {
  // Covers: B101
  const snapshot = { candidates: [], review: null, error: null }
  const view = { snapshot, status: '2 in inbox', version: '0.3.0', run: { state: 7 } }
  const files: Files = new Map([[`${HOME}/.local/state/m2b/band-view.json`, JSON.stringify({ writtenAtMs: NOW, value: view })]])
  const fake = reviewedFake()
  await start($, on, fake, {}, files)
  expect(fake.calls.map(call => call[0])).toContain('band')
})

test('where the pane cannot be shown, the command answers with its content instead of nothing', async ($, on) => {
  // Covers: B101
  const fake = reviewedFake()
  fake.paneWaits = 'no surface attached places panes'
  fake.searchHits = [{ path: 'memory/people/sam.md', line: 2, text: 'Sam: neighbour' }]
  await start($, on, fake)

  const review = (await typed($, 'm2b-review')).text ?? ''
  const search = (await typed($, 'm2b-search', 'Sam')).text ?? ''

  expect(review.split('\n')[0]).toBe('the m2b pane cannot be shown here: no surface attached places panes')
  expect(review).toContain(LONG_FINDING)
  expect(review).toContain('- Still current? Planning the trip to Porto')
  expect(search.split('\n')).toEqual([
    'the m2b pane cannot be shown here: no surface attached places panes',
    '1 hit for Sam',
    'memory/people/sam.md:2',
    '  Sam: neighbour',
  ])
})

test('the pane wraps findings and titles, where the band cuts them', async ($, on) => {
  // Covers: B101
  const fake = reviewedFake()
  await start($, on, fake)
  await typed($, 'm2b-review')
  const wrapOf = async (ui: { findAll: (q: { type: string }) => Promise<{ text: string; props: Record<string, unknown> }[]> }, words: string) =>
    (await ui.findAll({ type: 'Text' })).find(found => found.text.includes(words))?.props['wrap']

  const inPane = await $.ui.mount({ ...pane(PANE, 24), surface: 'terminal' })
  expect(await wrapOf(inPane, 'lint: broken link in a.md')).toBe('wrap')
  expect(await wrapOf(inPane, 'Remember? Dana prefers tea 1')).toBe('wrap')
  await inPane.unmount()
  const inBand = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await wrapOf(inBand, 'Remember? Dana prefers tea 1')).toBe('truncate-end')
  await inBand.unmount()
})

test('the text where the pane cannot be shown is kept short', async ($, on) => {
  // Covers: B101
  const fake = new FakeM2b()
  fake.paneWaits = 'no surface attached places panes'
  fake.searchHits = Array.from({ length: 30 }, (_, n) => ({ path: `korpus/n${n}.md`, line: 1, text: 'x'.repeat(400) }))
  await start($, on, fake)
  const lines = ((await typed($, 'm2b-search', 'x')).text ?? '').split('\n')
  expect(lines).toHaveLength(22)
  expect(lines.at(-1)).toBe('and 41 more lines')
  expect(Math.max(...lines.map(line => line.length))).toBeLessThanOrEqual(201)
})
