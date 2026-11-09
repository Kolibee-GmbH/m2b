import { expect, test } from 'claude-code/testing'

import { isPartOn } from '../../hooks/parts'

test('a part is on only when m2b parts list names it with on: true', () => {
  const rows = JSON.stringify([
    { name: 'band', on: true, summary: 'x' },
    { name: 'backup', on: false, summary: 'y' },
  ])
  expect(isPartOn(rows, 'band')).toBe(true)
  expect(isPartOn(rows, 'backup')).toBe(false)
  expect(isPartOn(rows, 'herdr')).toBe(false)
  expect(isPartOn('not json', 'band')).toBe(false)
  expect(isPartOn(JSON.stringify({ band: true }), 'band')).toBe(false)
  expect(isPartOn(JSON.stringify([{ name: 'band', on: 'yes' }]), 'band')).toBe(false)
})
