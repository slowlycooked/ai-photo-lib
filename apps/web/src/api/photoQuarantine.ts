import { request, qs } from "./client";
import type {
  PhotoQuarantineItem,
  PhotoQuarantineListResponse,
  ProjectPhotoQuarantineSettings,
  ProjectPhotoQuarantineSettingsUpdate,
  ProjectTask,
} from "./types";

export const photoQuarantineApi = {
  getSettings: (projectId: number) =>
    request<ProjectPhotoQuarantineSettings>(`/projects/${projectId}/photo-quarantine/settings`),

  updateSettings: (projectId: number, body: ProjectPhotoQuarantineSettingsUpdate) =>
    request<ProjectPhotoQuarantineSettings>(`/projects/${projectId}/photo-quarantine/settings`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  list: (projectId: number, status?: string, limit = 200, offset = 0) =>
    request<PhotoQuarantineListResponse>(
      `/projects/${projectId}/photo-quarantine/items${qs({ status, limit, offset })}`,
    ),

  startRun: (projectId: number) =>
    request<ProjectTask>(`/projects/${projectId}/photo-quarantine/runs`, { method: "POST" }),

  move: (projectId: number, itemId: number) =>
    request<PhotoQuarantineItem>(
      `/projects/${projectId}/photo-quarantine/items/${itemId}/move`,
      { method: "POST" },
    ),

  restore: (projectId: number, itemId: number) =>
    request<PhotoQuarantineItem>(
      `/projects/${projectId}/photo-quarantine/items/${itemId}/restore`,
      { method: "POST" },
    ),

  confirmDeleted: (projectId: number, itemId: number) =>
    request<PhotoQuarantineItem>(
      `/projects/${projectId}/photo-quarantine/items/${itemId}/confirm-deleted`,
      { method: "POST" },
    ),

  keep: (projectId: number, itemId: number) =>
    request<PhotoQuarantineItem>(
      `/projects/${projectId}/photo-quarantine/items/${itemId}/keep`,
      { method: "POST" },
    ),
};
