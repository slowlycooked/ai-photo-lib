const BASE = "/api";

export interface Photo {
  id: number;
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

export interface ScanStatus {
  running: boolean;
  scanned: number;
  inserted: number;
  updated: number;
  errors: number;
  current_path: string | null;
  message: string;
}

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

export interface SearchResultItem {
  photo_id: number;
  file_name: string;
  thumbnail_url: string;
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

export interface AppSettings {
  photo_library_path: string;
  thumbnail_path: string;
  thumbnail_size: number;
  openai_base_url: string;
  openai_model: string;
  openai_vision_model: string;
  ai_worker_concurrency: number;
  ai_max_retries: number;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init);
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`API ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => request<{ status: string }>("/health"),

  photos: {
    list: (page = 1, pageSize = 50) =>
      request<PhotoListResponse>(`/photos?page=${page}&page_size=${pageSize}`),
    get: (id: number) => request<PhotoDetail>(`/photos/${id}`),
    thumbnailUrl: (id: number) => `${BASE}/photos/${id}/thumbnail`,
    getAI: (id: number) => request<AIAnalysis>(`/photos/${id}/ai`),
  },

  scan: {
    start: () =>
      request<{ message: string; status: ScanStatus }>("/scan/start", { method: "POST" }),
    status: () => request<ScanStatus>("/scan/status"),
  },

  ai: {
    startAnalysis: () =>
      request<{ created_jobs: number; message: string }>("/ai/analyze/start", {
        method: "POST",
      }),
    status: () => request<AIStatus>("/ai/status"),
    jobs: (status?: string, limit = 50, offset = 0) =>
      request<AIJobListResponse>(
        `/ai/jobs?${status ? `status=${status}&` : ""}limit=${limit}&offset=${offset}`
      ),
    retryFailed: () =>
      request<{ retried_jobs: number; message: string }>("/ai/jobs/retry-failed", {
        method: "POST",
      }),
  },

  search: {
    query: (q: string, page = 1, pageSize = 50) =>
      request<SearchResponse>(
        `/search?q=${encodeURIComponent(q)}&page=${page}&page_size=${pageSize}`
      ),
  },

  tags: {
    list: () => request<TagsResponse>("/tags"),
  },

  settings: {
    get: () => request<AppSettings>("/settings"),
  },
};
