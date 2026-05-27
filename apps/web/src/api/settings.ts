import { request } from "./client";
import type {
  AppSettings,
  DebugSettingsResponse,
  DebugSettingsUpdate,
  SystemHealthResponse,
} from "./types";

export const settingsApi = {
  get: () => request<AppSettings>("/settings"),

  health: () => request<SystemHealthResponse>("/health/system"),

  getDebug: () => request<DebugSettingsResponse>("/settings/debug"),

  updateDebug: (body: DebugSettingsUpdate) =>
    request<DebugSettingsResponse>("/settings/debug", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  resetDebug: () =>
    request<DebugSettingsResponse>("/settings/debug", { method: "DELETE" }),
};
