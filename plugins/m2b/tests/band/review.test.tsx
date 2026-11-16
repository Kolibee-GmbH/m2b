import { expect, test } from 'claude-code/testing'

import { parseReview } from '../../hooks/tasks'
import {
  BAND,
  CALM_ROW,
  FakeM2b,
  ONLY_WHILE_WAITING,
  answerKeys,
  insetsAt,
  linesAt,
  lookOf,
  pane,
  partLines,
  pathPieces,
  piecesAt,
  pressTab,
  rowSaying,
  shownBand,
  start,
  startView,
  texts,
} from './harness'
import type { ShownPiece } from './harness'

const UNDO_MS = 5_000
const REVIEW = 'Review of the last curation run'
const REVIEW_ROW = 'review:r1'
const REVIEW_CHANGED = 'The review changed since it was drawn, nothing written: Review of the last curation run'
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

test('the review counts as one in the band, and its row in the pane is named for what it is and sums up the changed facts beside ok', async ($, on) => {
  // Covers: B106
  await start($, on, changedFake())
  const band = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await shownBand(band)).toEqual(rowSaying('1 waits for you'))
  await band.unmount()

  const ui = await startView($)
  const shown = await texts(ui)
  expect(await linesAt(ui, REVIEW_ROW)).toEqual([REVIEW, '[ok] 2 facts changed: Sam, Dana likes old maps'])
  expect(await lookOf(ui, '2 facts changed: Sam, Dana likes old maps')).toEqual({ color: undefined, dimColor: true, wrap: 'wrap' })
  // Whatever the task is titled in the task list, the row does not say it.
  expect(shown).not.toContain('m2b: review')
  expect(shown).toContain('The whole review is in the tab Review.')
  expect(await answerKeys(ui)).toEqual(['ok:r1'])
  expect(shown.join('\n')).not.toContain('rewrote the facts line')
  expect(shown.join('\n')).not.toContain('/home/alex/copy')

  // The findings no change stands for are left as written, in the view of the review.
  await pressTab(ui, 'review')
  const whole = (await texts(ui)).join('\n')
  expect(whole).toContain('lint: broken link in a.md')
  expect(whole).not.toContain('rewrote the facts line')
  await ui.unmount()
})

test('ok closes the review after the undo window, and undo within it writes nothing', async ($, on) => {
  // Covers: B106
  const fake = changedFake()
  const { clock } = await start($, on, fake)
  const ui = await startView($)

  await ui.press({ key: 'ok:r1' })
  expect(await linesAt(ui, REVIEW_ROW)).toEqual([REVIEW, '[undo] closing'])
  expect(await answerKeys(ui)).toEqual(['undo:r1'])
  await ui.press({ key: 'undo:r1' })
  await clock.advance(UNDO_MS * 2)
  expect(fake.writes()).toEqual([])

  await ui.press({ key: 'ok:r1' })
  await clock.advance(UNDO_MS)
  expect(fake.writes()).toEqual([['tasks', 'complete', '--', 'r1']])
  expect(await linesAt(ui, REVIEW_ROW)).toBeNull()
  expect(await partLines(ui, 'waits')).toEqual(['Nothing waits for you.'])
  await ui.unmount()
})

test('the pane shows each changed fact with its file and the added and removed words marked', async ($, on) => {
  // Covers: B106
  await start($, on, changedFake())
  await $.command.run({ command: 'm2b-review', args: '', origin: { kind: 'composer' }, presentation: { isFullscreen: false, columns: 100 } })
  const ui = await $.ui.mount({ ...pane('m2b'), surface: 'terminal' })

  // Under the run's line: each change, where the copies of the facts lie, then the finding no change stands for.
  expect(await partLines(ui, 'run')).toEqual([
    'succeeded',
    'Sam (sam.md)',
    'Sam, neighbour — Sam Rivers (carpenter), Lee',
    'Dana likes old maps (dana.md, line removed)',
    'Dana likes old maps',
    'facts before the run:',
    '/home/alex/older',
    'facts before the run; 2 notes filed:',
    '/home/alex/copy',
    'lint: broken link in a.md',
  ])
  expect((await texts(ui)).join('\n')).not.toContain('rewrote the facts line')
  const added = (await piecesAt(ui, 'part:run')).filter(piece => piece.color === 'success')
  expect(added.map(piece => piece.text)).toEqual([' (carpenter)'])
  await ui.unmount()
})

/** A piece of text as drawn where a test names nothing else: to be read, in no color. */
function piece(text: string, look: Partial<ShownPiece> = {}): ShownPiece {
  return { text, color: undefined, dimColor: undefined, weight: undefined, strikethrough: undefined, ...look }
}

