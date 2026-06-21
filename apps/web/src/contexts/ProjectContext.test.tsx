import { renderHook, act } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ProjectProvider, useProjectContext } from "./ProjectContext";

const projectListMock = vi.fn();
const useQueryMock = vi.fn();

vi.mock("@/api", async () => {
  const actual = await vi.importActual<typeof import("@/api")>("@/api");
  return {
    ...actual,
    api: {
      ...actual.api,
      projectCore: {
        ...actual.api.projectCore,
        list: (...args: unknown[]) => projectListMock(...args),
      },
    },
  };
});

vi.mock("@tanstack/react-query", async () => {
  const actual = await vi.importActual<typeof import("@tanstack/react-query")>("@tanstack/react-query");
  return {
    ...actual,
    useQuery: (...args: unknown[]) => useQueryMock(...args),
  };
});

function buildProject(id: number, name: string, isDefault = false) {
  return {
    id,
    name,
    description: null,
    photo_library_path: "/photos",
    thumbnail_path: "/thumbs",
    is_default: isDefault,
    created_at: "2026-06-21T00:00:00Z",
    updated_at: "2026-06-21T00:00:00Z",
  };
}

describe("ProjectProvider", () => {
  beforeEach(() => {
    projectListMock.mockReset();
    useQueryMock.mockReset();
  });

  it("refreshes the project list and drops revoked projects from the context", async () => {
    let queryData = {
      total: 2,
      items: [buildProject(1, "Default project", true), buildProject(2, "Revoked project")],
    };

    useQueryMock.mockImplementation((options: { queryKey?: unknown; refetchInterval?: number; refetchIntervalInBackground?: boolean }) => {
      projectListMock(options);
      return {
        data: queryData,
        isLoading: false,
      };
    });

    const wrapper = ({ children }: { children: ReactNode }) => (
      <ProjectProvider>{children}</ProjectProvider>
    );

    const { result, rerender } = renderHook(() => useProjectContext(), { wrapper });

    await act(async () => {
      await Promise.resolve();
    });

    expect(projectListMock.mock.calls.length).toBeGreaterThan(0);
    expect(useQueryMock.mock.calls[0]?.[0]).toMatchObject({
      refetchInterval: 30_000,
      refetchIntervalInBackground: true,
    });
    expect(result.current.projects.map((project) => project.id)).toEqual([1, 2]);
    expect(result.current.currentProjectId).toBe(1);

    queryData = {
      total: 1,
      items: [buildProject(1, "Default project", true)],
    };

    await act(async () => {
      rerender();
      await Promise.resolve();
    });

    expect(result.current.projects.map((project) => project.id)).toEqual([1]);
    expect(result.current.currentProjectId).toBe(1);
    expect(result.current.currentProject?.id).toBe(1);
  });
});