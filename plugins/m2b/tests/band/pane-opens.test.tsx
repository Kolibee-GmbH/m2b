import { expect, test } from 'claude-code/testing'
import type { CommandRunResult } from 'claude-code'
import type { Engine } from 'claude-code/testing'

import { closeAnswer, docksFor, staysBesideChat } from '../../hooks/pane-seat'
import { BAND, FakeM2b, SESSION_ID, pane, start, texts } from './harness'

const PANE = 'm2b'
const CLOSED_BY_HAND = 'paneClosedByHand'
const BY_ITSELF = { id: PANE, title: 'm2b' }
const AS_A_DIALOG = { id: PANE, title: 'm2b', closeOnEscape: true, focus: true }
const TO_STAY = { id: PANE, title: 'm2b', focus: true }
const FULLSCREEN = { columns: 160, rows: 50, isFullscreen: true }
const MAIN_SCREEN = { columns: 160, rows: 50, isFullscreen: false }

function typed($: Engine, command: string, presentation = { isFullscreen: false, columns: 100 }): Promise<CommandRunResult> {
  return $.command.run({ command, args: command === 'm2b-search' ? 'tea' : '', origin: { kind: 'composer' }, presentation })
}

type Viewport = { columns: number; rows: number; isFullscreen?: boolean }

/** The band's drawing and the moment after it; `null` is a surface that has not measured. */
async function drawBand($: Engine, clock: { advance: (ms: number) => Promise<void> }, viewport: Viewport | null = FULLSCREEN) {
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal', ...(viewport === null ? {} : { viewport }) })
  await clock.advance(1)
  return ui
}

function searchedFake(): FakeM2b {
  const fake = new FakeM2b()
  fake.searchHits = [{ path: 'memory/dana.md', line: 3, text: 'Dana prefers tea' }]
  fake.review('r1', ['lint: broken link in a.md'])
  fake.proposal('a1a1a1a1a1a1', 'Dana is head of IT at Northwind.', 'Dana runs IT at Northwind')
  return fake
}

test('under the fullscreen layout the pane opens by itself with the band, without the keyboard', async ($, on) => {
  // Covers: B186
  const fake = new FakeM2b()
  fake.given = { topics: [{ name: 'Northwind', facts: 3, current: 0 }], atStart: 'whole', offUnder: null }
  const { clock, opened, openPanes } = await start($, on, fake)
  expect(opened).toEqual([])

  const band = await drawBand($, clock)

  expect(opened).toEqual([BY_ITSELF])
  expect(openPanes.has(PANE)).toBe(true)
  const ui = await $.ui.mount({ ...pane(PANE), surface: 'terminal' })
  expect(await texts(ui)).toContain('In this session')
  expect(await texts(ui)).toContain('Northwind: 3 facts')
  await ui.unmount()
  await band.unmount()
})

test('a session opens the pane by itself once, however often the band is drawn', async ($, on) => {
  // Covers: B186
  const { clock, opened } = await start($, on, new FakeM2b())

  const band = await drawBand($, clock)
  await band.redraw()
  await clock.advance(60_000)
  await band.unmount()
  const again = await drawBand($, clock)

  expect(opened).toEqual([BY_ITSELF])
  await again.unmount()
})

test('on the main screen, and where the surface has not said how it is laid out, nothing opens by itself', async ($, on) => {
  // Covers: B186
  const { clock, opened } = await start($, on, new FakeM2b())

  for (const viewport of [MAIN_SCREEN, null, { columns: 160, rows: 50 }]) {
    const band = await drawBand($, clock, viewport)
    await band.unmount()
  }

  expect(opened).toEqual([])
})

test('a pane the terminal is too narrow to draw stays open, so it appears once the terminal is wider', async ($, on) => {
  // Covers: B186
  const fake = new FakeM2b()
  fake.paneWaits = 'an unrequested pane is placed from 144 columns; the terminal has 120'
  const { clock, opened, openPanes } = await start($, on, fake)

  const band = await drawBand($, clock, { columns: 120, rows: 50, isFullscreen: true })

  expect(opened).toEqual([BY_ITSELF])
  expect(openPanes.has(PANE)).toBe(true)
  await band.unmount()
})

