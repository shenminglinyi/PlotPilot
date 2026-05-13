/**
 * 引导页「抽卡起名」：从扩展姓氏池 + 名库随机组合，刻意避开网文高频大姓。
 * 与后端命名守卫中的俗套姓集合对齐，便于用户一键换名。
 */
export const CLICHE_SURNAMES = new Set(['李', '王', '张', '刘', '陈', '杨', '林', '赵', '周', '吴'])

/** 复姓（权重略低，抽中更有「稀有卡」感） */
const COMPOUND_SURNAMES = [
  '欧阳',
  '司马',
  '上官',
  '诸葛',
  '慕容',
  '司徒',
  '司空',
  '尉迟',
  '公孙',
  '东方',
  '西门',
  '南宫',
  '皇甫',
  '令狐',
  '宇文',
  '长孙',
  '独孤',
  '端木',
  '濮阳',
  '轩辕',
  '即墨',
  '闻人',
  '申屠',
  '太叔',
  '呼延',
  '钟离',
  '澹台',
  '公冶',
  '宗政',
  '完颜',
  '耶律',
  '拓跋',
  '羊舌',
  '梁丘',
  '左丘',
  '谷梁',
  '乐正',
]

/** 单姓：真实存在、出现频率通常低于十大姓的池子（去重后枚举） */
const SINGLE_SURNAMES = [
  '顾', '苏', '沈', '萧', '裴', '荀', '喻', '柏', '水', '窦', '云', '狄', '贝', '明', '臧', '计', '伏', '茅', '庞', '纪', '舒', '屈', '祝', '阮', '蓝', '闵', '季', '路', '娄', '危', '童', '颜', '尹', '邵', '邹', '郝', '崔', '龚', '黎', '易', '武', '戴', '莫', '孔', '白', '常', '康', '傅', '严', '魏', '陶', '姜', '范', '叶', '余', '潘', '段', '贺', '毛', '江', '史', '侯', '倪', '覃', '温', '芦', '俞', '安', '梅', '辛', '管', '左', '薄', '宁', '柯', '桂', '柴', '车', '房', '边', '吉', '饶', '刁', '瞿', '戚', '丘', '米', '池', '滕', '佟', '言', '蔺', '栾', '冷', '訾', '阚', '茹', '逄', '夔', '郗', '隗', '鄂', '蓟', '蒲', '邰', '咸', '籍', '楼', '仇', '迟', '宦', '艾', '鱼', '容', '向', '古', '慎', '戈', '荆', '燕', '尚', '农', '迟', '宦', '郦', '雍', '却', '璩', '濮', '扈', '郏', '浦', '尚', '农', '逢', '步', '都', '耿', '满', '弘', '匡', '国', '文', '寇', '广', '禄', '阙', '东', '欧', '殳', '沃', '利', '蔚', '越', '夔', '隆', '师', '巩', '厍', '聂', '晁', '勾', '敖', '融', '訾', '辛', '阚', '那', '简', '饶', '空', '曾', '沙', '乜', '鞠', '须', '丰', '巢',   '关', '蒯', '相', '查', '后', '荆', '红', '游', '竺', '权', '逯', '盖', '益', '桓', '公',
]

function dedupeStrings(arr: string[]): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  for (const s of arr) {
    const t = s.trim()
    if (!t || seen.has(t)) continue
    seen.add(t)
    out.push(t)
  }
  return out
}

const SINGLE_POOL = dedupeStrings(SINGLE_SURNAMES).filter((s) => {
  if (s.length !== 1) return false
  return !CLICHE_SURNAMES.has(s[0]!)
})

const COMPOUND_POOL = dedupeStrings(COMPOUND_SURNAMES)

/** 单字名（配复姓或极短风格） */
const GIVEN_ONE = [
  '珩',
  '澈',
  '岚',
  '朔',
  '棠',
  '渊',
  '翎',
  '珂',
  '彧',
  '谌',
  '昀',
  '昫',
  '昭',
  '辞',
  '蕴',
  '咫',
  '恪',
  '衍',
  '濯',
  '翊',
  '珣',
  '琮',
  '璋',
  '璞',
  '筠',
  '霁',
  '凛',
  '骁',
  '韫',
]

/** 双字名（配单姓 → 三字名） */
const GIVEN_TWO = [
  '清渊',
  '景行',
  '知微',
  '望舒',
  '怀瑾',
  '若瑜',
  '云深',
  '雪舟',
  '听澜',
  '枕月',
  '临渊',
  '慕远',
  '书昀',
  '言蹊',
  '以宁',
  '则灵',
  '既白',
  '予安',
  '念卿',
  '栖迟',
  '停云',
  '漱石',
  '观澜',
  '问渠',
  '见鹿',
  '闻溪',
  '照夜',
  '衔青',
  '枕寒',
  '藏锋',
  '藏渊',
  '逐风',
  '逐影',
  '越尘',
  '越川',
  '凌洲',
  '渡舟',
  '泊远',
  '归鸿',
  '归鹤',
  '寄凡',
  '寄遥',
]

function pick<T>(arr: T[]): T {
  return arr[Math.floor(Math.random() * arr.length)]!
}

function shuffleInPlace<T>(arr: T[]): void {
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[arr[i], arr[j]] = [arr[j]!, arr[i]!]
  }
}

/**
 * 抽一张「完整姓名卡」：复姓约 22% 概率，否则单姓 + 双字名为主。
 * @param taken 已占用全名（当前书人物），尽量避免重复
 */
export function drawGachaFullName(taken: Set<string> = new Set()): string {
  const maxTry = 80
  for (let n = 0; n < maxTry; n++) {
    const compoundRoll = Math.random() < 0.22
    let name = ''
    if (compoundRoll) {
      const sur = pick(COMPOUND_POOL)
      const given = Math.random() < 0.55 ? pick(GIVEN_ONE) : pick(GIVEN_TWO)
      name = sur + given
    } else {
      const sur = pick(SINGLE_POOL)
      const given = Math.random() < 0.12 ? pick(GIVEN_ONE) : pick(GIVEN_TWO)
      name = sur + given
    }
    if (name.length < 2 || name.length > 4) continue
    const first = name[0]!
    if (CLICHE_SURNAMES.has(first)) continue
    if (taken.has(name)) continue
    return name
  }
  const sur = pick(SINGLE_POOL)
  const given = pick(GIVEN_TWO)
  return sur + given
}

/** 仅洗牌姓氏展示用（去重后的单姓+复姓扁平列表） */
export function allGachaSurnamesForDisplay(): string[] {
  const merged = [...COMPOUND_POOL, ...SINGLE_POOL]
  shuffleInPlace(merged)
  return merged
}
