/** Whether `m2b parts list --json` names `part` as on; anything else it answers counts as off. */
export function isPartOn(stdout: string, part: string): boolean {
  let rows: unknown
  try {
    rows = JSON.parse(stdout)
  } catch {
    return false
  }
  return (
    Array.isArray(rows) &&
    rows.some(row => typeof row === 'object' && row !== null && row.name === part && row.on === true)
  )
}