test('a changed fact is its topic in bold with its file stepped back and, indented whole below, its line: added words in the color of what is done, removed ones in the color of trouble and struck through, the rest plain', async ($, on) => {
  // Covers: B101, B106
  const fake = changedFake()
  if (fake.reviewDetails === null) {
    throw new Error('the fake names no changes')
  }
  fake.reviewDetails.changes = [
    {
      kind: 'rewrote',
      file: 'sam.md',
      topic: 'Sam',
      parts: [
        { text: 'Sam, neighbour', change: 'same' },
        { text: ' (carpenter)', change: 'added' },
        { text: ', Lee', change: 'removed' },
      ],
    },
    { kind: 'removed', file: 'acme.md', topic: 'Acme', parts: [{ text: 'Acme pays within 30 days', change: 'same' }] },
  ]
  fake.reviewDetails.copies = [{ path: '/home/alex/my notes/copy', captures: ['a.md'] }]
  await start($, on, fake)
  await $.command.run({ command: 'm2b-review', args: '', origin: { kind: 'composer' }, presentation: { isFullscreen: false, columns: 100 } })
  const ui = await $.ui.mount({ ...pane('m2b'), surface: 'terminal' })
  const dim = { dimColor: true }

  expect(await piecesAt(ui, 'part:run')).toEqual([
    piece('Last curation run', { color: 'remember', weight: 'bold' }),
    piece('succeeded'),
    piece('Sam', { weight: 'bold' }),
    piece(' (sam.md)', dim),
    piece('Sam, neighbour'),
    piece(' (carpenter)', { color: 'success' }),
    // Struck through as well, so it reads as removed without its color.
    piece(', Lee', { color: 'error', strikethrough: true }),
    piece('Acme', { weight: 'bold' }),
    // What happened to a whole line stands after its file; the line itself is as it was.
    piece(' (acme.md, line removed)', dim),
    piece('Acme pays within 30 days'),
    piece('facts before the run; 1 note filed:', dim),
    // The path of the copy is one text for each folder, so it breaks before a slash and nowhere else.
    piece('/home', dim),
    piece('/alex', dim),
    piece('/my notes', dim),
    piece('/copy', dim),
    piece('lint: broken link in a.md'),
  ])
  expect(await pathPieces(ui, 'part:run')).toEqual(['/home', '/alex', '/my notes', '/copy'])
  // A change's line and a finding stand in by a box, so their further lines stand in as well where they wrap.
  expect(await insetsAt(ui, 'part:run')).toEqual([
    { paddingLeft: 2, lines: ['Sam, neighbour (carpenter), Lee'] },
    { paddingLeft: 2, lines: ['Acme pays within 30 days'] },
    { paddingLeft: 2, lines: ['lint: broken link in a.md'] },
  ])
  await ui.unmount()
})

test('a fact file a run removed or emptied is named with what happened to it', async ($, on) => {
  // Covers: B101, B106
  const fake = changedFake()
  if (fake.reviewDetails === null) {
    throw new Error('the fake names no changes')
  }
  // As the core names a change of a whole file: by the file, without a line.
  fake.reviewDetails.changes = [
    { kind: 'file_removed', file: 'acme.md', topic: 'acme.md', parts: [] },
    { kind: 'file_emptied', file: 'northwind.md', topic: 'northwind.md', parts: [] },
  ]
  await start($, on, fake)
  await $.command.run({ command: 'm2b-review', args: '', origin: { kind: 'composer' }, presentation: { isFullscreen: false, columns: 100 } })
  const ui = await $.ui.mount({ ...pane('m2b'), surface: 'terminal' })

  // The file is named once, and no empty line stands below it: a file that went holds no line to show.
  const lines = (await partLines(ui, 'run')) ?? []
  expect(lines.slice(1, 3)).toEqual(['acme.md (file removed)', 'northwind.md (file emptied)'])
  await ui.unmount()
})

test('a core that names no changes leaves every finding as written', async ($, on) => {
  // Covers: B106
  const fake = changedFake()
  fake.reviewDetails = null
  await start($, on, fake)
  const ui = await startView($)
  // Nothing stands beside ok: no count of none.
  expect(await linesAt(ui, REVIEW_ROW)).toEqual([REVIEW, '[ok]'])
  expect((await texts(ui)).join('\n')).not.toContain('changed')

  await pressTab(ui, 'review')
  const whole = (await texts(ui)).join('\n')
  expect(whole).toContain('rewrote the facts line')
  expect(whole).toContain('/home/alex/copy')
  expect(whole).not.toContain('facts changed')
  await ui.unmount()
})

test('ok writes nothing when a run rewrote the review since it was drawn, says so where it was pressed, and shows the new one', async ($, on) => {
  // Covers: B106, B207
  const fake = changedFake()
  const { clock } = await start($, on, fake)
  const band = await $.ui.mount({ ...BAND, surface: 'terminal' })
  const ui = await startView($)

  await ui.press({ key: 'ok:r1' })
  const review = fake.tasks.find(task => task.id === 'r1')
  if (review === undefined) {
    throw new Error('the fake has no review')
  }
  review.notes = `${review.notes}\n\nlint: broken link in c.md`
  await clock.advance(UNDO_MS)

  expect(fake.writes()).toEqual([])
  expect(await shownBand(band)).toEqual(rowSaying('1 waits for you'))
  expect((await partLines(ui, 'waits'))?.slice(0, 2)).toEqual([REVIEW_CHANGED, REVIEW])
  expect(await lookOf(ui, REVIEW_CHANGED)).toEqual({ color: 'error', dimColor: undefined, wrap: 'wrap' })
  expect(await answerKeys(ui)).toEqual(['ok:r1'])
  await pressTab(ui, 'review')
  expect(await texts(ui)).toContain('lint: broken link in c.md')
  await ui.unmount()
  await band.unmount()
})

