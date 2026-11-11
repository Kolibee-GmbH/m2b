import { expect, test } from 'claude-code/testing'

import { BAND, FakeM2b, pane, start, texts } from './harness'

const UNDO_MS = 5_000
const SAM_PARAGRAPH = 'ingest: rewrote the facts line "- Sam, neighbour — Sam Rivers, Lee (sam.md)" as "- Sam, ..."'
const COPY_PARAGRAPH = 'ingest: memory/ as it was before this run is in /home/alex/copy; check the changes above'

/** An open review whose run changed two facts, as `m2b band --json` of 0.3.3 names them. */
function changedFake(): FakeM2b {
  const fake = new FakeM2b()
  fake.review('r1', [SAM_PARAGRAPH, 'ingest: removed the facts line "- Dana likes old maps (dana.md)"', COPY_PARAGRAPH, 'lint: broken link in a.md'])
  fake.reviewDetails = {
    changes: [
      {
        kind: 'rewrote',
        file: 'sam.md',
        topic: 'Sam',
        parts: [
          { text: 'Sam, neighbour — Sam Rivers', change: 'same' },
          { text: ' (carpenter)', change: 'added' },
          { text: ', Lee', change: 'same' },
        ],
      },
      { kind: 'removed', file: 'dana.md', topic: 'Dana likes old maps', parts: [{ text: 'Dana likes old maps', change: 'same' }] },
    ],
    copy: { path: '/home/alex/copy', captures: ['a.md', 'b.md'] },
    paragraphs: [SAM_PARAGRAPH, 'ingest: removed the facts line "- Dana likes old maps (dana.md)"', COPY_PARAGRAPH],
  }
  return fake
}

test('the band sums up the changed facts in one row and leaves the other findings as written', async ($, on) => {
  // Covers: B106
  await start($, on, changedFake())
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  const shown = await texts(ui)

  expect(shown).toContain('m2b: review')
  expect(shown).toContain('2 facts changed: Sam, Dana likes old maps')
  expect(shown).toContain('lint: broken link in a.md')
  expect(shown).toContain('the whole review: /m2b-review')
  expect(shown.join('\n')).not.toContain('rewrote the facts line')
  expect(shown.join('\n')).not.toContain('/home/alex/copy')
  await ui.unmount()
})

test('ok closes the review after the undo window, and undo within it writes nothing', async ($, on) => {
  // Covers: B106
  const fake = changedFake()
  const { clock } = await start($, on, fake)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })

  await ui.press({ key: 'ok:r1' })
  expect(await texts(ui)).toContain('closing: m2b: review')
  await ui.press({ key: 'undo:r1' })
  await clock.advance(UNDO_MS * 2)
  expect(fake.writes()).toEqual([])

  await ui.press({ key: 'ok:r1' })
  await clock.advance(UNDO_MS)
  expect(fake.writes()).toEqual([['tasks', 'complete', '--', 'r1']])
  expect((await texts(ui)).join('\n')).not.toContain('m2b: review')
  await ui.unmount()
})

test('the pane shows each changed fact with its file and the added and removed words marked', async ($, on) => {
  // Covers: B106
  await start($, on, changedFake())
  await $.command.run({ command: 'm2b-review', args: '', origin: { kind: 'composer' }, presentation: { isFullscreen: false, columns: 100 } })
  const ui = await $.ui.mount({ ...pane('m2b'), surface: 'terminal' })
  const shown = (await texts(ui)).join('\n')

  expect(shown).toContain('Sam (sam.md)')
  expect(shown).toContain('Dana likes old maps (dana.md, line removed)')
  expect(shown).toContain('facts before the run: /home/alex/copy; 2 notes filed')
  expect(shown).toContain('lint: broken link in a.md')
  expect(shown).not.toContain('rewrote the facts line')
  const added = (await ui.findAll({ type: 'Text' })).filter(found => found.props['color'] === 'success')
  expect(added.map(found => found.text)).toEqual([' (carpenter)'])
  await ui.unmount()
})

test('a core that names no changes leaves every finding as written', async ($, on) => {
  // Covers: B106
  const fake = changedFake()
  fake.reviewDetails = null
  await start($, on, fake)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  const shown = (await texts(ui)).join('\n')

  expect(shown).toContain('rewrote the facts line')
  expect(shown).not.toContain('facts changed')
  expect(shown).not.toContain('the whole review')
  await ui.unmount()
})
