import { expect, test } from 'claude-code/testing'
import type { CommandRunResult } from 'claude-code'
import type { Engine } from 'claude-code/testing'

import { wholePath } from '../../hooks/plain-text'
import { FakeM2b, SESSION_ID, pane, start, texts } from './harness'

const PANE = 'm2b'
const UNDO_MS = 5_000
const ACME = '/home/alex/code/acme'
const LOOK = ['band', '--json', '--session', SESSION_ID, '--session-only']
const OFF_UNDER_ACME = `The distillate is off under ${ACME}: a session that starts there gets none.`
const KEEPS = 'This session keeps what it was given and gets no more topics.'

function typed($: Engine, command: string): Promise<CommandRunResult> {
  return $.command.run({ command, args: '', origin: { kind: 'composer' }, presentation: { isFullscreen: false, columns: 100 } })
}

async function startView($: Engine) {
  await typed($, 'm2b')
  return $.ui.mount({ ...pane(PANE), surface: 'terminal' })
}

/** A session in the folder of a customer, which was given that customer's topic. */
function inAcme(folder = ACME): FakeM2b {
  const fake = new FakeM2b()
  fake.given = { topics: [{ name: 'Acme Ltd', facts: 3, current: 0 }], atStart: 'whole', offUnder: null, folder }
  return fake
}

async function buttons(ui: { findAll: (q: { type: string }) => Promise<{ key?: string }[]> }): Promise<(string | undefined)[]> {
  return (await ui.findAll({ type: 'Button' })).map(button => button.key)
}

test('the start view offers to leave m2b out of the folder the session runs in, and names it', async ($, on) => {
  // Covers: B189
  await start($, on, inAcme())

  const ui = await startView($)

  expect(await buttons(ui)).toContain('folder:off')
  // Below what the session was given and how its start printed the distillate, above its notes.
  expect((await texts(ui)).slice(0, 5)).toEqual([
    'In this session',
    'Acme Ltd: 3 facts',
    'The distillate was printed whole at the start.',
    `of ${ACME}`,
    'Waits for you',
  ])
  expect((await ui.findAll({ type: 'Button' })).find(button => button.key === 'folder:off')?.props['label']).toBe('leave m2b out')
  await ui.unmount()
})

test('a press waits for undo, then turns the distillate off for the folder the answer named', async ($, on) => {
  // Covers: B189
  const fake = inAcme()
  const { clock } = await start($, on, fake)
  const ui = await startView($)
  const looksBefore = fake.looks.length

  await ui.press({ key: 'folder:off' })

  expect(await texts(ui)).toContain(`leaving m2b out of ${ACME}`)
  expect(await buttons(ui)).toContain('undo:folder')
  expect(await buttons(ui)).not.toContain('folder:off')
  await clock.advance(UNDO_MS - 1)
  expect(fake.folderCalls()).toEqual([])

  await clock.advance(1)

  expect(fake.folderCalls()).toEqual([['distillate', 'off', '--', ACME]])
  // Asked again after the write: the view is what m2b says now, not what the press hoped for.
  expect(fake.looks.slice(looksBefore)).toEqual([LOOK])
  const shown = await texts(ui)
  expect(shown).toContain(OFF_UNDER_ACME)
  expect(shown).toContain(KEEPS)
  expect(shown).toContain('Acme Ltd: 3 facts')
  expect(await buttons(ui)).toContain('folder:on')
  expect(await buttons(ui)).not.toContain('folder:off')
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
  expect(await buttons(ui)).toContain('folder:off')
  expect(await texts(ui)).not.toContain(KEEPS)
  await ui.unmount()
})

test('where the distillate is off, the button turns it on again for the folder it is off under', async ($, on) => {
  // Covers: B189
  const fake = inAcme(`${ACME}/api`)
  fake.given = { topics: [], atStart: 'none', offUnder: ACME, folder: `${ACME}/api` }
  const { clock } = await start($, on, fake)
  const ui = await startView($)
  expect(await texts(ui)).toContain(KEEPS)
  expect(await texts(ui)).toContain(`the distillate under ${ACME} again`)

  await ui.press({ key: 'folder:on' })
  expect(await texts(ui)).toContain(`turning the distillate on under ${ACME}`)
  await clock.advance(UNDO_MS)

  // The folder that is turned off, which may lie above the session's own.
  expect(fake.folderCalls()).toEqual([['distillate', 'on', '--', ACME]])
  const shown = await texts(ui)
  expect(shown).not.toContain(OFF_UNDER_ACME)
  expect(shown).not.toContain(KEEPS)
  expect(await buttons(ui)).toContain('folder:off')
  await ui.unmount()
})

