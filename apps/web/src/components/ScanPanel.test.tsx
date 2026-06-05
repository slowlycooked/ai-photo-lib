import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";

import { ScanPanel } from "./ScanPanel";
import type { ScanStatus } from "@/api";

const taskFailuresMock = vi.fn();

vi.mock("@/api", async () => {
  const actual = await vi.importActual<typeof import("@/api")>("@/api");
  return {
    ...actual,
    api: {
      ...actual.api,
      projectTasks: {
        ...actual.api.projectTasks,
        failures: (...args: unknown[]) => taskFailuresMock(...args),
      },
    },
  };
});

function buildStatus(overrides: Partial<ScanStatus> = {}): ScanStatus {
  return {
    task_id: 21,
    running: false,
    scanned: 10,
    inserted: 1,
    updated: 2,
    errors: 0,
    current_path: null,
    message: "done",
    recent_errors: [],
    recent_files: [],
    ...overrides,
  };
}

describe("ScanPanel", () => {
  it("shows unified failure details for finished scans with errors", async () => {
    taskFailuresMock.mockResolvedValue({
      total: 1,
      items: [
        {
          key: "file_progress:result_payload:/tmp/a/bad.jpg:2026-01-01T00:00:00+00:00:decode failed",
          source: "file_progress",
          message: "decode failed",
          path: "/tmp/a/bad.jpg",
          status: "failed",
          timestamp: "2026-01-01T00:00:00Z",
          details: { payload: "result_payload" },
        },
      ],
    });

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <ScanPanel
          projectId={7}
          status={buildStatus({
            errors: 1,
            recent_errors: ["bad.jpg: decode failed"],
          })}
          isLoading={false}
          onStart={vi.fn()}
          isPending={false}
        />
      </QueryClientProvider>,
    );

    expect(screen.getByText("扫描完成（含错误）")).toBeInTheDocument();
    expect(await screen.findByText("扫描失败明细")).toBeInTheDocument();
    expect(screen.getByText("path=/tmp/a/bad.jpg")).toBeInTheDocument();
  });

  it("shows completed-with-errors when a finished scan has errors", () => {
    taskFailuresMock.mockResolvedValue({ total: 0, items: [] });
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <ScanPanel
          projectId={7}
          status={buildStatus({
            errors: 1,
            recent_errors: ["bad.jpg: decode failed"],
          })}
          isLoading={false}
          onStart={vi.fn()}
          isPending={false}
        />
      </QueryClientProvider>,
    );

    expect(screen.getByText("扫描完成（含错误）")).toBeInTheDocument();
  });
});
