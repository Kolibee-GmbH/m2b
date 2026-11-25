import type { EngineInterface, ResolveInput } from 'claude-code'

import type { BandPress, EditCopy } from '../types'

import type { EditLook } from './facts-tab'
import { pressLine, said } from './look'
import type { ButtonSpec } from './look'
import { runM2b } from './m2b'
import { plainLine, wholePath } from './plain-text'

/*
 * `edit` in a fact file's view: a press has the core copy the fact file into this machine's state
 * folder and open the copy in the system's text editor (`m2b store edit`). Nothing in `memory/` is
 * written outside a curation run: the owner's version goes to the inbox with `keep the edit`, after
 * the five seconds of `undo` every press that writes has, and the next run puts it in place.
 *
 * What the copy is, the view reads from the core with the fact file (`edit` in `m2b source --json
 * --viewer`), so a save in the editor is seen once the view reads the file again: when the time of
 * the copy's last save changes, by a press on its tab, or after a write. The copy's path names the fact file, which can name a customer: it is held
 * with the file in this module, as is what a press could not do, and never put in the session's
 * state, which other plugins can read.
 */

/** The key of the box that says what became of the copy. */
export const EDITING = 'fact:editing'
/** The key of the button `edit`. */
export const EDIT = 'fact:edit'
/** The key of the button `keep the edit`. */
export const KEEP_EDIT = 'fact:edit:keep'
/** The key of the button `discard`. */
export const DISCARD_EDIT = 'fact:edit:discard'
/** The press of `keep the edit` or `discard`, in the session's presses. */
export const EDIT_PRESS = 'fact:edit'
/** The key of `undo` while that press waits. */
export const UNDO_EDIT = 'undo:edit'

// The core copies one file, after waiting up to 20 s for an evicted store.json, and starts the editor without waiting for it.
const EDIT_TIMEOUT_MS = 30_000

/** What the presses on a fact file's editing copy do. */
export type EditActions = {
  open: () => Promise<void>
  keep: () => Promise<void>
  discard: () => Promise<void>
  undo: () => Promise<void>
}

/**
 * What is held between draws: the fact file the press of keep or discard is for while it waits or
 * writes, and, by fact file, what the last press on its copy could not do, as it is said.
 */
const held: { pressFor: string | null; notices: Map<string, string> } = { pressFor: null, notices: new Map() }

/** The button `edit`, which stands beside `correct`. */
export function editButton(actions: EditActions): ButtonSpec {
  return { key: EDIT, label: 'edit', kind: 'default', onPress: () => void actions.open() }
}

/**
 * Has the core make the copy of `file`, or find the one there is, and open it where the session
 * has a screen. What the core refused is held for the view, cleaned; where no editor opened the
 * view names the copy's path alone: any editor in any terminal takes it.
 */
export async function openEditCopy($: EngineInterface, file: string): Promise<void> {
  // `--`: the name is the distillate's own text, and it may start with a dash.
  const outcome = await runM2b($, ['store', 'edit', '--json', '--', file], EDIT_TIMEOUT_MS)
  noteOutcome(file, outcome.ok ? null : plainLine(outcome.error))
}

/** Takes the press of keep or discard for `file`; false while another one has not landed. */
export function takeEditPress(file: string): boolean {
  if (held.pressFor !== null) {
    return false
  }
  held.pressFor = file
  held.notices.delete(file)
  return true
}

/** The button the focus goes back to once a press of `choice` is taken back, so Enter does that again. */
export function focusAfterUndo(choice: EditCopy): string {
  return choice === 'keep the edit' ? KEEP_EDIT : DISCARD_EDIT
}

/** Undo: the press is forgotten, and the copy is as it was. */
export function giveEditPressBack(): void {
  held.pressFor = null
}

/**
 * Keeps the copy of `file` as a capture for the next run, or removes it (`m2b store edit --keep`
 * or `--discard`). What the core refused is held for the view, which says it below the copy.
 */
export async function writeEditCopy($: EngineInterface, file: string, choice: EditCopy): Promise<void> {
  const flag = choice === 'keep the edit' ? '--keep' : '--discard'
  const outcome = await runM2b($, ['store', 'edit', '--json', flag, '--', file], EDIT_TIMEOUT_MS)
  held.pressFor = null
  noteOutcome(file, outcome.ok ? null : `${choice === 'keep the edit' ? 'not kept' : 'not discarded'}: ${plainLine(outcome.error)}`)
}

/** Forgets everything held: a session that starts, and the conversation after `/clear` or a resume. */
export function forgetEdits(): void {
  held.pressFor = null
  held.notices.clear()
}

function noteOutcome(file: string, refused: string | null): void {
  if (refused === null) {
    held.notices.delete(file)
  } else {
    held.notices.set(file, refused)
  }
}

/** What the view says of a copy, by the state the core names: behind the fact file, changed, or as it was made. */
function copyState(edit: EditLook): { said: string; canKeep: boolean } {
  if (edit.factFileChanged) {
    return { said: 'the fact file changed since you opened the copy', canKeep: false }
  }
  if (edit.differs) {
    return { said: 'your copy differs from the fact file', canKeep: true }
  }
  // Saved in the editor, the view follows by itself (`watchShownCopy` in register.tsx); this says so.
  return { said: 'an editing copy is open: save it, and this view follows', canKeep: false }
}

/**
 * Below the buttons of a fact file's view: while a press of keep or discard waits, `undo` and what
 * it does; else what the copy is, its path whole and what can be done with it, `keep the edit`
 * only for a copy that differs from a fact file that did not change since; below that what the last
 * press could not do. Nothing where there is no copy and nothing to say.
 */
export function editRow($: EngineInterface, e: ResolveInput, file: string, edit: EditLook, pressed: BandPress | undefined, actions: EditActions) {
  const ui = $.ui.resolve(e)
  const { Box } = ui
  if (pressed !== undefined && held.pressFor === file) {
    const doing = pressed.action === 'keep the edit' ? 'keeping the edit' : 'discarding the copy'
    return (
      <Box key={EDITING} flexDirection="column">
        {pressed.phase === 'waiting'
          ? pressLine(ui, [{ key: UNDO_EDIT, label: 'undo', kind: 'default', onPress: () => void actions.undo() }], doing)
          : said(ui, `${doing}…`, 'quiet')}
      </Box>
    )
  }
  const notice = held.notices.get(file) ?? null
  if (edit.copy === null && notice === null) {
    return null
  }
  const state = edit.copy === null ? null : copyState(edit)
  const buttons: ButtonSpec[] = [
    ...(state?.canKeep === true ? [{ key: KEEP_EDIT, label: 'keep the edit', kind: 'default' as const, onPress: () => void actions.keep() }] : []),
    { key: DISCARD_EDIT, label: 'discard', kind: 'default', onPress: () => void actions.discard() },
  ]
  return (
    <Box key={EDITING} flexDirection="column">
      {state !== null && said(ui, state.said, state.canKeep ? 'waits' : 'plain')}
      {/* Whole, as a folder is named: the path is one to hand to an editor, each character as it is. */}
      {edit.copy !== null && said(ui, wholePath(edit.copy), 'quiet')}
      {edit.copy !== null && pressLine(ui, buttons)}
      {notice !== null && said(ui, notice, 'trouble')}
    </Box>
  )
}
