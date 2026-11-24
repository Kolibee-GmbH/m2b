import { isObject } from './facts-tab'

/*
 * What `m2b capture --json` answers, read in one place for the note tool and `/m2b-note`.
 */

/** In the reason of a failed capture with a follow-up whose note was written but whose task is not confirmed. */
export const CAPTURED_BUT_TASK_UNCONFIRMED = ' was captured, but its follow-up task'

/** `followUp` is a follow-up that waits for ingest; once its task is made, the day is not in it. */
export type Saved = { path: string; taskId: string | null; followUp: string | null }

/** What `m2b capture --json` answered, or undefined for an answer this mod cannot read. */
export function parseCapture(stdout: string): Saved | undefined {
  let answer: unknown
  try {
    answer = JSON.parse(stdout)
  } catch {
    return undefined
  }
  if (!isObject(answer) || typeof answer['path'] !== 'string') {
    return undefined
  }
  const taskId = typeof answer['task_id'] === 'string' ? answer['task_id'] : null
  const followUp = typeof answer['follow_up'] === 'string' ? answer['follow_up'] : null
  return { path: answer['path'], taskId, followUp }
}

/**
 * What a saved capture also said on standard error, as a follow-up that waits for the next run:
 * each line without the `m2b: ` the core puts before it, cleaned by `clean`, empty lines left out.
 */
export function notices(stderr: string, clean: (line: string) => string): string[] {
  return stderr
    .split('\n')
    .map(line => clean(line.replace(/^m2b: /, '')).trim())
    .filter(line => line !== '')
}
