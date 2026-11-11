import type { BandCandidate, BandDueTask, BandReview } from '../types'

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
export function parseReview(list: unknown): BandReview | null {
  const [review] = openTasks(list)
  if (review === undefined) {
    return null
  }
  const findings = review.notes
    .split(/\n\s*\n/)
    .slice(1)
    .map(paragraph => paragraph.trim())
    .filter(paragraph => paragraph !== '')
  return { id: review.id, title: review.title, findings }
}

/** The tasks due today or overdue; none when the part is absent, as with `band.due_tasks` off. */
export function parseDue(list: unknown): BandDueTask[] {
  if (list === undefined) {
    return []
  }
  return openTasks(list).map(task => ({ id: task.id, title: task.title, overdue: isOverdue(task) }))
}

function isOverdue(task: TaskJson): boolean {
  return (task as Record<string, unknown>)['overdue'] === true
}

/** The task part of `m2b band --json`: the band's rows, or the reason the task list could not be read. */
export function parseBandTasks(
  part: unknown,
): { candidates: BandCandidate[]; review: BandReview | null; due: BandDueTask[] } | string {
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
    review: parseReview(fields['reviews']),
    due: parseDue(fields['due']),
  }
}
