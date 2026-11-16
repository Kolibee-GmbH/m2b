import type { CommandSpec, EngineInterface, ResolveInput } from 'claude-code'

import type { PaneView } from '../types'
import { apart, part, pressLine, said, under, valueRow } from './look'
import type { ValueSpec } from './look'
import { runM2b } from './m2b'
import { tabKey } from './pane-tabs'
import { plainLine } from './plain-text'
import { OLDER_CORE } from './session'

/*
 * Every setting of m2b in the pane, by what a person wants from m2b: the few choices first, each
 * with what it does and its values side by side, then what only informs or is changed by a
 * command, behind one row that opens it under a tab of its own. A switch is set by a press on one
 * of its values; every other setting names the command or the skill that changes it. The list,
 * its groups and their order are the core's (`m2b settings --json`), and so is the one command a
 * press runs (`m2b settings set`), which refuses whatever is no switch.
 *
 * One switch a session's shell does not turn on: `sessions.propose`, with which a session hands in
 * proposals with words from what its agent read. The core refuses it while `CLAUDECODE` is set, as
 * it is for every command of a session's shell. No tool of Claude Code hands the mod a press: one
 * arrives as input on a client that draws the session. So a press on its value does turn it on;
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

/**
 * One setting as `m2b settings --json` lists it. `shows` is its value in words; `value` only tells
 * which choice is set. `group` names the group the core sorts it into, `place` its place there.
 */
