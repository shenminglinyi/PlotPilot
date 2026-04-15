/// <reference types="vite/client" />

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<{}, {}, any>
  export default component
}

interface Window {
  $message?: {
    success: (content: string) => void
    error: (content: string) => void
    warning: (content: string) => void
    info: (content: string) => void
  }
}
