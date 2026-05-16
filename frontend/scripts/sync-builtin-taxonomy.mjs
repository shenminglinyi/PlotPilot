/**
 * 将 shared/taxonomy/builtin_cn_v1.yaml 解析为 JSON，供 Vite/TypeScript 静态 import。
 * 权威格式为 YAML；JSON 仅为前端打包用的生成物。
 * 脚本放在 frontend/ 下以便解析 devDependency `yaml`。
 */
import { readFileSync, writeFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { parse } from 'yaml'

const __dirname = dirname(fileURLToPath(import.meta.url))
const repoRoot = resolve(__dirname, '..', '..')
const src = resolve(repoRoot, 'shared/taxonomy/builtin_cn_v1.yaml')
const out = resolve(repoRoot, 'frontend/src/domain/taxonomy/builtin_cn_v1.bundle.json')

const doc = parse(readFileSync(src, 'utf8'))
writeFileSync(out, `${JSON.stringify(doc, null, 2)}\n`, 'utf8')
console.log('[sync:taxonomy] wrote', out)
