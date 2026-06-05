import { request } from "./client";
import type { ScanStatus } from "./types";

export type ReindexScope = "all" | "missing_metadata" | "missing_location";

export const projectScansApi = {
  start: (projectId: number) =>
    request<{ message: string; status: ScanStatus }>(`/projects/${projectId}/scan/start`, {
      method: "POST",
    }),

  status: (projectId: number) =>
    request<ScanStatus>(`/projects/${projectId}/scan/status`),

  cancel: (projectId: number) =>
    request<ScanStatus>(`/projects/${projectId}/scan/cancel`, {
      method: "POST",
    }),

  reindex: (
    projectId: number,
    scope: ReindexScope = "missing_metadata",
  ) =>
    request<{ message: string; status: ScanStatus }>(
      `/projects/${projectId}/scan/reindex?scope=${scope}`,
      { method: "POST" },
    ),
};
