import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { getLatestObserverCallback, intersectingEntry, stubIntersectionObserver } from "@/test/intersectionObserver";

import { SearchResultGrid } from "./SearchResultGrid";
import { SearchCard } from "./search/SearchCard";
import type { SearchResultItem } from "@/api/types";

const useSearchMock = vi.fn();
const masonryMock = vi.fn();

vi.mock("@/hooks/useSearch", () => ({
  useSearch: (...args: unknown[]) => useSearchMock(...args),
}));

vi.mock("@/components/search/SearchResultMasonry", () => ({
  SearchResultMasonry: (props: {
    items: SearchResultItem[];
    onPreview: (item: SearchResultItem) => void;
  }) => {
    masonryMock(props.items.map((item) => item.photo_id));
    return (
      <div data-testid="search-masonry">
        {props.items.map((item) => (
          <button key={item.photo_id} onClick={() => props.onPreview(item)}>
            photo-{item.photo_id}
          </button>
        ))}
      </div>
    );
  },
}));

vi.mock("@/components/search/SearchDebugPanel", () => ({
  SearchDebugPanel: () => <div data-testid="debug-panel" />,
}));

vi.mock("@/components/search/SearchPhotoLightbox", () => ({
  SearchPhotoLightbox: ({ onDeleted }: { onDeleted?: () => void }) => (
    <button data-testid="lightbox" onClick={onDeleted}>delete-photo</button>
  ),
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

  it("removes a deleted photo from the current search results", () => {
    useSearchMock.mockReturnValue({
      data: {
        pages: [{ total: 2, page: 1, page_size: 50, items: [{ photo_id: 1 }, { photo_id: 2 }] }],
      },
      fetchNextPage: vi.fn(),
      hasNextPage: false,
      isFetchingNextPage: false,
      isLoading: false,
      isError: false,
      error: null,
    });

    render(<SearchResultGrid query="海边" projectId={1} />);

    fireEvent.click(screen.getByText("photo-1"));
    fireEvent.click(screen.getByTestId("lightbox"));

    expect(screen.queryByText("photo-1")).not.toBeInTheDocument();
    expect(screen.getByText("photo-2")).toBeInTheDocument();
    expect(screen.getByText(/共找到/)).toHaveTextContent("1 张照片");
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

describe("SearchCard", () => {
  it("links a result back to its photo-library location", () => {
    const item = {
      photo_id: 42,
      file_name: "beach.jpg",
      thumbnail_url: "/thumbnail.jpg",
      updated_at: "2026-08-26T00:00:00Z",
      taken_at: null,
      width: 400,
      height: 300,
      caption: null,
      matched_tags: [],
      score: 1,
    } satisfies SearchResultItem;

    render(
      <MemoryRouter>
        <SearchCard item={item} />
      </MemoryRouter>,
    );

    expect(
      screen.getByRole("link", { name: "在原文件夹中查看 beach.jpg" }),
    ).toHaveAttribute("href", "/photos?photo_id=42");
  });
});
