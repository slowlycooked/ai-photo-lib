import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { TasksPage } from "@/pages/TasksPage";

const tasksMock = vi.fn();
const taskFailuresMock = vi.fn();
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
    projects: {
      tasks: (...args: unknown[]) => tasksMock(...args),
      taskFailures: (...args: unknown[]) => taskFailuresMock(...args),
      getFaceSettings: (...args: unknown[]) => getFaceSettingsMock(...args),
      projectFaceScanStatus: (...args: unknown[]) => projectFaceScanStatusMock(...args),
      projectFaceClusterUnknownStatus: (...args: unknown[]) => projectFaceClusterUnknownStatusMock(...args),
      projectFaceRematchUnknownStatus: (...args: unknown[]) => projectFaceRematchUnknownStatusMock(...args),
      startProjectFaceScan: (...args: unknown[]) => startProjectFaceScanMock(...args),
      clusterUnknownFaces: (...args: unknown[]) => clusterUnknownFacesMock(...args),
      rematchUnknownFaces: (...args: unknown[]) => rematchUnknownFacesMock(...args),
      cancelProjectFaceScan: (...args: unknown[]) => cancelProjectFaceScanMock(...args),
      cancelClusterUnknownFaces: (...args: unknown[]) => cancelClusterUnknownFacesMock(...args),
      cancelRematchUnknownFaces: (...args: unknown[]) => cancelRematchUnknownFacesMock(...args),
      cancelTask: vi.fn(),
      pauseTask: vi.fn(),
      resumeTask: vi.fn(),
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
      max_faces: 1000,
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

  it("shows the canonical ai settings link and no embedded ai-settings tab", () => {
    renderPage();

    expect(screen.getByRole("link", { name: "打开项目 AI 配置" })).toHaveAttribute(
      "href",
      "/projects/7/settings/vision-ai",
    );
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

    expect(await screen.findByText("#12 · library_scan")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "详情" }));

    expect(await screen.findByText("失败明细")).toBeInTheDocument();
    expect(screen.getAllByText("scan exploded")).toHaveLength(2);
    expect(screen.getByText("path=/tmp/a/bad.jpg")).toBeInTheDocument();
    expect(screen.getByText("request_params")).toBeInTheDocument();
    expect(screen.getByText(/"scope": "all"/)).toBeInTheDocument();
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

    expect(await screen.findByText("#13 · library_scan")).toBeInTheDocument();
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
});
