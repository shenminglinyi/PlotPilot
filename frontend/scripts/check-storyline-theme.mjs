import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const projectRoot = resolve(import.meta.dirname, '..')
const mainCss = readFileSync(resolve(projectRoot, 'src/assets/styles/main.css'), 'utf8')
const storylinePanel = readFileSync(resolve(projectRoot, 'src/components/workbench/StorylinePanel.vue'), 'utf8')

const checks = [
  {
    description: 'main.css exposes theme-safe text color aliases',
    pass:
      mainCss.includes('--text-color-1: var(--app-text-primary);') &&
      mainCss.includes('--text-color-2: var(--app-text-secondary);') &&
      mainCss.includes('--text-color-3: var(--app-text-muted);'),
  },
  {
    description: 'StorylinePanel uses theme-aware hover colors instead of hard-coded indigo',
    pass:
      storylinePanel.includes('border-color: var(--color-brand-border') &&
      storylinePanel.includes('box-shadow: 0 6px 18px var(--color-brand-light'),
  },
  {
    description: 'StorylinePanel info rows use a resilient two-column grid layout',
    pass:
      storylinePanel.includes('grid-template-columns: 88px minmax(0, 1fr);') &&
      storylinePanel.includes('@media (max-width: 640px)'),
  },
]

const failedChecks = checks.filter((check) => !check.pass)

if (failedChecks.length > 0) {
  console.error('Storyline theme regression checks failed:')
  for (const check of failedChecks) {
    console.error(`- ${check.description}`)
  }
  process.exit(1)
}

console.log('Storyline theme regression checks passed.')
