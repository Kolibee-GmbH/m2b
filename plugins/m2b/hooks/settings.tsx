import type { CommandSpec, EngineInterface, ResolveInput } from 'claude-code'

import type { PaneView } from '../types'
import { runM2b } from './m2b'
import { plainLine } from './plain-text'
import { OLDER_CORE } from './session'

/*
 * Every setting of m2b in the pane: a list in three groups, by the file a setting lives in, and a
 * card per setting with what it does and what changes it. `previous` and `next` on a card walk
 * through all of them, so the list is also the way to be taken through every setting once. A
 * switch is pressed on its card; every other setting names the command or the skill that changes
 * it. The list is the core's (`m2b settings --json`), and so is the one command a press runs
 * (`m2b settings set`), which refuses whatever is no switch.
 *
 * One switch a session's shell does not turn on: `sessions.propose`, with which a session hands in
 * proposals with words from what its agent read. The core refuses it while `CLAUDECODE` is set, as
 * it is for every command of a session's shell. No tool of Claude Code hands the mod a press: one
 * arrives as input on a client that draws the session. So a press on its card does turn it on;
 * `pressTurnsHandingInOn` is the one place that says which press that is.
 *
 * The values hold folders, the owner's name and what the store is called. This module hands them
 * to the pane's drawing alone: they stand in a variable of the module, never in the session's
 * state, which every plugin can read, and in no text a command answers. No command sets a value;
 * a value changes by a press and in no other way. The mod writes no settings file itself: the
 * core checks the whole file before it writes.
 */

export const SETTINGS_COMMAND: CommandSpec = {
  name: 'm2b-settings',
  description: 'Show every setting of m2b in a pane, with what it does and the switches to press',
  immediate: true,
}

export const SETTINGS_PLACED = 'every setting of m2b is in the m2b pane'
/** Where the list is when no pane can be shown: the answer of a command reaches the model, the values do not. */
export const SETTINGS_IN_A_TERMINAL = 'm2b settings lists them in a terminal'

type Scope = 'machine' | 'store' | 'owner'
type Choice = string | boolean | number

/** One setting as `m2b settings --json` lists it. `shows` is its value in words; `value` only tells which choice is set. */
export type Setting = {
  key: string
  file: string
  scope: Scope
  kind: 'switch' | 'shown' | 'named'
  title: string
  does: string
  isRead: boolean
  value: unknown
  shows: string | null
  defaultValue: unknown
  choices: Choice[]
  changedBy: string
  change: string | null
  isOfCuration: boolean
}

export type Catalog = { settings: Setting[]; curates: boolean | null; notRead: Record<string, string> }

/** A look at the settings, as m2b answered: the list, or why it could not be read. */
export type SettingsLook = { state: 'reading' } | { state: 'read'; catalog: Catalog } | { state: 'failed'; error: string }

/**
 * A press on a switch: it waits for undo, then it is written. It names its setting and the value
 * by what they are, never by a place in the list: the list is read again after every write, and a
 * place could then be another setting's. `press` is the opening of the view it was made in.
 * `isTurningHandingInOn` marks the one press `pressTurnsHandingInOn` names, settled when the
 * press is made, from the surface the press itself said: the card can be drawn on several
 * surfaces at once.
 */
type Change = {
  token: string
  press: string
  scope: Scope
  key: string
  choice: Choice
  isTurningHandingInOn: boolean
  phase: 'waiting' | 'writing'
}
/** What the command said to the last change it refused, with the setting it was about. */
type Refusal = { scope: Scope; key: string; line: string }
/**
 * What the view draws from: the list as last read, why a later read failed while that list is
 * still shown, the one change under way and the last refusal.
 */
export type Held = { look: SettingsLook; trouble: string | null; change: Change | null; refusal: Refusal | null }

