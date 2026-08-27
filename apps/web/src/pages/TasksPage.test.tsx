import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { TasksPage } from "@/pages/TasksPage";

const tasksMock = vi.fn();
const taskFailuresMock = vi.fn();
const aiStatusMock = vi.fn();
const startAiMock = vi.fn();
const reanalyzeMock = vi.fn();
const forceStopAiMock = vi.fn();
const getFaceSettingsMock = vi.fn();
const projectFaceScanStatusMock = vi.fn();
const projectFaceClusterUnknownStatusMock = vi.fn();
const projectFaceRematchUnknownStatusMock = vi.fn();
const startProjectFaceScanMock = vi.fn();
const clusterUnknownFacesMock = vi.fn();
const rematchUnknownFacesMock = vi.fn();
const cancelProjectFaceScanMock = vi.fn();
const cancelClusterUnknownFacesMock = vi.fn();
const cancelRematchUnknownFacesMock = vi.fn();
const useProjectContextMock = vi.fn();
const useScanStatusMock = vi.fn();
const useStartScanMock = vi.fn();
const useStartReindexMock = vi.fn();
const useCancelScanMock = vi.fn();

vi.mock("@/contexts/ProjectContext", () => ({
  useProjectContext: () => useProjectContextMock(),
}));

vi.mock("@/api", () => ({
  api: {
    projectAiJobs: {
      status: (...args: unknown[]) => aiStatusMock(...args),
      startAnalysis: (...args: unknown[]) => startAiMock(...args),
      reanalyze: (...args: unknown[]) => reanalyzeMock(...args),
      forceStop: (...args: unknown[]) => forceStopAiMock(...args),
      list: vi.fn().mockResolvedValue({ total: 0, items: [] }),
      retryFailed: vi.fn(),
      clearFailed: vi.fn(),
    },
    projectTasks: {
      list: (...args: unknown[]) => tasksMock(...args),
      failures: (...args: unknown[]) => taskFailuresMock(...args),
      cancel: vi.fn(),
      pause: vi.fn(),
      resume: vi.fn(),
    },
    projectFaces: {
      projectScanStatus: (...args: unknown[]) => projectFaceScanStatusMock(...args),
      clusterUnknownStatus: (...args: unknown[]) => projectFaceClusterUnknownStatusMock(...args),
      rematchUnknownStatus: (...args: unknown[]) => projectFaceRematchUnknownStatusMock(...args),
      startProjectScan: (...args: unknown[]) => startProjectFaceScanMock(...args),
      clusterUnknown: (...args: unknown[]) => clusterUnknownFacesMock(...args),
      rematchUnknown: (...args: unknown[]) => rematchUnknownFacesMock(...args),
      cancelProjectScan: (...args: unknown[]) => cancelProjectFaceScanMock(...args),
      cancelClusterUnknown: (...args: unknown[]) => cancelClusterUnknownFacesMock(...args),
      cancelRematchUnknown: (...args: unknown[]) => cancelRematchUnknownFacesMock(...args),
    },
    projectSettings: {
      getFace: (...args: unknown[]) => getFaceSettingsMock(...args),
    },
  },
}));

vi.mock("@/hooks/useScan", () => ({
  useScanStatus: (...args: unknown[]) => useScanStatusMock(...args),
  useStartScan: (...args: unknown[]) => useStartScanMock(...args),
  useStartReindex: (...args: unknown[]) => useStartReindexMock(...args),
  useCancelScan: (...args: unknown[]) => useCancelScanMock(...args),
}));

vi.mock("@/components/ScanPanel", () => ({
  ScanPanel: () => <div>Scan Panel</div>,
}));

