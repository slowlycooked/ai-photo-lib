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
  project_id: number | null;
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

// ─── HTTP helper ──────────────────────────────────────────────────────────────

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init);
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`API ${res.status}: ${text}`);
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
  },

  photos: {
    list: (
      page = 1,
      pageSize = 50,
      projectId?: number | null,
      dateFrom?: string | null,
      dateTo?: string | null
    ) =>
      request<PhotoListResponse>(
        `/photos${qs({
          page,
          page_size: pageSize,
          project_id: projectId,
          date_from: dateFrom,
          date_to: dateTo,
        })}`
      ),
    timeline: (projectId?: number | null) =>
      request<TimelineResponse>(
        `/photos/timeline${qs({ project_id: projectId })}`
      ),
    get: (id: number) => request<PhotoDetail>(`/photos/${id}`),
    thumbnailUrl: (id: number, updatedAt?: string | null) => {
      const base = `${BASE}/photos/${id}/thumbnail`;
      if (!updatedAt) return base;
      const version = Date.parse(updatedAt);
      return Number.isNaN(version) ? base : `${base}?v=${version}`;
    },
    originalUrl: (id: number) => `${BASE}/photos/${id}/original`,
    getAI: (id: number) => request<AIAnalysis>(`/photos/${id}/ai`),
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
    query: (q: string, page = 1, pageSize = 50, projectId?: number | null) =>
      request<SearchResponse>(
        `/search${qs({
          q,
          page,
          page_size: pageSize,
          project_id: projectId,
        })}`
      ),
  },

  tags: {
    list: (projectId?: number | null) =>
      request<TagsResponse>(`/tags${qs({ project_id: projectId })}`),
  },

  settings: {
    get: () => request<AppSettings>("/settings"),
  },
};
