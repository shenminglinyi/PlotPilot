type StorageArea = 'local' | 'session'

function getStorage(area: StorageArea): Storage | null {
  if (typeof window === 'undefined') return null
  try {
    return area === 'local' ? window.localStorage : window.sessionStorage
  } catch {
    return null
  }
}

export function readStorageString(key: string, fallback = '', area: StorageArea = 'local'): string {
  try {
    return getStorage(area)?.getItem(key) ?? fallback
  } catch {
    return fallback
  }
}

export function writeStorageString(key: string, value: string, area: StorageArea = 'local'): void {
  try {
    getStorage(area)?.setItem(key, value)
  } catch {
    /* ignore storage quota / privacy-mode failures */
  }
}

export function readStorageBoolean(key: string, fallback = false, area: StorageArea = 'local'): boolean {
  const raw = readStorageString(key, '', area)
  if (raw === 'true') return true
  if (raw === 'false') return false
  return fallback
}

export function writeStorageBoolean(key: string, value: boolean, area: StorageArea = 'local'): void {
  writeStorageString(key, String(value), area)
}

export function readStorageJson<T>(key: string, fallback: T, area: StorageArea = 'local'): T {
  const raw = readStorageString(key, '', area)
  if (!raw) return fallback
  try {
    return JSON.parse(raw) as T
  } catch {
    return fallback
  }
}

export function writeStorageJson(key: string, value: unknown, area: StorageArea = 'local'): void {
  writeStorageString(key, JSON.stringify(value), area)
}

export function removeStorageItem(key: string, area: StorageArea = 'local'): void {
  try {
    getStorage(area)?.removeItem(key)
  } catch {
    /* ignore */
  }
}
