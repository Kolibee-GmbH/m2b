import type { EngineInterface, ResolveInput } from 'claude-code'

import type { BandPress, PaneView } from '../types'
import { correctionRow, waitingCorrections } from './correct-field'
import type { CorrectActions } from './correct-field'
import { currentItemRow } from './current-item'
import { opensRow, part, pressLine, said, topicLabel } from './look'
import { runM2b } from './m2b'
import { OLDER_CORE } from './session'
import { plainLine } from './plain-text'
import type { AnswersCuration } from './proposals'

/*
 * The tab "Facts": what every session starts with, the facts and the current items outside any
 * topic, as `m2b distillate topics --json` answers at the press that opens the tab, each fact that
 * names a fact file a row that opens it, and each current item with a button for a note it names
 * (`current-item.tsx`); and the topics, each a button that opens its lines. A fact's row turns the
 * pane to the fact's file under a tab of its own, read with `m2b source --json`.
 *
 * The facts are the owner's and often a customer's. As a topic's lines, they are this module's
 * alone, for the opening that read them, and dropped the moment the pane turns away: the session's
 * state is one every plugin can read. A fact file stays kept while a source it rests on is shown
 * (an evidence entry's row, in `source-view.tsx`): the tab that leads back draws it as it was.
 */

export type StartFact = { statement: string; file: string | null }
export type TopicCount = { name: string; facts: number; current: number }

export type FactsLook =
  | { state: 'reading' }
  | { state: 'read'; facts: StartFact[]; current: string[]; topics: TopicCount[] }
  | { state: 'failed'; error: string }

/** One evidence entry of a fact file, as `m2b source --json` names it. */
export type Evidence = {
  name: string
  state: string
  day: string | null
  kind: string | null
  originalName: string | null
  firstLine: string | null
}

/** A correction that waits in the inbox for the next curation run: its capture, and its first line as typed. */
export type WaitingCorrection = { capture: string; firstLine: string }

export type FactFileLook =
  | { state: 'reading' }
  | { state: 'read'; title: string; until: string | null; lines: string[]; earlier: string[]; evidence: Evidence[]; corrections: WaitingCorrection[] }
  | { state: 'failed'; error: string }

/** The topic a fact file was opened from: the press that opened the topic, and the place of the fact in it. */
export type FromTopic = { press: string; index: number }

let heldFacts: { press: string; look: FactsLook } | null = null
// The file's name too: it may name a customer, and the view in the session's state names only the press.
// `topic` is the topic's view its tab leads back to, null for a file opened from the tab Facts.
let heldFile: { press: string; file: string; topic: FromTopic | null; look: FactFileLook } | null = null

export function beginFacts(press: string): void {
  heldFacts = { press, look: { state: 'reading' } }
}

export function fillFacts(press: string, look: FactsLook): boolean {
  if (heldFacts === null || heldFacts.press !== press) {
    return false
  }
  heldFacts = { press, look }
  return true
}

export function factsOf(press: string): FactsLook {
  return heldFacts !== null && heldFacts.press === press ? heldFacts.look : { state: 'reading' }
}

export function beginFactFile(press: string, file: string, topic: FromTopic | null = null): void {
  heldFile = { press, file, topic, look: { state: 'reading' } }
}

export function fillFactFile(press: string, look: FactFileLook): boolean {
  if (heldFile === null || heldFile.press !== press) {
    return false
  }
  heldFile = { ...heldFile, look }
  return true
}

/** The topic the fact file the press opened was opened from; null for one opened from the tab Facts, or where nothing is kept. */
export function topicOfFactFile(press: string): FromTopic | null {
  return heldFile !== null && heldFile.press === press ? heldFile.topic : null
}

/** The name of the fact file the press opened; empty where nothing is kept for it, as after a reload of the mod. */
export function factFileNameOf(press: string): string {
  return heldFile !== null && heldFile.press === press ? heldFile.file : ''
}

export function factFileOf(press: string): FactFileLook {
  return heldFile !== null && heldFile.press === press ? heldFile.look : { state: 'reading' }
}

/** Whether anything is kept at all. Nothing outside the module can read what it keeps, so its tests ask this. */
export function holdsFacts(): boolean {
  return heldFacts !== null || heldFile !== null
}

