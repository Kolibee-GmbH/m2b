import { expect, test } from 'claude-code/testing'

import { BAND, FakeM2b, answerKeys, linesAt, lookOf, partLines, rowSaying, shownBand, start, startView } from './harness'

const UNDO_MS = 5_000

test('drop, then undo within the window, leaves the task open and writes nothing', async ($, on) => {
  // Covers: B94
  const fake = new FakeM2b().candidate('c1', 'Remember? Acme moved')
  const { clock } = await start($, on, fake)
  const ui = await startView($)

  await ui.press({ key: 'drop:c1' })
  expect(await linesAt(ui, 'row:c1')).toEqual(['Remember? Acme moved', '[undo] dropping'])
  await clock.advance(UNDO_MS - 1_000)
  await ui.press({ key: 'undo:c1' })
  await clock.advance(UNDO_MS * 2)

  expect(fake.writes()).toEqual([])
  const task = fake.tasks[0]
  expect(task?.completed).toBe(false)
  expect(task?.dropped).toBe(false)
  expect(await linesAt(ui, 'row:c1')).toEqual(['Remember? Acme moved', '[keep] [drop]'])
  expect(await answerKeys(ui)).toEqual(['keep:c1', 'drop:c1'])
  await ui.unmount()
})

test('drop without undo is written once the window is over', async ($, on) => {
  // Covers: B94
  const fake = new FakeM2b().candidate('c1', 'Remember? Acme moved')
  const { clock } = await start($, on, fake)
  const ui = await startView($)

  await ui.press({ key: 'drop:c1' })
  await clock.advance(UNDO_MS - 1)
  expect(fake.writes()).toEqual([])
  await clock.advance(1)

  expect(fake.writes()).toEqual([['tasks', 'drop', '--', 'c1']])
  expect(fake.tasks[0]?.dropped).toBe(true)
  expect(await answerKeys(ui)).toEqual([])
  await ui.unmount()
})

test('while a press waits, its row offers only undo and the other rows stay pressable', async ($, on) => {
  // Covers: B94
  const fake = new FakeM2b().candidate('c1', 'Remember? Acme moved').candidate('c2', 'Remember? Dana likes tea')
  const { clock } = await start($, on, fake)
  const band = await $.ui.mount({ ...BAND, surface: 'terminal' })
  const ui = await startView($)

  await ui.press({ key: 'keep:c1' })
  expect(await answerKeys(ui)).toEqual(['undo:c1', 'keep:c2', 'drop:c2'])
  expect(await linesAt(ui, 'row:c1')).toEqual(['Remember? Acme moved', '[undo] keeping'])
  // A row that was pressed counts until its write has landed.
  expect(await shownBand(band)).toEqual(rowSaying('2 wait for you'))

  await ui.press({ key: 'drop:c2' })
  await clock.advance(UNDO_MS)
  expect(fake.writes()).toEqual([
    ['tasks', 'complete', '--', 'c1'],
    ['tasks', 'drop', '--', 'c2'],
  ])
  await ui.unmount()
  await band.unmount()
})

test('a press another session settled during the window writes nothing and says so in the pane, where it was pressed', async ($, on) => {
  // Covers: B30, B207
  const fake = new FakeM2b().candidate('c1', 'Remember? Acme moved')
  const { clock } = await start($, on, fake)
  const band = await $.ui.mount({ ...BAND, surface: 'terminal' })
  const ui = await startView($)

  await ui.press({ key: 'drop:c1' })
  const task = fake.tasks[0]
  if (task !== undefined) {
    task.completed = true
  }
  await clock.advance(UNDO_MS)

  const refused = 'Already settled in another session, nothing written: Remember? Acme moved'
  expect(fake.writes()).toEqual([])
  // The row is gone, and with it the one thing that waited: the band draws nothing of its own.
  expect(await partLines(ui, 'waits')).toEqual([refused, 'Nothing waits for you.'])
  expect(await lookOf(ui, refused)).toEqual({ color: 'error', dimColor: undefined, wrap: 'wrap' })
  expect(await shownBand(band)).toBeNull()
  await ui.unmount()
  await band.unmount()
})
