import '@testing-library/jest-dom/vitest'

// jsdom doesn't implement scrollTo; ChatWindow calls it to keep the
// transcript pinned to the latest message.
if (!Element.prototype.scrollTo) {
  Element.prototype.scrollTo = () => {}
}