test('ok pressed in the view of the review on a review a run rewrote says so above its row there, until the next prompt, and the band keeps counting', async ($, on) => {
  // Covers: B207
  on('prompt.submit', (_, e) => ({ text: e.text }))
  const fake = changedFake()
  const { clock } = await start($, on, fake)
  const band = await $.ui.mount({ ...BAND, surface: 'terminal' })
  await $.command.run({ command: 'm2b-review', args: '', origin: { kind: 'composer' }, presentation: { isFullscreen: false, columns: 100 } })
  const ui = await $.ui.mount({ ...pane('m2b'), surface: 'terminal' })

  await ui.press({ key: 'ok:r1' })
  const review = fake.tasks.find(task => task.id === 'r1')
  if (review === undefined) {
    throw new Error('the fake has no review')
  }
  review.notes = `${review.notes}\n\nlint: broken link in c.md`
  await clock.advance(UNDO_MS)

  expect(fake.writes()).toEqual([])
  const shown = await texts(ui)
  expect(shown[shown.indexOf(REVIEW_CHANGED) + 1]).toBe(REVIEW)
  expect(await lookOf(ui, REVIEW_CHANGED)).toEqual({ color: 'error', dimColor: undefined, wrap: 'wrap' })
  expect(await shownBand(band)).toEqual(rowSaying('1 waits for you'))

  await $.prompt.submit({ text: 'go on', origin: { kind: 'composer' }, wait: false })
  expect(await texts(ui)).not.toContain(REVIEW_CHANGED)
  expect(await linesAt(ui, REVIEW_ROW)).toEqual([REVIEW, '[ok] 2 facts changed: Sam, Dana likes old maps'])
  await ui.unmount()
  await band.unmount()
})

test('ok on a review another session closed writes nothing, says so where it was pressed, and takes the row away', async ($, on) => {
  // Covers: B106, B207
  const fake = changedFake()
  fake.shows = ONLY_WHILE_WAITING
  const { clock } = await start($, on, fake)
  const band = await $.ui.mount({ ...BAND, surface: 'terminal' })
  const ui = await startView($)

  await ui.press({ key: 'ok:r1' })
  const review = fake.tasks.find(task => task.id === 'r1')
  if (review !== undefined) {
    review.completed = true
  }
  await clock.advance(UNDO_MS)

  expect(fake.writes()).toEqual([])
  // Nothing waits any more, so the band draws nothing of its own: what m2b said is in the pane.
  expect(await shownBand(band)).toBeNull()
  expect(await partLines(ui, 'waits')).toEqual([
    'Already settled in another session, nothing written: Review of the last curation run',
    'Nothing waits for you.',
  ])
  expect(await answerKeys(ui)).toEqual([])
  expect(await linesAt(ui, REVIEW_ROW)).toBeNull()
  await ui.unmount()
  await band.unmount()
})

test('ok on a review another session closed leaves a band that is always there calm: what m2b said is in the pane', async ($, on) => {
  // Covers: B207, B213
  const fake = changedFake()
  const { clock } = await start($, on, fake)
  const band = await $.ui.mount({ ...BAND, surface: 'terminal' })
  const ui = await startView($)

  await ui.press({ key: 'ok:r1' })
  const review = fake.tasks.find(task => task.id === 'r1')
  if (review !== undefined) {
    review.completed = true
  }
  await clock.advance(UNDO_MS)

  expect(fake.writes()).toEqual([])
  expect(await shownBand(band)).toEqual(CALM_ROW)
  expect(await partLines(ui, 'waits')).toEqual([
    'Already settled in another session, nothing written: Review of the last curation run',
    'Nothing waits for you.',
  ])
  await ui.unmount()
  await band.unmount()
})

test('the findings a shared answer keeps stay whole, for a band that draws no changes', () => {
  // Covers: B106
  const notes = ['m2b:review\nCuration run of 2026-03-14 18:02', SAM_PARAGRAPH, 'lint: broken link in a.md'].join('\n\n')
  const list = [{ id: 'r1', title: 'm2b: review', notes, completed: false, dropped: false, marker: 'review' }]

  const review = parseReview(list, { changes: [], copies: [], paragraphs: [SAM_PARAGRAPH] })

  expect(review?.findings).toEqual([SAM_PARAGRAPH, 'lint: broken link in a.md'])
  expect(review?.told).toEqual([SAM_PARAGRAPH])
})
