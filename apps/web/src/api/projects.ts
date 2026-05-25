import { request, qs, BASE } from "./client";
import type {
  AIAnalysis,
  AIJobListResponse,
  AIStatus,
  EmbeddingStatusResponse,
  EmbeddingTestRequest,
  EmbeddingTestResponse,
  FolderScope,
  PhotoDetail,
  PhotoListResponse,
  ProjectAISettings,
  ProjectAISettingsUpdate,
  ProjectCreate,
  ProjectEmbeddingSettings,
  ProjectEmbeddingSettingsUpdate,
  ProjectListResponse,
  ProjectSearchSettings,
  ProjectSearchSettingsUpdate,
  ProjectUpdate,
  Project,
  PromptTemplate,
  PromptTemplateCreate,
  PromptTemplateListResponse,
  PromptTemplateTestRequest,
  PromptTemplateTestResponse,
  PromptTemplateUpdate,
  RebuildRequest,
  RebuildResponse,
  ScanStatus,
  SearchMode,
  SearchResponse,
  TagField,
  TagsResponse,
  TimelineResponse,
} from "./types";

export const projectsApi = {
  list: () => request<ProjectListResponse>("/projects"),

  get: (id: number) => request<Project>(`/projects/${id}`),

  create: (body: ProjectCreate) =>
    request<Project>("/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  update: (id: number, body: ProjectUpdate) =>
    request<Project>(`/projects/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  delete: (id: number) => request<void>(`/projects/${id}`, { method: "DELETE" }),

  // ── Scan ──────────────────────────────────────────────────────────────────

  startScan: (id: number) =>
    request<{ message: string; status: ScanStatus }>(`/projects/${id}/scan/start`, {
      method: "POST",
    }),

  scanStatus: (id: number) => request<ScanStatus>(`/projects/${id}/scan/status`),

  startReindex: (
    id: number,
    scope: "all" | "missing_metadata" | "missing_location" = "missing_metadata",
  ) =>
    request<{ message: string; status: ScanStatus }>(
      `/projects/${id}/scan/reindex?scope=${scope}`,
      { method: "POST" },
    ),

  // ── AI Jobs ───────────────────────────────────────────────────────────────

  startAI: (id: number) =>
    request<{ created_jobs: number; message: string }>(
      `/projects/${id}/ai/analyze/start`,
      { method: "POST" },
    ),

  aiStatus: (id: number) => request<AIStatus>(`/projects/${id}/ai/status`),

  aiJobs: (id: number, status?: string, limit = 50, offset = 0) =>
    request<AIJobListResponse>(
      `/projects/${id}/ai/jobs${qs({ status, limit, offset })}`,
    ),

  retryFailedAiJobs: (id: number) =>
    request<{ retried_jobs: number; message: string }>(
      `/projects/${id}/ai/jobs/retry-failed`,
      { method: "POST" },
    ),

  clearFailedAiJobs: (id: number) =>
    request<{ deleted_jobs: number; message: string }>(
      `/projects/${id}/ai/jobs/failed`,
      { method: "DELETE" },
    ),

  reanalyze: (
    id: number,
    body: {
      scope: "all" | "completed" | "failed" | "selected";
      photo_ids?: number[];
      clear_existing_analysis?: boolean;
    },
  ) =>
    request<{ created_jobs: number; message: string }>(
      `/projects/${id}/ai/analyze/restart`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      },
    ),

  // ── AI Settings ───────────────────────────────────────────────────────────

  getAiSettings: (id: number) =>
    request<ProjectAISettings>(`/projects/${id}/ai-settings`),

  updateAiSettings: (id: number, body: ProjectAISettingsUpdate) =>
    request<ProjectAISettings>(`/projects/${id}/ai-settings`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  // ── Prompt Templates ──────────────────────────────────────────────────────

  promptTemplates: (id: number, taskType = "image_analysis") =>
    request<PromptTemplateListResponse>(
      `/projects/${id}/prompt-templates${qs({ task_type: taskType })}`,
    ),

  createPromptTemplate: (id: number, body: PromptTemplateCreate) =>
    request<PromptTemplate>(`/projects/${id}/prompt-templates`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  updatePromptTemplate: (id: number, templateId: number, body: PromptTemplateUpdate) =>
    request<PromptTemplate>(`/projects/${id}/prompt-templates/${templateId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  deletePromptTemplate: (id: number, templateId: number) =>
    request<void>(`/projects/${id}/prompt-templates/${templateId}`, {
      method: "DELETE",
    }),

  resetDefaultPromptTemplate: (id: number) =>
    request<PromptTemplate>(`/projects/${id}/prompt-templates/reset-default`, {
      method: "POST",
    }),

  testPromptTemplate: (id: number, body: PromptTemplateTestRequest) =>
    request<PromptTemplateTestResponse>(`/projects/${id}/prompt-templates/test`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  // ── Search ────────────────────────────────────────────────────────────────

  search: (
    id: number,
    q: string,
    page = 1,
    pageSize = 50,
    folderId?: number | null,
    folderScope: FolderScope = "subtree",
    mode: SearchMode = "hybrid",
    debug = false,
    tagField?: TagField | null,
    tagValue?: string | null,
  ) =>
    request<SearchResponse>(
      `/projects/${id}/search${qs({
        q,
        page,
        page_size: pageSize,
        folder_id: folderId,
        folder_scope: folderScope,
        mode,
        debug: debug || undefined,
        filter: tagField && tagValue ? "tag" : undefined,
        tag_field: tagField ?? undefined,
        tag_value: tagValue ?? undefined,
      })}`,
    ),

  // ── Embedding Settings ────────────────────────────────────────────────────

  getEmbeddingSettings: (id: number) =>
    request<ProjectEmbeddingSettings>(`/projects/${id}/embedding-settings`),

  updateEmbeddingSettings: (id: number, body: ProjectEmbeddingSettingsUpdate) =>
    request<ProjectEmbeddingSettings>(`/projects/${id}/embedding-settings`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  testEmbeddingSettings: (id: number, body: EmbeddingTestRequest) =>
    request<EmbeddingTestResponse>(`/projects/${id}/embedding-settings/test`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  getEmbeddingStatus: (id: number) =>
    request<EmbeddingStatusResponse>(`/projects/${id}/embeddings/status`),

  rebuildEmbeddings: (id: number, body: RebuildRequest) =>
    request<RebuildResponse>(`/projects/${id}/embeddings/rebuild`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  // ── Tags ──────────────────────────────────────────────────────────────────

  tags: (id: number) => request<TagsResponse>(`/projects/${id}/tags`),

  // ── Photos ────────────────────────────────────────────────────────────────

  photos: (
    id: number,
    page = 1,
    pageSize = 50,
    dateFrom?: string | null,
    dateTo?: string | null,
    folderId?: number | null,
    folderScope: FolderScope = "subtree",
  ) =>
    request<PhotoListResponse>(
      `/projects/${id}/photos${qs({
        page,
        page_size: pageSize,
        date_from: dateFrom,
        date_to: dateTo,
        folder_id: folderId,
        folder_scope: folderScope,
      })}`,
    ),

  timeline: (
    id: number,
    folderId?: number | null,
    folderScope: FolderScope = "subtree",
  ) =>
    request<TimelineResponse>(
      `/projects/${id}/photos/timeline${qs({
        folder_id: folderId,
        folder_scope: folderScope,
      })}`,
    ),

  photo: (id: number, photoId: number) =>
    request<PhotoDetail>(`/projects/${id}/photos/${photoId}`),

  photoAI: (id: number, photoId: number) =>
    request<AIAnalysis>(`/projects/${id}/photos/${photoId}/ai`),

  thumbnailUrl: (id: number, photoId: number, updatedAt?: string | null) => {
    const base = `${BASE}/projects/${id}/photos/${photoId}/thumbnail`;
    if (!updatedAt) return base;
    const version = Date.parse(updatedAt);
    return Number.isNaN(version) ? base : `${base}?v=${version}`;
  },

  originalUrl: (id: number, photoId: number) =>
    `${BASE}/projects/${id}/photos/${photoId}/original`,

  previewUrl: (id: number, photoId: number) =>
    `${BASE}/projects/${id}/photos/${photoId}/preview`,

  // ── Search Settings ───────────────────────────────────────────────────────

  getSearchSettings: (id: number) =>
    request<ProjectSearchSettings>(`/projects/${id}/search-settings`),

  updateSearchSettings: (id: number, body: ProjectSearchSettingsUpdate) =>
    request<ProjectSearchSettings>(`/projects/${id}/search-settings`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  resetSearchSettings: (id: number) =>
    request<ProjectSearchSettings>(`/projects/${id}/search-settings/reset`, {
      method: "POST",
    }),
};
