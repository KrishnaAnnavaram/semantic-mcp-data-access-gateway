/// <reference types="vite/client" />

interface ImportMetaEnv {
  // Not marked readonly: Vitest stubs these directly on import.meta.env per test.
  VITE_AGENT_BACKEND?: string
  VITE_AGENT_API_URL?: string
  VITE_AGENT_TIMEOUT_SECONDS?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
