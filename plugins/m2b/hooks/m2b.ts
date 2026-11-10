import type { EngineInterface } from 'claude-code'

export type M2bOutcome = { ok: true; stdout: string } | { ok: false; error: string }

const LAUNCHER = '.local/bin/m2b'

/**
 * The folder the core puts its machine paths under, resolved as the core resolves it: `M2B_HOME`
 * when set, with a leading `~` meaning the home folder, else the home folder. The core falls back
 * to the account's home when `HOME` is unset; the module cannot look that up and answers undefined.
 */
export async function m2bHome($: EngineInterface): Promise<string | undefined> {
  const userHome = withoutTrailingSlash(await $.env.get('HOME'))
  const override = await $.env.get('M2B_HOME')
  if (!override) {
    return userHome
  }
  if (override === '~' || override.startsWith('~/')) {
    return userHome === undefined ? undefined : withoutTrailingSlash(userHome + override.slice(1))
  }
  return withoutTrailingSlash(override)
}

function withoutTrailingSlash(path: string | undefined): string | undefined {
  return path ? path.replace(/\/+$/, '') || '/' : undefined
}

const MACHINE_CONFIG = '.config/m2b/config.json'

/** The machine config the core reads; it exists once m2b is set up on this machine. */
export async function machineConfigPath($: EngineInterface): Promise<string | undefined> {
  const home = await m2bHome($)
  return home === undefined ? undefined : `${home}/${MACHINE_CONFIG}`
}

export async function launcherPath($: EngineInterface): Promise<string | undefined> {
  const home = await m2bHome($)
  return home === undefined ? undefined : `${home}/${LAUNCHER}`
}

/** Runs `m2b <args>`; a failure of any kind comes back as one line of text, never as a rejection. */
export async function runM2b(
  $: EngineInterface,
  args: readonly string[],
  timeoutMs: number,
): Promise<M2bOutcome> {
  const launcher = await launcherPath($)
  if (launcher === undefined) {
    return { ok: false, error: 'neither M2B_HOME nor HOME is set' }
  }
  try {
    const { exitCode, stdout, stderr } = await $.process.run([launcher, ...args], { timeoutMs })
    if (exitCode === 0) {
      return { ok: true, stdout }
    }
    const reason = firstLine(stderr)?.replace(/^m2b: /, '')
    return { ok: false, error: reason ?? `m2b ${args.join(' ')} ended with exit ${exitCode}` }
  } catch (error) {
    return { ok: false, error: `could not run ${launcher}: ${firstLine(String(error)) ?? 'no reason given'}` }
  }
}

function firstLine(text: string): string | undefined {
  return text
    .split('\n')
    .map(line => line.trim())
    .find(line => line !== '')
}
