export type BandCandidate = { id: string; title: string }

export type BandReview = { id: string; title: string; findings: string[] }

export type BandSnapshot = {
  candidates: BandCandidate[]
  review: BandReview | null
  error: string | null
}

declare module 'claude-code' {
  interface PluginState {
    m2b: {
      bandSnapshot: BandSnapshot | null
      bandNotice: string | null
      bandIsBusy: boolean
    }
  }
}
