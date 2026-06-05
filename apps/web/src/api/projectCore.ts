import { request } from "./client";
import type {
  Project,
  ProjectCreate,
  ProjectListResponse,
  ProjectReadinessResponse,
  ProjectUpdate,
} from "./types";

export const projectCoreApi = {
  list: () => request<ProjectListResponse>("/projects"),

  get: (projectId: number) => request<Project>(`/projects/${projectId}`),

  readiness: (projectId: number) =>
    request<ProjectReadinessResponse>(`/projects/${projectId}/readiness`),

  create: (body: ProjectCreate) =>
    request<Project>("/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  update: (projectId: number, body: ProjectUpdate) =>
    request<Project>(`/projects/${projectId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  delete: (projectId: number) =>
    request<void>(`/projects/${projectId}`, { method: "DELETE" }),
};
