import { expect, test } from 'claude-code/testing'
import type { CommandRunResult } from 'claude-code'
import type { Engine } from 'claude-code/testing'

import { FakeM2b, STATUS, pane, partLook, shownParts, shownTabs, start, texts } from './harness'
import type { PartKey } from './harness'

// The form the pane's views share beside the overview: the proposals, the review, a topic and a
// search are each drawn as parts under their titles, and the tab above a view is the one place
// that names it. What each view holds is tested with the view.

const PANE = 'm2b'
const KIM = "Kim Lee leads Northwind's IT"

type View = 'proposals' | 'review' | 'topic' | 'search'

/** A part as a view is expected to draw it: its key, its title and the count beside the title. */
type Headed = [key: PartKey, title: string, count: string | null]

/** The parts of each view of a session with something under every one, in the order drawn. */
const PARTS: Readonly<Record<View, Headed[]>> = {
  proposals: [['proposals', 'Proposals from your sessions', '3']],
  review: [
    ['run', 'Last curation run', null],
    ['waits', 'Waits for you', '3'],
  ],
  topic: [['topic', 'Northwind', null]],
  search: [['search', '1 hit for tea', null]],
}
/** The parts of each view where nothing waits and nothing is found. */
const QUIET_PARTS: Readonly<Record<View, Headed[]>> = {
  proposals: [['proposals', 'Proposals from your sessions', null]],
  review: [
    ['run', 'Last curation run', null],
    ['waits', 'Waits for you', null],
  ],
  topic: [['topic', 'Northwind', null]],
  search: [['search', '1 hit for tea', null]],
}
/** The label of the tab the row marks above each view. */
const TAB: Readonly<Record<View, string>> = { proposals: 'Proposals 3', review: 'Review', topic: 'Northwind', search: 'Search' }
const VIEWS = Object.keys(PARTS) as View[]

function typed($: Engine, command: string, args = ''): Promise<CommandRunResult> {
  return $.command.run({ command, args, origin: { kind: 'composer' }, presentation: { isFullscreen: false, columns: 100 } })
}

/** A session given one topic, with a hit to search for and nothing that waits. */
function quietFake(): FakeM2b {
  const fake = new FakeM2b()
  fake.given = { topics: [{ name: 'Northwind', facts: 1, current: 0 }], atStart: 'whole', offUnder: null }
  fake.topicLines = { Northwind: { facts: [KIM], current: [] } }
  fake.searchHits = [{ path: 'memory/dana.md', line: 3, text: 'Dana prefers tea' }]
  fake.status = { ...STATUS, run: { state: 'succeeded', started_at: '2026-03-14T18:00:05+01:00', finished_at: '2026-03-14T18:02:10+01:00' } }
  return fake
}

/** The same session with something under every view: a candidate, a question and the review, and three proposals. */
function fullFake(): FakeM2b {
  const fake = quietFake()
  fake.candidate('c1', 'Remember? Dana prefers tea')
  fake.question('q1', 'Still current? Planning the trip to Porto')
  fake.review('r1', ['lint: broken link in a.md'])
  fake
    .proposal('a1a1a1a1a1a1', 'Dana is head of IT at Northwind.', 'Dana runs IT at Northwind')
    .proposal('b2b2b2b2b2b2', 'Call Sam about the ladder.')
    .proposal('c3c3c3c3c3c3', 'The spare key is in the shed.')
  return fake
}

/** The pane turned to `view`, at a width: by the view's command and, for a topic, the press on its button in the overview. */
async function shown($: Engine, view: View, columns = 80) {
  await typed($, view === 'topic' ? 'm2b-pane' : `m2b-${view}`, view === 'search' ? 'tea' : '')
  const ui = await $.ui.mount({ ...pane(PANE, columns), surface: 'terminal' })
  if (view === 'topic') {
    await ui.press({ key: 'topic:0' })
  }
  return ui
}

for (const view of VIEWS) {
  test(`the view of ${view === 'review' ? 'the review' : view === 'proposals' ? 'the proposals' : `a ${view}`} is drawn as parts, each under its title, and nothing of it stands outside a part`, async ($, on) => {
    // Covers: B208
    await start($, on, fullFake())

    const ui = await shown($, view)

    const parts = await shownParts(ui)
    expect(parts.map(part => [part.key, part.title, part.count])).toEqual(PARTS[view])
    const inParts = parts.flatMap(part => [part.title, ...(part.count === null ? [] : [part.count]), ...part.lines])
    expect((await texts(ui)).filter(text => !inParts.some(line => line.includes(text)))).toEqual([])
    for (const part of parts) {
      expect(part.lines).not.toEqual([])
    }
    await ui.unmount()
  })

  test(`the view of ${view === 'review' ? 'the review' : view === 'proposals' ? 'the proposals' : `a ${view}`} has no heading that repeats its tab: below the row of tabs stands the title of its first part, and each title stands once`, async ($, on) => {
    // Covers: B208
    await start($, on, fullFake())

    const ui = await shown($, view)

    const tab = (await shownTabs(ui)).find(one => one.key === null)?.label
    expect(tab).toBe(TAB[view])
    const parts = await shownParts(ui)
    const drawn = await texts(ui)
    expect(drawn[0]).toBe(parts[0]?.title)
    for (const part of parts) {
      expect(drawn.filter(text => text === part.title)).toEqual([part.title])
      // No line below a title says the tab or the title again.
      expect(part.lines.filter(line => line === tab || line === part.title || line.startsWith(`${part.title}:`))).toEqual([])
    }
    await ui.unmount()
  })
}

test('where nothing waits and nothing is counted, each view is the same parts under the same titles, with no count and no heading that counts none', async ($, on) => {
  // Covers: B208
  await start($, on, quietFake())

  for (const view of VIEWS) {
    const ui = await shown($, view)

    expect((await shownParts(ui)).map(part => [part.key, part.title, part.count])).toEqual(QUIET_PARTS[view])
    const drawn = await texts(ui)
    expect(drawn.filter(text => /^\d+ proposals? from your sessions$/.test(text))).toEqual([])
    expect(drawn.filter(text => text.startsWith('Last curation run:'))).toEqual([])
    expect(drawn).not.toContain('Nothing to keep or drop.')
    expect(drawn).not.toContain('0')
    await ui.unmount()
  }
})

test('the parts of every view are framed from 36 columns of pane and have a bar down their left below that, at 24 columns too', async ($, on) => {
  // Covers: B208
  await start($, on, fullFake())

  for (const view of VIEWS) {
    for (const [columns, frame] of [
      [80, { borderStyle: 'round', paddingX: 1 }],
      [36, { borderStyle: 'round', paddingX: 1 }],
      [35, { borderStyle: 'quote', paddingX: 0 }],
      [24, { borderStyle: 'quote', paddingX: 0 }],
    ] as const) {
      const ui = await shown($, view, columns)

      const parts = await shownParts(ui)
      // The same parts with the same lines at every width.
      expect(parts.map(part => [part.key, part.title, part.count])).toEqual(PARTS[view])
      for (const [key] of PARTS[view]) {
        expect(await partLook(ui, key)).toMatchObject(frame)
      }
      await ui.unmount()
    }
  }
})