test('a core that names no folder gets no button to leave m2b out, and still one to turn it on', async ($, on) => {
  // Covers: B189
  const fake = new FakeM2b()
  fake.given = { topics: [], atStart: 'whole', offUnder: null }
  const { clock } = await start($, on, fake)
  const ui = await startView($)
  expect(await buttons(ui)).not.toContain('folder:off')

  fake.given = { topics: [], atStart: 'whole', offUnder: ACME }
  await $.turn.complete({ answer: 'done', durationMs: 5, isAborted: false, turnId: 't1', reason: 'answer' })
  await clock.advance(1)
  expect(await buttons(ui)).toContain('folder:on')
  await ui.unmount()
})

test('a look that failed offers no button: m2b does not know which folder it would turn off', async ($, on) => {
  // Covers: B189
  const fake = inAcme()
  fake.lookFails = 'the machine state cannot be read'
  await start($, on, fake)

  const ui = await startView($)

  expect(await buttons(ui)).toEqual([])
  await ui.unmount()
})

test('a write m2b refuses is said in the view, and the button stays', async ($, on) => {
  // Covers: B189
  const fake = inAcme()
  fake.distillateFails = 'the machine config cannot be written'
  on('prompt.submit', (_, e) => ({ text: e.text }))
  const { clock } = await start($, on, fake)
  const ui = await startView($)

  await ui.press({ key: 'folder:off' })
  await clock.advance(UNDO_MS)

  const shown = await texts(ui)
  expect(shown).toContain(`m2b could not leave itself out of ${ACME}: the machine config cannot be written`)
  expect(shown).not.toContain(KEEPS)
  expect(await buttons(ui)).toContain('folder:off')

  // The next prompt clears what was said, as it clears the band's notices.
  await $.prompt.submit({ text: 'go on', origin: { kind: 'composer' }, wait: false })
  expect((await texts(ui)).some(line => line.startsWith('m2b could not leave itself out'))).toBe(false)
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
  expect((await texts(ui)).some(line => line.startsWith('m2b could not leave itself out'))).toBe(true)

  fake.distillateFails = null
  await ui.press({ key: 'folder:off' })

  expect((await texts(ui)).some(line => line.startsWith('m2b could not leave itself out'))).toBe(false)
  await ui.press({ key: 'undo:folder' })
  expect((await texts(ui)).some(line => line.startsWith('m2b could not leave itself out'))).toBe(false)
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

  expect((await texts(ui)).some(line => line.startsWith(`m2b could not leave itself out of ${ACME}: `))).toBe(true)
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

  expect(await buttons(ui)).toEqual(['topic:0'])
  expect(await texts(ui)).toContain(`leaving m2b out of ${ACME}`)
  await clock.advance(2_000)
  expect(await buttons(ui)).toContain('folder:on')
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
  expect(await texts(ui)).toContain('of /home/alex/code/ac\\x1b[31mme\\u200b\\x0a')
  expect(await texts(ui)).not.toContain(`of ${ACME}`)

  await ui.press({ key: 'folder:off' })
  expect(await texts(ui)).toContain('leaving m2b out of /home/alex/code/ac\\x1b[31mme\\u200b\\x0a')
  await clock.advance(UNDO_MS)

  expect(fake.folderCalls()).toEqual([['distillate', 'off', '--', odd]])
  expect(await texts(ui)).toContain(
    'The distillate is off under /home/alex/code/ac\\x1b[31mme\\u200b\\x0a: a session that starts there gets none.',
  )
  await ui.unmount()
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

test('where the pane cannot be shown, the lines say the state and offer no button', async ($, on) => {
  // Covers: B189
  const fake = inAcme()
  fake.given = { topics: [], atStart: 'whole', offUnder: ACME, folder: ACME }
  fake.paneWaits = 'no surface attached places panes'
  await start($, on, fake)

  const answer = (await typed($, 'm2b')).text ?? ''

  expect(answer).toContain(`  ${OFF_UNDER_ACME}`)
  expect(answer).toContain(`  ${KEEPS}`)
  expect(answer).not.toContain('turn on')
  expect(answer).not.toContain('leave m2b out')
})

test('the row wraps in a pane as narrow as a dock gets', async ($, on) => {
  // Covers: B189
  await start($, on, inAcme())
  await typed($, 'm2b')

  const ui = await $.ui.mount({ ...pane(PANE, 24), surface: 'terminal' })

  expect((await ui.findAll({ type: 'Text', text: `of ${ACME}` }))[0]?.props['wrap']).toBe('wrap')
  await ui.unmount()
})
