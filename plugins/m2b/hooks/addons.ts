/** Whether `m2b addons list --json` names `addon` as on; anything else it answers counts as off. */
export function isAddonOn(stdout: string, addon: string): boolean {
  let rows: unknown
  try {
    rows = JSON.parse(stdout)
  } catch {
    return false
  }
  return (
    Array.isArray(rows) &&
    rows.some(row => typeof row === 'object' && row !== null && row.name === addon && row.on === true)
  )
}
