import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createQueryClientWrapper } from "@/test/queryClient";

const photosMock = vi.fn();

vi.mock("@/api", async () => {
  const actual = await vi.importActual<typeof import("@/api")>("@/api");
  return {
    ...actual,
    api: {
      ...actual.api,
      projectPhotos: {
        ...actual.api.projectPhotos,
        list: (...args: unknown[]) => photosMock(...args),
      },
    },
  };
});

import { usePhotos } from "@/hooks/usePhotos";

function buildItems(page: number, count: number) {
  return Array.from({ length: count }, (_, index) => ({
    id: (page - 1) * 50 + index + 1,
  })) as any[];
}

describe("usePhotos", () => {
  beforeEach(() => {
    photosMock.mockReset();
  });

  it("uses requested page params to avoid repeated page fetches", async () => {
    photosMock.mockImplementation((_projectId: number, page: number, pageSize: number) =>
      Promise.resolve({
        total: 500,
        // Simulate a backend that incorrectly echoes page=1 in every response.
        page: 1,
        page_size: pageSize,
        items: buildItems(page, pageSize),
      }),
    );

    const { result } = renderHook(() => usePhotos({ projectId: 1 }), {
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

    const requestedPages = photosMock.mock.calls.map((call) => call[1]);
    expect(requestedPages).toEqual([1, 2, 3]);
  });

  it("stops requesting next pages when last page is shorter than page_size", async () => {
    photosMock.mockImplementation((_projectId: number, page: number, pageSize: number) =>
      Promise.resolve({
        total: 70,
        page,
        page_size: pageSize,
        items: page === 1 ? buildItems(page, 50) : buildItems(page, 20),
      }),
    );

    const { result } = renderHook(() => usePhotos({ projectId: 1 }), {
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

    const requestedPages = photosMock.mock.calls.map((call) => call[1]);
    expect(requestedPages).toEqual([1, 2]);
  });
});
