import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { FailedJobsSection } from "@/components/tasks/FailedJobsSection";

const aiJobsMock = vi.fn();
const retryFailedAiJobsMock = vi.fn();
const clearFailedAiJobsMock = vi.fn();

vi.mock("@/api", async () => {
  const actual = await vi.importActual<typeof import("@/api")>("@/api");
  return {
    ...actual,
    api: {
      ...actual.api,
      projects: {
        ...actual.api.projects,
        aiJobs: (...args: unknown[]) => aiJobsMock(...args),
        retryFailedAiJobs: (...args: unknown[]) => retryFailedAiJobsMock(...args),
        clearFailedAiJobs: (...args: unknown[]) => clearFailedAiJobsMock(...args),
      },
    },
  };
});

function renderSection() {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return render(
    <QueryClientProvider client={client}>
      <FailedJobsSection
        projectId={7}
        title="AI 失败任务"
        jobType="analyze,reanalyze"
        listQueryKey="ai-jobs-failed"
      />
    </QueryClientProvider>
  );
}

describe("FailedJobsSection", () => {
  beforeEach(() => {
    aiJobsMock.mockReset();
    retryFailedAiJobsMock.mockReset();
    clearFailedAiJobsMock.mockReset();

    aiJobsMock.mockResolvedValue({
      total: 1,
      items: [
        {
          id: 1,
          photo_id: 9,
          job_type: "analyze",
          status: "failed",
          retry_count: 0,
          error_message: "boom",
          prompt_template_id: 1,
          prompt_version: 2,
          model_name: "qwen",
          model_params: null,
          raw_model_output: "raw",
          parse_error: "parse",
          file_name: "a.jpg",
          started_at: null,
          finished_at: null,
          created_at: "2026-05-26T00:00:00Z",
          updated_at: "2026-05-26T00:00:00Z",
        },
      ],
    });
    retryFailedAiJobsMock.mockResolvedValue({ retried_jobs: 1, message: "ok" });
    clearFailedAiJobsMock.mockResolvedValue({ deleted_jobs: 1, message: "ok" });
  });

  it("loads failed jobs with configured job type", async () => {
    renderSection();

    expect(await screen.findByText("AI 失败任务")).toBeInTheDocument();
    expect(await screen.findByText("a.jpg")).toBeInTheDocument();
    expect(aiJobsMock).toHaveBeenCalledWith(7, "failed", 50, 0, "analyze,reanalyze");
  });

  it("retries failed jobs through shared action", async () => {
    const user = userEvent.setup();
    renderSection();

    await screen.findByText("a.jpg");
    await user.click(screen.getByRole("button", { name: "全部重试" }));

    await waitFor(() => {
      expect(retryFailedAiJobsMock).toHaveBeenCalledWith(7, "analyze,reanalyze");
    });
  });

  it("clears failed jobs through shared action", async () => {
    const user = userEvent.setup();
    renderSection();

    await screen.findByText("a.jpg");
    await user.click(screen.getByRole("button", { name: "清除失败记录" }));

    await waitFor(() => {
      expect(clearFailedAiJobsMock).toHaveBeenCalledWith(7, "analyze,reanalyze");
    });
  });

  it("does not render section when no failed jobs", async () => {
    aiJobsMock.mockResolvedValueOnce({ total: 0, items: [] });
    renderSection();

    await waitFor(() => {
      expect(screen.queryByText("AI 失败任务")).not.toBeInTheDocument();
    });
  });
});
