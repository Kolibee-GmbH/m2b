import type { BandCandidate, BandReview } from '../types'

export class TaskJsonError extends Error {
  constructor() {
    super('m2b answered something other than a task list')
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

/** The open tasks in the output of `m2b tasks list --json`. */
function openTasks(stdout: string): TaskJson[] {
  let parsed: unknown
  try {
    parsed = JSON.parse(stdout)
  } catch {
    throw new TaskJsonError()
  }
  if (!Array.isArray(parsed) || !parsed.every(isTaskJson)) {
    throw new TaskJsonError()
  }
  return parsed.filter(task => !task.completed && !task.dropped)
}

export function parseCandidates(stdout: string): BandCandidate[] {
  return openTasks(stdout).map(({ id, title }) => ({ id, title }))
}

/**
 * The open review task with its findings: the paragraphs of its notes after the first, which
 * holds the marker line and the time of the run.
 */
export function parseReview(stdout: string): BandReview | null {
  const [review] = openTasks(stdout)
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
