import { create } from 'zustand'
import type { ChatMessage, ChatSession, OpenArtifact } from '../types/chat'

const TITLE_MAX_LEN = 40

function newSessionId(): string {
  return crypto.randomUUID()
}

function newSession(): ChatSession {
  return { title: 'New chat', messages: [], pending: null, startedAt: Date.now(), titled: false }
}

interface ChatStore {
  chats: Record<string, ChatSession>
  activeChatId: string
  openArtifact: OpenArtifact | null

  newChat: () => void
  switchChat: (id: string) => void
  clearActiveChat: () => void
  openArtifactPanel: (ref: OpenArtifact) => void
  closeArtifactPanel: () => void

  appendMessage: (message: ChatMessage) => void
  setPending: (pending: ChatSession['pending']) => void
  setProvisionalTitle: (title: string) => void
  setTitle: (title: string) => void
  markTitled: () => void
  popLastMessage: () => ChatMessage | undefined
}

const firstId = newSessionId()

export const useChatStore = create<ChatStore>((set, get) => ({
  chats: { [firstId]: newSession() },
  activeChatId: firstId,
  openArtifact: null,

  newChat: () => {
    const id = newSessionId()
    set((state) => ({
      chats: { ...state.chats, [id]: newSession() },
      activeChatId: id,
      openArtifact: null,
    }))
  },

  switchChat: (id) => set({ activeChatId: id, openArtifact: null }),

  clearActiveChat: () =>
    set((state) => ({
      chats: { ...state.chats, [state.activeChatId]: newSession() },
      openArtifact: null,
    })),

  openArtifactPanel: (ref) => set({ openArtifact: ref }),
  closeArtifactPanel: () => set({ openArtifact: null }),

  appendMessage: (message) =>
    set((state) => {
      const chat = state.chats[state.activeChatId]
      return {
        chats: {
          ...state.chats,
          [state.activeChatId]: { ...chat, messages: [...chat.messages, message] },
        },
      }
    }),

  setPending: (pending) =>
    set((state) => {
      const chat = state.chats[state.activeChatId]
      return { chats: { ...state.chats, [state.activeChatId]: { ...chat, pending } } }
    }),

  // Caller is responsible for only calling this on the chat's first turn
  // (see useSend's `wasFirstTurn`, captured before any message is appended —
  // by the time this runs, the turn's messages already exist in the chat).
  setProvisionalTitle: (title) =>
    set((state) => {
      const chat = state.chats[state.activeChatId]
      const truncated = title.length > TITLE_MAX_LEN ? `${title.slice(0, TITLE_MAX_LEN)}…` : title
      return { chats: { ...state.chats, [state.activeChatId]: { ...chat, title: truncated } } }
    }),

  setTitle: (title) =>
    set((state) => {
      const chat = state.chats[state.activeChatId]
      return { chats: { ...state.chats, [state.activeChatId]: { ...chat, title } } }
    }),

  markTitled: () =>
    set((state) => {
      const chat = state.chats[state.activeChatId]
      return { chats: { ...state.chats, [state.activeChatId]: { ...chat, titled: true } } }
    }),

  popLastMessage: () => {
    const state = get()
    const chat = state.chats[state.activeChatId]
    const last = chat.messages.at(-1)
    set({
      chats: {
        ...state.chats,
        [state.activeChatId]: { ...chat, messages: chat.messages.slice(0, -1) },
      },
    })
    return last
  },
}))
