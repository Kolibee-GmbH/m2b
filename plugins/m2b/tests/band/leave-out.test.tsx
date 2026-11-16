import { expect, test } from 'claude-code/testing'
import type { CommandRunResult } from 'claude-code'
import type { Engine } from 'claude-code/testing'

import { wholePath } from '../../hooks/plain-text'
import { CURATE_NOW, FakeM2b, SESSION_ID, buttonsAt, linesAt, lookOf, pane, partLines, pathPieces, start, texts, viewButtons } from './harness'

const PANE = 'm2b'
const UNDO_MS = 5_000
const ACME = '/home/alex/code/acme'
const LOOK = ['band', '--json', '--session', SESSION_ID, '--session-only']
const PRINTED_WHOLE = 'The distillate was printed whole at the start.'
const ON_HERE = 'm2b is on in this folder.'
const OFF_HERE = 'm2b is off under this folder.'
const KEEPS = 'This session keeps what it was given and gets no more topics.'
const FOLDER_ROW = 'row:folder'

function typed($: Engine, command: string): Promise<CommandRunResult> {
  return $.command.run({ command, args: '', origin: { kind: 'composer' }, presentation: { isFullscreen: false, columns: 100 } })
}

async function startView($: Engine) {
  await typed($, 'm2b-pane')
  return $.ui.mount({ ...pane(PANE), surface: 'terminal' })
}

/** A session in the folder of a customer, which was given that customer's topic. */
function inAcme(folder = ACME): FakeM2b {
  const fake = new FakeM2b()
  fake.given = { topics: [{ name: 'Acme Ltd', facts: 3, current: 0 }], atStart: 'whole', offUnder: null, folder }
  return fake
}

test('the overview says that m2b is on in the folder the session runs in, names the folder, and offers to turn m2b off there', async ($, on) => {
  // Covers: B189
  await start($, on, inAcme())

  const ui = await startView($)

  // Below what the session was given and how its start printed the distillate.
  expect(await partLines(ui, 'session')).toEqual(['[Acme Ltd] 3 facts', PRINTED_WHOLE, ON_HERE, ACME, '[turn off here]'])
  // Turning m2b off is beside the point of the part: its button steps back.
  expect(await buttonsAt(ui, FOLDER_ROW)).toEqual([{ key: 'folder:off', label: 'turn off here', variant: undefined, dimColor: true }])
  expect(await texts(ui)).not.toContain(KEEPS)
  await ui.unmount()
})

test('a press waits for undo, then turns the distillate off for the folder the answer named', async ($, on) => {
  // Covers: B189
  const fake = inAcme()
  const { clock } = await start($, on, fake)
  const ui = await startView($)
  const looksBefore = fake.looks.length

  await ui.press({ key: 'folder:off' })

  expect(await linesAt(ui, FOLDER_ROW)).toEqual([ON_HERE, ACME, '[undo] turning m2b off here'])
  expect(await viewButtons(ui)).toContain('undo:folder')
  expect(await viewButtons(ui)).not.toContain('folder:off')
  await clock.advance(UNDO_MS - 1)
  expect(fake.folderCalls()).toEqual([])

  await clock.advance(1)

  expect(fake.folderCalls()).toEqual([['distillate', 'off', '--', ACME]])
  // Asked again after the write: the view is what m2b says now, not what the press hoped for.
  expect(fake.looks.slice(looksBefore)).toEqual([LOOK])
  expect(await partLines(ui, 'session')).toEqual(['[Acme Ltd] 3 facts', PRINTED_WHOLE, OFF_HERE, ACME, '[turn on here]', KEEPS])
  expect(await lookOf(ui, KEEPS)).toEqual({ color: undefined, dimColor: true, wrap: 'wrap' })
  expect(await viewButtons(ui)).toContain('folder:on')
  expect(await viewButtons(ui)).not.toContain('folder:off')
  await ui.unmount()
})

test('undo within the window leaves the folder as it was and writes nothing', async ($, on) => {
  // Covers: B189
  const fake = inAcme()
  const { clock } = await start($, on, fake)
  const ui = await startView($)

  await ui.press({ key: 'folder:off' })
  await clock.advance(UNDO_MS - 1_000)
  await ui.press({ key: 'undo:folder' })
  await clock.advance(UNDO_MS * 2)

  expect(fake.folderCalls()).toEqual([])
  expect(await linesAt(ui, FOLDER_ROW)).toEqual([ON_HERE, ACME, '[turn off here]'])
  expect(await texts(ui)).not.toContain(KEEPS)
  await ui.unmount()
})

