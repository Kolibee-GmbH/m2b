/*
 * Where the m2b pane sits and what a close of it comes to. Under the fullscreen layout the pane
 * sits beside the chat and stays there: the mod opens it by itself, and only the person's close on
 * the view it starts in takes it away, for later sessions too. Above the prompt it is a block that
 * takes rows from the chat: it comes on a command and goes with Escape, and closing it says nothing
 * about the pane beside the chat.
 */

/** In the mod's own store, which outlives a session: the person closed the pane beside the chat by hand. */
export const CLOSED_BY_HAND = 'paneClosedByHand'

// The width from which the fullscreen layout seats a pane beside the transcript, as Claude Code names it.
const DOCKS_FROM_COLUMNS = 110

/** Where a command's answer shows, as Claude Code stamps it on the command. */
export type Presentation = { isFullscreen: boolean; columns: number }

/** Whether a pane opened for this command will sit beside the chat. */
export function docksFor(presentation: Presentation): boolean {
  return presentation.isFullscreen && presentation.columns >= DOCKS_FROM_COLUMNS
}

/**
 * Whether the pane sits where it stays, given the seat of its last drawing on each surface: beside
 * the chat, or in any seat that is not the block above the prompt, on at least one of them. A
 * session can be drawn on several surfaces, and the close does not say which one it came from. A
 * pane not drawn anywhere yet does not stay.
 */
export function staysBesideChat(placements: Iterable<string>): boolean {
  return [...placements].some(placement => placement !== 'inline')
}

/**
 * Where the pane stands for the band of one surface. `beside`: it sits beside the chat in the view
 * it starts in and is the pane shown, so every row of the band is there with its buttons. `shown`:
 * it is in view without holding those rows, as the block above the prompt, as the desktop app's
 * small form, or turned to another view. `away`: it is not in view there.
 */
export type PaneSight = 'beside' | 'shown' | 'away'

/**
 * `seat` is where the pane's last drawing sat on the band's surface, undefined where it was never
 * drawn there or closed since; `pane` is what Claude Code says of the open pane now, undefined
 * where none is open. A seat alone can be of a drawing long ago: the pane may wait undrawn since
 * the terminal got narrower, or be a tab behind another plugin's pane. Whatever is not certain is
 * `away`, where the band draws all it has. A seat this band does not know counts as beside the
 * chat, as Claude Code asks; the block above the prompt is read and closed, and a click may not
 * reach the small form, so neither takes the band's rows. Nor does a pane turned to the review, a
 * search, the proposals or a topic: only the view it starts in holds every row.
 */
export function paneSight(
  seat: string | undefined,
  pane: { isShown: boolean; isPlaced: boolean } | undefined,
  isOnStartView: boolean,
): PaneSight {
  if (seat === undefined || pane === undefined || !pane.isPlaced || !pane.isShown) {
    return 'away'
  }
  return seat === 'inline' || seat === 'widget' || !isOnStartView ? 'shown' : 'beside'
}

/**
 * What a close of the pane comes to: `back` returns to the view the pane starts in and keeps it
 * open, `by hand` closes it and is remembered, `close` closes it and no more.
 */
export type CloseAnswer = 'back' | 'by hand' | 'close'

/**
 * The person's close (the close mark, or Escape on a pane opened as a dialog) on the review, a
 * search or the proposals goes back; on the start view it closes, and beside the chat that is their
 * word that the pane stays closed. A close right after one that went back is the same key pressed
 * twice and goes back too: it must not close the pane for every later session. A close of the
 * mod's own, or of the engine's, is never held back.
 */
export function closeAnswer(origin: string, isOnStartView: boolean, isBesideChat: boolean, isRightAfterBack: boolean): CloseAnswer {
  if (origin !== 'person') {
    return 'close'
  }
  if (!isOnStartView || isRightAfterBack) {
    return 'back'
  }
  return isBesideChat ? 'by hand' : 'close'
}
