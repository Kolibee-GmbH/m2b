// Replays the bytes a terminal session drew into xterm.js in headless Chrome and saves a PNG.
// Usage: node render_terminal.mjs <recording> <png> <columns> <rows> <xterm package folder> <background>
//
// Adapted from .claude/skills/live-check/render.mjs of prismantis,
// https://github.com/NahumLitvin/prismantis, under the MIT License:
//
// Copyright (c) 2026 Nahum Litvin
//
// Permission is hereby granted, free of charge, to any person obtaining a copy
// of this software and associated documentation files (the "Software"), to deal
// in the Software without restriction, including without limitation the rights
// to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
// copies of the Software, and to permit persons to whom the Software is
// furnished to do so, subject to the following conditions:
//
// The above copyright notice and this permission notice shall be included in all
// copies or substantial portions of the Software.
//
// THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
// IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
// FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
// AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
// LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
// OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
// SOFTWARE.
import { execFileSync } from 'node:child_process'
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const [recording, png, columns, rows, xterm, background] = process.argv.slice(2)
const chrome = [
  process.env.CHROME,
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  '/Applications/Chromium.app/Contents/MacOS/Chromium',
  '/usr/bin/chromium',
  '/usr/bin/google-chrome',
].find((path) => path && existsSync(path))
if (!chrome) {
  console.error('render_terminal: no Chrome or Chromium found; set CHROME')
  process.exit(1)
}
const folder = mkdtempSync(join(tmpdir(), 'sb-test-render-'))
try {
  const page = join(folder, 'terminal.html')
  const bytes = readFileSync(recording).toString('base64')
  const script = readFileSync(join(xterm, 'lib/xterm.js'), 'utf8')
  const style = readFileSync(join(xterm, 'css/xterm.css'), 'utf8')
  writeFileSync(
    page,
    `<!doctype html><html><head><meta charset="utf-8"><style>${style} body{margin:0;background:${background}} #t{padding:12px;display:inline-block}</style></head>` +
      `<body><div id="t"></div><script>${script}</script><script>
const terminal = new Terminal({ cols: ${Number(columns)}, rows: ${Number(rows)}, fontFamily: 'Menlo, monospace', fontSize: 14, theme: { background: '${background}' } })
terminal.open(document.getElementById('t'))
terminal.write(Uint8Array.from(atob('${bytes}'), (c) => c.charCodeAt(0)))
</script></body></html>`,
  )
  execFileSync(
    chrome,
    [
      '--headless=new',
      '--disable-gpu',
      '--no-first-run',
      `--user-data-dir=${join(folder, 'profile')}`,
      '--hide-scrollbars',
      `--window-size=${Number(columns) * 9 + 30},${Number(rows) * 16 + 130}`,
      '--virtual-time-budget=4000',
      `--screenshot=${png}`,
      `file://${page}`,
    ],
    { stdio: 'ignore', timeout: 60000 },
  )
} catch (error) {
  console.error(`render_terminal: ${error.message}`)
  process.exitCode = 1
} finally {
  rmSync(folder, { recursive: true, force: true })
}