test('nothing opens by itself before m2b is set up', async ($, on) => {
  // Covers: B186
  const fake = new FakeM2b()
  fake.isSetUp = false
  const { clock, opened } = await start($, on, fake)

  const band = await drawBand($, clock)

  expect(opened).toEqual([])
  await band.unmount()
})

test('a fenced step of a curation run opens no pane', async ($, on) => {
  // Covers: B186
  const { clock, opened } = await start($, on, new FakeM2b(), { M2B_CURATION_RUN: '1' })

  const band = await drawBand($, clock)

  expect(opened).toEqual([])
  await band.unmount()
})

test('a close is the word to keep the pane closed only from the person, on the start view, beside the chat', () => {
  // Covers: B186
  expect(closeAnswer('person', true, true, false)).toBe('by hand')
  // The block above the prompt, and a pane not drawn yet, close and no more.
  expect(closeAnswer('person', true, false, false)).toBe('close')
  expect(closeAnswer('plugin', true, true, false)).toBe('close')
  expect(closeAnswer('unload', true, true, false)).toBe('close')
})

test('the pane stays where one surface seats it anywhere but above the prompt', () => {
  // Covers: B186
  expect(staysBesideChat(['dock'])).toBe(true)
  // The desktop app's small form, and a seat this band does not know, stay as the dock does.
  expect(staysBesideChat(['widget'])).toBe(true)
  expect(staysBesideChat(['rail'])).toBe(true)
  expect(staysBesideChat(['inline'])).toBe(false)
  expect(staysBesideChat([])).toBe(false)
  // Drawn on two surfaces, the close does not say which one it came from.
  expect(staysBesideChat(['inline', 'dock'])).toBe(true)
})

test('a fullscreen drawing of another surface than the terminal opens nothing by itself', async ($, on) => {
  // Covers: B186
  const { clock, opened } = await start($, on, new FakeM2b())

  const band = await $.ui.mount({ ...BAND, surface: 'desktop', viewport: FULLSCREEN })
  await clock.advance(1)

  expect(opened).toEqual([])
  await band.unmount()
})

test('a session that starts after the pane was closed by hand opens nothing by itself', async ($, on) => {
  // Covers: B186
  const fake = new FakeM2b()
  fake.stored = { [CLOSED_BY_HAND]: true }
  const { clock, opened } = await start($, on, fake)

  const band = await drawBand($, clock)
  // The conversation after `/clear` is another session, which would open the pane once more.
  await $.session.end({ reason: 'clear', sessionId: SESSION_ID, resume: { id: SESSION_ID } })
  await band.redraw()
  await clock.advance(1)

  expect(opened).toEqual([])
  await band.unmount()
})

for (const command of ['m2b', 'm2b-review', 'm2b-search', 'm2b-proposals']) {
  test(`after the person opened the pane with /${command}, it opens by itself again`, async ($, on) => {
    // Covers: B186
    const fake = searchedFake()
    fake.stored = { [CLOSED_BY_HAND]: true }
    await start($, on, fake)

    await typed($, command, { isFullscreen: true, columns: 160 })

    expect(fake.stored[CLOSED_BY_HAND]).toBeUndefined()
  })
}

test('a command whose pane cannot be shown leaves the pane one that was closed by hand', async ($, on) => {
  // Covers: B186
  const fake = searchedFake()
  fake.stored = { [CLOSED_BY_HAND]: true }
  fake.paneWaits = 'no surface attached places panes'
  await start($, on, fake)

  await typed($, 'm2b')

  expect(fake.stored[CLOSED_BY_HAND]).toBe(true)
})

