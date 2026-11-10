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

declare module 'claude-code' {
  interface PluginState {
    m2b: {
      bandSnapshot: BandSnapshot | null
      bandNotice: string | null
      /** The rows pressed in this session, by task id. */
      bandPresses: Record<string, BandPress>
      /** Set while this session runs the band of another m2b version than the one installed. */
      bandVersionNotice: string | null
    }
  }
}
