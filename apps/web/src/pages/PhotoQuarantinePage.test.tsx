import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PhotoQuarantinePage } from "@/pages/PhotoQuarantinePage";

const getSettingsMock = vi.fn();
const listMock = vi.fn();
const restoreMock = vi.fn();
const requestDeleteMock = vi.fn();
const keepMock = vi.fn();
const batchMock = vi.fn();
const calibrationMock = vi.fn();
const taskListMock = vi.fn();
const startRunMock = vi.fn();
const cancelTaskMock = vi.fn();
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
        requestDelete: (...args: unknown[]) => requestDeleteMock(...args),
        keep: (...args: unknown[]) => keepMock(...args),
        batch: (...args: unknown[]) => batchMock(...args),
        getCalibration: (...args: unknown[]) => calibrationMock(...args),
        startRun: (...args: unknown[]) => startRunMock(...args),
      },
      projectTasks: {
        ...actual.api.projectTasks,
        list: (...args: unknown[]) => taskListMock(...args),
        cancel: (...args: unknown[]) => cancelTaskMock(...args),
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
    requestDeleteMock.mockResolvedValue({ ...item, status: "delete_queued", quarantine_path: null });
    keepMock.mockResolvedValue({ ...item, status: "kept", human_label: "KEEP" });
    batchMock.mockResolvedValue({ requested: 1, succeeded: 1, failed: 0, results: [] });
    calibrationMock.mockResolvedValue({
      labeled_total: 42,
      human_keep: 22,
      human_trash: 20,
      true_positive: 18,
      false_positive: 1,
      true_negative: 21,
      false_negative: 2,
      precision: 18 / 19,
      recall: 0.9,
      false_positive_rate: 1 / 22,
      target_sample_size: 300,
      minimum_per_label: 100,
      sample_target_met: false,
      class_balance_met: false,
      zero_false_positive_met: false,
      ready_for_auto_move: false,
      categories: [],
    });
    taskListMock.mockResolvedValue({ total: 0, items: [] });
    startRunMock.mockResolvedValue({
      id: 88,
      project_id: 1,
      task_type: "photo_quarantine_analysis",
      status: "queued",
      progress_payload: { running: false },
      result_payload: null,
      error_message: null,
    });
    cancelTaskMock.mockResolvedValue({
      id: 88,
      project_id: 1,
      task_type: "photo_quarantine_analysis",
      status: "running",
      progress_payload: { running: true, cancel_requested: true },
      result_payload: null,
      error_message: null,
    });
  });

  it("keeps start and stop scan controls visible while their enabled state changes", async () => {
    const user = userEvent.setup();
    const activeTask = {
      id: 88,
      project_id: 1,
      task_type: "photo_quarantine_analysis",
      status: "running",
      progress_payload: { running: true, analyzed: 1 },
      result_payload: null,
      error_message: null,
    };
    taskListMock
      .mockResolvedValueOnce({ total: 0, items: [] })
      .mockResolvedValue({ total: 1, items: [activeTask] });
    startRunMock.mockResolvedValue(activeTask);
    renderPage();

    const startButton = await screen.findByRole("button", { name: "启动扫描" });
    expect(screen.getByRole("button", { name: "停止扫描" })).toBeDisabled();
    await user.click(startButton);

    await waitFor(() => expect(startRunMock).toHaveBeenCalledWith(1));
    expect(await screen.findByRole("button", { name: "启动扫描" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "停止扫描" }));

    await waitFor(() => expect(cancelTaskMock).toHaveBeenCalledWith(1, 88));
    expect(await screen.findByRole("button", { name: "正在停止" })).toBeDisabled();
    expect(screen.getByText("正在停止分析，将在当前图片处理完成后退出")).toBeInTheDocument();
  });

  it("shows the recoverability guarantee and restores an item", async () => {
    const user = userEvent.setup();
    renderPage();

    expect(await screen.findByText(/页面只写入删除清单，不会移动或删除原片/)).toBeInTheDocument();
    expect(await screen.findByText("明显误触且没有可保留内容")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "放回原处" }));

    await waitFor(() => expect(restoreMock).toHaveBeenCalledWith(1, 7));
    expect(await screen.findByText("照片已安全放回原位置，并记为应保留")).toBeInTheDocument();
  });

  it("uses the server batch endpoint for selected restores", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("checkbox", { name: "选择审核项" }));
    await user.click(screen.getByRole("button", { name: "批量放回（1）" }));

    await waitFor(() => expect(batchMock).toHaveBeenCalledWith(1, "RESTORE", [7]));
    expect(await screen.findByText("已放回 1 张")).toBeInTheDocument();
  });

  it("selects and clears all actionable items on the current page", async () => {
    const user = userEvent.setup();
    listMock.mockResolvedValue({
      total: 2,
      items: [
        { ...item, id: 7, status: "review" },
        { ...item, id: 8, photo_id: 80, status: "analysis_failed" },
      ],
    });
    renderPage();

    await user.click(await screen.findByRole("button", { name: "全选当前页（2）" }));

    expect(screen.getByText("已选 2 张")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "批量保留（2）" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "批量提交删除（2）" })).toBeInTheDocument();
    for (const checkbox of screen.getAllByRole("checkbox", { name: "选择审核项" })) {
      expect(checkbox).toBeChecked();
    }

    await user.click(screen.getByRole("button", { name: "取消全选" }));

    expect(screen.queryByText("已选 2 张")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "批量保留（2）" })).not.toBeInTheDocument();
  });

  it("submits all selected approval items as one delete batch", async () => {
    const user = userEvent.setup();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    listMock.mockResolvedValue({
      total: 2,
      items: [
        { ...item, id: 7, status: "review" },
        { ...item, id: 8, photo_id: 80, status: "analysis_failed" },
      ],
    });
    renderPage();

    await user.click(await screen.findByRole("button", { name: "全选当前页（2）" }));
    await user.click(screen.getByRole("button", { name: "批量提交删除（2）" }));

    await waitFor(() => expect(batchMock).toHaveBeenCalledWith(
      1,
      "REQUEST_DELETE",
      [7, 8],
    ));
  });

  it("keeps failed batch items selected and names the failure", async () => {
    const user = userEvent.setup();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const reviewItems = [
      { ...item, id: 7, original_path: "/photos/IMG_2561.jpg", status: "review" },
      { ...item, id: 8, photo_id: 80, original_path: "/photos/DSC_2480.jpg", status: "analysis_failed" },
    ];
    listMock.mockResolvedValue({ total: 2, items: reviewItems });
    batchMock.mockResolvedValue({
      requested: 2,
      succeeded: 1,
      failed: 1,
      results: [
        {
          item_id: 7,
          succeeded: true,
          item: { ...reviewItems[0], status: "delete_queued" },
          error_code: null,
          message: null,
        },
        {
          item_id: 8,
          succeeded: false,
          item: null,
          error_code: "invalid_item",
          message: "Original file is missing",
        },
      ],
    });
    renderPage();

    await user.click(await screen.findByRole("button", { name: "全选当前页（2）" }));
    await user.click(screen.getByRole("button", { name: "批量提交删除（2）" }));

    expect(await screen.findByText(/DSC_2480\.jpg（Original file is missing）/)).toBeInTheDocument();
    const checkboxes = screen.getAllByRole("checkbox", { name: "选择审核项" });
    expect(checkboxes[0]).not.toBeChecked();
    expect(checkboxes[1]).toBeChecked();
  });

  it("can retry a queued item when its deletion manifest needs rebuilding", async () => {
    const user = userEvent.setup();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    listMock.mockResolvedValue({
      total: 1,
      items: [{ ...item, status: "delete_queued", quarantine_path: null }],
    });
    renderPage();

    await user.click(await screen.findByRole("checkbox", { name: "选择审核项" }));
    await user.click(screen.getByRole("button", { name: "批量重写删除清单（1）" }));

    await waitFor(() => expect(batchMock).toHaveBeenCalledWith(
      1,
      "REQUEST_DELETE",
      [7],
    ));
  });

  it("removes batch-approved deletions from the default pending view", async () => {
    const user = userEvent.setup();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const reviewItems = [
      { ...item, id: 7, status: "review" },
      { ...item, id: 8, photo_id: 80, status: "analysis_failed" },
    ];
    listMock
      .mockResolvedValueOnce({ total: 2, items: reviewItems })
      .mockImplementation(() => new Promise(() => undefined));
    batchMock.mockResolvedValue({
      requested: 2,
      succeeded: 2,
      failed: 0,
      results: reviewItems.map((reviewItem) => ({
        item_id: reviewItem.id,
        succeeded: true,
        item: { ...reviewItem, status: "delete_queued", human_label: "TRASH" },
        error_code: null,
        message: null,
      })),
    });
    renderPage();

    await user.click(await screen.findByRole("button", { name: "全选当前页（2）" }));
    await user.click(screen.getByRole("button", { name: "批量提交删除（2）" }));

    expect(await screen.findByText("当前筛选条件下没有图片。")).toBeInTheDocument();
    expect(screen.getByText("共 0 项")).toBeInTheDocument();
  });

  it("defaults to statuses that still need human handling", async () => {
    renderPage();

    await waitFor(() => expect(listMock).toHaveBeenCalled());
    const defaultStatuses = String(listMock.mock.calls[0][1]);
    expect(defaultStatuses).toContain("review");
    expect(defaultStatuses).toContain("analysis_failed");
    expect(defaultStatuses).not.toContain("delete_queued");
    expect(defaultStatuses).not.toContain("quarantined");
  });

  it("requests the next server page instead of loading every item", async () => {
    const user = userEvent.setup();
    listMock.mockImplementation((_projectId, _status, _limit, offset) =>
      Promise.resolve({ total: 25, items: offset === 0 ? [item] : [] }),
    );
    renderPage();

    await user.click(await screen.findByRole("button", { name: "下一页" }));

    await waitFor(() => expect(listMock).toHaveBeenCalledWith(1, expect.any(String), 24, 24, undefined));
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

  it("lets a human queue review-only screenshots for backend deletion", async () => {
    const user = userEvent.setup();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    listMock.mockResolvedValue({
      total: 1,
      items: [{ ...item, status: "review", decision: "REVIEW", classification: "screenshot" }],
    });
    renderPage();

    await user.click(await screen.findByRole("button", { name: "提交删除" }));

    await waitFor(() => expect(requestDeleteMock).toHaveBeenCalledWith(1, 7));
  });

  it("immediately removes a submitted deletion from the default pending view", async () => {
    const user = userEvent.setup();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    listMock
      .mockResolvedValueOnce({
        total: 1,
        items: [{ ...item, status: "review", decision: "REVIEW" }],
      })
      .mockImplementation(() => new Promise(() => undefined));
    renderPage();

    await user.click(await screen.findByRole("button", { name: "提交删除" }));

    expect(await screen.findByText("当前筛选条件下没有图片。")).toBeInTheDocument();
    expect(screen.getByText("共 0 项")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "提交删除" })).not.toBeInTheDocument();
  });

  it("renders queued deletion items with a prominent preview overlay", async () => {
    listMock.mockResolvedValue({
      total: 1,
      items: [{ ...item, status: "delete_queued", quarantine_path: null }],
    });
    renderPage();

    expect(await screen.findByLabelText("已提交删除，等待后台处理")).toBeInTheDocument();
    expect(screen.getByText("等待 NAS 后台处理")).toBeInTheDocument();
  });

  it("uses approval actions as the human labels", async () => {
    const user = userEvent.setup();
    listMock.mockResolvedValue({
      total: 1,
      items: [{ ...item, status: "review", human_label: null }],
    });
    renderPage();

    expect(await screen.findByText("42 / 300")).toBeInTheDocument();
    expect(screen.getByText("误删风险项").nextElementSibling).toHaveTextContent("1");
    expect(screen.queryByRole("button", { name: "仅标记应保留" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "仅标记垃圾" })).not.toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: "保留" }));

    await waitFor(() => expect(keepMock).toHaveBeenCalledWith(1, 7));
    expect(requestDeleteMock).not.toHaveBeenCalled();
  });

  it("offers both approval choices for an analysis failure", async () => {
    listMock.mockResolvedValue({
      total: 1,
      items: [{ ...item, status: "analysis_failed", human_label: null }],
    });
    renderPage();

    expect(await screen.findByRole("button", { name: "提交删除" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "保留" })).toBeInTheDocument();
  });

  it("requests only unlabelled calibration items", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.selectOptions(await screen.findByLabelText("人工标签筛选"), "UNLABELED");

    await waitFor(() => expect(listMock).toHaveBeenLastCalledWith(
      1,
      expect.any(String),
      24,
      0,
      "UNLABELED",
    ));
  });
});
