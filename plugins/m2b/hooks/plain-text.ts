/*
 * Text from the store reaches the band as it was captured: a title pasted from terminal output
 * can carry an escape sequence, a finding a line break. Claude Code refuses a drawing whose text
 * holds a control character, and then draws none of the band, so every string is cleaned first.
 */

// CSI (colours, cursor moves), OSC (titles, links, ended by BEL or ESC \), the other escapes of
// ESC with intermediate bytes (`ESC ( B` from `tput sgr0`, `ESC 7`, `ESC c`), and the one-byte CSI.
const ESCAPE_SEQUENCE =
  /\u001b(?:\[[0-?]*[ -/]*[@-~]|\][^\u0007\u001b]*(?:\u0007|\u001b\\)?|[ -/]*[0-~])|\u009b[0-?]*[ -/]*[@-~]/g
const LINE_BREAKS_AND_TABS = /[\r\n\t\v\f\u2028\u2029]+/g
// C0 and C1 controls, DEL, the marks that reorder text (Arabic letter mark, left-to-right and
// right-to-left marks, embeddings, overrides, isolates) and the byte order mark.
const INVISIBLE_CONTROLS = /[\u0000-\u001f\u007f-\u009f\u061c\u200e\u200f\u202a-\u202e\u2066-\u2069\ufeff]/g

/** The text as one plain line: escape sequences and controls removed, line breaks and tabs as one space. */
export function plainLine(text: string): string {
  return text.replace(ESCAPE_SEQUENCE, '').replace(LINE_BREAKS_AND_TABS, ' ').replace(INVISIBLE_CONTROLS, '')
}
