const BASE = "/api";

// ─── Project ──────────────────────────────────────────────────────────────────

export interface Project {
  id: number;
  name: string;
  description: string | null;
  photo_library_path: string;
  thumbnail_path: string | null;
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

export interface ProjectListResponse {
  total: number;
  items: Project[];
}

export interface ProjectCreate {
  name: string;
  description?: string | null;
  photo_library_path: string;
  thumbnail_path?: string | null;
  is_default?: boolean;
}

export interface ProjectUpdate {
  name?: string;
  description?: string | null;
  photo_library_path?: string;
  thumbnail_path?: string | null;
  is_default?: boolean;
}

// ─── Photo ────────────────────────────────────────────────────────────────────

export interface Photo {
  id: number;
  project_id: number;
  file_name: string;
  mime_type: string | null;
  width: number | null;
  height: number | null;
  taken_at: string | null;
  file_size: number | null;
  status: string;
  thumbnail_path: string | null;
  created_at: string;
  updated_at: string;
}

export interface PhotoDetail extends Photo {
  exif: Record<string, string> | null;
  gps_latitude: number | null;
  gps_longitude: number | null;
  gps_altitude: number | null;
  camera_make: string | null;
  camera_model: string | null;
  lens_model: string | null;
  focal_length: string | null;
  aperture: string | null;
  exposure_time: string | null;
  iso: number | null;
  orientation: number | null;
}

export interface PhotoListResponse {
  total: number;
  page: number;
  page_size: number;
  items: Photo[];
}

export interface TimelineItem {
  key: string;
  year: number;
  month: number;
  count: number;
}

export interface TimelineResponse {
  items: TimelineItem[];
}

// ─── Folder ───────────────────────────────────────────────────────────────────

export interface FolderNode {
  id: number;
  name: string;
  relative_path: string;
  depth: number;
  photo_count_direct: number;
  photo_count_recursive: number;
  children?: FolderNode[];
}

export interface FolderTreeResponse {
  project_id: number;
  root: FolderNode | null;
}

export interface FolderBreadcrumbItem {
  id: number;
  name: string;
  relative_path: string;
}

export interface FolderBreadcrumbResponse {
  items: FolderBreadcrumbItem[];
}

export type FolderScope = "direct" | "subtree";

// ─── Scan ─────────────────────────────────────────────────────────────────────

export interface ScanStatus {
  running: boolean;
  scanned: number;
  inserted: number;
  updated: number;
  errors: number;
  current_path: string | null;
  message: string;
}

// ─── AI ───────────────────────────────────────────────────────────────────────

export interface AIAnalysis {
  id: number;
  photo_id: number;
  model_name: string | null;
  model_version: string | null;
  caption: string | null;
  ocr_text: string | null;
  scene_tags: string[] | null;
  object_tags: string[] | null;
  activity_tags: string[] | null;
  quality_tags: string[] | null;
  location_clues: string[] | null;
  search_keywords: string[] | null;
  people_count: number | null;
  confidence: number | null;
  created_at: string;
  updated_at: string;
}

export interface AIStatus {
  queued: number;
  running: number;
  success: number;
  failed: number;
  total: number;
}

export interface AIJob {
  id: number;
  photo_id: number;
  job_type: string | null;
  status: string;
  retry_count: number;
  error_message: string | null;
  prompt_template_id: number | null;
  prompt_version: number | null;
  model_name: string | null;
  model_params: Record<string, unknown> | null;
  raw_model_output: string | null;
  parse_error: string | null;
  file_name: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface AIJobListResponse {
  total: number;
  items: AIJob[];
}

// ─── Search ───────────────────────────────────────────────────────────────────

export interface SearchResultItem {
  photo_id: number;
  file_name: string;
  thumbnail_url: string;
  updated_at: string;
  taken_at: string | null;
  width: number | null;
  height: number | null;
  caption: string | null;
  matched_tags: string[];
  score: number;
}

export interface SearchResponse {
  query: string;
  total: number;
  page: number;
  page_size: number;
  items: SearchResultItem[];
}

// ─── Tags ─────────────────────────────────────────────────────────────────────

export interface TagCount {
  tag: string;
  count: number;
}

export interface TagsResponse {
  scene_tags: TagCount[];
  object_tags: TagCount[];
  activity_tags: TagCount[];
  quality_tags: TagCount[];
  search_keywords: TagCount[];
}

// ─── Settings ─────────────────────────────────────────────────────────────────

export interface AppSettings {
  photo_library_path: string;
  host_photo_library_path: string;
  thumbnail_path: string;
  thumbnail_size: number;
  openai_base_url: string;
  openai_model: string;
  openai_vision_model: string;
  ai_worker_concurrency: number;
  ai_max_retries: number;
}

export type DebugMode = "off" | "basic" | "debug" | "trace";
export type LogLevel = "ERROR" | "WARNING" | "INFO" | "DEBUG";

export interface DebugSettings {
  debug_mode: DebugMode;
  backend_log_level: LogLevel;
  frontend_log_level: LogLevel;
  ai_log_level: LogLevel;
  search_log_level: LogLevel;
  db_log_level: LogLevel;
  task_log_level: LogLevel;
  log_request_body: boolean;
  log_ai_prompt: boolean;
  log_ai_response: boolean;
  log_sql: boolean;
  log_stacktrace: boolean;
  max_log_text_length: number;
}

export interface ProjectAISettings {
  id: number;
  project_id: number;
  provider: string;
  endpoint_url: string;
  model_name: string;
  temperature: number;
  top_p: number;
  max_tokens: number;
  retry_count: number;
  output_language: string;
  json_parse_strategy: string;
  active_prompt_template_id: number | null;
  created_at: string;
  updated_at: string;
}

export interface ProjectAISettingsUpdate {
  provider: string;
  endpoint_url: string;
  model_name: string;
  temperature: number;
  top_p: number;
  max_tokens: number;
  retry_count: number;
  output_language: string;
  json_parse_strategy: string;
  active_prompt_template_id?: number | null;
}

export interface PromptTemplate {
  id: number;
  project_id: number;
  name: string;
  task_type: string;
  system_prompt: string | null;
  user_prompt: string;
  output_schema: Record<string, unknown> | null;
  is_active: boolean;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface PromptTemplateListResponse {
  total: number;
  items: PromptTemplate[];
}

export interface PromptTemplateCreate {
  name: string;
  task_type?: string;
  system_prompt?: string | null;
  user_prompt: string;
  output_schema?: Record<string, unknown> | null;
  is_active?: boolean;
}

export interface PromptTemplateUpdate {
  name?: string;
  system_prompt?: string | null;
  user_prompt: string;
  output_schema?: Record<string, unknown> | null;
  is_active?: boolean;
}

export interface PromptTemplateTestRequest {
  image_id: number;
  prompt_template_id?: number;
  override_prompt?: string;
}

export interface PromptTemplateTestResponse {
  success: boolean;
  raw_output: string;
  parsed_json: Record<string, unknown> | null;
  error: string | null;
  duration_ms: number;
}

// ─── HTTP helper ──────────────────────────────────────────────────────────────

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: unknown,
  ) {
    const msg =
      typeof detail === "string"
        ? detail
        : (detail as Record<string, unknown>)?.message
          ? String((detail as Record<string, unknown>).message)
          : JSON.stringify(detail);
    super(msg);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init);

