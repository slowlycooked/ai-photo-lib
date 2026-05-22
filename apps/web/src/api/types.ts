/**
 * Shared TypeScript interfaces for the ai-photo-lib API.
 */

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
  keyword_score?: number;
  vector_score?: number;
  rrf_score?: number;
  match_source?: string[];
  field_scores?: {
    content?: number;
    caption?: number;
    tag?: number;
    ocr?: number;
  };
}

export interface SearchDebugPayload {
  original_query: string;
  normalized_query: string;
  expanded_terms: string[];
  intent: string;
  mode: string;
  embedding_model: string;
  embedding_dimension: number;
  keyword_candidates: number;
  vector_candidates: number;
  merged_candidates: number;
  fallback_reason?: string;
}

export interface SearchResponse {
  query: string;
  total: number;
  page: number;
  page_size: number;
  items: SearchResultItem[];
  debug?: SearchDebugPayload | null;
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
  ai_max_retries: number;
}

export type DebugMode = "OFF" | "BASIC" | "DEBUG" | "TRACE" | "CUSTOM";
export type DebugPresetMode = Exclude<DebugMode, "CUSTOM">;
export type LogLevel = "OFF" | "ERROR" | "WARNING" | "INFO" | "DEBUG" | "TRACE";

export interface DebugMatrix {
  frontendLogLevel: LogLevel;
  backendLogLevel: LogLevel;
  aiLogLevel: LogLevel;
  searchLogLevel: LogLevel;
  sqlLogLevel: LogLevel;
  taskLogLevel: LogLevel;
}

export interface DebugSettingsResponse {
  debugMode: DebugMode;
  debugMatrix: DebugMatrix;
  presets: Record<DebugPresetMode, DebugMatrix>;
  updatedAt: string | null;
}

export interface DebugSettingsUpdate {
  debugMode: DebugMode;
  debugMatrix: DebugMatrix;
}

// ─── AI Settings / Prompt Templates ──────────────────────────────────────────

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

// ─── Embedding Settings ───────────────────────────────────────────────────────

export type SearchMode = "keyword" | "vector" | "hybrid";

export interface ProjectEmbeddingSettings {
  id: number;
  project_id: number;
  provider: string;
  endpoint_url: string;
  model_name: string;
  embedding_dimension: number;
  batch_size: number;
  timeout_seconds: number;
  input_prefix_query: string;
  input_prefix_document: string;
  enabled: boolean;
  search_content_vector_weight: number;
  search_tag_vector_weight: number;
  search_caption_vector_weight: number;
  search_ocr_vector_weight: number;
  created_at: string;
  updated_at: string;
}

export interface ProjectEmbeddingSettingsUpdate {
  provider?: string;
  endpoint_url?: string;
  api_key?: string | null;
  model_name?: string;
  embedding_dimension?: number;
  batch_size?: number;
  timeout_seconds?: number;
  input_prefix_query?: string;
  input_prefix_document?: string;
  enabled?: boolean;
  search_content_vector_weight?: number;
  search_tag_vector_weight?: number;
  search_caption_vector_weight?: number;
  search_ocr_vector_weight?: number;
}

export interface EmbeddingTestRequest {
  text: string;
}

export interface EmbeddingTestResponse {
  success: boolean;
  model_name: string;
  embedding_dimension: number;
  sample: number[];
  duration_ms: number;
  error: string | null;
}

export interface EmbeddingStatusResponse {
  project_id: number;
  total_analyzed_photos: number;
  ready: number;
  missing: number;
  stale: number;
  failed: number;
  running_jobs: number;
  queued_jobs: number;
  embedding_model: string;
  embedding_dimension: number;
  input_version: string;
}

export type RebuildScope = "all" | "stale" | "failed" | "missing" | "selected";

export interface RebuildRequest {
  scope: RebuildScope;
  photo_ids?: number[];
  force?: boolean;
}

export interface RebuildResponse {
  created_jobs: number;
  skipped_existing_jobs: number;
  skipped_up_to_date: number;
  total_checked: number;
  message: string;
}
