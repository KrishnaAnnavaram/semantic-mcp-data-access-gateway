import { create } from 'zustand'

export type Theme = 'light' | 'dark'

const STORAGE_KEY = 'smcp-gateway-theme'

// Renaming a storage key silently orphans everything saved under the old one,
// so anyone who had chosen dark mode would open the app in light and have to
// choose again. Read the old key once, then let the new one take over.
const LEGACY_STORAGE_KEY = 'vantage-theme'

function readInitialTheme(): Theme {
  const stored = localStorage.getItem(STORAGE_KEY)
                 ?? localStorage.getItem(LEGACY_STORAGE_KEY)
  return stored === 'dark' ? 'dark' : 'light'
}

function applyTheme(theme: Theme) {
  document.documentElement.dataset.theme = theme
  localStorage.setItem(STORAGE_KEY, theme)
}

interface ThemeStore {
  theme: Theme
  toggleTheme: () => void
}

export const useThemeStore = create<ThemeStore>((set, get) => ({
  theme: readInitialTheme(),
  toggleTheme: () => {
    const next: Theme = get().theme === 'light' ? 'dark' : 'light'
    applyTheme(next)
    set({ theme: next })
  },
}))

// Apply on module load so the correct theme is set before first paint.
applyTheme(useThemeStore.getState().theme)
