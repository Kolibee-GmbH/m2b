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

// What draws nothing, as the core knows it (`src/m2b/notes/characters.py` holds the same table, and
// a test of the core compares the two): Unicode's default ignorable code points without the
// zero-width joiner and non-joiner, which emoji and several scripts need. Among them the variation
// selectors, which can carry bytes no one sees, and the tag characters, which spell ASCII no font
// draws.
const HIDDEN_RANGES: readonly (readonly [number, number])[] = [
  [0x00ad, 0x00ad], // soft hyphen
  [0x034f, 0x034f], // combining grapheme joiner
  [0x061c, 0x061c], // Arabic letter mark
  [0x115f, 0x1160], // Hangul fillers
  [0x17b4, 0x17b5], // Khmer inherent vowels
  [0x180b, 0x180f], // Mongolian variation selectors and vowel separator
  [0x200b, 0x200b], // zero-width space
  [0x200e, 0x200f], // direction marks
  [0x202a, 0x202e], // bidirectional embeddings and overrides
  [0x2060, 0x206f], // word joiner, invisible operators, isolates, deprecated format controls
  [0x3164, 0x3164], // Hangul filler
  [0xfe00, 0xfe0f], // variation selectors
  [0xfeff, 0xfeff], // byte order mark
  [0xffa0, 0xffa0], // halfwidth Hangul filler
  [0xfff0, 0xfff8], // reserved
  [0x1bca0, 0x1bca3], // shorthand format controls
  [0x1d173, 0x1d17a], // musical format controls
  [0xe0000, 0xe0fff], // tag characters, variation selectors supplement
]
const HIDDEN = new RegExp(
  `[${HIDDEN_RANGES.map(([first, last]) => `\\u{${first.toString(16)}}-\\u{${last.toString(16)}}`).join('')}]`,
  'gu',
)

/** The text as a model gets it: without any character that draws nothing. */
export function withoutHidden(text: string): string {
  return text.replace(HIDDEN, '')
}

// Every control and format character, and whatever else a terminal draws with no width: the marks
// that reorder text, the zero-width characters, the byte order mark, soft hyphens, variation
// selectors and tag characters. By Unicode property, so the list cannot fall behind.
const NEVER_DRAWN = /[\p{Cc}\p{Cf}\p{Default_Ignorable_Code_Point}]/gu
// White space as `\s` knows it, without the byte order mark, which is written out instead.
const WHITE_SPACE = /[\t\n\v\f\r \u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+/g

/**
 * A text the person is asked to keep, as one line: white space as single spaces, and every control
 * character and every mark that reorders or hides text written out (`\x1b`, `\u202e`) where
 * `plainLine` leaves it out. Keeping keeps the text as it is stored, so a part the drawing left out
 * would be kept unseen.
 */
export function writtenOut(text: string): string {
  return text
    .replace(WHITE_SPACE, ' ')
    .replace(/^ | $/g, '')
    .replace(NEVER_DRAWN, written)
}

function written(character: string): string {
  const code = character.codePointAt(0) ?? 0
  const digits = code.toString(16)
  if (code <= 0xff) {
    return `\\x${digits.padStart(2, '0')}`
  }
  return code <= 0xffff ? `\\u${digits.padStart(4, '0')}` : `\\u{${digits}}`
}