function renderPage(initialEntry = "/tasks?tab=scan") {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path="/tasks" element={<TasksPage />} />
          <Route path="/photos" element={<div>Photos Page</div>} />
          <Route path="/projects/:projectId/settings/*" element={<div>Project AI Settings</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("TasksPage", () => {
  beforeEach(() => {
    tasksMock.mockReset();
    taskFailuresMock.mockReset();
    aiStatusMock.mockReset();
    startAiMock.mockReset();
    reanalyzeMock.mockReset();
    forceStopAiMock.mockReset();
    getFaceSettingsMock.mockReset();
    projectFaceScanStatusMock.mockReset();
    projectFaceClusterUnknownStatusMock.mockReset();
    projectFaceRematchUnknownStatusMock.mockReset();
    startProjectFaceScanMock.mockReset();
    clusterUnknownFacesMock.mockReset();
    rematchUnknownFacesMock.mockReset();
    cancelProjectFaceScanMock.mockReset();
    cancelClusterUnknownFacesMock.mockReset();
    cancelRematchUnknownFacesMock.mockReset();
    useProjectContextMock.mockReset();
    useScanStatusMock.mockReset();
    useStartScanMock.mockReset();
    useStartReindexMock.mockReset();
    useCancelScanMock.mockReset();

    useProjectContextMock.mockReturnValue({
      currentProjectId: 7,
      currentProject: { id: 7, name: "Project 7", is_default: true },
    });
    useScanStatusMock.mockReturnValue({ data: null, isLoading: false });
    useStartScanMock.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      error: null,
    });
    useStartReindexMock.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    });
    useCancelScanMock.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    });
    tasksMock.mockResolvedValue({ total: 0, items: [] });
    taskFailuresMock.mockResolvedValue({ total: 0, items: [] });
    aiStatusMock.mockResolvedValue({
      queued: 0,
      running: 0,
      success: 0,
      failed: 0,
      total: 0,
    });
    startAiMock.mockResolvedValue({ created_jobs: 0, message: "ok" });
    reanalyzeMock.mockResolvedValue({ created_jobs: 0, message: "ok" });
    forceStopAiMock.mockResolvedValue({
      stopped_jobs: 0,
      stopped_queued: 0,
      stopped_running: 0,
      message: "No active jobs to stop",
    });
    getFaceSettingsMock.mockResolvedValue({
      face_recognition_enabled: true,
      face_provider: "opencv",
      face_detector_model: "yunet",
      face_embedding_model: "sface",
      face_runtime: "cpu",
      min_face_size: 64,
      min_detection_confidence: 0.5,
    });
    projectFaceScanStatusMock.mockResolvedValue({
      queued: 0,
      running: 0,
      success: 0,
      failed: 0,
      total: 0,
      task_id: null,
      task_status: null,
    });
    projectFaceClusterUnknownStatusMock.mockResolvedValue({
      project_id: 7,
      task_id: null,
      status: "idle",
      running: false,
      max_faces: 500,
      clusters_created: 0,
      persons_created: 0,
      faces_clustered: 0,
      assignments_created: 0,
      errors: 0,
      recent_errors: [],
      message: "idle",
    });
    projectFaceRematchUnknownStatusMock.mockResolvedValue({
      project_id: 7,
      task_id: null,
      status: "idle",
      running: false,
      max_faces: 10000,
      scope: "unknown",
      person_id: null,
      start_time: null,
      end_time: null,
      faces_considered: 0,
      matched_faces: 0,
      auto_assigned: 0,
      review_pending: 0,
      errors: 0,
      recent_errors: [],
      message: "idle",
    });
    startProjectFaceScanMock.mockResolvedValue({});
    clusterUnknownFacesMock.mockResolvedValue({});
    rematchUnknownFacesMock.mockResolvedValue({});
    cancelProjectFaceScanMock.mockResolvedValue({});
    cancelClusterUnknownFacesMock.mockResolvedValue({});
    cancelRematchUnknownFacesMock.mockResolvedValue({});
  });

  it("does not show embedded ai-settings entry in task center", () => {
    renderPage();

    expect(screen.queryByRole("link", { name: "打开项目 AI 配置" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "AI 配置" })).not.toBeInTheDocument();
  });

  it("redirects legacy ai-settings task links to the canonical project settings route", () => {
    renderPage("/tasks?tab=ai-settings");

    expect(screen.getByText("Project AI Settings")).toBeInTheDocument();
  });

  it("falls back to photos page when legacy ai-settings links open without a current project", () => {
    useProjectContextMock.mockReturnValue({
      currentProjectId: null,
      currentProject: null,
    });

    renderPage("/tasks?tab=ai-settings");

    expect(screen.getByText("Photos Page")).toBeInTheDocument();
  });

  it("shows expandable project task diagnostics", async () => {
    const user = userEvent.setup();
    tasksMock.mockResolvedValue({
      total: 1,
      items: [
        {
          id: 12,
          project_id: 7,
          task_type: "library_scan",
          status: "failed",
          retry_count: 1,
          request_params: { scope: "all" },
          progress_payload: { message: "failed" },
          result_payload: null,
          error_message: "scan exploded",
          recent_errors: ["bad.jpg: decode failed", "scan exploded"],
          failure_count: 2,
          latest_failure: {
            key: "task_error:12:0",
            source: "task_error",
            message: "scan exploded",
            path: null,
            status: "failed",
            timestamp: "2026-01-01T00:00:01Z",
            details: { task_status: "failed" },
          },
          started_at: null,
          finished_at: null,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:01Z",
        },
      ],
    });
    taskFailuresMock.mockResolvedValue({
      total: 2,
      items: [
        {
          key: "task_error:12:0",
          source: "task_error",
          message: "scan exploded",
          path: null,
          status: "failed",
          timestamp: "2026-01-01T00:00:01Z",
          details: { task_status: "failed" },
        },
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

    renderPage();

    expect(await screen.findByText("#12 · 照片扫描")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /最近任务状态/ })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /任务类型分布/ })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "详情" }));

    expect(await screen.findByText("失败明细")).toBeInTheDocument();
    expect(screen.getAllByText("scan exploded")).toHaveLength(2);
    expect(screen.getByText("path=/tmp/a/bad.jpg")).toBeInTheDocument();
    const technicalDetails = screen.getByText("技术数据").closest("details");
    expect(technicalDetails).not.toHaveAttribute("open");
    await user.click(screen.getByText("技术数据"));
    expect(technicalDetails).toHaveAttribute("open");
    expect(screen.getByText("request_params")).toBeInTheDocument();
    expect(screen.getByText(/"scope": "all"/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "需关注" }));
    expect(screen.getByText("#12 · 照片扫描")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "已完成" }));
    expect(screen.queryByText("#12 · 照片扫描")).not.toBeInTheDocument();
    expect(screen.getByText("当前筛选下暂无任务。")).toBeInTheDocument();
  });

  it("shows resume action for paused project tasks", async () => {
    tasksMock.mockResolvedValue({
      total: 1,
      items: [
        {
          id: 13,
          project_id: 7,
          task_type: "library_scan",
          status: "paused",
          retry_count: 0,
          request_params: {},
          progress_payload: { message: "paused" },
          result_payload: null,
          error_message: null,
          recent_errors: [],
          failure_count: 0,
          latest_failure: null,
          started_at: null,
          finished_at: null,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:01Z",
        },
      ],
    });

    renderPage();

    expect(await screen.findByText("#13 · 照片扫描")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "恢复" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "取消" })).toBeInTheDocument();
  });

  it("explains project task history 404 as an api upgrade hint", async () => {
    tasksMock.mockRejectedValue(new Error("Not Found"));

    renderPage();

    expect(await screen.findByText("任务历史接口暂不可用")).toBeInTheDocument();
    expect(screen.getByText(/当前 API 进程可能还没重启/)).toBeInTheDocument();
  });

  it("shows unified failure details in face cluster status cards", async () => {
    projectFaceClusterUnknownStatusMock.mockResolvedValue({
      project_id: 7,
      task_id: 55,
      status: "failed",
      running: false,
      max_faces: 500,
      clusters_created: 2,
      persons_created: 1,
      faces_clustered: 20,
      assignments_created: 10,
      errors: 1,
      recent_errors: ["cluster exploded"],
      message: "cluster exploded",
    });
    taskFailuresMock.mockResolvedValue({
      total: 1,
      items: [
        {
          key: "task_error:55:0",
          source: "task_error",
          message: "cluster exploded",
          path: null,
          status: "failed",
          timestamp: "2026-01-01T00:00:00Z",
          details: { task_status: "failed" },
        },
      ],
    });

    renderPage("/tasks?tab=face-scan");

    expect(await screen.findByText("未知人脸聚类任务 · failed")).toBeInTheDocument();
    expect(await screen.findByText("聚类失败明细")).toBeInTheDocument();
    expect(screen.getAllByText("cluster exploded").length).toBeGreaterThanOrEqual(2);
  });

  it("starts a project-wide face rematch into labeled people", async () => {
    const user = userEvent.setup();
    rematchUnknownFacesMock.mockResolvedValue({
      message: "queued",
      status: {
        project_id: 7,
        task_id: 77,
        status: "queued",
        running: true,
        max_faces: 10000,
        scope: "project",
        person_id: null,
        start_time: null,
        end_time: null,
        faces_considered: 0,
        matched_faces: 0,
        auto_assigned: 0,
        review_pending: 0,
        errors: 0,
        recent_errors: [],
        message: "queued",
      },
    });

    renderPage("/tasks?tab=face-scan");

    expect(await screen.findByLabelText("全项目聚合 max_faces")).toHaveValue(10000);
    await user.click(await screen.findByRole("button", { name: "聚合到已打标人物" }));

    expect(rematchUnknownFacesMock).toHaveBeenCalledWith(7, {
      scope: "project",
      max_faces: 10000,
    });
    expect(await screen.findByText("已提交全项目已打标人物聚合任务（max_faces=10000）")).toBeInTheDocument();
  });

  it("uses the configured project-wide face rematch max_faces value", async () => {
    const user = userEvent.setup();
    rematchUnknownFacesMock.mockResolvedValue({
      message: "queued",
      status: {
        project_id: 7,
        task_id: 78,
        status: "queued",
        running: true,
        max_faces: 2500,
        scope: "project",
        person_id: null,
        start_time: null,
        end_time: null,
        faces_considered: 0,
        matched_faces: 0,
        auto_assigned: 0,
        review_pending: 0,
        errors: 0,
        recent_errors: [],
        message: "queued",
      },
    });

    renderPage("/tasks?tab=face-scan");

    const maxFacesInput = await screen.findByLabelText("全项目聚合 max_faces");
    await user.clear(maxFacesInput);
    await user.type(maxFacesInput, "2500");
    await user.click(await screen.findByRole("button", { name: "聚合到已打标人物" }));

    expect(rematchUnknownFacesMock).toHaveBeenCalledWith(7, {
      scope: "project",
      max_faces: 2500,
    });
    expect(await screen.findByText("已提交全项目已打标人物聚合任务（max_faces=2500）")).toBeInTheDocument();
  });

  it("can force-stop ai analyze jobs from tasks page", async () => {
    const user = userEvent.setup();
    aiStatusMock.mockResolvedValue({
      queued: 2,
      running: 1,
      success: 0,
      failed: 0,
      total: 3,
    });
    forceStopAiMock.mockResolvedValue({
      stopped_jobs: 3,
      stopped_queued: 2,
      stopped_running: 1,
      message: "Active jobs force-stopped",
    });
    vi.spyOn(window, "confirm").mockReturnValue(true);

    renderPage("/tasks?tab=ai");

    await user.click(await screen.findByRole("button", { name: "强制停止分析" }));

    expect(forceStopAiMock).toHaveBeenCalledWith(7, "analyze,reanalyze");
    expect(await screen.findByText("已强制停止 3 个任务（queued=2, running=1）")).toBeInTheDocument();
  });
});