/**
 * Drops what is kept unless `view` is the opening it was read for; a fact file stays while a source
 * it rests on is shown, which leads back to it.
 */
export function forgetFactsUnless(view: PaneView | null): void {
  if (heldFacts !== null && !(view?.kind === 'facts' && view.press === heldFacts.press)) {
    heldFacts = null
  }
  const isFileShown = (view?.kind === 'fact' && view.press === heldFile?.press) || (view?.kind === 'source' && view.from === heldFile?.press)
  if (heldFile !== null && !isFileShown) {
    heldFile = null
  }
}

const READ_TIMEOUT_MS = 20_000
// The exit of the core's command line for a call it cannot take, and what it says to a command it does not know.
const EXIT_USAGE = 2
const UNKNOWN_COMMAND = /invalid choice|unrecognized arguments/

/** Whether m2b refused the call as a core from before the command would. */
export function isOlderCore(outcome: { exitCode?: number; stderr?: string }): boolean {
  return outcome.exitCode === EXIT_USAGE && UNKNOWN_COMMAND.test(outcome.stderr ?? '')
}
const OTHER_SHAPE = 'm2b answered something other than the facts'
const OTHER_FILE = 'm2b answered something other than a fact file'
// What a session gets, named by when it gets it; no part bears the name of the tab.
export const AT_THE_START = 'Every session starts with'
export const WHEN_NAMED = 'When a prompt names them'
const CURRENT = 'Current'
const READING = 'm2b is reading the distillate…'
const NOTHING_YET = 'The distillate holds no facts yet.'
const NO_TOPICS = 'The distillate has no topics.'
const READING_FILE = 'm2b is reading the fact file…'
// A fact file of a long contract or a person met often has many; the rest is said as a number.
const EVIDENCE_SHOWN = 8

export async function readFacts($: EngineInterface): Promise<FactsLook> {
  const outcome = await runM2b($, ['distillate', 'topics', '--json'], READ_TIMEOUT_MS)
  if (!outcome.ok) {
    return { state: 'failed', error: isOlderCore(outcome) ? OLDER_CORE : outcome.error }
  }
  return parseFacts(outcome.stdout)
}

export function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

export function strings(value: unknown): string[] | null {
  return Array.isArray(value) && value.every(item => typeof item === 'string') ? value : null
}

/** The answer of `m2b distillate topics --json`; one of any other shape is could not read, never no facts. */
export function parseFacts(text: string): FactsLook {
  let answer: unknown
  try {
    answer = JSON.parse(text)
  } catch {
    return { state: 'failed', error: OTHER_SHAPE }
  }
  if (!isObject(answer) || !Array.isArray(answer['facts']) || !Array.isArray(answer['topics'])) {
    return { state: 'failed', error: OTHER_SHAPE }
  }
  const current = strings(answer['current'])
  const facts = answer['facts'].filter(isObject).filter(fact => typeof fact['statement'] === 'string' && (fact['file'] === null || typeof fact['file'] === 'string'))
  const topics = answer['topics']
    .filter(isObject)
    .filter(topic => typeof topic['name'] === 'string' && Number.isInteger(topic['facts']) && Number.isInteger(topic['current']))
  if (current === null || facts.length !== answer['facts'].length || topics.length !== answer['topics'].length) {
    return { state: 'failed', error: OTHER_SHAPE }
  }
  return {
    state: 'read',
    facts: facts.map(fact => ({ statement: String(fact['statement']), file: typeof fact['file'] === 'string' ? fact['file'] : null })),
    current,
    topics: topics.map(topic => ({ name: String(topic['name']), facts: Number(topic['facts']), current: Number(topic['current']) })),
  }
}

/** Reads one fact file with `m2b source --json --viewer`; a file not on this machine or not readable is could not read. */
export async function readFactFile($: EngineInterface, file: string): Promise<FactFileLook> {
  // `--`: a name is the distillate's own text, and it may start with a dash.
  // `--viewer`: the corrections that wait for the file in the inbox come with it.
  const outcome = await runM2b($, ['source', '--json', '--viewer', '--', file], READ_TIMEOUT_MS)
  if (!outcome.ok) {
    return { state: 'failed', error: isOlderCore(outcome) ? OLDER_CORE : outcome.error }
  }
  return parseFactFile(outcome.stdout)
}

