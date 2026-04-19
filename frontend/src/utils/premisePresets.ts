/**
 * 从 novels.premise 解析建档时写入的前缀：
 * `【类型：…；世界观基调：…】`（可与后端 premise_genre_world.py 对照）
 */
export function parseGenreWorldFromPremise(fullPremise: string): {
  genre: string
  worldPreset: string
} {
  const raw = (fullPremise || '').trim()
  if (!raw) return { genre: '', worldPreset: '' }

  // 全篇匹配（不要求独占一行；兼容中英文分号；允许块内换行）
  const full = /【类型：\s*([^】；]+?)\s*[；;]\s*世界观基调：\s*([^】]+?)\s*】/s.exec(raw)
  if (full) {
    return { genre: full[1].trim(), worldPreset: full[2].trim() }
  }

  const genreOnly = /【类型：\s*([^】]+?)\s*】/.exec(raw)
  if (genreOnly) {
    return { genre: genreOnly[1].trim(), worldPreset: '' }
  }

  // 无书名号（旧数据）
  const plain = /类型：\s*([^\n；;]+?)\s*[；;]\s*世界观基调：\s*([^\n]+)/.exec(raw)
  if (plain) {
    return { genre: plain[1].trim(), worldPreset: plain[2].trim() }
  }

  // 逐段（兼容「系统块」与「类型块」之间仅单个 \n）
  const blocks = raw.split(/\n+/).map((s) => s.trim()).filter(Boolean)
  for (const b of blocks) {
    if (/系统内部/.test(b) && /叙事结构规划/.test(b)) continue
    const lineFull = /^【类型：(.+?)；世界观基调：(.+?)】$/.exec(b)
    if (lineFull) {
      return { genre: lineFull[1].trim(), worldPreset: lineFull[2].trim() }
    }
    const lineSemi = /^【类型：(.+?)[;；]世界观基调：(.+?)】$/.exec(b)
    if (lineSemi) {
      return { genre: lineSemi[1].trim(), worldPreset: lineSemi[2].trim() }
    }
  }

  return { genre: '', worldPreset: '' }
}
