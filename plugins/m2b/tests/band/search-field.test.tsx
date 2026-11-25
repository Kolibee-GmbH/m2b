import { expect, test } from 'claude-code/testing'

import type { Engine } from 'claude-code/testing'

import { backTabKey } from '../../hooks/pane-tabs'

import { FakeM2b, SESSION_ID, linesAt, lookOf, pane, pressTab, shownParts, shownTabs, start } from './harness'

const PANE = 'm2b'
const BOX = 'facts:search'
const FIELD = 'facts:search:field'
const TROUBLE = { color: 'error', dimColor: undefined, wrap: 'wrap' }

function factsFake(): FakeM2b {
  const fake = new FakeM2b()
  fake.distillate = { facts: [{ statement: 'Dana is my sister', file: 'dana.md' }], current: [], topics: [] }
  fake.searchHits = [
    { path: 'memory/dana.md', line: 3, text: 'Dana gärtnert in Porto' },
    { path: 'corpus/2026/10/20261012T081500Z-claude-3f2a.md', line: 5, text: 'Dana and the garden' },
  ]
  return fake
}

/** The pane turned to the tab Facts. */
async function factsView($: Engine, columns = 80) {
  await $.command.run({ command: 'm2b-pane', args: '', origin: { kind: 'composer' }, presentation: { isFullscreen: false, columns: 100 } })
  const ui = await $.ui.mount({ ...pane(PANE, columns), surface: 'terminal' })
  await pressTab(ui, 'facts')
  return ui
}

type Mounted = Awaited<ReturnType<typeof factsView>>

async function searchFor(ui: Mounted, text: string): Promise<void> {
  await ui.input({ key: FIELD, text, kind: 'change' })
  await ui.input({ key: FIELD, text })
}

function searchCalls(fake: FakeM2b): string[][] {
  return fake.calls.filter(call => call[0] === 'search')
}

test('the tab Facts has the field search above its parts, the parts below as they were', async ($, on) => {
  // Covers: B325
  await start($, on, factsFake())
  const ui = await factsView($)

  expect(await linesAt(ui, BOX)).toEqual(['search: (what to look for)'])
  expect((await ui.find({ key: FIELD }))?.props['submitLabel']).toBe('search')
  expect((await shownParts(ui)).map(one => one.title)).toEqual(['Every session starts with', 'When a prompt names them'])
  await ui.unmount()
})

test('a text and Enter search as /m2b-search does and show the hits under the seventh tab, and Facts leads back to the field as it was', async ($, on) => {
  // Covers: B325
  const fake = factsFake()
  await start($, on, fake)
  const ui = await factsView($)

  await searchFor(ui, 'gärtnert')

  expect(searchCalls(fake)).toEqual([['search', '--json', '--', 'gärtnert']])
  expect(await shownParts(ui)).toEqual([
    {
      key: 'search',
      title: '2 hits for gärtnert',
      count: null,
      lines: ['memory/dana.md:3', 'Dana gärtnert in Porto', 'corpus/2026/10/20261012T081500Z-claude-3f2a.md:5', 'Dana and the garden'],
    },
  ])
  expect((await shownTabs(ui)).at(-1)).toEqual({ label: 'Search', key: null })
  // The focus is asked for Facts as the search's view draws it, which leads back.
  expect((await shownTabs(ui)).map(tab => tab.key)).toContain(backTabKey('facts'))

  await pressTab(ui, 'facts')
  expect(await linesAt(ui, BOX)).toEqual(['search: gärtnert'])
  await ui.unmount()
})

test('a search without hits says so under the field and the pane stays on the tab Facts', async ($, on) => {
  // Covers: B325
  const fake = factsFake()
  fake.searchHits = []
  await start($, on, fake)
  const ui = await factsView($)

  await searchFor(ui, 'plywood')

  expect(await linesAt(ui, BOX)).toEqual(['search: plywood', 'no hits for plywood'])
  expect((await shownParts(ui)).map(one => one.title)).toEqual(['Every session starts with', 'When a prompt names them'])
  await ui.unmount()
})

