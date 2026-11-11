export type BandCandidate = { id: string; title: string }

/** A part of a changed facts line: kept, added or removed, word by word. */
export type BandChangePart = { text: string; change: 'same' | 'added' | 'removed' }

/** A change of the facts the open review names: its fact file, what it is about, and the line in parts. */
export type BandFactChange = { kind: string; file: string; topic: string; parts: BandChangePart[] }

/**
 * The open review task: its findings, the paragraphs of its notes, less those `changes` and `copy`
 * stand for. `changes` and `copy` are absent from a core before 0.3.3, and then every paragraph
 * is a finding.
 */
export type BandReview = {
  id: string
  title: string
  findings: string[]
  changes?: BandFactChange[]
  copy?: { path: string; captures: number } | null
}

/** One of the owner's own tasks due today or overdue. */
export type BandDueTask = { id: string; title: string; overdue: boolean }

export type BandSnapshot = {
  candidates: BandCandidate[]
  review: BandReview | null
  error: string | null
  /** Absent in an answer of a band before due tasks, and with `band.due_tasks` off: none to show. */
  due?: BandDueTask[]
}

/** What a press on keep or drop asks the task list for. */
export type BandSettle = 'complete' | 'drop'

/**
 * A press on a row: `waiting` while undo can still take it back and nothing is written, `writing`
 * from the write until the reload after it has landed, at the latest until `deadlineMs`. The row
 * offers nothing else meanwhile. `token` tells one press from a later one on the same row.
 */
export type BandPress = {
  action: BandSettle
  phase: 'waiting' | 'writing'
  token: string
  deadlineMs?: number
}

/** The last curation run, as `m2b band --json` reports it under `status.run`; times as written, with their offset. */
export type BandRun = {
  state: string
  startedAt: string | null
  finishedAt: string | null
  message: string | null
}

/** One line of `m2b search` that holds the text. */
export type SearchHit = { path: string; line: number; text: string }

/**
 * A search the pane shows: the text, its first hits and how many there are, and how many files it
 * could not search; `wholeWords` when only whole words were matched (absent in a search kept before).
 */
export type PaneSearch = {
  query: string
  hits: SearchHit[]
  total: number
  evicted: number
  unreadable: number
  wholeWords?: boolean
}

/** What the m2b pane shows: the last curation run, or a search. */
export type PaneView = { kind: 'review' } | { kind: 'search'; search: PaneSearch }

declare module 'claude-code' {
  interface PluginState {
    m2b: {
      bandSnapshot: BandSnapshot | null
      bandNotice: string | null
      /** The rows pressed in this session, by task id. */
      bandPresses: Record<string, BandPress>
      /** Set while this session runs the band of another m2b version than the one installed. */
      bandVersionNotice: string | null
      /** The last curation run, from the same answer as the band; null until it is read. */
      bandRun: BandRun | null
      /** What the m2b pane shows. */
      paneView: PaneView | null
      /** The start of the last failed run this session was shown, so it is shown once. */
      bandToastedRun: string | null
    }
  }
}
