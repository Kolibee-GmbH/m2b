import type { EngineInterface } from 'claude-code'

import { m2bHome } from './m2b'

/**
 * Every open session refreshes the band each minute. An answer another session wrote less than
 * this long ago is taken as it is, so the sessions together start m2b about once a minute.
 */
export const FRESH_FOR_MS = 55_000

const FOLDER = '.local/state/m2b'

type Entry = { writtenAtMs: number; value: unknown }

/**
 * `load()`'s answer, or the one any session stored under `kind` within `FRESH_FOR_MS`. A value
 * `isValid` refuses, a file that cannot be read and a write that fails all fall back to loading:
 * the cache saves calls, it never decides what the band shows.
 */
export async function shared<T>(
  $: EngineInterface,
  kind: string,
  load: () => Promise<T>,
  isValid: (value: unknown) => value is T,
  isForced = false,
): Promise<T> {
  const path = await cachePath($, kind)
  if (path === undefined) {
    return load()
  }
  if (!isForced) {
    const stored = await readEntry($, path)
    const ageMs = stored === undefined ? -1 : (await $.clock.now()) - stored.writtenAtMs
    if (stored !== undefined && ageMs >= 0 && ageMs < FRESH_FOR_MS && isValid(stored.value)) {
      return stored.value
    }
  }
  // Stamped with when the load started: an answer another session began later, after a keep or
  // drop, is never replaced by this older one, however long this load took.
  const startedAtMs = await $.clock.now()
  const value = await load()
  const latest = await readEntry($, path)
  if (latest !== undefined && latest.writtenAtMs > startedAtMs) {
    return value
  }
  try {
    await $.fs.write(path, JSON.stringify({ writtenAtMs: startedAtMs, value }))
  } catch {
    // No shared answer this time; the next refresh loads again.
  }
  return value
}

async function cachePath($: EngineInterface, kind: string): Promise<string | undefined> {
  const home = await m2bHome($)
  return home === undefined ? undefined : `${home}/${FOLDER}/band-${kind}.json`
}

async function readEntry($: EngineInterface, path: string): Promise<Entry | undefined> {
  try {
    const raw: unknown = JSON.parse(await $.fs.read(path))
    if (typeof raw === 'object' && raw !== null && 'writtenAtMs' in raw && typeof raw.writtenAtMs === 'number') {
      return { writtenAtMs: raw.writtenAtMs, value: 'value' in raw ? raw.value : undefined }
    }
  } catch {
    // Missing or not JSON: load instead.
  }
  return undefined
}
