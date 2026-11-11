import { expect, test } from 'claude-code/testing'

import { parseReview } from '../../hooks/tasks'
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
    copies: [
      { path: '/home/alex/older', captures: [] },
      { path: '/home/alex/copy', captures: ['a.md', 'b.md'] },
    ],
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
  expect(shown).toContain('facts before the run: /home/alex/older')
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

test('ok writes nothing when a run rewrote the review since it was drawn, and shows the new one', async ($, on) => {
  // Covers: B106
  const fake = changedFake()
  const { clock } = await start($, on, fake)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })

  await ui.press({ key: 'ok:r1' })
  const review = fake.tasks.find(task => task.id === 'r1')
  if (review === undefined) {
    throw new Error('the fake has no review')
  }
  review.notes = `${review.notes}\n\nlint: broken link in c.md`
  await clock.advance(UNDO_MS)

  expect(fake.writes()).toEqual([])
  const shown = await texts(ui)
  expect(shown).toContain('The review changed since it was drawn, nothing written: m2b: review')
  expect(shown).toContain('lint: broken link in c.md')
  await ui.unmount()
})

test('ok on a review another session closed writes nothing and takes the row away', async ($, on) => {
  // Covers: B106
  const fake = changedFake()
  const { clock } = await start($, on, fake)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })

  await ui.press({ key: 'ok:r1' })
  const review = fake.tasks.find(task => task.id === 'r1')
  if (review !== undefined) {
    review.completed = true
  }
  await clock.advance(UNDO_MS)

  expect(fake.writes()).toEqual([])
  const shown = (await texts(ui)).join('\n')
  expect(shown).toContain('Already settled in another session, nothing written: m2b: review')
  expect(await ui.findAll({ type: 'Button' })).toHaveLength(0)
  await ui.unmount()
})

test('the findings a shared answer keeps stay whole, for a band that draws no changes', () => {
  // Covers: B106
  const notes = ['m2b:review\nCuration run of 2026-03-14 18:02', SAM_PARAGRAPH, 'lint: broken link in a.md'].join('\n\n')
  const list = [{ id: 'r1', title: 'm2b: review', notes, completed: false, dropped: false, marker: 'review' }]

  const review = parseReview(list, { changes: [], copies: [], paragraphs: [SAM_PARAGRAPH] })

  expect(review?.findings).toEqual([SAM_PARAGRAPH, 'lint: broken link in a.md'])
  expect(review?.told).toEqual([SAM_PARAGRAPH])
})
