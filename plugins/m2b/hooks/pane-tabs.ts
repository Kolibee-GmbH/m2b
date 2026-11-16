import type { PaneView } from '../types'
import type { Tab } from './look'
import { plainLine } from './plain-text'
import { topicShowKey } from './session-view'
import type { SessionModel } from './session-view'

/*
 * The tabs above every view of the m2b pane: four that stay, always in one order, and a fifth for
 * a topic's lines or a search, which stands there only while it is shown. A tab is the one way
 * from a view to another, so no view has a button that leads back.
 */

/** A tab that stays, named like the view it turns the pane to. */
export type TabId = 'overview' | 'proposals' | 'review' | 'settings'

/** What the pane shows, as its row of tabs has it: one of the four, or the fifth beside them. */
export type Shown = TabId | 'aside'

const TAB_IDS: readonly TabId[] = ['overview', 'proposals', 'review', 'settings']
const LABELS: Readonly<Record<TabId, string>> = {
  overview: 'Overview',
  proposals: 'Proposals',
  review: 'Review',
  settings: 'Settings',
}
const SEARCH = 'Search'
// A topic's name is the fifth tab's label; its view names it whole in its heading.
const TOPIC_LABEL_LENGTH = 20

export function shownOf(view: PaneView | null): Shown {
  if (view === null) {
    return 'overview'
  }
  return view.kind === 'topic' || view.kind === 'search' ? 'aside' : view.kind
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
 * The key of the tab the focus is asked for once a press turned the pane from `left` to `to`: the
 * tab that leads back to the view that was left. The same key pressed again returns there, and the
 * focus never stands on a button that writes. The fifth tab is gone once it is left: `Overview`
 * stands in for it, and on the overview itself the tab beside it.
 */
export function tabKeyAfterTurn(left: Shown, to: Shown): string {
  if (left !== 'aside' && left !== to) {
    return tabKey(left, to)
  }
  return tabKey(to === 'overview' ? 'proposals' : 'overview', to)
}

/**
 * The key of the button the focus is asked for once a press on the tab `to` turned the pane from
 * the view `left`. A topic left for the start view has a way back of its own there, `show` on its
 * row, where `model` has the start view draw that row; every other turn follows the tabs' rule.
 */
export function focusKeyAfterTab(left: PaneView | null, to: TabId, model: SessionModel): string {
  const show = to === 'overview' && left?.kind === 'topic' ? topicShowKey(model, left.name) : null
  return show ?? tabKeyAfterTurn(shownOf(left), to)
}

function cut(text: string, length: number): string {
  const characters = Array.from(text)
  return characters.length <= length ? text : `${characters.slice(0, length - 1).join('')}…`
}

function asideLabel(view: PaneView | null): string | null {
  if (view?.kind === 'topic') {
    return cut(plainLine(view.name), TOPIC_LABEL_LENGTH)
  }
  return view?.kind === 'search' ? SEARCH : null
}

/**
 * The pane's tabs above `view`. `waiting` is how many proposals wait: the tab counts them, and a
 * zero is not said. `onTurn` is the press on a tab.
 */
export function paneTabs(view: PaneView | null, waiting: number, onTurn: (to: TabId) => void): Tab[] {
  const shown = shownOf(view)
  const staying = TAB_IDS.map(id => ({
    label: id === 'proposals' && waiting > 0 ? `${LABELS[id]} ${waiting}` : LABELS[id],
    turn: id === shown ? null : { key: tabKey(id, shown), onPress: () => onTurn(id) },
  }))
  const aside = asideLabel(view)
  return aside === null ? staying : [...staying, { label: aside, turn: null }]
}