// What the pane shows, with the opening that asked for it. The module's own: it starts over with
// the module, and it is gone the moment the pane turns to another view.
// `asked` counts the reads started for the opening: only the answer to the latest is kept.
let held: { press: string; look: SettingsLook; trouble: string | null; refusal: Refusal | null; asked: number } | null = null
// The one change under way. It is not part of an opening: a change being written goes on when the
// view is left, and a view opened meanwhile must neither start a second one nor miss its refusal.
let change: Change | null = null

/**
 * Begins a look for an opening of the view, in place of whatever was kept before: m2b reads. A
 * press that still waited in the opening before is taken back, one being written goes on.
 */
export function beginSettings(press: string): void {
  dropWaitingChange()
  held = { press, look: { state: 'reading' }, trouble: null, refusal: null, asked: 0 }
}

/**
 * Notes that a read starts for an opening and answers its number, which `fillSettings` is handed
 * with the answer; null where the pane no longer shows that opening.
 */
export function askSettings(press: string): number | null {
  if (held === null || held.press !== press) {
    return null
  }
  held = { ...held, asked: held.asked + 1 }
  return held.asked
}

/**
 * Puts m2b's answer in the place of the look kept for the opening that asked. A read that fails
 * while a list is shown keeps that list and says the trouble beside it, so the view keeps its way
 * on. False, and nothing kept, once the pane turned away from that opening, or once a later read
 * was started for it: a read begun before a change was written can answer after the one begun
 * behind it, and would put the old values back.
 */
export function fillSettings(press: string, look: SettingsLook, asked: number): boolean {
  if (held === null || held.press !== press || held.asked !== asked) {
    return false
  }
  held =
    look.state === 'failed' && held.look.state === 'read'
      ? { ...held, trouble: look.error }
      : { ...held, look, trouble: null }
  return true
}

/** What is kept for this opening. Where nothing is, as after a reload of the mod, m2b counts as still reading. */
export function heldSettings(press: string): Held {
  return held !== null && held.press === press
    ? { look: held.look, trouble: held.trouble, change, refusal: held.refusal }
    : { look: { state: 'reading' }, trouble: null, change, refusal: null }
}

/** Whether anything is kept at all. Nothing outside the module can read what it keeps, so its tests ask this. */
export function holdsSettings(): boolean {
  return held !== null
}

/** The opening the module keeps a look for, null where the pane shows no settings. */
export function openSettings(): string | null {
  return held?.press ?? null
}

/**
 * Drops what is kept unless `view` is the settings view it was read for. A press that still waits
 * for undo goes with it: nobody could take it back any more, so it is not written.
 */
export function forgetSettingsUnless(view: PaneView | null): void {
  if (held !== null && !(view !== null && view.kind === 'settings' && view.press === held.press)) {
    held = null
    dropWaitingChange()
  }
}

/** Takes back a press that still waits, whatever opening it was made in; one being written goes on. */
export function dropWaitingChange(): void {
  if (change?.phase === 'waiting') {
    change = null
  }
}

/** The list a card belongs to: null where `view` is no card. */
export function listOf(view: PaneView | null): PaneView | null {
  return view !== null && view.kind === 'settings' && view.at !== null ? { ...view, at: null } : null
}

/**
 * Where a close by the person that leads back takes the pane: from a setting's card to the list,
 * from every other view to the view the pane starts in. `isCardShown` says whether the pane draws
 * a card: a view at a place the list no longer has is drawn as the list, and is left like it. On
 * the list, a close right after the one that led there is the same key pressed twice and stays,
 * so two quick presses on a card do not skip the list.
 */
export function afterBack(view: PaneView | null, isCardShown: boolean, isRightAfterBack: boolean): 'list' | 'stay' | 'start' {
  if (view === null || view.kind !== 'settings') {
    return 'start'
  }
  if (isCardShown) {
    return 'list'
  }
  return isRightAfterBack ? 'stay' : 'start'
}

const HANDING_IN = 'sessions.propose'
// The surfaces on which the card offers to turn handing in on. A surface is what the client that
// draws names itself: a fact about drawing, no proof of who presses. The list keeps a tap in the
// mobile app from turning it on, and holds out no client that names itself otherwise.
const OFFERED_THE_TURN_ON: readonly string[] = ['terminal', 'desktop', 'vscode']