/** Why `m2b source --json` did not read the source, where it says so; null for a source it read. */
export function notReadError(answer: Record<string, unknown>): string | null {
  if (answer['kind'] !== 'not read') {
    return null
  }
  if (typeof answer['fetch'] === 'string') {
    return `not downloaded to this machine; ${answer['fetch']} fetches it`
  }
  return typeof answer['reason'] === 'string' ? answer['reason'] : 'it could not be read'
}

export function parseFactFile(text: string): FactFileLook {
  let answer: unknown
  try {
    answer = JSON.parse(text)
  } catch {
    return { state: 'failed', error: OTHER_FILE }
  }
  if (!isObject(answer)) {
    return { state: 'failed', error: OTHER_FILE }
  }
  const notRead = notReadError(answer)
  if (notRead !== null) {
    return { state: 'failed', error: notRead }
  }
  const lines = strings(answer['lines'])
  const earlier = strings(answer['earlier'])
  if (
    answer['kind'] !== 'fact file' ||
    typeof answer['title'] !== 'string' ||
    lines === null ||
    earlier === null ||
    !Array.isArray(answer['evidence']) ||
    !answer['evidence'].every(isObject)
  ) {
    return { state: 'failed', error: OTHER_FILE }
  }
  return {
    state: 'read',
    title: answer['title'],
    until: textOrNull(answer['until']),
    lines,
    earlier,
    evidence: answer['evidence'].filter(isObject).map(item => ({
      name: String(item['name'] ?? ''),
      state: String(item['state'] ?? ''),
      day: textOrNull(item['day']),
      kind: textOrNull(item['kind']),
      originalName: textOrNull(item['original_name']),
      firstLine: textOrNull(item['first_line']),
    })),
    // A core without the field, or an answer without `--viewer`, names none.
    corrections: (Array.isArray(answer['corrections']) ? answer['corrections'] : []).filter(isObject).map(item => ({
      capture: String(item['capture'] ?? ''),
      firstLine: String(item['first_line'] ?? ''),
    })),
  }
}

/** The key of the row of the fact drawn at `index`, which opens its file; a fact's file can be named by more than one fact. */
export function detailsKey(index: number): string {
  return `details:${index}`
}

/** The key of the button of the topic drawn at `index`. */
export function factsTopicKey(index: number): string {
  return `facts-topic:${index}`
}

/** The key of the evidence row drawn at `index`, which shows its source. */
export function showKey(index: number): string {
  return `show:${index}`
}

export type FactFileActions = { show: (index: number, evidence: Evidence) => Promise<void> }

/** What the view of a fact file draws its correction from: the press of the field, how curation stands, and the presses. */
export type FactFileCorrection = { pressed: BandPress | undefined; curation: AnswersCuration; actions: CorrectActions }

export type FactsActions = {
  details: (file: string) => Promise<void>
  showNote: (note: string) => Promise<void>
  showTopic: (name: string) => Promise<void>
}

export function textOrNull(value: unknown): string | null {
  return typeof value === 'string' ? value : null
}

/** `2 facts, 1 current`; a topic without current items says only its facts. */
function counts(topic: TopicCount): string {
  const facts = `${topic.facts} ${topic.facts === 1 ? 'fact' : 'facts'}`
  return topic.current === 0 ? facts : `${facts}, ${topic.current} current`
}

/**
 * The tab's view: what every session starts with, then the topics, each part under when a session
 * gets it. `nowMs` is the moment a note's day is said against.
 */
