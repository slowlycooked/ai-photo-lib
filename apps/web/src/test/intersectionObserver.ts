import { vi } from "vitest";

export type ObserverCallback = (entries: IntersectionObserverEntry[], observer: IntersectionObserver) => void;

let latestObserverCallback: ObserverCallback | null = null;

class MockIntersectionObserver {
  private readonly callback: ObserverCallback;

  constructor(callback: ObserverCallback) {
    this.callback = callback;
    latestObserverCallback = callback;
  }

  observe() {
    // noop
  }

  disconnect() {
    // noop
  }

  unobserve() {
    // noop
  }

  takeRecords() {
    return [];
  }

  trigger(entries: IntersectionObserverEntry[]) {
    this.callback(entries, this as unknown as IntersectionObserver);
  }
}

export function stubIntersectionObserver() {
  latestObserverCallback = null;
  vi.stubGlobal("IntersectionObserver", MockIntersectionObserver as unknown as typeof IntersectionObserver);
}

export function getLatestObserverCallback() {
  return latestObserverCallback;
}

export function intersectingEntry(): IntersectionObserverEntry {
  return {
    isIntersecting: true,
    target: document.createElement("div"),
    boundingClientRect: {} as DOMRectReadOnly,
    intersectionRatio: 1,
    intersectionRect: {} as DOMRectReadOnly,
    rootBounds: null,
    time: Date.now(),
  };
}
