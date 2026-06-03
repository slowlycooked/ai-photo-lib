import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getLatestObserverCallback, intersectingEntry, stubIntersectionObserver } from "@/test/intersectionObserver";

import { SearchResultGrid } from "./SearchResultGrid";
import type { SearchResultItem } from "@/api/types";

const useSearchMock = vi.fn();
const masonryMock = vi.fn();

vi.mock("@/hooks/useSearch", () => ({
  useSearch: (...args: unknown[]) => useSearchMock(...args),
}));

vi.mock("@/components/search/SearchResultMasonry", () => ({
  SearchResultMasonry: (props: { items: SearchResultItem[] }) => {
    masonryMock(props.items.map((item) => item.photo_id));
    return (
      <div data-testid="search-masonry">
        {props.items.map((item) => (
          <span key={item.photo_id}>photo-{item.photo_id}</span>
        ))}
      </div>
    );
  },
}));

vi.mock("@/components/search/SearchDebugPanel", () => ({
  SearchDebugPanel: () => <div data-testid="debug-panel" />,
}));

vi.mock("@/components/search/SearchPhotoLightbox", () => ({
  SearchPhotoLightbox: () => <div data-testid="lightbox" />,
}));

describe("SearchResultGrid", () => {
  beforeEach(() => {
    useSearchMock.mockReset();
    masonryMock.mockReset();
    stubIntersectionObserver();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("deduplicates search results with the same photo_id from different pages", () => {
    useSearchMock.mockReturnValue({
      data: {
        pages: [
          { total: 3, page: 1, page_size: 50, items: [{ photo_id: 1 }, { photo_id: 2 }] },
          { total: 3, page: 2, page_size: 50, items: [{ photo_id: 2 }, { photo_id: 3 }] },
        ],
      },
      fetchNextPage: vi.fn(),
      hasNextPage: false,
      isFetchingNextPage: false,
      isLoading: false,
      isError: false,
      error: null,
    });

    render(<SearchResultGrid query="海边" projectId={1} />);

    expect(screen.getByTestId("search-masonry")).toBeInTheDocument();
    expect(masonryMock).toHaveBeenCalledWith([1, 2, 3]);
  });

  it("prevents duplicate fetchNextPage calls while one is in flight", async () => {
    let resolveFetch = () => {};
    const fetchNextPage = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          resolveFetch = resolve;
        }),
    );

    useSearchMock.mockReturnValue({
      data: {
        pages: [{ total: 100, page: 1, page_size: 50, items: [{ photo_id: 1 }] }],
      },
      fetchNextPage,
      hasNextPage: true,
      isFetchingNextPage: false,
      isLoading: false,
      isError: false,
      error: null,
    });

    render(<SearchResultGrid query="海边" projectId={1} />);

    const callback = getLatestObserverCallback();
    expect(callback).not.toBeNull();

    callback!([intersectingEntry()], {} as IntersectionObserver);
    callback!([intersectingEntry()], {} as IntersectionObserver);

    expect(fetchNextPage).toHaveBeenCalledTimes(1);

    resolveFetch();
    await Promise.resolve();

    callback!([intersectingEntry()], {} as IntersectionObserver);
    expect(fetchNextPage).toHaveBeenCalledTimes(2);
  });
});
