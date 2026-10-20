import { request } from "./client";
import type { ScanStatus } from "./types";

export type ReindexScope = "all" | "missing_metadata" | "missing_location";

export const projectScansApi = {
  start: (projectId: number, rebuild = false) =>
    request<{ message: string; status: ScanStatus }>(
      `/projects/${projectId}/scan/start${rebuild ? "?rebuild=true" : ""}`,
      { method: "POST" },
    ),

  status: (projectId: number, signal?: AbortSignal) =>
    request<ScanStatus>(`/projects/${projectId}/scan/status`, { signal }),

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
