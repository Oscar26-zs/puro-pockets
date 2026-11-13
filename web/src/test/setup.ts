import * as matchers from "@testing-library/jest-dom/matchers"

// Se extiende el `expect` global (con `globals: true`)
expect.extend(matchers)
// Con `globals: true`, Testing Library limpia el DOM después de cada prueba.

// jsdom no trae ResizeObserver ni matchMedia (Recharts y el tema los usan)
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??= ResizeObserverStub as unknown as typeof ResizeObserver
if (typeof window.matchMedia !== "function") {
  window.matchMedia = (query: string) =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }) as MediaQueryList
}
