import { request, qs } from "./client";
import type { AIJobListResponse, AIStatus } from "./types";

export interface ProjectReanalyzeRequest {
  scope: "all" | "completed" | "failed" | "selected";
  photo_ids?: number[];
  clear_existing_analysis?: boolean;
}

export const projectAiJobsApi = {
  startAnalysis: (projectId: number) =>
    request<{ created_jobs: number; message: string }>(
      `/projects/${projectId}/ai/analyze/start`,
      { method: "POST" },
    ),

  status: (projectId: number) =>
    request<AIStatus>(`/projects/${projectId}/ai/status`),

  list: (
    projectId: number,
    status?: string,
    limit = 50,
    offset = 0,
    jobType?: string,
  ) =>
    request<AIJobListResponse>(
      `/projects/${projectId}/ai/jobs${qs({ status, limit, offset, job_type: jobType })}`,
    ),

  retryFailed: (projectId: number, jobType?: string) =>
    request<{
      retried_jobs: number;
      message: string;
      task_id?: number | null;
      task_created?: boolean;
      task_status?: string | null;
    }>(
      `/projects/${projectId}/ai/jobs/retry-failed${qs({ job_type: jobType })}`,
      { method: "POST" },
    ),

  clearFailed: (projectId: number, jobType?: string) =>
    request<{ deleted_jobs: number; message: string }>(
      `/projects/${projectId}/ai/jobs/failed${qs({ job_type: jobType })}`,
      { method: "DELETE" },
    ),

  forceStop: (projectId: number, jobType?: string) =>
    request<{
      stopped_jobs: number;
      stopped_queued: number;
      stopped_running: number;
      message: string;
    }>(
      `/projects/${projectId}/ai/jobs/force-stop${qs({ job_type: jobType })}`,
      { method: "POST" },
    ),

  reanalyze: (projectId: number, body: ProjectReanalyzeRequest) =>
    request<{ created_jobs: number; message: string }>(
      `/projects/${projectId}/ai/analyze/restart`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      },
    ),
};
