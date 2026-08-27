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

  it("uses each returned cursor once when fetching more photos", async () => {
    photosMock.mockImplementation((...args: unknown[]) => {
      const pageSize = args[2] as number;
      const cursor = args[8] as string | null;
      const logicalPage = cursor === null ? 1 : cursor === "cursor-2" ? 2 : 3;
      return Promise.resolve({
        total: 500,
        page: logicalPage,
        page_size: pageSize,
        items: buildItems(logicalPage, pageSize),
        next_cursor: logicalPage < 3 ? `cursor-${logicalPage + 1}` : null,
        has_more: logicalPage < 3,
      });
    });

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

    expect(photosMock.mock.calls.map((call) => call[7])).toEqual(["cursor", "cursor", "cursor"]);
    expect(photosMock.mock.calls.map((call) => call[8])).toEqual([null, "cursor-2", "cursor-3"]);
  });

  it("stops requesting next pages when the backend clears has_more", async () => {
    photosMock.mockImplementation((...args: unknown[]) => {
      const pageSize = args[2] as number;
      const cursor = args[8] as string | null;
      const logicalPage = cursor === null ? 1 : 2;
      return Promise.resolve({
        total: 70,
        page: logicalPage,
        page_size: pageSize,
        items: logicalPage === 1 ? buildItems(1, 50) : buildItems(2, 20),
        next_cursor: logicalPage === 1 ? "cursor-2" : null,
        has_more: logicalPage === 1,
      });
    });

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

    expect(photosMock.mock.calls.map((call) => call[8])).toEqual([null, "cursor-2"]);
  });

  it("starts from the located offset page and continues with nearby pages", async () => {
    photosMock.mockImplementation((...args: unknown[]) => {
      const page = args[1] as number;
      const pageSize = args[2] as number;
      return Promise.resolve({
        total: 210,
        page,
        page_size: pageSize,
        items: buildItems(page, pageSize),
        next_cursor: null,
        has_more: null,
      });
    });

    const { result } = renderHook(
      () => usePhotos({
        projectId: 1,
        folderId: 10,
        folderScope: "direct",
        initialPage: 3,
      }),
      { wrapper: createQueryClientWrapper().wrapper },
    );

    await waitFor(() => expect(result.current.data?.pages.length).toBe(1));
    await act(async () => {
      await result.current.fetchNextPage();
    });

    expect(photosMock.mock.calls.map((call) => call[1])).toEqual([3, 4]);
    expect(photosMock.mock.calls.map((call) => call[7])).toEqual(["offset", "offset"]);
    expect(photosMock.mock.calls.map((call) => call[8])).toEqual([null, null]);
  });
});
