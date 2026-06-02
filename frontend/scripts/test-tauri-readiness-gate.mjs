import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

const __dirname = dirname(fileURLToPath(import.meta.url))
const configSource = readFileSync(resolve(__dirname, '../src/api/config.ts'), 'utf8')
const mainSource = readFileSync(resolve(__dirname, '../src/main.ts'), 'utf8')

assert.match(
  configSource,
  /TAURI_BACKEND_WAIT_MS\s*=\s*120_000/,
  'Tauri API initialization should wait up to 120s, matching Rust wait_for_ready(port, 120).',
)

assert.match(
  configSource,
  /waitForTauriBackendReady/,
  'Tauri API initialization should use a backend readiness helper, not only a port helper.',
)

assert.doesNotMatch(
  configSource,
  /后端健康检查异常/,
  'Tauri health check failures must not be logged and ignored before app mount.',
)

assert.doesNotMatch(
  configSource,
  /127\.0\.0\.1:8005\/api\/v1/,
  'Tauri startup must not fall back to a guessed 8005 API base URL after IPC/readiness failure.',
)

assert.match(
  mainSource,
  /renderStartupFailure/,
  'Startup should render a static failure message instead of mounting first-screen API consumers.',
)

assert.match(
  mainSource,
  /return\s*\n\s*}/,
  'Bootstrap should stop before app.mount() when initApiClient() fails.',
)

console.log('Tauri readiness gate checks passed')