test('after /clear a pane that is still open is left as it is', async ($, on) => {
  // Covers: B186
  const { clock, opened } = await start($, on, searchedFake())
  const band = await drawBand($, clock)
  await typed($, 'm2b-review', { isFullscreen: true, columns: 160 })
  expect(opened).toEqual([BY_ITSELF, AS_A_DIALOG])

  await $.session.end({ reason: 'clear', sessionId: SESSION_ID, resume: { id: SESSION_ID } })
  await band.redraw()
  await clock.advance(1)

  // Opened again it would lose the keyboard and its Escape.
  expect(opened).toEqual([BY_ITSELF, AS_A_DIALOG])
  await band.unmount()
})

test('a pane that went during a session comes back by itself only with the next one', async ($, on) => {
  // Covers: B186
  const fake = searchedFake()
  const { clock, opened, openPanes } = await start($, on, fake)
  const band = await drawBand($, clock)
  // A command whose pane no surface can show closes the pane it opened.
  fake.paneWaits = 'no surface attached places panes'
  await typed($, 'm2b-review')
  fake.paneWaits = null
  expect(openPanes.has(PANE)).toBe(false)

  await band.redraw()
  await clock.advance(60_000)
  expect(opened).toEqual([BY_ITSELF, AS_A_DIALOG])

  // The band is not drawn anew for a `/clear`: the pane comes without waiting for its next drawing.
  await $.session.end({ reason: 'clear', sessionId: SESSION_ID, resume: { id: SESSION_ID } })
  await clock.advance(1)
  expect(opened).toEqual([BY_ITSELF, AS_A_DIALOG, BY_ITSELF])
  await band.unmount()
})

test('on the main screen a /clear opens nothing either', async ($, on) => {
  // Covers: B186
  const { clock, opened } = await start($, on, new FakeM2b())
  const band = await drawBand($, clock, MAIN_SCREEN)

  await $.session.end({ reason: 'clear', sessionId: SESSION_ID, resume: { id: SESSION_ID } })
  await clock.advance(60_000)

  expect(opened).toEqual([])
  await band.unmount()
})

test('a pane the mod closed itself opens again in the next session, in the view it starts in', async ($, on) => {
  // Covers: B186
  const fake = searchedFake()
  fake.paneWaits = 'no surface attached places panes'
  const { clock, opened, openPanes } = await start($, on, fake)
  await typed($, 'm2b-review')
  expect(openPanes.has(PANE)).toBe(false)

  fake.paneWaits = null
  const band = await drawBand($, clock)

  expect(opened.at(-1)).toEqual(BY_ITSELF)
  const ui = await $.ui.mount({ ...pane(PANE), surface: 'terminal' })
  expect(await texts(ui)).toContain('In this session')
  await ui.unmount()
  await band.unmount()
})

test("the person's close on the review, a search or the proposals leads back and is no close", () => {
  // Covers: B187
  for (const isBesideChat of [true, false]) {
    expect(closeAnswer('person', false, isBesideChat, false)).toBe('back')
    // The mod's own close, and the engine's, are never held back by the view.
    expect(closeAnswer('plugin', false, isBesideChat, false)).toBe('close')
    expect(closeAnswer('unload', false, isBesideChat, true)).toBe('close')
  }
})

test('Escape pressed twice goes back once and does not close the pane for later sessions', () => {
  // Covers: B187
  // The second close finds the start view already, right after the first one went back.
  expect(closeAnswer('person', true, true, true)).toBe('back')
  expect(closeAnswer('person', true, false, true)).toBe('back')
  expect(closeAnswer('plugin', true, true, true)).toBe('close')
})

for (const [command, shows] of [
  ['m2b-review', 'lint: broken link in a.md'],
  ['m2b-search', 'memory/dana.md:3'],
  ['m2b-proposals', 'said on 2026-03-12: "Dana runs IT at Northwind"'],
] as const) {
  test(`back in the view of /${command} returns to the view the pane starts in, and the pane stays`, async ($, on) => {
    // Covers: B187
    const fake = searchedFake()
    const { openPanes } = await start($, on, fake)
    await typed($, command)
    const ui = await $.ui.mount({ ...pane(PANE), surface: 'terminal' })
    expect(await texts(ui)).toContain(shows)

    await ui.press({ key: 'back' })

    expect(openPanes.has(PANE)).toBe(true)
    expect(await texts(ui)).toContain('In this session')
    expect(await texts(ui)).not.toContain(shows)
    await ui.unmount()
  })
}