/** A choice as `m2b settings set` takes it: a text as it is, anything else as its JSON. */
function argumentOf(choice: Choice): string {
  return typeof choice === 'string' ? choice : JSON.stringify(choice)
}

/** Whether `setting` is the switch for handing in of this machine's config, by its file and its key. */
function isHandingInOfThisMachine(setting: Pick<Setting, 'scope' | 'key'>): boolean {
  return setting.scope === 'machine' && setting.key === HANDING_IN
}

/**
 * Whether `value` is the one that turns handing in on, by what the command would be handed for
 * `key`: whatever file the list names the key under, and however a core spells the value.
 */
function turnsHandingInOn(key: string, value: unknown): boolean {
  return key === HANDING_IN && isChoice(value) && argumentOf(value) === 'true'
}

/**
 * Whether a press on `choice` of `setting`, from a client that names itself `surface`, turns
 * handing in on: this machine's switch, the value the command takes for it, a surface the card
 * offers it on. Only the write of such a press is handed to m2b as made outside a session; every
 * other write is handed on as a session's, and the core decides.
 *
 * What this stands on is that no tool of Claude Code hands the mod a press: a press arrives as
 * input on a client that draws the session. That is a threshold and no boundary. Claude Code
 * does not say who pressed, and the surface is the client's own word, so another plugin can
 * change what a press says, and whatever attaches to the session as a client, types into the
 * terminal or steers the screen presses as the person does, a model whose tools steer that
 * input among them.
 */
export function pressTurnsHandingInOn(setting: Pick<Setting, 'scope' | 'key'>, choice: Choice, surface: string): boolean {
  return isHandingInOfThisMachine(setting) && turnsHandingInOn(setting.key, choice) && OFFERED_THE_TURN_ON.includes(surface)
}

/** The places of every value of a switch but the one that is set; none where the setting is no switch or was not read. */
function otherValues(setting: Setting): number[] {
  if (setting.kind !== 'switch' || !setting.isRead) {
    return []
  }
  return setting.choices.flatMap((choice, place) => (choice === setting.value ? [] : [place]))
}

/**
 * The places, among a switch's choices, of the values the card offers on `surface`: every value
 * but the one that is set, and the one that turns handing in on only as the press that may.
 */
export function offered(setting: Setting, surface: string): number[] {
  return otherValues(setting).filter(place => {
    const choice = setting.choices[place]
    return choice !== undefined && (!turnsHandingInOn(setting.key, choice) || pressTurnsHandingInOn(setting, choice, surface))
  })
}

function settingNamed(catalog: Catalog, scope: Scope, key: string): Setting | undefined {
  return catalog.settings.find(setting => setting.scope === scope && setting.key === key)
}

/**
 * Notes a press on a switch, made on `surface`, which writes nothing yet. False where the press is
 * not one the card offers there, or another change waits or is being written, in whatever
 * opening: one change at a time from this pane, so two of its writes never race for a file and a
 * refusal is about the press the person just made. A change made elsewhere meanwhile, in a
 * terminal or another session, is not known here.
 */
export function beginChange(press: string, at: number, place: number, token: string, surface: string): boolean {
  if (held === null || held.press !== press || change !== null || held.look.state !== 'read') {
    return false
  }
  const setting = held.look.catalog.settings[at]
  const choice = setting?.choices[place]
  if (setting === undefined || choice === undefined || !offered(setting, surface).includes(place)) {
    return false
  }
  // Asked of the rule itself, not taken from what `offered` let through.
  const isTurningHandingInOn = pressTurnsHandingInOn(setting, choice, surface)
  change = { token, press, scope: setting.scope, key: setting.key, choice, isTurningHandingInOn, phase: 'waiting' }
  held = { ...held, refusal: null }
  return true
}