test('where m2b is off, the overview names the folder it is off under, and the button turns it on again for that folder', async ($, on) => {
  // Covers: B189
  const fake = inAcme(`${ACME}/api`)
  fake.given = { topics: [], atStart: 'none', offUnder: ACME, folder: `${ACME}/api` }
  const { clock } = await start($, on, fake)
  const ui = await startView($)
  // The folder m2b is off under, which may lie above the session's own.
  expect(await linesAt(ui, FOLDER_ROW)).toEqual([OFF_HERE, ACME, '[turn on here]'])
  expect(await buttonsAt(ui, FOLDER_ROW)).toEqual([{ key: 'folder:on', label: 'turn on here', variant: undefined, dimColor: false }])
  expect(await texts(ui)).toContain(KEEPS)

  await ui.press({ key: 'folder:on' })
  expect(await linesAt(ui, FOLDER_ROW)).toEqual([OFF_HERE, ACME, '[undo] turning m2b on here'])
  await ui.press({ key: 'undo:folder' })
  await clock.advance(UNDO_MS * 2)
  expect(fake.folderCalls()).toEqual([])
  expect(await linesAt(ui, FOLDER_ROW)).toEqual([OFF_HERE, ACME, '[turn on here]'])

  await ui.press({ key: 'folder:on' })
  await clock.advance(UNDO_MS)

  expect(fake.folderCalls()).toEqual([['distillate', 'on', '--', ACME]])
  expect(await linesAt(ui, FOLDER_ROW)).toEqual([ON_HERE, `${ACME}/api`, '[turn off here]'])
  expect(await texts(ui)).not.toContain(KEEPS)
  await ui.unmount()
})

test('a core that names no folder gets no row for it and no button to turn m2b off, and still one to turn it on', async ($, on) => {
  // Covers: B189
  const fake = new FakeM2b()
  fake.given = { topics: [], atStart: 'whole', offUnder: null }
  const { clock } = await start($, on, fake)
  const ui = await startView($)
  expect(await linesAt(ui, FOLDER_ROW)).toBeNull()
  expect(await viewButtons(ui)).not.toContain('folder:off')

  fake.given = { topics: [], atStart: 'whole', offUnder: ACME }
  await $.turn.complete({ answer: 'done', durationMs: 5, isAborted: false, turnId: 't1', reason: 'answer' })
  await clock.advance(1)
  expect(await linesAt(ui, FOLDER_ROW)).toEqual([OFF_HERE, ACME, '[turn on here]'])
  await ui.unmount()
})

test('a look that failed offers no button for the folder, m2b does not know which one it would turn off: the one button of the view is curate now, in the part about m2b', async ($, on) => {
  // Covers: B189
  const fake = inAcme()
  fake.lookFails = 'the machine state cannot be read'
  await start($, on, fake)

  const ui = await startView($)

  expect(await viewButtons(ui)).toEqual([CURATE_NOW])
  await ui.unmount()
})

test('a write m2b refuses is said in the part of the session, in the color of trouble, and the button stays', async ($, on) => {
  // Covers: B189
  const fake = inAcme()
  fake.distillateFails = 'the machine config cannot be written'
  on('prompt.submit', (_, e) => ({ text: e.text }))
  const { clock } = await start($, on, fake)
  const ui = await startView($)

  await ui.press({ key: 'folder:off' })
  await clock.advance(UNDO_MS)

  const refused = `m2b could not be turned off in ${ACME}: the machine config cannot be written`
  expect(await partLines(ui, 'session')).toEqual(['[Acme Ltd] 3 facts', PRINTED_WHOLE, ON_HERE, ACME, '[turn off here]', refused])
  expect(await lookOf(ui, refused)).toEqual({ color: 'error', dimColor: undefined, wrap: 'wrap' })
  // Said where it was pressed, and nowhere else in the view.
  expect(await partLines(ui, 'waits')).toEqual(['Nothing waits for you.'])
  expect(await texts(ui)).not.toContain(KEEPS)
  expect(await viewButtons(ui)).toContain('folder:off')

  // The next prompt clears what was said, as it clears what m2b said to a press on a row.
  await $.prompt.submit({ text: 'go on', origin: { kind: 'composer' }, wait: false })
  expect((await texts(ui)).some(line => line.startsWith('m2b could not be turned off in'))).toBe(false)
  await ui.unmount()
})

