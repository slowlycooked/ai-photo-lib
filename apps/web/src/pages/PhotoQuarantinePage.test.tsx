import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PhotoQuarantinePage } from "@/pages/PhotoQuarantinePage";

const getSettingsMock = vi.fn();
const listMock = vi.fn();
const restoreMock = vi.fn();
const batchMock = vi.fn();
const taskListMock = vi.fn();
const setCurrentProjectIdMock = vi.fn();

vi.mock("@/api", async () => {
  const actual = await vi.importActual<typeof import("@/api")>("@/api");
  return {
    ...actual,
    api: {
      ...actual.api,
      photoQuarantine: {
        ...actual.api.photoQuarantine,
        getSettings: (...args: unknown[]) => getSettingsMock(...args),
        list: (...args: unknown[]) => listMock(...args),
        restore: (...args: unknown[]) => restoreMock(...args),
        batch: (...args: unknown[]) => batchMock(...args),
      },
      projectTasks: {
        ...actual.api.projectTasks,
        list: (...args: unknown[]) => taskListMock(...args),
      },
    },
  };
});

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ session: { role: "project_manager" } }),
}));

vi.mock("@/contexts/ProjectContext", () => ({
  useProjectContext: () => ({
    projects: [{ id: 1, name: "家庭照片" }],
    currentProjectId: 1,
    setCurrentProjectId: setCurrentProjectIdMock,
  }),
}));

const item = {
  id: 7,
  project_id: 1,
  photo_id: 70,
  status: "quarantined",
  decision: "QUARANTINE",
  classification: "accidental_capture",
  confidence: 0.995,
  reason: "明显误触且没有可保留内容",
  preservation_flags: [],
  first_result: {},
  verification_result: {},
  model_name: "qwen3.8:27b",
  prompt_version: "photo-quarantine-v1",
  original_path: "/photos/2026/IMG_007.jpg",
  quarantine_path: "/tobetrash/project-1/2026-08-24/7/IMG_007.jpg",
  content_hash: "abc",
  moved_at: "2026-08-24T01:00:00Z",
  restored_at: null,
  deleted_confirmed_at: null,
  last_error: null,
  created_at: "2026-08-24T01:00:00Z",
  updated_at: "2026-08-24T01:00:00Z",
};

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/projects/1/photo-quarantine"]}>
        <Routes>
          <Route path="/projects/:projectId/photo-quarantine" element={<PhotoQuarantinePage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("PhotoQuarantinePage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getSettingsMock.mockResolvedValue({
      id: 1,
      project_id: 1,
      enabled: true,
      dry_run: true,
      start_hour: 1,
      end_hour: 6,
      timezone: "Asia/Shanghai",
      model_name: "qwen3.8:27b",
      retention_days: 30,
      created_at: "2026-08-24T00:00:00Z",
      updated_at: "2026-08-24T00:00:00Z",
    });
    listMock.mockResolvedValue({ total: 1, items: [item] });
    restoreMock.mockResolvedValue({ ...item, status: "restored" });
    batchMock.mockResolvedValue({ requested: 1, succeeded: 1, failed: 0, results: [] });
    taskListMock.mockResolvedValue({ total: 0, items: [] });
  });

  it("shows the recoverability guarantee and restores an item", async () => {
    const user = userEvent.setup();
    renderPage();

    expect(await screen.findByText("系统只移动文件，不会永久删除；放回时绝不覆盖原位置已有文件。")).toBeInTheDocument();
    expect(await screen.findByText("明显误触且没有可保留内容")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "放回原处" }));

    await waitFor(() => expect(restoreMock).toHaveBeenCalledWith(1, 7));
    expect(await screen.findByText("照片已安全放回原位置")).toBeInTheDocument();
  });

  it("uses the server batch endpoint for selected restores", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("checkbox", { name: "选择审核项" }));
    await user.click(screen.getByRole("button", { name: "批量放回（1）" }));

    await waitFor(() => expect(batchMock).toHaveBeenCalledWith(1, "RESTORE", [7]));
    expect(await screen.findByText("已放回 1 张")).toBeInTheDocument();
  });

  it("requests the next server page instead of loading every item", async () => {
    const user = userEvent.setup();
    listMock.mockImplementation((_projectId, _status, _limit, offset) =>
      Promise.resolve({ total: 25, items: offset === 0 ? [item] : [] }),
    );
    renderPage();

    await user.click(await screen.findByRole("button", { name: "下一页" }));

    await waitFor(() => expect(listMock).toHaveBeenCalledWith(1, expect.any(String), 24, 24));
    expect(await screen.findByText("第 2 / 2 页")).toBeInTheDocument();
  });

  it("shows progress from the latest quarantine task", async () => {
    taskListMock.mockResolvedValue({
      total: 1,
      items: [{
        id: 88,
        project_id: 1,
        task_type: "photo_quarantine_analysis",
        status: "running",
        progress_payload: { analyzed: 12, review: 3 },
        result_payload: null,
        error_message: null,
      }],
    });
    renderPage();

    expect(await screen.findByText(/最近分析任务：running · 已分析 12 张 · 待审核 3 张/)).toBeInTheDocument();
  });
});