export type Setting = {
  key: string
  file: string
  scope: Scope
  group: string
  place: number
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

/** A group of the core's list. `isFolded`: it holds what only informs or is changed by a command, and no switch. */
export type Group = { name: string; title: string; isFolded: boolean }

export type Catalog = { settings: Setting[]; groups: Group[]; curates: boolean | null; notRead: Record<string, string> }

/** A look at the settings, as m2b answered: the list, or why it could not be read. */
export type SettingsLook = { state: 'reading' } | { state: 'read'; catalog: Catalog } | { state: 'failed'; error: string }

/**
 * A press on a switch: it waits for undo, then it is written. It names its setting and the value
 * by what they are, never by a place in the list: the list is read again after every write, and a
 * place could then be another setting's. `press` is the opening of the view it was made in.
 * `isTurningHandingInOn` marks the one press `pressTurnsHandingInOn` names, settled when the
 * press is made, from the surface the press itself said: the view can be drawn on several
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
// `pressed` is the setting the opening's last press was on: the focus rests near it afterwards.
let held: {
  press: string
  look: SettingsLook
  trouble: string | null
  refusal: Refusal | null
  asked: number
  pressed: { scope: Scope; key: string } | null
} | null = null
// The one change under way. It is not part of an opening: a change being written goes on when the
// view is left, and a view opened meanwhile must neither start a second one nor miss its refusal.
let change: Change | null = null

/**
 * Begins a look for an opening of the view, in place of whatever was kept before: m2b reads. A
 * press that still waited in the opening before is taken back, one being written goes on.
 */
export function beginSettings(press: string): void {
  dropWaitingChange()
  held = { press, look: { state: 'reading' }, trouble: null, refusal: null, asked: 0, pressed: null }
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

const HANDING_IN = 'sessions.propose'
// The surfaces on which the view offers to turn handing in on. A surface is what the client that
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
 * handing in on: this machine's switch, the value the command takes for it, a surface the view
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
 * The places, among a switch's choices, of the values the view offers on `surface`: every value
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
 * Notes a press on a value of the setting at `at` of the list, made on `surface`, which writes
 * nothing yet. False where the press is not one the view offers there, or another change waits or
 * is being written, in whatever opening: one change at a time from this pane, so two of its
 * writes never race for a file and a refusal is about the press the person just made. A change
 * made elsewhere meanwhile, in a terminal or another session, is not known here.
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
  held = { ...held, refusal: null, pressed: { scope: setting.scope, key: setting.key } }
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

function present<T>(value: T | null): value is T {
  return value !== null
}

function isChoice(value: unknown): value is Choice {
  return typeof value === 'string' || typeof value === 'boolean' || typeof value === 'number'
}

function groupOf(value: unknown): Group | null {
  if (!isObject(value)) {
    return null
  }
  const { name, title, folded } = value
  return typeof name === 'string' && typeof title === 'string' && typeof folded === 'boolean' ? { name, title, isFolded: folded } : null
}

function settingOf(value: unknown): Setting | null {
  if (!isObject(value)) {
    return null
  }
  const { key, file, scope, group, place, kind, title, does, read, shows, choices, changed_by: changedBy, change, curation } = value
  const isKnown =
    typeof key === 'string' &&
    typeof file === 'string' &&
    (scope === 'machine' || scope === 'store' || scope === 'owner') &&
    typeof group === 'string' &&
    typeof place === 'number' &&
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
    group,
    place,
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

/**
 * The answer of `m2b settings --json`; one of any other shape is could not read, never a list
 * without settings. A list without groups is a core's from before it sorted them, and is said as
 * that: the view has no order of its own to draw one in.
 */
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
  if (answer['groups'] === undefined) {
    return { state: 'failed', error: OLDER_CORE }
  }
  const { curates, not_read: notRead } = answer
  const groups = Array.isArray(answer['groups']) ? answer['groups'].map(groupOf).filter(present) : []
  const settings = answer['settings'].map(settingOf)
  const reasons = Object.entries(notRead)
  const named = new Set(groups.map(group => group.name))
  if (
    !Array.isArray(answer['groups']) ||
    groups.length !== answer['groups'].length ||
    settings.some(setting => setting === null || !named.has(setting.group)) ||
    !(curates === null || typeof curates === 'boolean') ||
    !reasons.every(([, reason]) => typeof reason === 'string')
  ) {
    return { state: 'failed', error: OTHER_SHAPE }
  }
  return {
    state: 'read',
    catalog: {
      settings: settings.filter(present),
      groups,
      curates,
      notRead: Object.fromEntries(reasons.map(([file, reason]) => [file, String(reason)])),
    },
  }
}

/** The key of the button that takes a waiting press back. */
export const SETTINGS_UNDO = 'settings:undo'

/** The key of the button that sets the value at `place` of the setting at `at` of the list. */
export function valueKey(at: number, place: number): string {
  return `set:${at}:${place}`
}

/** The key of the tab that leads from the settings to the start view. */
export const OFF_THE_VALUES = tabKey('overview', 'settings')

/** Whether a press waits, is being written, or none is under way: with it the buttons the view draws change. */
type Phase = 'idle' | Change['phase']

function phaseOf(under: Change | null): Phase {
  return under?.phase ?? 'idle'
}

/**
 * The key of the button that shows the settings of the group `name`, which the view keeps behind
 * one row. It names the phase the view is drawn in: while a press waits or
 * is written the values are no buttons, so the row stands at another place among the buttons.
 * Claude Code looks a key up in what is drawn when the focus is asked for and waits only for one
 * that is not drawn yet: one key for every phase would be found in the drawing before, at a place
 * where the next one has a value.
 */
export function foldKey(name: string, phase: Phase = 'idle'): string {
  return phase === 'idle' ? `settings:fold:${name}` : `settings:fold:${name}:${phase}`
}

/**
 * The key of the button the focus is asked for once the button it stood on is gone, after `undo`
 * and when a press is written or dropped. Every button of the view sets a value but two kinds, the
 * tab that leads to the start view, above the settings, and the row of a folded group; the mod
 * asks for the focus on no value, since Enter pressed once more must never write. Of those two
 * kinds it is the one nearest to the setting that was pressed, counted in settings: the pane
 * follows the focus, so the view stays near where the person works. The tab where nothing was
 * pressed, or the list no longer has that setting. A row's key is the one of the phase the view
 * is in when this is asked.
 */
export function restKey(): string {
  if (held === null || held.look.state !== 'read' || held.pressed === null) {
    return OFF_THE_VALUES
  }
  const { settings, groups } = held.look.catalog
  const { scope, key } = held.pressed
  // What the view draws below the tabs, in its order: a setting each, and one row per folded group.
  const drawn = groups.flatMap((group): { isPressed: boolean; rest: string | null }[] => {
    const listed = heldBy(settings, group)
    if (!group.isFolded) {
      return listed.map(({ setting }) => ({ isPressed: setting.scope === scope && setting.key === key, rest: null }))
    }
    return listed.length > 0 ? [{ isPressed: false, rest: foldKey(group.name, phaseOf(change)) }] : []
  })
  const pressedAt = drawn.findIndex(one => one.isPressed)
  if (pressedAt < 0) {
    return OFF_THE_VALUES
  }
  // The tab stands before the first setting; where a row is as near, the tab it is.
  let nearest = { key: OFF_THE_VALUES, away: pressedAt + 1 }
  drawn.forEach((one, at) => {
    if (one.rest !== null && Math.abs(at - pressedAt) < nearest.away) {
      nearest = { key: one.rest, away: Math.abs(at - pressedAt) }
    }
  })
  return nearest.key
}

/** Whether the press `token` names still waits for undo: neither taken back nor being written. */
export function waits(token: string): boolean {
  return change !== null && change.token === token && change.phase === 'waiting'
}

/**
 * What the view's buttons do. `choose` is a press on a value of the setting at a place of the
 * list, with the surface the press named; `showGroup` turns the view to the settings of a group
 * it keeps behind one row.
 */
export type SettingsActions = {
  choose: (at: number, place: number, surface: string) => Promise<void>
  undo: () => Promise<void>
  showGroup: (group: string) => Promise<void>
}

const READING = 'm2b is reading its settings…'
const COULD_NOT_READ = 'm2b could not read its settings'
const NOT_READ = 'not read'
const NOTHING_HERE = 'This machine does not curate: the settings of the curation run do nothing here.'
const IN_YOUR_OWN_TERMINAL = `Turned on in a terminal of your own: m2b settings set ${HANDING_IN} true`
const BY_YOUR_PRESS = 'Your press here turns it on, as a terminal of your own does.'
const EVERY_MACHINE = 'Every machine that shares the store needs an m2b that knows handing in.'
// The mod registers the tool when it loads, at a session's start and on a reload; the command takes a call at once.
const AT_ITS_START =
  'A session gets the tool when it starts or its plugins are reloaded: until then, one that ran before this was turned on does not have it.'
const KEPT_BY_M2B = 'kept by m2b, never changed by hand'
const FOLDED = 'that only inform or are changed by a command'

/** A text of the core as one plain line, with its white space as single spaces: a run of spaces would wrap into what reads as rows of its own. */
function oneLine(text: string): string {
  return plainLine(text).replace(/ {2,}/g, ' ').trim()
}

function shown(setting: Setting): string {
  return setting.isRead ? oneLine(setting.shows ?? '') : NOT_READ
}

/** A value as its row names it: `on` and `off` for a switch of two, any other as it is. */
function valueLabel(choice: Choice): string {
  return typeof choice === 'boolean' ? (choice ? 'on' : 'off') : plainLine(String(choice))
}

/** What a press that waits or is being written does, below the setting's title. */
function changeLine(choice: Choice): string {
  return typeof choice === 'boolean' ? `turning ${choice ? 'on' : 'off'}` : `changing to ${plainLine(String(choice))}`
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

function settingsCount(count: number): string {
  return `${count} ${count === 1 ? 'setting' : 'settings'}`
}

/** A setting with its place in the list as read, by which its buttons say which setting a press is on. */
type Listed = { setting: Setting; at: number }

/** The settings of a group, in the order the core gave them there. */
function heldBy(settings: readonly Setting[], group: Group): Listed[] {
  return settings
    .map((setting, at) => ({ setting, at }))
    .filter(({ setting }) => setting.group === group.name)
    .sort((one, other) => one.setting.place - other.setting.place)
}

/** Why files were not read, each reason once with the files it is about: a store out of reach is one reason for two files. */
function unreadLines(notRead: Readonly<Record<string, string>>): string[] {
  const reasons = [...new Set(Object.values(notRead))]
  return reasons.map(reason => {
    const files = Object.keys(notRead).filter(file => notRead[file] === reason)
    return `m2b could not read ${files.map(plainLine).join(' and ')}: ${plainLine(reason)}`
  })
}

/**
 * The view's drawing: a part per group of the core's list, in the core's order. In a group of
 * choices every setting is its title, what it does and its values in a row; a group the core
 * marks as folded is one row. A press on it turns the view to that group alone (`view.aside`),
 * every setting of it with its value and what changes it: a list that long, opened below the
 * choices, would lie under the part of the pane a person sees. `columns` is the width of the
 * pane's body.
 */
export function settingsPane(
  $: EngineInterface,
  e: ResolveInput,
  view: Extract<PaneView, { kind: 'settings' }>,
  kept: Held,
  actions: SettingsActions,
  columns: number,
) {
  const ui = $.ui.resolve(e)
  const { Box } = ui
  const { look, trouble, change, refusal } = kept
  if (look.state !== 'read') {
    return look.state === 'reading' ? said(ui, READING, 'quiet') : said(ui, `${COULD_NOT_READ}: ${plainLine(look.error)}`, 'trouble')
  }
  const { settings, groups, curates, notRead } = look.catalog
  const idles = (setting: Setting): boolean => setting.isOfCuration && curates === false
  const isAbout = (one: { scope: Scope; key: string } | null, setting: Setting): boolean =>
    one !== null && one.scope === setting.scope && one.key === setting.key

  /** A switch's values: the one in force marked, every other a button where this surface offers it and no change is under way. */
  const valuesOf = ({ setting, at }: Listed): ValueSpec[] => {
    if (setting.kind !== 'switch') {
      return [{ label: shown(setting), isInForce: true, set: null }]
    }
    const canBePressed = change === null ? offered(setting, e.surface) : []
    const values = setting.choices.map((choice, place) => ({
      label: valueLabel(choice),
      isInForce: choice === setting.value,
      // The press names its surface, which is not always the one this drawing is for.
      // No button here has a hotkey, and the mod never asks for the focus on one.
      set: canBePressed.includes(place)
        ? { key: valueKey(at, place), onPress: (pressed: { surface: string }) => actions.choose(at, place, pressed.surface) }
        : null,
    }))
    // A value the file holds that is none of the switch's: shown as it is, before the ones to change to.
    return values.some(value => value.isInForce) ? values : [{ label: shown(setting), isInForce: true, set: null }, ...values]
  }

  /** What stands where a setting's values do: the values, or the press that waits or is being written. */
  const valuesOrChange = (listed: Listed) => {
    const { setting } = listed
    if (!setting.isRead) {
      return said(ui, NOT_READ, 'quiet')
    }
    if (change === null || !isAbout(change, setting)) {
      return valueRow(ui, valuesOf(listed), `values:${listed.at}`)
    }
    if (change.phase === 'waiting') {
      const takeBack = { key: SETTINGS_UNDO, label: 'undo', kind: 'default' as const, onPress: () => actions.undo() }
      return pressLine(ui, [takeBack], changeLine(change.choice), `values:${listed.at}`)
    }
    return said(ui, `${changeLine(change.choice)}…`, 'quiet')
  }

  /** A setting to choose: its title, what it does, and its values side by side. */
  const toChoose = (listed: Listed) => {
    const { setting } = listed
    const isHandingIn = isHandingInOfThisMachine(setting) && setting.kind === 'switch' && setting.isRead
    const isHandingInOn = isHandingIn && turnsHandingInOn(setting.key, setting.value)
    const turnsOnHere = setting.choices.some(one => pressTurnsHandingInOn(setting, one, e.surface))
    return (
      <Box key={`setting:${listed.at}`} flexDirection="column">
        {said(ui, plainLine(setting.title), idles(setting) ? 'quiet' : 'strong')}
        {said(ui, plainLine(setting.does), 'quiet')}
        {isHandingIn && said(ui, EVERY_MACHINE, 'quiet')}
        {isHandingInOn && said(ui, AT_ITS_START, 'quiet')}
        {refusal !== null && isAbout(refusal, setting) && said(ui, `not changed: ${plainLine(refusal.line)}`, 'trouble')}
        {/* How it is turned on stands above whatever is pressed, so it is on the screen for the press. */}
        {isHandingIn && !isHandingInOn && said(ui, turnsOnHere ? BY_YOUR_PRESS : IN_YOUR_OWN_TERMINAL)}
        {valuesOrChange(listed)}
        {setting.kind !== 'switch' && under(ui, howItChanges(setting))}
      </Box>
    )
  }

  /** A setting that informs: its title with its value, and below it what changes it. */
  const informed = ({ setting, at }: Listed) => (
    <Box key={`setting:${at}`} flexDirection="column">
      {said(ui, `${plainLine(setting.title)}: ${shown(setting)}`, idles(setting) ? 'quiet' : 'plain')}
      {under(ui, howItChanges(setting))}
    </Box>
  )

  const partOf = (group: Group) => {
    const held = heldBy(settings, group)
    const spec = { key: group.name, title: plainLine(group.title), waits: false, columns }
    const idle = held.some(({ setting }) => idles(setting)) ? [said(ui, NOTHING_HERE, 'quiet')] : []
    if (!group.isFolded) {
      return part(ui, spec, [apart(ui, [...idle, ...held.map(toChoose)])])
    }
    if (group.name === aside?.name) {
      // Under its own tab, which bears the group's title: the part says what it holds.
      return part(ui, { ...spec, title: `${settingsCount(held.length)} ${FOLDED}` }, [...idle, ...held.map(informed)])
    }
    const lead = {
      key: foldKey(group.name, phaseOf(change)),
      label: settingsCount(held.length),
      kind: 'default' as const,
      onPress: () => actions.showGroup(group.name),
    }
    return part(ui, spec, [pressLine(ui, [lead], FOLDED, `folded:${group.name}`)])
  }

  // The group the view was turned to, where the list as it is now still has it; else the choices.
  const aside = groups.find(group => group.isFolded && group.name === view.aside?.name && heldBy(settings, group).length > 0)
  const drawn = aside === undefined ? groups.filter(group => heldBy(settings, group).length > 0) : [aside]
  return (
    <Box flexDirection="column">
      {trouble !== null && said(ui, `${COULD_NOT_READ} again: ${plainLine(trouble)}`, 'trouble')}
      {unreadLines(notRead).map(line => said(ui, line, 'trouble'))}
      {drawn.map(partOf)}
    </Box>
  )
}

/**
 * The title of the group `name` of the list held for `press`, where the view keeps that group
 * behind one row and it holds a setting; null else, as for a list that was read again without it.
 */
export function foldedTitle(press: string, name: string): string | null {
  if (held === null || held.press !== press || held.look.state !== 'read') {
    return null
  }
  const { settings, groups } = held.look.catalog
  const group = groups.find(one => one.isFolded && one.name === name && heldBy(settings, one).length > 0)
  return group === undefined ? null : plainLine(group.title)
}