/** Takes the press of this opening back while it waits; false once it is being written or nothing waits. */
export function undoChange(press: string): boolean {
  if (change === null || change.press !== press || change.phase !== 'waiting') {
    return false
  }
  change = null
  return true
}

/**
 * Turns the waiting press `token` names into one being written and answers what to hand to
 * `m2b settings set`, and whether this is the press that turns handing in on, as it was settled
 * when the press was made. Null, and the press dropped, where the list as it is now no longer has
 * that value for that setting as one to change to; null where the press was taken back or the
 * view left meanwhile.
 */
export function startWriting(token: string): { key: string; argument: string; isTurningHandingInOn: boolean } | null {
  if (change === null || change.token !== token || change.phase !== 'waiting') {
    return null
  }
  const { scope, key, choice, isTurningHandingInOn } = change
  // A press that waits is of the opening the module holds: every other way out took it back.
  const setting = held !== null && held.look.state === 'read' ? settingNamed(held.look.catalog, scope, key) : undefined
  if (setting === undefined || !otherValues(setting).some(place => setting.choices[place] === choice)) {
    change = null
    return null
  }
  change = { ...change, phase: 'writing' }
  return { key, argument: argumentOf(choice), isTurningHandingInOn }
}

/**
 * Ends the change `token` names; `refused` is what the command said when it wrote nothing. The
 * refusal is kept for the view that is open now, which may be a later opening than the press's.
 */
export function endChange(token: string, refused: string | null): void {
  if (change === null || change.token !== token) {
    return
  }
  const { scope, key } = change
  change = null
  if (held !== null) {
    held = { ...held, refusal: refused === null ? null : { scope, key, line: refused } }
  }
}

const READ_TIMEOUT_MS = 30_000
// The exit of the core's command line for a call it cannot take, and what it says to a command it does not know.
const EXIT_USAGE = 2
const UNKNOWN_COMMAND = /invalid choice|unrecognized arguments/
const OTHER_SHAPE = 'm2b answered something other than its settings'

