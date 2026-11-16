/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_DEV_STUDENT_TOKEN?: string
  readonly VITE_DEV_ADMIN_TOKEN?: string
  readonly VITE_DISABLE_DEV_AUTH?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<{}, {}, any>
  export default component
}
