import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createQueryClientWrapper } from "@/test/queryClient";

const searchMock = vi.fn();

vi.mock("@/api", async () => {
  const actual = await vi.importActual<typeof import("@/api")>("@/api");
  return {
    ...actual,
    api: {
      ...actual.api,
      projects: {
        ...actual.api.projects,
        search: (...args: unknown[]) => searchMock(...args),
      },
    },
  };
});

import { useSearch } from "@/hooks/useSearch";

function buildItems(page: number, count: number) {
  return Array.from({ length: count }, (_, index) => ({
    photo_id: (page - 1) * 50 + index + 1,
  })) as any[];
}

describe("useSearch", () => {
  beforeEach(() => {
    searchMock.mockReset();
  });

  it("uses requested page params to avoid repeated page fetches", async () => {
    searchMock.mockImplementation((_projectId: number, _query: string, page: number, pageSize: number) =>
      Promise.resolve({
        total: 500,
        page: 1,
        page_size: pageSize,
        items: buildItems(page, pageSize),
      }),
    );

    const { result } = renderHook(() => useSearch("海边", 1), {
      wrapper: createQueryClientWrapper().wrapper,
    });

    await waitFor(() => {
      expect(result.current.data?.pages.length).toBe(1);
    });

    await act(async () => {
      await result.current.fetchNextPage();
    });
    await act(async () => {
      await result.current.fetchNextPage();
    });

    await waitFor(() => {
      expect(result.current.data?.pages.length).toBe(3);
    });

    const requestedPages = searchMock.mock.calls.map((call) => call[2]);
    expect(requestedPages).toEqual([1, 2, 3]);
  });

  it("stops requesting next pages when the last page is shorter than page_size", async () => {
    searchMock.mockImplementation((_projectId: number, _query: string, page: number, pageSize: number) =>
      Promise.resolve({
        total: 70,
        page,
        page_size: pageSize,
        items: page === 1 ? buildItems(page, 50) : buildItems(page, 20),
      }),
    );

    const { result } = renderHook(() => useSearch("海边", 1), {
      wrapper: createQueryClientWrapper().wrapper,
    });

    await waitFor(() => {
      expect(result.current.data?.pages.length).toBe(1);
    });

    await act(async () => {
      await result.current.fetchNextPage();
    });

    await waitFor(() => {
      expect(result.current.data?.pages.length).toBe(2);
      expect(result.current.hasNextPage).toBe(false);
    });

    const requestedPages = searchMock.mock.calls.map((call) => call[2]);
    expect(requestedPages).toEqual([1, 2]);
  });
});