export function factsPane($: EngineInterface, e: ResolveInput, look: FactsLook, actions: FactsActions, columns: number, nowMs: number) {
  const ui = $.ui.resolve(e)
  if (look.state !== 'read') {
    const line =
      look.state === 'reading' ? said(ui, READING, 'quiet') : said(ui, `m2b could not read the distillate: ${plainLine(look.error)}`, 'trouble')
    return part(ui, { key: 'facts:start', title: AT_THE_START, waits: false, columns }, [line])
  }
  const { Box } = ui
  const start = [
    look.facts.length === 0 && look.current.length === 0 && said(ui, NOTHING_YET, 'quiet'),
    ...look.facts.map((fact, index) => {
      const file = fact.file
      return (
        <Box key={`fact:${index}`} flexDirection="column">
          {file === null
            ? said(ui, plainLine(fact.statement))
            : opensRow(ui, { key: detailsKey(index), text: plainLine(fact.statement), onPress: () => actions.details(file) })}
        </Box>
      )
    }),
    look.current.length > 0 && said(ui, CURRENT, 'strong'),
    ...look.current.map((item, index) => currentItemRow($, e, index, item, actions.showNote, nowMs)),
  ]
  const topics = look.topics.length === 0
    ? [said(ui, NO_TOPICS, 'quiet')]
    : look.topics.map((topic, index) => (
        <Box key={`facts-topic-row:${index}`}>
          {pressLine(ui, [{ key: factsTopicKey(index), label: topicLabel(topic.name), kind: 'default', onPress: () => actions.showTopic(topic.name) }], counts(topic))}
        </Box>
      ))
  return [
    part(ui, { key: 'facts:start', title: AT_THE_START, waits: false, columns }, start),
    part(ui, { key: 'facts:topics', title: WHEN_NAMED, waits: false, columns }, topics),
  ]
}

const KIND_IN_WORDS: Readonly<Record<string, string>> = { note: 'a note', picture: 'a picture', document: 'a document' }

function evidenceLine(item: Evidence): string {
  const name = plainLine(item.name)
  if (item.state === 'missing') {
    return `${name}: no note of the archive has this name`
  }
  if (item.state === 'evicted') {
    return `${name}: not downloaded to this machine`
  }
  if (item.state === 'unreadable') {
    return `${name}: could not be read`
  }
  const what = KIND_IN_WORDS[item.kind ?? ''] ?? 'a note'
  const original = item.originalName === null ? '' : `, ${plainLine(item.originalName)}`
  const first = item.firstLine === null ? '' : `: ${plainLine(item.firstLine)}`
  return [item.day === null ? '' : plainLine(item.day), `${what}${original}${first}`].filter(part => part !== '').join(' ')
}

/** The fact file under its own tab: its title, last day, lines, earlier values and evidence. */
export function factFilePane(
  $: EngineInterface,
  e: ResolveInput,
  press: string,
  actions: FactFileActions,
  correction: FactFileCorrection,
  columns: number,
) {
  const ui = $.ui.resolve(e)
  const file = factFileNameOf(press)
  const look = factFileOf(press)
  if (look.state !== 'read') {
    const line =
      look.state === 'reading' ? said(ui, READING_FILE, 'quiet') : said(ui, `m2b could not read the fact file: ${plainLine(look.error)}`, 'trouble')
    return part(ui, { key: 'fact', title: plainLine(file), waits: false, columns }, [line])
  }
  const { Box } = ui
  const shown = look.evidence.slice(0, EVIDENCE_SHOWN)
  const more = look.evidence.length - shown.length
  const facts = part(ui, { key: 'fact', title: plainLine(look.title), waits: look.corrections.length > 0, columns }, [
    correctionRow($, e, file, correction.pressed, correction.actions, columns),
    look.until !== null && said(ui, `true until ${plainLine(look.until)}`, 'quiet'),
    ...look.lines.map(line => said(ui, plainLine(line))),
    look.earlier.length > 0 && said(ui, 'Earlier', 'strong'),
    ...look.earlier.map(line => said(ui, plainLine(line), 'quiet')),
    waitingCorrections($, e, look.corrections, correction.curation),
  ])
  if (look.evidence.length === 0) {
    return facts
  }
  const evidence = part(ui, { key: 'fact:evidence', title: 'What it rests on', waits: false, columns }, [
    ...shown.map((item, index) =>
      item.state === 'read' ? (
        <Box key={`evidence:${index}`} flexDirection="column">
          {opensRow(ui, { key: showKey(index), text: evidenceLine(item), onPress: () => actions.show(index, item) })}
        </Box>
      ) : (
        said(ui, evidenceLine(item), 'trouble')
      ),
    ),
    more > 0 && said(ui, `${more} more not shown`, 'quiet'),
  ])
  return [facts, evidence]
}

/** The label of the tab beside the six for a fact file: its name without `.md`, cut as a topic's is. */
export function factTabLabel(file: string): string {
  return topicLabel(file.replace(/\.md$/, ''))
}

