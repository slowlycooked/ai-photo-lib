import { request } from "./client";
import type {
  EmbeddingStatusResponse,
  EmbeddingTestRequest,
  EmbeddingTestResponse,
  ProjectAISettings,
  ProjectAISettingsUpdate,
  ProjectEmbeddingSettings,
  ProjectEmbeddingSettingsUpdate,
  ProjectEffectiveSettings,
  ProjectFaceSettings,
  ProjectFaceSettingsUpdate,
  ProjectQueryPlannerSettings,
  ProjectQueryPlannerSettingsUpdate,
  ProjectSearchSettings,
  ProjectSearchSettingsUpdate,
  QueryPlannerTestResponse,
  RebuildRequest,
  RebuildResponse,
} from "./types";

export const projectSettingsApi = {
  getAi: (projectId: number) =>
    request<ProjectAISettings>(`/projects/${projectId}/ai-settings`),

  initAi: (projectId: number) =>
    request<ProjectAISettings>(`/projects/${projectId}/ai-settings/init`, {
      method: "POST",
    }),

  updateAi: (projectId: number, body: ProjectAISettingsUpdate) =>
    request<ProjectAISettings>(`/projects/${projectId}/ai-settings`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  getFace: (projectId: number) =>
    request<ProjectFaceSettings>(`/projects/${projectId}/face-settings`),

  updateFace: (projectId: number, body: ProjectFaceSettingsUpdate) =>
    request<ProjectFaceSettings>(`/projects/${projectId}/face-settings`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  resetFace: (projectId: number) =>
    request<ProjectFaceSettings>(`/projects/${projectId}/face-settings/reset`, {
      method: "POST",
    }),

  getEmbedding: (projectId: number) =>
    request<ProjectEmbeddingSettings>(`/projects/${projectId}/embedding-settings`),

  updateEmbedding: (projectId: number, body: ProjectEmbeddingSettingsUpdate) =>
    request<ProjectEmbeddingSettings>(`/projects/${projectId}/embedding-settings`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  testEmbedding: (projectId: number, body: EmbeddingTestRequest) =>
    request<EmbeddingTestResponse>(`/projects/${projectId}/embedding-settings/test`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  embeddingStatus: (projectId: number) =>
    request<EmbeddingStatusResponse>(`/projects/${projectId}/embeddings/status`),

  rebuildEmbeddings: (projectId: number, body: RebuildRequest) =>
    request<RebuildResponse>(`/projects/${projectId}/embeddings/rebuild`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  getSearch: (projectId: number) =>
    request<ProjectSearchSettings>(`/projects/${projectId}/search-settings`),

  updateSearch: (projectId: number, body: ProjectSearchSettingsUpdate) =>
    request<ProjectSearchSettings>(`/projects/${projectId}/search-settings`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  resetSearch: (projectId: number) =>
    request<ProjectSearchSettings>(`/projects/${projectId}/search-settings/reset`, {
      method: "POST",
    }),

  effective: (projectId: number) =>
    request<ProjectEffectiveSettings>(`/projects/${projectId}/settings/effective`),

  getQueryPlanner: (projectId: number) =>
    request<ProjectQueryPlannerSettings>(`/projects/${projectId}/query-planner-settings`),

  updateQueryPlanner: (projectId: number, body: ProjectQueryPlannerSettingsUpdate) =>
    request<ProjectQueryPlannerSettings>(`/projects/${projectId}/query-planner-settings`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  resetQueryPlanner: (projectId: number) =>
    request<ProjectQueryPlannerSettings>(`/projects/${projectId}/query-planner-settings/reset`, {
      method: "POST",
    }),

  testQueryPlanner: (projectId: number, query: string) =>
    request<QueryPlannerTestResponse>(`/projects/${projectId}/query-planner-settings/test`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
    }),
};