test('a press that could not turn m2b on again is said in the part of the session too, and m2b stays off there', async ($, on) => {
  // Covers: B189
  const fake = inAcme()
  fake.given = { topics: [], atStart: 'whole', offUnder: ACME, folder: ACME }
  fake.distillateFails = 'the machine config cannot be written'
  const { clock } = await start($, on, fake)
  const ui = await startView($)

  await ui.press({ key: 'folder:on' })
  await clock.advance(UNDO_MS)

  const refused = `m2b could not be turned on under ${ACME}: the machine config cannot be written`
  expect(fake.folderCalls()).toEqual([['distillate', 'on', '--', ACME]])
  expect(await partLines(ui, 'session')).toEqual([PRINTED_WHOLE, OFF_HERE, ACME, '[turn on here]', KEEPS, refused])
  expect(await lookOf(ui, refused)).toEqual({ color: 'error', dimColor: undefined, wrap: 'wrap' })
  await ui.unmount()
})

test('the next press on the button clears what the last one could not write, before it writes', async ($, on) => {
  // Covers: B189
  const fake = inAcme()
  fake.distillateFails = 'the machine config cannot be written'
  const { clock } = await start($, on, fake)
  const ui = await startView($)
  await ui.press({ key: 'folder:off' })
  await clock.advance(UNDO_MS)
  expect((await texts(ui)).some(line => line.startsWith('m2b could not be turned off in'))).toBe(true)

  fake.distillateFails = null
  await ui.press({ key: 'folder:off' })

  expect((await texts(ui)).some(line => line.startsWith('m2b could not be turned off in'))).toBe(false)
  await ui.press({ key: 'undo:folder' })
  expect((await texts(ui)).some(line => line.startsWith('m2b could not be turned off in'))).toBe(false)
  await ui.unmount()
})

test('a launcher that cannot be started is said the same way', async ($, on) => {
  // Covers: B189
  const fake = inAcme()
  const { clock } = await start($, on, fake)
  const ui = await startView($)

  await ui.press({ key: 'folder:off' })
  fake.runFails = 'timed out'
  await clock.advance(UNDO_MS)
  fake.runFails = null

  expect((await texts(ui)).some(line => line.startsWith(`m2b could not be turned off in ${ACME}: `))).toBe(true)
  await ui.unmount()
})

test('while the write is under way the row offers nothing, and a second press cannot queue', async ($, on) => {
  // Covers: B189
  const fake = inAcme()
  fake.delayMs = args => (args[0] === 'distillate' ? 2_000 : 0)
  const { clock } = await start($, on, fake)
  const ui = await startView($)

  await ui.press({ key: 'folder:off' })
  await clock.advance(UNDO_MS + 1)

  // The folder's row has none: the topic's button and curate now belong to other rows.
  expect(await viewButtons(ui)).toEqual(['topic:0', CURATE_NOW])
  expect(await linesAt(ui, FOLDER_ROW)).toEqual([ON_HERE, ACME, 'turning m2b off here…'])
  await clock.advance(2_000)
  expect(await viewButtons(ui)).toContain('folder:on')
  expect(fake.folderCalls()).toHaveLength(1)
  await ui.unmount()
})

test('a folder is drawn whole, so what is read is the folder the press turns off', async ($, on) => {
  // Covers: B189
  const odd = '/home/alex/code/ac\u001b[31mme\u200b\n'
  const fake = inAcme(odd)
  const { clock } = await start($, on, fake)
  const ui = await startView($)
  // A character a terminal would run or draw with no width is written out, never left out:
  // left out, the pane would name a folder beside the one the press turns off.
  const written = '/home/alex/code/ac\\x1b[31mme\\u200b\\x0a'
  expect(await linesAt(ui, FOLDER_ROW)).toEqual([ON_HERE, written, '[turn off here]'])
  expect(await pathPieces(ui, FOLDER_ROW)).toEqual(['/home', '/alex', '/code', '/ac\\x1b[31mme\\u200b\\x0a'])

  await ui.press({ key: 'folder:off' })
  expect(await linesAt(ui, FOLDER_ROW)).toEqual([ON_HERE, written, '[undo] turning m2b off here'])
  await clock.advance(UNDO_MS)

  expect(fake.folderCalls()).toEqual([['distillate', 'off', '--', odd]])
  expect(await linesAt(ui, FOLDER_ROW)).toEqual([OFF_HERE, written, '[turn on here]'])
  await ui.unmount()
})

