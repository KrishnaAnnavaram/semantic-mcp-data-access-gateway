import '@testing-library/jest-dom/vitest'

// jsdom doesn't implement scrollTo; ChatWindow calls it to keep the
// transcript pinned to the latest message.
if (!Element.prototype.scrollTo) {
  Element.prototype.scrollTo = () => {}
}

// React Flow (the GRAPH tab) measures the pane with ResizeObserver and reads
// prefers-color-scheme via matchMedia; jsdom implements neither. Polyfill both
// so components that mount the graph can be tested without a real browser.
if (typeof globalThis.ResizeObserver === 'undefined') {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver
}

if (typeof window !== 'undefined' && !window.matchMedia) {
  window.matchMedia = (query: string) =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }) as unknown as MediaQueryList
}
