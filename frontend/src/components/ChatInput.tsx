import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import { Mic, Send } from 'lucide-react'

function getSpeechRecognition(): SpeechRecognitionLike | null {
  const Ctor = window.SpeechRecognition ?? window.webkitSpeechRecognition
  if (!Ctor) return null
  const recognition = new Ctor()
  recognition.lang = 'en-US'
  recognition.interimResults = false
  recognition.continuous = false
  return recognition
}

export function ChatInput({ onSend, disabled }: { onSend: (text: string) => void; disabled?: boolean }) {
  const [value, setValue] = useState('')
  const [listening, setListening] = useState(false)
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null)
  const speechSupported = typeof window !== 'undefined' && (window.SpeechRecognition ?? window.webkitSpeechRecognition) != null

  useEffect(() => {
    return () => recognitionRef.current?.stop()
  }, [])

  function submit() {
    if (!value.trim() || disabled) return
    onSend(value)
    setValue('')
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }

  function toggleDictation() {
    if (listening) {
      recognitionRef.current?.stop()
      return
    }
    const recognition = getSpeechRecognition()
    if (!recognition) return
    recognition.onresult = (event) => {
      const transcript = event.results[0][0].transcript
      setValue((current) => (current ? `${current} ${transcript}` : transcript))
    }
    recognition.onerror = () => setListening(false)
    recognition.onend = () => setListening(false)
    recognitionRef.current = recognition
    setListening(true)
    recognition.start()
  }

  return (
    <div className="shrink-0 border-t border-border bg-surface p-3">
      <div className="flex items-end gap-2 rounded-md border border-border bg-surface-2 px-3 py-2 focus-within:border-accent/50">
        <textarea
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={onKeyDown}
          rows={1}
          placeholder={listening ? 'Listening...' : 'Ask a market risk question...'}
          disabled={disabled}
          className="max-h-32 flex-1 resize-none bg-transparent text-sm text-text placeholder:text-text-faint focus:outline-none"
        />
        {speechSupported && (
          <button
            onClick={toggleDictation}
            disabled={disabled}
            aria-label={listening ? 'Stop dictation' : 'Start dictation'}
            aria-pressed={listening}
            className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-md transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${
              listening
                ? 'bg-danger/10 text-danger animate-pulse'
                : 'text-text-muted hover:bg-surface-hover hover:text-text'
            }`}
          >
            <Mic size={13} />
          </button>
        )}
        <button
          onClick={submit}
          disabled={disabled || !value.trim()}
          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-accent text-white transition-colors hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-40"
          aria-label="Send"
        >
          <Send size={13} />
        </button>
      </div>
    </div>
  )
}
