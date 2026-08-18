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

// Web Speech API — not part of TS's default DOM lib, and only the two
// vendor-prefixed constructors exist in shipping browsers.
interface SpeechRecognitionResultLike {
  0: { transcript: string }
}
interface SpeechRecognitionEventLike extends Event {
  results: ArrayLike<SpeechRecognitionResultLike>
}
interface SpeechRecognitionLike extends EventTarget {
  lang: string
  interimResults: boolean
  continuous: boolean
  start(): void
  stop(): void
  onresult: ((event: SpeechRecognitionEventLike) => void) | null
  onerror: (() => void) | null
  onend: (() => void) | null
}
interface Window {
  SpeechRecognition?: new () => SpeechRecognitionLike
  webkitSpeechRecognition?: new () => SpeechRecognitionLike
}