/** Reads the list of the settings; whatever fails, the look says why. */
export async function readSettings($: EngineInterface): Promise<SettingsLook> {
  const outcome = await runM2b($, ['settings', '--json'], READ_TIMEOUT_MS)
  if (outcome.ok) {
    return parseSettings(outcome.stdout)
  }
  const isOlderCore = outcome.exitCode === EXIT_USAGE && UNKNOWN_COMMAND.test(outcome.stderr ?? '')
  return { state: 'failed', error: isOlderCore ? OLDER_CORE : outcome.error }
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isChoice(value: unknown): value is Choice {
  return typeof value === 'string' || typeof value === 'boolean' || typeof value === 'number'
}

function settingOf(value: unknown): Setting | null {
  if (!isObject(value)) {
    return null
  }
  const { key, file, scope, kind, title, does, read, shows, choices, changed_by: changedBy, change, curation } = value
  const isKnown =
    typeof key === 'string' &&
    typeof file === 'string' &&
    (scope === 'machine' || scope === 'store' || scope === 'owner') &&
    (kind === 'switch' || kind === 'shown' || kind === 'named') &&
    typeof title === 'string' &&
    typeof does === 'string' &&
    typeof read === 'boolean' &&
    (shows === null || typeof shows === 'string') &&
    Array.isArray(choices) &&
    choices.every(isChoice) &&
    typeof changedBy === 'string' &&
    (change === null || typeof change === 'string') &&
    typeof curation === 'boolean'
  if (!isKnown) {
    return null
  }
  return {
    key,
    file,
    scope,
    kind,
    title,
    does,
    isRead: read,
    value: value['value'],
    shows,
    defaultValue: value['default'],
    choices,
    changedBy,
    change,
    isOfCuration: curation,
  }
}

/** The answer of `m2b settings --json`; one of any other shape is could not read, never a list without settings. */
export function parseSettings(text: string): SettingsLook {
  let answer: unknown
  try {
    answer = JSON.parse(text)
  } catch {
    return { state: 'failed', error: OTHER_SHAPE }
  }
  // m2b has settings wherever it is set up: a list without any is no list.
  if (!isObject(answer) || !Array.isArray(answer['settings']) || answer['settings'].length === 0 || !isObject(answer['not_read'])) {
    return { state: 'failed', error: OTHER_SHAPE }
  }
  const { curates, not_read: notRead } = answer
  const settings = answer['settings'].map(settingOf)
  const reasons = Object.entries(notRead)
  if (
    settings.some(setting => setting === null) ||
    !(curates === null || typeof curates === 'boolean') ||
    !reasons.every(([, reason]) => typeof reason === 'string')
  ) {
    return { state: 'failed', error: OTHER_SHAPE }
  }
  return {
    state: 'read',
    catalog: {
      settings: settings.filter((setting): setting is Setting => setting !== null),
      curates,
      notRead: Object.fromEntries(reasons.map(([file, reason]) => [file, String(reason)])),
    },
  }
}

/**
 * What the view's buttons do. `open` turns the pane to the card at a place of the list; `choose`
 * is a press on a switch, with the surface the press named.
 */
export type SettingsActions = {
  open: (at: number) => Promise<void>
  toList: () => Promise<void>
  choose: (at: number, place: number, surface: string) => Promise<void>
  undo: () => Promise<void>
}

/** Whether the view draws a setting's card: the list was read and holds a setting at the view's place. */
export function showsCard(view: Extract<PaneView, { kind: 'settings' }>, kept: Held): boolean {
  return view.at !== null && kept.look.state === 'read' && kept.look.catalog.settings[view.at] !== undefined
}

const HEADING = 'Settings'
const READING = 'm2b is reading its settings…'
const COULD_NOT_READ = 'm2b could not read its settings'
const NOT_READ = 'not read'
const GROUPS: readonly { scope: Scope; heading: string; where: string }[] = [
  { scope: 'machine', heading: 'This machine', where: 'this machine' },
  { scope: 'store', heading: 'The store, for every machine', where: 'the store, for every machine' },
  { scope: 'owner', heading: 'The owner, for every machine', where: 'the owner, for every machine' },
]
const DOES_NOT_CURATE = 'This machine does not curate.'
const NOTHING_HERE = `${DOES_NOT_CURATE.slice(0, -1)}: the settings of the curation run do nothing here.`
const IN_YOUR_OWN_TERMINAL = `Turned on in a terminal of your own: m2b settings set ${HANDING_IN} true`
const BY_YOUR_PRESS = 'Your press here turns it on, as a terminal of your own does.'
const EVERY_MACHINE = 'Every machine that shares the store needs an m2b that knows handing in.'
// The mod registers the tool when it loads, at a session's start and on a reload; the command takes a call at once.
const AT_ITS_START =
  'A session gets the tool when it starts or its plugins are reloaded: until then, one that ran before this was turned on does not have it.'
const KEPT_BY_M2B = 'kept by m2b, never changed by hand'
// Below this width a row is two lines, the title and below it the value: beside the chat the pane can be 24 columns wide.
const NARROW_BELOW = 41

/** A text of the core as one plain line, with its white space as single spaces: a run of spaces would wrap into what reads as rows of its own. */
function oneLine(text: string): string {
  return plainLine(text).replace(/ {2,}/g, ' ').trim()
}

function shown(setting: Setting): string {
  return setting.isRead ? oneLine(setting.shows ?? '') : NOT_READ
}

function inWords(value: unknown): string {
  return typeof value === 'boolean' ? (value ? 'on' : 'off') : plainLine(String(value))
}

function choiceLabel(choice: Choice): string {
  return typeof choice === 'boolean' ? (choice ? 'turn on' : 'turn off') : `set to ${plainLine(String(choice))}`
}

function changeLine(key: string, choice: Choice): string {
  return typeof choice === 'boolean'
    ? `turning ${plainLine(key)} ${choice ? 'on' : 'off'}`
    : `setting ${plainLine(key)} to ${plainLine(String(choice))}`
}

function underWay(change: { key: string }): string {
  return `A change of ${plainLine(change.key)} is under way.`
}

/** How a setting that is no switch changes, in the words `m2b settings` uses for it. */
function howItChanges(setting: Setting): string {
  if (setting.change === null) {
    return KEPT_BY_M2B
  }
  if (setting.changedBy === 'setup') {
    return `set up with ${oneLine(setting.change)}`
  }
  return `${setting.changedBy === 'by hand' ? 'by hand' : 'change'}: ${oneLine(setting.change)}`
}

/**
 * The view's drawing: the card of the setting the view is at, else the list. Every line wraps.
 * `columns` is the width of the pane's body.
 */
export function settingsPane(
  $: EngineInterface,
  e: ResolveInput,
  view: Extract<PaneView, { kind: 'settings' }>,
  kept: Held,
  actions: SettingsActions,
  columns: number,
) {
  const { Box, Button, Text } = $.ui.resolve(e)
  const heading = (text: string) => (
    <Text weight="semibold" wrap="wrap">
      {text}
    </Text>
  )
  const quiet = (text: string) => (
    <Text dimColor wrap="wrap">
      {text}
    </Text>
  )
  const failure = (text: string) => (
    <Text color="error" wrap="wrap">
      {text}
    </Text>
  )
  const { look, trouble, change, refusal } = kept
  if (look.state !== 'read') {
    return (
      <Box flexDirection="column">
        {heading(HEADING)}
        {look.state === 'reading' ? quiet(READING) : failure(`${COULD_NOT_READ}: ${plainLine(look.error)}`)}
      </Box>
    )
  }
  const { settings, curates, notRead } = look.catalog
  const isNarrow = columns < NARROW_BELOW
  const idles = (setting: Setting): boolean => setting.isOfCuration && curates === false
  const again = trouble === null ? null : failure(`${COULD_NOT_READ} again: ${plainLine(trouble)}`)
  const setting = view.at === null ? undefined : settings[view.at]
  if (view.at === null || setting === undefined) {
    const row = (listed: Setting, at: number) =>
      isNarrow ? (
        <Box key={`row:setting:${at}`} flexDirection="column">
          <Box flexDirection="row">
            <Button key={`setting:${at}`} label="open" onPress={() => actions.open(at)} />
            <Text dimColor={idles(listed)} wrap="wrap">
              {` ${plainLine(listed.title)}`}
            </Text>
          </Box>
          <Text dimColor wrap="wrap">
            {`  ${shown(listed)}`}
          </Text>
        </Box>
      ) : (
        <Box key={`row:setting:${at}`} flexDirection="row">
          <Button key={`setting:${at}`} label="open" onPress={() => actions.open(at)} />
          <Text dimColor={idles(listed)} wrap="wrap">
            {` ${plainLine(listed.title)}: ${shown(listed)}`}
          </Text>
        </Box>
      )
    return (
      <Box flexDirection="column">
        {heading(HEADING)}
        {again}
        {change !== null && quiet(underWay(change))}
        {GROUPS.map(group => {
          const listed = settings.map((one, at) => ({ one, at })).filter(({ one }) => one.scope === group.scope)
          const reasons = [...new Set(listed.map(({ one }) => notRead[one.file]).filter(reason => reason !== undefined))]
          return (
            <Box key={`group:${group.scope}`} flexDirection="column">
              {heading(group.heading)}
              {reasons.map(reason => (
                <Text key={`reason:${reason}`} dimColor wrap="wrap">
                  {`${NOT_READ}: ${plainLine(reason)}`}
                </Text>
              ))}
              {listed.some(({ one }) => idles(one)) && quiet(NOTHING_HERE)}
              {listed.map(({ one, at }) => row(one, at))}
            </Box>
          )
        })}
      </Box>
    )
  }
  const at = view.at
  const where = GROUPS.find(group => group.scope === setting.scope)?.where ?? setting.scope
  const isPressed = change !== null && change.scope === setting.scope && change.key === setting.key
  const refused = refusal !== null && refusal.scope === setting.scope && refusal.key === setting.key ? refusal.line : null
  const hasDefault = setting.isRead && setting.defaultValue !== null && setting.defaultValue !== undefined
  const reason = notRead[setting.file]
  const isHandingIn = isHandingInOfThisMachine(setting) && setting.kind === 'switch' && setting.isRead
  const isHandingInOn = isHandingIn && turnsHandingInOn(setting.key, setting.value)
  const turnsOnHere = setting.choices.some(choice => pressTurnsHandingInOn(setting, choice, e.surface))
  const previous = at > 0 ? <Button key="settings:previous" label="previous" onPress={() => actions.open(at - 1)} /> : null
  const next = at < settings.length - 1 ? <Button key="settings:next" label="next" onPress={() => actions.open(at + 1)} /> : null
  const list = <Button key="settings:list" label="list" onPress={actions.toList} />
  return (
    <Box flexDirection="column">
      {heading(`${HEADING} · ${at + 1} of ${settings.length}`)}
      {/* The way on comes before any switch, so that a switch is never the first thing a key can press. */}
      {isNarrow ? (
        // Three buttons side by side are wider than the narrowest pane: `list` goes below the other two.
        <Box key="row:walk" flexDirection="column">
          <Box flexDirection="row">
            {previous}
            {previous !== null && next !== null && <Text> </Text>}
            {next}
          </Box>
          {list}
        </Box>
      ) : (
        <Box key="row:nav" flexDirection="row">
          {previous}
          {previous !== null && <Text> </Text>}
          {next}
          {next !== null && <Text> </Text>}
          {list}
        </Box>
      )}
      {again}
      {heading(plainLine(setting.title))}
      {quiet(`${where} · ${plainLine(setting.key)}`)}
      <Text wrap="wrap">{`now: ${shown(setting)}`}</Text>
      {hasDefault && setting.defaultValue !== setting.value && quiet(`default: ${inWords(setting.defaultValue)}`)}
      <Text wrap="wrap">{plainLine(setting.does)}</Text>
      {isHandingIn && quiet(EVERY_MACHINE)}
      {isHandingInOn && quiet(AT_ITS_START)}
      {!setting.isRead && reason !== undefined && quiet(`${NOT_READ}: ${plainLine(reason)}`)}
      {idles(setting) && quiet(DOES_NOT_CURATE)}
      {refused !== null && failure(`not changed: ${plainLine(refused)}`)}
      {/* How it is turned on stands above whatever is pressed, so it is on the screen for the press. */}
      {isHandingIn && !isHandingInOn && <Text wrap="wrap">{turnsOnHere ? BY_YOUR_PRESS : IN_YOUR_OWN_TERMINAL}</Text>}
      {isPressed && change.phase === 'waiting' && (
        <Box key="row:change" flexDirection="row">
          <Button key="settings:undo" label="undo" onPress={actions.undo} />
          <Text dimColor wrap="wrap">
            {` ${changeLine(change.key, change.choice)}`}
          </Text>
        </Box>
      )}
      {isPressed && change.phase === 'writing' && quiet(`${changeLine(change.key, change.choice)}…`)}
      {change !== null && !isPressed && quiet(underWay(change))}
      {change === null &&
        offered(setting, e.surface).map(place => {
          const choice = setting.choices[place]
          // The key names the card: a key that follows the keyboard from card to card must not land on another switch.
          // No button here has a hotkey or takes the focus by itself, so no single key presses a switch.
          // The press names its surface, which is not always the one this drawing is for.
          return choice === undefined ? null : (
            <Button key={`set:${at}:${place}`} label={choiceLabel(choice)} onPress={pressed => actions.choose(at, place, pressed.surface)} />
          )
        })}
      {setting.kind !== 'switch' && quiet(howItChanges(setting))}
    </Box>
  )
}
