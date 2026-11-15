export type BandCandidate = { id: string; title: string }

/** A part of a changed facts line: kept, added or removed, word by word. */
export type BandChangePart = { text: string; change: 'same' | 'added' | 'removed' }

/** A change of the facts the open review names: its fact file, what it is about, and the line in parts. */
export type BandFactChange = { kind: string; file: string; topic: string; parts: BandChangePart[] }

/**
 * The open review task: its findings, every paragraph of its notes. `told` are the paragraphs
 * `changes` and `copies` stand for, which the band leaves out when it draws; the findings stay
 * whole, so a session of an older band that reads this shared answer still shows them. All three
 * are absent from a core before 0.3.3.
 */
export type BandReview = {
  id: string
  title: string
  findings: string[]
  told?: string[]
  changes?: BandFactChange[]
  copies?: { path: string; captures: number }[]
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

/** What a press on the pane's button for the session's folder asks: the distillate off there, or on again. */
export type FolderSwitch = 'off' | 'on'

/**
 * A press on a row: `waiting` while undo can still take it back and nothing is written, `writing`
 * from the write until the reload after it has landed, at the latest until `deadlineMs`. The row
 * offers nothing else meanwhile. `token` tells one press from a later one on the same row. `ids`
 * are the proposals a press on keep all stands for: those the pane showed when it was pressed.
 */
export type BandPress = {
  action: BandSettle | FolderSwitch
  phase: 'waiting' | 'writing'
  token: string
  deadlineMs?: number
  ids?: string[]
}

/**
 * What a reading of the sessions proposed for the memory, or a session handed in by itself, with
 * the words it stands on and the day they were written.
 */
export type BandProposal = {
  id: string
  kind: string
  text: string
  quote: string
  day: string
  topic: string | null
  due: string | null
  /** Where the quote stands in the session: `typed` when absent, or something else, such as `pasted`. */
  source?: string
  /** The tool whose result holds the quote, where the source is `tool`. */
  tool?: string | null
  /** Who proposed where it was no reading: `session` for a proposal a session handed in. */
  by?: string | null
}

/**
 * The proposals that wait for keep or drop, as `m2b band --json` names them, and how many answers
 * wait for the next curation run. `error` is why m2b could not look; nothing is listed then.
 */
export type BandProposals = { waiting: BandProposal[]; answered: number; error: string | null }

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

/**
 * What the m2b pane shows beside the view it starts in, which is the one without a value: the last
 * curation run, a search, the proposals from the sessions, or one topic. A topic's lines are not
 * part of this value: the session's state is one every plugin can read, so the module that draws
 * the lines holds them. `press` tells this opening of the topic from an earlier one, and `isRead`
 * turns true when m2b has answered, which draws the pane again. The settings are held the same
 * way: this value says where the view is, `at` a place in the list for a setting's card and null
 * for the list, and never what a setting holds; `drawn` counts up when what the module holds
 * changed, which draws the pane again.
 */
export type PaneView =
  | { kind: 'review' }
  | { kind: 'search'; search: PaneSearch }
  | { kind: 'proposals' }
  | { kind: 'topic'; name: string; press: string; isRead: boolean }
  | { kind: 'settings'; press: string; at: number | null; drawn: number }

/**
 * A topic whose facts m2b gave this session, with the facts lines and current items its block held
 * then; null where an m2b before the counts noted the name alone.
 */
export type SessionTopic = { name: string; facts: number | null; current: number | null }

/**
 * What m2b gave this session since its last start, as `m2b band --json --session <id>` names it.
 * `id` is the session that was asked about, null where the session could not name itself: after
 * `/clear` the session goes on under another id, and this is then no longer about it. `known` is
 * false for a session this machine holds no note of, which is not "given nothing".
 * `atStart` is how the start printed the distillate (`whole`, `cut`, `none`), `offUnder` the folder
 * the distillate is turned off under now, `folder` the session's own folder as m2b looked at it,
 * null from a core that does not name it (absent in an answer kept before). `error` is why m2b
 * could not look; nothing else is said then.
 */
export type BandSession = {
  id: string | null
  known: boolean
  topics: SessionTopic[]
  atStart: string | null
  offUnder: string | null
  folder?: string | null
  error: string | null
}

/** The notes a session wrote through the mod's command and tool, with the id of that session. */
export type SessionNotes = { session: string | null; count: number }

declare module 'claude-code' {
  /**
   * The arguments of the tools the mod registers. Without them a hook on one of the tools is
   * refused wherever the types in the plugin's folder declare the MCP tools of a session: once one
   * tool is declared, a name that is not declared is no tool.
   */
  interface McpToolInputs {
    mcp__m2b__note: { text: string; follow_up?: string; quiet?: boolean }
    mcp__m2b__search: { terms: string[]; question_language: string; whole_words?: boolean }
    mcp__m2b__propose: { kind: string; text: string; quote: string; due?: string }
  }

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
      /** The proposals from the sessions, from the same answer as the band; null until it is read. */
      bandProposals: BandProposals | null
      /** What m2b said to the last answer to a proposal it refused or could not write; cleared by the next prompt. */
      bandProposalsNotice: string | null
      /** What the m2b pane shows; null for the view it starts in. */
      paneView: PaneView | null
      /** Where the pane's last drawing sat on each surface, by the surface's name; empty once the pane closed. */
      paneSeats: Record<string, string>
      /** What m2b gave this session, from this session's own question; null until it is answered. */
      bandSession: BandSession | null
      /** The notes this session wrote through the mod; null before the first. */
      sessionNotes: SessionNotes | null
      /** Why the last press on the folder's button wrote nothing; cleared by the next press on it and the next prompt. */
      sessionNotice: string | null
      /** The start of the last failed run this session was shown, so it is shown once. */
      bandToastedRun: string | null
      /** The words of each prompt the person submitted in this session, the newest last. */
      ownPrompts: string[][]
    }
  }
}
