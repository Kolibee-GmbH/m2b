export type BandCandidate = { id: string; title: string }

export type BandReview = { id: string; title: string; findings: string[] }

export type BandSnapshot = {
  candidates: BandCandidate[]
  review: BandReview | null
  error: string | null
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

/** A search the pane shows: the text, its first hits and how many there are, and how many files it could not search. */
export type PaneSearch = { query: string; hits: SearchHit[]; total: number; evicted: number; unreadable: number }

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
    }
  }
}
