import { request, qs } from "./client";
import type {
  ProjectTask,
  ProjectTaskFailureListResponse,
  ProjectTaskListResponse,
} from "./types";

export interface ProjectTaskListParams {
  status?: string;
  task_type?: string;
  limit?: number;
  offset?: number;
}

export interface ProjectTaskFailureParams {
  limit?: number;
  offset?: number;
}

export const projectTasksApi = {
  list: (projectId: number, params: ProjectTaskListParams = {}, signal?: AbortSignal) =>
    request<ProjectTaskListResponse>(
      `/projects/${projectId}/tasks${qs({
        status: params.status,
        task_type: params.task_type,
        limit: params.limit ?? 20,
        offset: params.offset ?? 0,
      })}`,
      { signal },
    ),

  get: (projectId: number, taskId: number) =>
    request<ProjectTask>(`/projects/${projectId}/tasks/${taskId}`),

  failures: (
    projectId: number,
    taskId: number,
    params: ProjectTaskFailureParams = {},
    signal?: AbortSignal,
  ) =>
    request<ProjectTaskFailureListResponse>(
      `/projects/${projectId}/tasks/${taskId}/failures${qs({
        limit: params.limit ?? 20,
        offset: params.offset ?? 0,
      })}`,
      { signal },
    ),

  pause: (projectId: number, taskId: number) =>
    request<ProjectTask>(`/projects/${projectId}/tasks/${taskId}/pause`, {
      method: "POST",
    }),

  cancel: (projectId: number, taskId: number) =>
    request<ProjectTask>(`/projects/${projectId}/tasks/${taskId}/cancel`, {
      method: "POST",
    }),

  resume: (projectId: number, taskId: number) =>
    request<ProjectTask>(`/projects/${projectId}/tasks/${taskId}/resume`, {
      method: "POST",
    }),
};
