import type { PaneView } from '../types'
import { factFileNameOf, factTabLabel, topicOfFactFile } from './facts-tab'
import { sourceLabelOf } from './source-view'
import { topicLabel } from './look'
import type { Tab } from './look'
import { topicNameOf } from './topic'

/*
 * The tabs above every view of the m2b pane: six that stay, always in one order, and a seventh for
 * a topic's lines, a fact's file, a note a current item names, a search or the settings that only
 * inform, which stands there only while it is shown. A source a fact rests on stands under an
 * eighth, beside the seventh that bears its fact file and leads back to it; so does a fact file
 * opened from a topic, beside the seventh that bears the topic's name. A tab is the one way from a
 * view to another, so no view has a button that leads back.
 */

/** A tab that stays, named like the view it turns the pane to. */
export type TabId = 'overview' | 'proposals' | 'review' | 'tasks' | 'facts' | 'settings'

/** What the pane shows, as its row of tabs has it: one of the six, or the seventh beside them. */
export type Shown = TabId | 'aside'

const TAB_IDS: readonly TabId[] = ['overview', 'proposals', 'review', 'tasks', 'facts', 'settings']
const LABELS: Readonly<Record<TabId, string>> = {
  overview: 'Overview',
  proposals: 'Proposals',
  review: 'Review',
  tasks: 'Tasks',
  facts: 'Facts',
  settings: 'Settings',
}
const SEARCH = 'Search'
// The letter of each tab that stays: its first, all six different.
const HOTKEYS: Readonly<Record<TabId, string>> = { overview: 'o', proposals: 'p', review: 'r', tasks: 't', facts: 'f', settings: 's' }

export function shownOf(view: PaneView | null): Shown {
  if (view === null) {
    return 'overview'
  }
  if (view.kind === 'topic' || view.kind === 'search' || view.kind === 'fact' || view.kind === 'source') {
    return 'aside'
  }
  return view.kind === 'settings' && view.aside !== null ? 'aside' : view.kind
}

/**
 * The key of the tab that turns the pane to `to`, as drawn above the view `shown`. It names both:
 * Claude Code looks a key up in what is drawn at the moment the focus is asked for and waits only
 * for one that is not drawn yet, so a key the view before drew too would be found there, at a
 * place where the new view may have another button.
 */
export function tabKey(to: TabId, shown: Shown): string {
  return `tab:${to}:in:${shown}`
}

/**
 * The key of the tab the focus is asked for once a press on the tab `to` turned the pane to its
 * view: that tab itself, drawn as the one shown, so the focus is the one mark in the row and Enter
 * reads the view again. The view before drew it under another key, unless it was that very view.
 */
export function focusKeyAfterTab(to: TabId): string {
  return tabKey(to, to)
}

/**
 * The key of the tab the focus is asked for once a press in the view `from` opened a view beside
 * the six (a topic's lines, a fact's file, a note): `from`'s tab, which leads back.
 */
export function backTabKey(from: TabId): string {
  return tabKey(from, 'aside')
}

function asideLabel(view: PaneView | null): string | null {
  if (view?.kind === 'topic') {
    return topicLabel(topicNameOf(view.press))
  }
  // A fact file's tab is drawn by `paneTabs` itself: shown, it is a button.
  // A note opened from a current item: no fact file stands above it, so its tab is the seventh.
  if (view?.kind === 'source') {
    return sourceLabelOf(view.press)
  }
  if (view?.kind === 'settings' && view.aside !== null) {
    return topicLabel(view.aside.title)
  }
  return view?.kind === 'search' ? SEARCH : null
}

/** The key of the tab that leads from a source back to the fact file it was shown from; no other view draws it. */
export const BACK_TO_THE_FACT_FILE_KEY = 'tab:fact:in:source'

/** The key of a fact file's own tab while its view is shown: a press reads the file again, to see what became of its editing copy. */
export const FACT_FILE_TAB_KEY = 'tab:fact:shown'

/** The key of the tab that leads from a fact file back to the topic it was opened from; no other view draws it. */
export const BACK_TO_THE_TOPIC_KEY = 'tab:topic:in:fact'

/**
 * The presses on a tab beside the six: one that leads back, to the fact file a source was shown
 * from or to the topic a fact file was opened from, and a fact file's own tab, which reads it again.
 */
export type BackTabs = { toFactFile: (from: string) => void; toTopic: (fact: string) => void; readFactFileAgain: () => void }

/**
 * The pane's tabs above `view`. `waiting` is how many proposals wait: the tab counts them, and a
 * zero is not said. `onTurn` is the press on a tab, `back` the presses on a tab that leads back.
 */
export function paneTabs(view: PaneView | null, waiting: number, onTurn: (to: TabId) => void, back: BackTabs): Tab[] {
  const shown = shownOf(view)
  const staying: Tab[] = TAB_IDS.map(id => ({
    label: id === 'proposals' && waiting > 0 ? `${LABELS[id]} ${waiting}` : LABELS[id],
    turn: { key: tabKey(id, shown), onPress: () => onTurn(id) },
    isShown: id === shown,
    hotkey: HOTKEYS[id],
  }))
  if (view?.kind === 'fact') {
    const fact = view.press
    const topic = topicOfFactFile(fact)
    // Shown, a fact file's tab is a button as each of the six is: Enter on it reads the file again.
    const own: Tab = { label: factTabLabel(factFileNameOf(fact)), turn: { key: FACT_FILE_TAB_KEY, onPress: () => back.readFactFileAgain() }, isShown: true, hotkey: null }
    if (topic === null) {
      return [...staying, own]
    }
    return [
      ...staying,
      { label: topicLabel(topicNameOf(topic.press)), turn: { key: BACK_TO_THE_TOPIC_KEY, onPress: () => back.toTopic(fact) }, isShown: false, hotkey: null },
      own,
    ]
  }
  if (view?.kind === 'source' && view.from !== null) {
    const from = view.from
    return [
      ...staying,
      { label: factTabLabel(factFileNameOf(from)), turn: { key: BACK_TO_THE_FACT_FILE_KEY, onPress: () => back.toFactFile(from) }, isShown: false, hotkey: null },
      { label: sourceLabelOf(view.press), turn: null, isShown: true, hotkey: null },
    ]
  }
  const aside = asideLabel(view)
  return aside === null ? staying : [...staying, { label: aside, turn: null, isShown: true, hotkey: null }]
}