test('a search m2b could not make says why under the field, in the error color', async ($, on) => {
  // Covers: B325
  const fake = factsFake()
  fake.searchFails = 'the store is not reachable'
  await start($, on, fake)
  const ui = await factsView($)

  await searchFor(ui, 'plywood')

  const why = 'could not search: the store is not reachable'
  expect(await linesAt(ui, BOX)).toEqual(['search: plywood', why])
  expect(await lookOf(ui, why)).toEqual(TROUBLE)
  await ui.unmount()
})

test('a text of blanks and Enter search nothing', async ($, on) => {
  // Covers: B325
  const fake = factsFake()
  await start($, on, fake)
  const ui = await factsView($)

  await searchFor(ui, '   ')

  expect(searchCalls(fake)).toEqual([])
  expect(await linesAt(ui, BOX)).toEqual(['search: (what to look for)'])
  await ui.unmount()
})

test('a second Enter while m2b searches starts no second search', async ($, on) => {
  // Covers: B325
  const fake = factsFake()
  fake.delayMs = args => (args[0] === 'search' ? 2_000 : 0)
  const { clock } = await start($, on, fake)
  const ui = await factsView($)

  const first = searchFor(ui, 'Porto')
  await clock.advance(1)
  expect(await linesAt(ui, BOX)).toEqual(['search: Porto', 'searching…'])
  await ui.input({ key: FIELD, text: 'Porto' })
  await clock.advance(2_000)
  await first

  expect(searchCalls(fake)).toEqual([['search', '--json', '--', 'Porto']])
  await ui.unmount()
})

test('below 36 columns the field has no label, only its placeholder', async ($, on) => {
  // Covers: B325
  await start($, on, factsFake())
  const ui = await factsView($, 24)
  expect(await linesAt(ui, BOX)).toEqual(['(search)'])
  await ui.unmount()
})

test('what is typed into the field before Enter is written into no state of the session, and /clear empties it', async ($, on) => {
  // Covers: B325
  const written: string[] = []
  on('state.set', { plugin: 'm2b' }, async (_, e, next) => {
    written.push(JSON.stringify(e.value))
    return next(e)
  })
  await start($, on, factsFake())
  const ui = await factsView($)

  await ui.input({ key: FIELD, text: 'Porto', kind: 'change' })
  await pressTab(ui, 'overview')
  await pressTab(ui, 'facts')
  expect(await linesAt(ui, BOX)).toEqual(['search: Porto'])
  expect(written.filter(value => value.includes('Porto'))).toEqual([])

  await $.session.end({ reason: 'clear', sessionId: SESSION_ID, resume: { id: SESSION_ID } })
  await pressTab(ui, 'facts')
  expect(await linesAt(ui, BOX)).toEqual(['search: (what to look for)'])
  await ui.unmount()
})

/** Starts a search m2b answers after two seconds, has `/clear` end the conversation meanwhile, and lets it answer. */
async function clearedWhileSearching($: Engine, on: Parameters<typeof start>[1], hits: FakeM2b['searchHits']) {
  const fake = factsFake()
  fake.searchHits = hits
  fake.delayMs = args => (args[0] === 'search' ? 2_000 : 0)
  const { clock } = await start($, on, fake)
  const ui = await factsView($)

  const first = searchFor(ui, 'Porto')
  await clock.advance(1)
  await $.session.end({ reason: 'clear', sessionId: SESSION_ID, resume: { id: SESSION_ID } })
  await clock.advance(2_000)
  await first
  return { fake, ui }
}

test('a search without hits that answers after /clear emptied the field says nothing below it, and the next Enter searches', async ($, on) => {
  // Covers: B325
  const { fake, ui } = await clearedWhileSearching($, on, [])

  expect(await linesAt(ui, BOX)).toEqual(['search: (what to look for)'])
  fake.delayMs = () => 0
  await searchFor(ui, 'plywood')
  expect(searchCalls(fake)).toEqual([
    ['search', '--json', '--', 'Porto'],
    ['search', '--json', '--', 'plywood'],
  ])
  await ui.unmount()
})

test('a search with hits that answers after /clear emptied the field turns the pane to nothing', async ($, on) => {
  // Covers: B325
  const { ui } = await clearedWhileSearching($, on, factsFake().searchHits)

  expect(await linesAt(ui, BOX)).toEqual(['search: (what to look for)'])
  expect((await shownParts(ui)).map(one => one.title)).toEqual(['Every session starts with', 'When a prompt names them'])
  await ui.unmount()
})