test('the view the pane starts in has no way back to itself', async ($, on) => {
  // Covers: B187
  await start($, on, searchedFake())
  await typed($, 'm2b')
  const ui = await $.ui.mount({ ...pane(PANE), surface: 'terminal' })

  expect(await ui.find({ key: 'back' })).toBeUndefined()
  await ui.unmount()
})

test('back in its start view beside the chat, the pane no longer closes on Escape', async ($, on) => {
  // Covers: B187
  const { opened, openPanes } = await start($, on, searchedFake())
  await typed($, 'm2b-review', { isFullscreen: true, columns: 160 })
  const ui = await $.ui.mount({ ...pane(PANE), surface: 'terminal' })
  expect(opened).toEqual([AS_A_DIALOG])

  await ui.press({ key: 'back' })

  expect(opened).toEqual([AS_A_DIALOG, BY_ITSELF])
  expect(openPanes.has(PANE)).toBe(true)
  await ui.unmount()
})

test('back in its start view above the prompt, the pane stays the dialog it was, so Escape closes the block', async ($, on) => {
  // Covers: B187
  const { opened, openPanes } = await start($, on, searchedFake())
  await typed($, 'm2b-review')
  const ui = await $.ui.mount({ ...pane(PANE, 80, 'inline'), surface: 'terminal' })

  await ui.press({ key: 'back' })

  expect(opened).toEqual([AS_A_DIALOG])
  expect(openPanes.has(PANE)).toBe(true)
  await ui.unmount()
})

test('going back asks again what this session was given', async ($, on) => {
  // Covers: B187
  const fake = searchedFake()
  const { clock } = await start($, on, fake)
  await typed($, 'm2b-review')
  const ui = await $.ui.mount({ ...pane(PANE), surface: 'terminal' })
  fake.given = { topics: [{ name: 'Northwind', facts: 3, current: 0 }], atStart: 'whole', offUnder: null }

  await ui.press({ key: 'back' })
  await clock.advance(1)

  expect(await texts(ui)).toContain('Northwind: 3 facts')
  await ui.unmount()
})

test('show in the start view turns the pane as a dialog, so Escape comes back from there too', async ($, on) => {
  // Covers: B187
  const { clock, opened } = await start($, on, searchedFake())
  const band = await drawBand($, clock)
  const ui = await $.ui.mount({ ...pane(PANE), surface: 'terminal' })

  await ui.press({ key: 'show:review' })
  expect(opened).toEqual([BY_ITSELF, AS_A_DIALOG])
  expect(await texts(ui)).toContain('lint: broken link in a.md')

  await ui.press({ key: 'back' })
  expect(await texts(ui)).toContain('In this session')
  expect(opened).toEqual([BY_ITSELF, AS_A_DIALOG, BY_ITSELF])
  await ui.unmount()
  await band.unmount()
})

test('the m2b command opens the pane to stay where it sits beside the chat, and as a dialog elsewhere', async ($, on) => {
  // Covers: B187
  const { opened } = await start($, on, new FakeM2b())

  await typed($, 'm2b', { isFullscreen: true, columns: 110 })
  await typed($, 'm2b', { isFullscreen: true, columns: 109 })
  await typed($, 'm2b', { isFullscreen: false, columns: 160 })

  expect(opened).toEqual([TO_STAY, AS_A_DIALOG, AS_A_DIALOG])
  expect(docksFor({ isFullscreen: true, columns: 110 })).toBe(true)
  expect(docksFor({ isFullscreen: true, columns: 109 })).toBe(false)
  expect(docksFor({ isFullscreen: false, columns: 160 })).toBe(false)
})