test('a path is one text for each folder, so it breaks before a slash and never inside a name, with a space in the name too', async ($, on) => {
  // Covers: B189
  const spaced = '/home/alex/my code/acme ltd'
  await start($, on, inAcme(spaced))
  await typed($, 'm2b-pane')

  for (const columns of [24, 80]) {
    const ui = await $.ui.mount({ ...pane(PANE, columns), surface: 'terminal' })

    expect(await pathPieces(ui, FOLDER_ROW)).toEqual(['/home', '/alex', '/my code', '/acme ltd'])
    expect((await linesAt(ui, FOLDER_ROW))?.[1]).toBe(spaced)
    // A piece is never cut or wrapped: the row breaks between the pieces.
    for (const piece of ['/home', '/my code', '/acme ltd']) {
      expect(await lookOf(ui, piece)).toEqual({ color: undefined, dimColor: true, wrap: undefined })
    }
    await ui.unmount()
  }
})

test('two folders read alike only when they are the same folder', () => {
  // Covers: B189
  expect(wholePath('/home/alex/code/acme')).toBe('/home/alex/code/acme')
  expect(wholePath('/home/alex/my code/acme')).toBe('/home/alex/my code/acme')
  // A line break, a tab, a space that is not the plain one, a space at an end: each written out in its place.
  expect(wholePath('/x/acme\n')).toBe('/x/acme\\x0a')
  expect(wholePath('/x/ac\tme')).toBe('/x/ac\\x09me')
  expect(wholePath('/x/ac\u00a0me')).toBe('/x/ac\\xa0me')
  expect(wholePath('/x/ac\u2028me')).toBe('/x/ac\\u2028me')
  expect(wholePath('/x/acme ')).toBe('/x/acme\\x20')
  expect(wholePath(' /x/acme')).toBe('\\x20/x/acme')
  expect(wholePath('/x/ac  me')).toBe('/x/ac  me')
  // A backslash in the name is doubled, so it is not read as a character written out.
  expect(wholePath('/x/ac\\x1bme')).toBe('/x/ac\\\\x1bme')
  expect(wholePath('/x/ac\u001bme')).toBe('/x/ac\\x1bme')
  const alike = ['/x/acme', '/x/acme ', '/x/acme\n', '/x/acme\u200b', '/x/acme\u00a0', '/x/ac\u001bme', '/x/ac\\x1bme']
  expect(new Set(alike.map(wholePath)).size).toBe(alike.length)
})

test('where the pane cannot be shown, the lines say whether m2b is on or off with the folder, and offer no button', async ($, on) => {
  // Covers: B189
  const fake = inAcme()
  fake.paneWaits = 'no surface attached places panes'
  const { clock } = await start($, on, fake)

  const whileOn = ((await typed($, 'm2b-pane')).text ?? '').split('\n')
  expect(whileOn).toContain(`  m2b is on in this folder: ${ACME}`)
  expect(whileOn).not.toContain(`  ${KEEPS}`)

  fake.given = { topics: [], atStart: 'whole', offUnder: ACME, folder: ACME }
  await $.turn.complete({ answer: 'done', durationMs: 5, isAborted: false, turnId: 't1', reason: 'answer' })
  await clock.advance(1)
  const whileOff = ((await typed($, 'm2b-pane')).text ?? '').split('\n')

  expect(whileOff).toContain(`  m2b is off under ${ACME}`)
  expect(whileOff).toContain(`  ${KEEPS}`)
  for (const answer of [whileOn, whileOff]) {
    expect(answer.join('\n')).not.toContain('turn on')
    expect(answer.join('\n')).not.toContain('turn off')
  }
})

test('the row wraps in a pane as narrow as a dock gets: its sentence wraps, and the path breaks between its folders', async ($, on) => {
  // Covers: B189
  await start($, on, inAcme())
  await typed($, 'm2b-pane')

  const ui = await $.ui.mount({ ...pane(PANE, 24), surface: 'terminal' })

  expect((await lookOf(ui, ON_HERE))?.wrap).toBe('wrap')
  expect(await pathPieces(ui, FOLDER_ROW)).toEqual(['/home', '/alex', '/code', '/acme'])
  await ui.unmount()
})
