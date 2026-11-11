import type { EngineEventOf } from 'claude-code'

/*
 * Whether a note is in the person's own words: the note tool runs without asking only then. A
 * session also reads text nobody typed, a web page or a file, and a note of such text would reach
 * the inbox, the next curation run and from there every later session without the person having
 * seen it.
 */

type Prompt = Pick<EngineEventOf['prompt.submit'], 'isMeta'> & {
  origin: EngineEventOf['prompt.submit']['origin'] | undefined
}

// The person at the terminal, the person over Remote Control, and the prompt a headless run was
// started with. A plugin's prompt is not theirs even when it is submitted as theirs: only the
// engine can say who typed.
const OWN_ORIGINS: readonly string[] = ['composer', 'bridge', 'sdk']

// A note quotes a prompt of the conversation at hand, most often the last one, so what lies
// further back or deeper in a long paste is not kept; a note of it is asked for.
const PROMPTS_KEPT = 100
const CHARACTERS_KEPT = 50_000

// "He [Sam] brings the plywood": what the note tool lets the model add where a sentence leans on
// the conversation. Anything longer is the note's text, not an addition to it.
const WORDS_IN_AN_ADDITION = 4

const WORD = /[\p{L}\p{N}\p{M}]+/gu
const BRACKETS = /\[([^[\]]*)\]/g
// Format characters draw nothing and are no word, so text spelled in them, as tag characters spell
// ASCII, would never be compared. The zero-width joiner and non-joiner are let through, as
// everywhere in m2b: emoji and several scripts need them.
const JOINERS = /[\u200c\u200d]/g
const UNSEEN = /\p{Cf}/u

/**
 * A prompt the person submitted and saw as typed. One whose origin the engine did not name is
 * nobody's: a note of it is asked for.
 */
export function isOwnPrompt({ origin, isMeta }: Prompt): boolean {
  return origin !== undefined && OWN_ORIGINS.includes(origin.kind) && isMeta !== true
}

/** The words of a text, as two spellings of the same word compare equal. */
export function wordsOf(text: string): string[] {
  return text.normalize('NFKC').toLowerCase().match(WORD) ?? []
}

/** The prompts kept with one more: each as its words, once each, the oldest dropped past the limit. */
export function withPrompt(prompts: readonly (readonly string[])[], text: string): string[][] {
  const words = [...new Set(wordsOf(text.slice(0, CHARACTERS_KEPT)))]
  const kept = prompts.map(prompt => [...prompt])
  return words.length === 0 ? kept : [...kept, words].slice(-PROMPTS_KEPT)
}

/**
 * True when every word of the note stands in one of the prompts. The order is free, because the
 * note is the request turned into a plain sentence ("remember that I ... sit" becomes "I sit ...").
 * Short additions in square brackets are left out, as long as they hold fewer words together than
 * the rest of the note has different ones: without that bound a whole foreign text would pass as
 * additions, paid for with one word of the person's repeated.
 */
export function isInOwnWords(note: string, prompts: readonly (readonly string[])[]): boolean {
  if (UNSEEN.test(note.replace(JOINERS, ''))) {
    return false
  }
  const additions: string[][] = []
  const rest = note.replace(BRACKETS, (whole, inside: string) => {
    const words = wordsOf(inside)
    if (words.length > WORDS_IN_AN_ADDITION) {
      return whole
    }
    additions.push(words)
    return ' '
  })
  const words = new Set(wordsOf(rest))
  if (words.size === 0 || additions.flat().length >= words.size) {
    return false
  }
  return prompts.some(prompt => {
    const said = new Set(prompt)
    return [...words].every(word => said.has(word))
  })
}
