import { request, qs } from "./client";
import type {
  PhotoQuarantineBatchAction,
  PhotoQuarantineBatchResponse,
  PhotoQuarantineCalibrationResponse,
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

  list: (
    projectId: number,
    status?: string,
    limit = 200,
    offset = 0,
    humanLabel?: "KEEP" | "TRASH" | "UNLABELED",
  ) =>
    request<PhotoQuarantineListResponse>(
      `/projects/${projectId}/photo-quarantine/items${qs({ status, human_label: humanLabel, limit, offset })}`,
    ),

  getCalibration: (projectId: number) =>
    request<PhotoQuarantineCalibrationResponse>(
      `/projects/${projectId}/photo-quarantine/calibration`,
    ),

  label: (projectId: number, itemId: number, label: "KEEP" | "TRASH", note?: string) =>
    request<PhotoQuarantineItem>(
      `/projects/${projectId}/photo-quarantine/items/${itemId}/label`,
      {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ label, note }),
      },
    ),

  startRun: (projectId: number) =>
    request<ProjectTask>(`/projects/${projectId}/photo-quarantine/runs`, { method: "POST" }),

  batch: (projectId: number, action: PhotoQuarantineBatchAction, itemIds: number[]) =>
    request<PhotoQuarantineBatchResponse>(`/projects/${projectId}/photo-quarantine/batches`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, item_ids: itemIds }),
    }),

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