  if (!res.ok) {
    const body = await res.json().catch(() => null);
    const detail = body?.error ?? body?.detail ?? res.statusText;
    throw new ApiError(res.status, detail);
  }

  if (res.status === 204) {
    return undefined as T;
  }

  return res.json() as Promise<T>;
}

function qs(params: Record<string, string | number | boolean | undefined | null>): string {
  const parts = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== null)
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`);
  return parts.length ? `?${parts.join("&")}` : "";
}

// ─── API ──────────────────────────────────────────────────────────────────────

export const api = {
  health: () => request<{ status: string }>("/health"),

  projects: {
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
    delete: (id: number) =>
      request<void>(`/projects/${id}`, { method: "DELETE" }),
    startScan: (id: number) =>
      request<{ message: string; status: ScanStatus }>(`/projects/${id}/scan/start`, {
        method: "POST",
      }),
    scanStatus: (id: number) =>
      request<ScanStatus>(`/projects/${id}/scan/status`),
    startAI: (id: number) =>
      request<{ created_jobs: number; message: string }>(
        `/projects/${id}/ai/analyze/start`,
        { method: "POST" }
      ),
    aiStatus: (id: number) => request<AIStatus>(`/projects/${id}/ai/status`),
    aiJobs: (id: number, status?: string, limit = 50, offset = 0) =>
      request<AIJobListResponse>(
        `/projects/${id}/ai/jobs${qs({ status, limit, offset })}`
      ),
    retryFailedAiJobs: (id: number) =>
      request<{ retried_jobs: number; message: string }>(
        `/projects/${id}/ai/jobs/retry-failed`,
        { method: "POST" }
      ),
    clearFailedAiJobs: (id: number) =>
      request<{ deleted_jobs: number; message: string }>(
        `/projects/${id}/ai/jobs/failed`,
        { method: "DELETE" }
      ),
    reanalyze: (
      id: number,
      body: {
        scope: "all" | "completed" | "failed" | "selected";
        photo_ids?: number[];
        clear_existing_analysis?: boolean;
      }
    ) =>
      request<{ created_jobs: number; message: string }>(
        `/projects/${id}/ai/analyze/restart`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        }
      ),
    getAiSettings: (id: number) =>
      request<ProjectAISettings>(`/projects/${id}/ai-settings`),
    updateAiSettings: (id: number, body: ProjectAISettingsUpdate) =>
      request<ProjectAISettings>(`/projects/${id}/ai-settings`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }),
    promptTemplates: (id: number, taskType = "image_analysis") =>
      request<PromptTemplateListResponse>(
        `/projects/${id}/prompt-templates${qs({ task_type: taskType })}`
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
    search: (id: number, q: string, page = 1, pageSize = 50, folderId?: number | null, folderScope: FolderScope = "subtree") =>
      request<SearchResponse>(
        `/projects/${id}/search${qs({ q, page, page_size: pageSize, folder_id: folderId, folder_scope: folderScope })}`
      ),
    tags: (id: number) => request<TagsResponse>(`/projects/${id}/tags`),
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
        })}`
      ),
    timeline: (id: number, folderId?: number | null, folderScope: FolderScope = "subtree") =>
      request<TimelineResponse>(
        `/projects/${id}/photos/timeline${qs({ folder_id: folderId, folder_scope: folderScope })}`
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
  },

  photos: {
    list: (
      page = 1,
      pageSize = 50,
      projectId?: number | null,
      dateFrom?: string | null,
      dateTo?: string | null,
      folderId?: number | null,
      folderScope: FolderScope = "subtree"
    ) =>
      request<PhotoListResponse>(
        `/photos${qs({
          page,
          page_size: pageSize,
          project_id: projectId,
          date_from: dateFrom,
          date_to: dateTo,
          folder_id: folderId,
          folder_scope: folderScope,
        })}`
      ),
    timeline: (projectId?: number | null, folderId?: number | null, folderScope: FolderScope = "subtree") =>
      request<TimelineResponse>(
        `/photos/timeline${qs({ project_id: projectId, folder_id: folderId, folder_scope: folderScope })}`
      ),
    /** @deprecated Use api.projects.photo(projectId, photoId) instead. */
    get: (id: number) => request<PhotoDetail>(`/photos/${id}`),
    /** @deprecated Use api.projects.thumbnailUrl(projectId, photoId, updatedAt) instead. */
    thumbnailUrl: (id: number, updatedAt?: string | null) => {
      const base = `${BASE}/photos/${id}/thumbnail`;
      if (!updatedAt) return base;
      const version = Date.parse(updatedAt);
      return Number.isNaN(version) ? base : `${base}?v=${version}`;
    },
    /** @deprecated Use api.projects.originalUrl(projectId, photoId) instead. */
    originalUrl: (id: number) => `${BASE}/photos/${id}/original`,
    /** @deprecated Use api.projects.photoAI(projectId, photoId) instead. */
    getAI: (id: number) => request<AIAnalysis>(`/photos/${id}/ai`),
  },

  folders: {
    tree: (projectId: number) =>
      request<FolderTreeResponse>(`/projects/${projectId}/folders/tree`),
    breadcrumb: (projectId: number, folderId: number) =>
      request<FolderBreadcrumbResponse>(`/projects/${projectId}/folders/${folderId}/breadcrumb`),
  },

  scan: {
    start: () =>
      request<{ message: string; status: ScanStatus }>("/scan/start", { method: "POST" }),
    status: () => request<ScanStatus>("/scan/status"),
  },

  ai: {
    startAnalysis: (projectId?: number | null) =>
      request<{ created_jobs: number; message: string }>(
        `/ai/analyze/start${qs({ project_id: projectId })}`,
        { method: "POST" }
      ),
    status: () => request<AIStatus>("/ai/status"),
    jobs: (status?: string, limit = 50, offset = 0) =>
      request<AIJobListResponse>(
        `/ai/jobs${qs({ status, limit, offset })}`
      ),
    retryFailed: () =>
      request<{ retried_jobs: number; message: string }>("/ai/jobs/retry-failed", {
        method: "POST",
      }),
    clearFailedJobs: () =>
      request<{ deleted_jobs: number; message: string }>("/ai/jobs/clear-failed", {
        method: "DELETE",
      }),
  },

  search: {
    query: (q: string, page = 1, pageSize = 50, projectId?: number | null, folderId?: number | null, folderScope: FolderScope = "subtree") =>
      request<SearchResponse>(
        `/search${qs({
          q,
          page,
          page_size: pageSize,
          project_id: projectId,
          folder_id: folderId,
          folder_scope: folderScope,
        })}`
      ),
  },

  tags: {
    list: (projectId?: number | null) =>
      request<TagsResponse>(`/tags${qs({ project_id: projectId })}`),
  },

  settings: {
    get: () => request<AppSettings>("/settings"),
    getDebug: () => request<DebugSettings>("/settings/debug"),
    updateDebug: (body: DebugSettings) =>
      request<DebugSettings>("/settings/debug", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }),
  },
};
