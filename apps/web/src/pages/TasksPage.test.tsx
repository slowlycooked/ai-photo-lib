import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { TasksPage } from "@/pages/TasksPage";

const useProjectContextMock = vi.fn();
const useScanStatusMock = vi.fn();
const useStartScanMock = vi.fn();
const useStartReindexMock = vi.fn();

vi.mock("@/contexts/ProjectContext", () => ({
  useProjectContext: () => useProjectContextMock(),
}));

vi.mock("@/hooks/useScan", () => ({
  useScanStatus: (...args: unknown[]) => useScanStatusMock(...args),
  useStartScan: (...args: unknown[]) => useStartScanMock(...args),
  useStartReindex: (...args: unknown[]) => useStartReindexMock(...args),
}));

vi.mock("@/components/ScanPanel", () => ({
  ScanPanel: () => <div>Scan Panel</div>,
}));

function renderPage(initialEntry = "/tasks?tab=scan") {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route path="/tasks" element={<TasksPage />} />
        <Route path="/photos" element={<div>Photos Page</div>} />
        <Route path="/projects/:projectId/settings/ai" element={<div>Project AI Settings</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("TasksPage", () => {
  beforeEach(() => {
    useProjectContextMock.mockReset();
    useScanStatusMock.mockReset();
    useStartScanMock.mockReset();
    useStartReindexMock.mockReset();

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
  });

  it("shows the canonical ai settings link and no embedded ai-settings tab", () => {
    renderPage();

    expect(screen.getByRole("link", { name: "打开项目 AI 配置" })).toHaveAttribute(
      "href",
      "/projects/7/settings/ai",
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
});
