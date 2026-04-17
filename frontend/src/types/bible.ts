/**
 * Bible / 世界观设定相关类型
 */

export interface BibleCharacter {
  name: string
  role: string
  traits: string
  arc_note: string
}

export interface BibleLocation {
  name: string
  description: string
}

export interface Bible {
  characters: BibleCharacter[]
  locations: BibleLocation[]
  timeline_notes: string[]
  style_notes: string
}
