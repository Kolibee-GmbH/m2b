import { expect, test } from 'claude-code/testing'

import { isAddonOn } from '../../hooks/addons'

test('an add-on is on only when m2b addons list names it with on: true', () => {
  const rows = JSON.stringify([
    { name: 'band', on: true, summary: 'x' },
    { name: 'worklog', on: false, summary: 'y' },
  ])
  expect(isAddonOn(rows, 'band')).toBe(true)
  expect(isAddonOn(rows, 'worklog')).toBe(false)
  expect(isAddonOn(rows, 'garden')).toBe(false)
  expect(isAddonOn('not json', 'band')).toBe(false)
  expect(isAddonOn(JSON.stringify({ band: true }), 'band')).toBe(false)
  expect(isAddonOn(JSON.stringify([{ name: 'band', on: 'yes' }]), 'band')).toBe(false)
})
