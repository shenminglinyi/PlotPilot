/**
 * 将 shared/taxonomy/builtin_cn_v1.yaml 解析为 JSON，供 Vite/TypeScript 静态 import。
 * 权威格式为 YAML；JSON 仅为前端打包用的生成物。
 * 脚本放在 frontend/ 下以便解析 devDependency `yaml`。
 */
import { readFileSync, writeFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { parse } from 'yaml'

const checkOnly = process.argv.includes('--check')
const __dirname = dirname(fileURLToPath(import.meta.url))
const repoRoot = resolve(__dirname, '..', '..')
const targets = [
  {
    src: resolve(repoRoot, 'shared/taxonomy/builtin_cn_v1.yaml'),
    out: resolve(repoRoot, 'frontend/src/domain/taxonomy/builtin_cn_v1.bundle.json'),
    label: 'taxonomy',
  },
  {
    src: resolve(repoRoot, 'shared/taxonomy/worldbuilding_contract_cn_v1.yaml'),
    out: resolve(repoRoot, 'frontend/src/domain/worldbuilding/contract.bundle.json'),
    label: 'worldbuilding-contract',
  },
]

for (const target of targets) {
  const doc = parse(readFileSync(target.src, 'utf8'))
  const next = `${JSON.stringify(doc, null, 2)}\n`
  if (checkOnly) {
    const current = readFileSync(target.out, 'utf8')
    if (current !== next) {
      console.error(`[sync:${target.label}] stale bundle`, target.out)
      process.exitCode = 1
    } else {
      console.log(`[sync:${target.label}] up to date`, target.out)
    }
  } else {
    writeFileSync(target.out, next, 'utf8')
    console.log(`[sync:${target.label}] wrote`, target.out)
  }
}
