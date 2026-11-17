import type { PaneView } from '../types'
import { factFileNameOf, factTabLabel } from './facts-tab'
import { sourceLabelOf } from './source-view'
import { topicLabel } from './look'
import type { Tab } from './look'
import { topicShowKey } from './session-view'
import { topicNameOf } from './topic'
import type { SessionModel } from './session-view'

/*
 * The tabs above every view of the m2b pane: six that stay, always in one order, and a seventh for
 * a topic's lines, a fact's file, a search or the settings that only inform, which stands there only while it is
 * shown. A source a fact rests on stands under an eighth, beside the seventh that bears its fact
 * file and leads back to it. A tab is the one way from a view to another, so no view has a button
 * that leads back.
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
 * The key of the tab the focus is asked for once a press turned the pane from `left` to `to`: the
 * tab that leads back to the view that was left. The same key pressed again returns there, and the
 * focus never stands on a button that writes. The seventh tab is gone once it is left: `Overview`
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
 * the view `left`. A topic left for the start view has a way back of its own there, the button
 * that bears its name, where `model` has the start view draw it; every other turn follows the
 * tabs' rule.
 */
export function focusKeyAfterTab(left: PaneView | null, to: TabId, model: SessionModel): string {
  const show = to === 'overview' && left?.kind === 'topic' ? topicShowKey(model, topicNameOf(left.press)) : null
  return show ?? tabKeyAfterTurn(shownOf(left), to)
}

function asideLabel(view: PaneView | null): string | null {
  if (view?.kind === 'topic') {
    return topicLabel(topicNameOf(view.press))
  }
  if (view?.kind === 'fact') {
    return factTabLabel(factFileNameOf(view.press))
  }
  if (view?.kind === 'settings' && view.aside !== null) {
    return topicLabel(view.aside.title)
  }
  return view?.kind === 'search' ? SEARCH : null
}

/** The key of the tab that leads from a source back to the fact file it was shown from; no other view draws it. */
export const BACK_TO_THE_FACT_FILE_KEY = 'tab:fact:in:source'

/**
 * The pane's tabs above `view`. `waiting` is how many proposals wait: the tab counts them, and a
 * zero is not said. `onTurn` is the press on a tab, `onBack` the press on the tab of the fact file
 * a source was shown from.
 */
export function paneTabs(view: PaneView | null, waiting: number, onTurn: (to: TabId) => void, onBack: (from: string) => void): Tab[] {
  const shown = shownOf(view)
  const staying = TAB_IDS.map(id => ({
    label: id === 'proposals' && waiting > 0 ? `${LABELS[id]} ${waiting}` : LABELS[id],
    turn: id === shown ? null : { key: tabKey(id, shown), onPress: () => onTurn(id) },
  }))
  if (view?.kind === 'source') {
    const from = view.from
    return [
      ...staying,
      { label: factTabLabel(factFileNameOf(from)), turn: { key: BACK_TO_THE_FACT_FILE_KEY, onPress: () => onBack(from) } },
      { label: sourceLabelOf(view.press), turn: null },
    ]
  }
  const aside = asideLabel(view)
  return aside === null ? staying : [...staying, { label: aside, turn: null }]
}
