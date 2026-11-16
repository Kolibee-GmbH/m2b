import type { BandCandidate, BandChangePart, BandDueTask, BandFactChange, BandPlace, BandReview, BandShows } from '../types'

export class TaskJsonError extends Error {
  constructor() {
    super('m2b answered something other than the band\'s task lists')
    this.name = 'TaskJsonError'
  }
}

type TaskJson = {
  id: string
  title: string
  notes: string
  completed: boolean
  dropped: boolean
}

function isTaskJson(value: unknown): value is TaskJson {
  if (typeof value !== 'object' || value === null) {
    return false
  }
  const task = value as Record<string, unknown>
  return (
    typeof task['id'] === 'string' &&
    typeof task['title'] === 'string' &&
    typeof task['notes'] === 'string' &&
    typeof task['completed'] === 'boolean' &&
    typeof task['dropped'] === 'boolean'
  )
}

/** The open tasks of one list in the answer of `m2b band --json`. */
function openTasks(list: unknown): TaskJson[] {
  if (!Array.isArray(list) || !list.every(isTaskJson)) {
    throw new TaskJsonError()
  }
  return list.filter(task => !task.completed && !task.dropped)
}

export function parseCandidates(list: unknown): BandCandidate[] {
  return openTasks(list).map(({ id, title }) => ({ id, title }))
}

/**
 * The open review task with its findings: the paragraphs of its notes after the first, which
 * holds the marker line and the time of the run.
 */
export function parseReview(list: unknown, details?: unknown): BandReview | null {
  const [review] = openTasks(list)
  if (review === undefined) {
    return null
  }
  const findings = review.notes
    .split(/\n\s*\n/)
    .slice(1)
    .map(paragraph => paragraph.trim())
    .filter(paragraph => paragraph !== '')
  if (!isObject(details) || !Array.isArray(details['changes'])) {
    return { id: review.id, title: review.title, findings }
  }
  const copies = Array.isArray(details['copies']) ? details['copies'].map(copyOf) : []
  return {
    id: review.id,
    title: review.title,
    findings,
    told: Array.isArray(details['paragraphs']) ? details['paragraphs'].filter(isString) : [],
    changes: details['changes'].filter(isObject).map(factChange),
    copies: copies.filter(copy => copy !== null),
  }
}

/** The findings that are drawn as written: those no change or copy stands for. */
export function untoldFindings(review: BandReview): string[] {
  const told = new Set(review.told ?? [])
  return review.findings.filter(finding => !told.has(finding))
}

function factChange(change: Record<string, unknown>): BandFactChange {
  const parts = Array.isArray(change['parts']) ? change['parts'].filter(isObject) : []
  return {
    kind: String(change['kind'] ?? ''),
    file: String(change['file'] ?? ''),
    topic: String(change['topic'] ?? change['file'] ?? ''),
    parts: parts.map(part => ({ text: String(part['text'] ?? ''), change: changeOf(part['change']) })),
  }
}

function changeOf(value: unknown): BandChangePart['change'] {
  return value === 'added' || value === 'removed' ? value : 'same'
}

function copyOf(value: unknown): { path: string; captures: number } | null {
  if (!isObject(value) || typeof value['path'] !== 'string') {
    return null
  }
  return { path: value['path'], captures: Array.isArray(value['captures']) ? value['captures'].length : 0 }
}

function isString(value: unknown): value is string {
  return typeof value === 'string'
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/** The tasks due today or overdue; undefined when the part is absent: not known, which is not none due. */
export function parseDue(list: unknown): BandDueTask[] | undefined {
  if (list === undefined) {
    return undefined
  }
  return openTasks(list).map(task => ({ id: task.id, title: task.title, overdue: isOverdue(task) }))
}

function isOverdue(task: TaskJson): boolean {
  return (task as Record<string, unknown>)['overdue'] === true
}

/** The task part of `m2b band --json`: the band's rows, or the reason the task list could not be read. */
export function parseBandTasks(
  part: unknown,
): { candidates: BandCandidate[]; review: BandReview | null; due: BandDueTask[] | undefined } | string {
  if (typeof part !== 'object' || part === null) {
    throw new TaskJsonError()
  }
  const fields = part as Record<string, unknown>
  if (typeof fields['error'] === 'string') {
    return fields['error']
  }
  return {
    // Whether a current item still holds is answered the same way as a candidate: keep or drop.
    candidates: [...parseCandidates(fields['candidates']), ...parseCandidates(fields['questions'])],
    review: parseReview(fields['reviews'], fields['review']),
    // A core before the three ways to show them names the tasks under `due`, and only while they are shown.
    due: parseDue(fields['due_by_today'] ?? fields['due']),
  }
}

/** What the band shows where the answer it draws from names no settings: what a machine without an entry shows. */
export const SHOWS_BY_DEFAULT: BandShows = { place: 'above', dueTasks: 'count', topics: false }

const PLACES: readonly BandPlace[] = ['above', 'below', 'waiting']
const DUE_TASKS_SHOWN: readonly BandShows['dueTasks'][] = ['off', 'count', 'list']

/**
 * The `band` part of `m2b band --json`, the machine's settings of that name; undefined where a
 * core before the part answered, or one of its values is none this band knows. A core before the
 * band's place names none: there the band stands where a machine without an entry has it.
 */
export function parseBandShows(part: unknown): BandShows | undefined {
  if (!isObject(part)) {
    return undefined
  }
  const place = part['place'] === undefined ? SHOWS_BY_DEFAULT.place : PLACES.find(known => known === part['place'])
  const dueTasks = DUE_TASKS_SHOWN.find(shown => shown === part['due_tasks'])
  const topics = part['topics']
  return place === undefined || dueTasks === undefined || typeof topics !== 'boolean' ? undefined : { place, dueTasks, topics }
}
