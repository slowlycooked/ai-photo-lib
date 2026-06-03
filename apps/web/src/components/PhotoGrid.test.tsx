import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PhotoGrid } from "./PhotoGrid";

const usePhotosMock = vi.fn();
const photoCardMock = vi.fn();

type ObserverCallback = (entries: IntersectionObserverEntry[], observer: IntersectionObserver) => void;

let observerCallback: ObserverCallback | null = null;

vi.mock("@/hooks/usePhotos", () => ({
  usePhotos: (...args: unknown[]) => usePhotosMock(...args),
}));

vi.mock("./PhotoCard", () => ({
  PhotoCard: (props: { photo: { id: number } }) => {
    photoCardMock(props.photo.id);
    return <div data-testid="photo-card">photo-{props.photo.id}</div>;
  },
}));

class MockIntersectionObserver {
  private readonly callback: ObserverCallback;

  constructor(callback: ObserverCallback) {
    this.callback = callback;
    observerCallback = callback;
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

function intersectingEntry(): IntersectionObserverEntry {
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

describe("PhotoGrid", () => {
  beforeEach(() => {
    usePhotosMock.mockReset();
    photoCardMock.mockReset();
    observerCallback = null;
    vi.stubGlobal("IntersectionObserver", MockIntersectionObserver as unknown as typeof IntersectionObserver);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("deduplicates photos with the same id from different pages", () => {
    usePhotosMock.mockReturnValue({
      data: {
        pages: [
          { total: 3, page: 1, page_size: 50, items: [{ id: 1 }, { id: 2 }] },
          { total: 3, page: 2, page_size: 50, items: [{ id: 2 }, { id: 3 }] },
        ],
      },
      fetchNextPage: vi.fn(() => Promise.resolve()),
      hasNextPage: false,
      isFetchingNextPage: false,
      isLoading: false,
      isError: false,
    });

    render(<PhotoGrid />);

    const cards = screen.getAllByTestId("photo-card");
    expect(cards).toHaveLength(3);
    expect(photoCardMock).toHaveBeenCalledTimes(3);
  });

  it("prevents duplicate fetchNextPage calls while one is in flight", async () => {
    let resolveFetch = () => {};
    const fetchNextPage = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          resolveFetch = resolve;
        }),
    );

    usePhotosMock.mockReturnValue({
      data: {
        pages: [{ total: 100, page: 1, page_size: 50, items: [{ id: 1 }] }],
      },
      fetchNextPage,
      hasNextPage: true,
      isFetchingNextPage: false,
      isLoading: false,
      isError: false,
    });

    render(<PhotoGrid />);

    expect(observerCallback).not.toBeNull();
    const callback = observerCallback as ObserverCallback;

    callback([intersectingEntry()], {} as IntersectionObserver);
    callback([intersectingEntry()], {} as IntersectionObserver);

    expect(fetchNextPage).toHaveBeenCalledTimes(1);

    resolveFetch();
    await Promise.resolve();

    callback([intersectingEntry()], {} as IntersectionObserver);
    expect(fetchNextPage).toHaveBeenCalledTimes(2);
  });
});
