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

export interface ProjectReadinessCheck {
  name: string;
  ready: boolean;
  message: string;
}

export interface ProjectReadinessResponse {
  project_id: number;
  ready: boolean;
  checks: ProjectReadinessCheck[];
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
  gps_latitude: number | null;
  gps_longitude: number | null;
  country_name: string | null;
  admin1: string | null;
  admin2: string | null;
  city: string | null;
  district: string | null;
  formatted_address: string | null;
  created_at: string;
  updated_at: string;
}

export interface PhotoDetail extends Photo {
  exif: Record<string, string> | null;
  gps_latitude: number | null;
  gps_longitude: number | null;
  gps_altitude: number | null;
  country_code: string | null;
  country_name: string | null;
  admin1: string | null;
  admin2: string | null;
  city: string | null;
  district: string | null;
  formatted_address: string | null;
  location_source: string | null;
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
  next_cursor?: string | null;
  has_more?: boolean | null;
}

export interface PhotoDeleteResponse {
  project_id: number;
  photo_id: number;
  deleted_thumbnail: boolean;
  deleted_original: boolean;
  queued_original_for_trash: boolean;
  message: string;
}

export interface PhotoBatchDeleteRequest {
  photo_ids: number[];
  delete_original?: boolean;
}

export interface PhotoBatchDeleteResponse {
  project_id: number;
  requested_count: number;
  deleted_count: number;
  deleted_photo_ids: number[];
  not_found_photo_ids: number[];
  deleted_thumbnail_count: number;
  deleted_original_count: number;
  queued_original_for_trash_count: number;
  message: string;
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
  task_id: number | null;
  running: boolean;
  scanned: number;
  discovered_count: number;
  prepared_count: number;
  persisted_count: number;
  inserted: number;
  updated: number;
  errors: number;
  current_stage: string | null;
  current_path: string | null;
  queue_depth: number;
  last_stage_latency_ms: number | null;
  message: string;
  recent_errors: string[];
  recent_files: ScanFileProgressEntry[];
}

export interface ScanFileProgressEntry {
  path: string;
  status: string;
  message: string | null;
  timestamp: string;
}

// ─── Project Tasks ───────────────────────────────────────────────────────────

export interface ProjectTask {
  id: number;
  project_id: number;
  task_type: string;
  status: string;
  retry_count: number;
  request_params: Record<string, unknown> | null;
  progress_payload: Record<string, unknown> | null;
  result_payload: Record<string, unknown> | null;
  error_message: string | null;
  recent_errors: string[];
  failure_count: number;
  latest_failure: ProjectTaskFailureDetail | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProjectTaskFailureDetail {
  key: string;
  source: string;
  message: string;
  path: string | null;
  status: string | null;
  timestamp: string | null;
  details: Record<string, unknown> | null;
}

export interface ProjectTaskFailureListResponse {
  total: number;
  items: ProjectTaskFailureDetail[];
}

export interface ProjectTaskListResponse {
  total: number;
  items: ProjectTask[];
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
  semantic_concepts: string[] | null;
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
  analyzed_count?: number;
  total_photos?: number;
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
  evidence_level?: string;
  rank_reason?: string;
  filter_reason?: string | null;
  term_level_hits?: Record<string, string[]>;
  negative_hits?: string[];
  core_facet_passed?: boolean;
  score_breakdown?: Record<string, number>;
  field_scores?: {
    content?: number;
    caption?: number;
    tag?: number;
    ocr?: number;
  };
  explain?: {
    keyword?: {
      matched_fields: Record<string, string[]>;
      rank: number | null;
    };
    vector?: {
      field_scores: Record<string, number>;
      rank: number | null;
    };
  };
  // EXIF / Photo metadata fields
  camera_make?: string | null;
  camera_model?: string | null;
  lens_model?: string | null;
  focal_length?: string | null;
  aperture?: string | null;
  exposure_time?: string | null;
  iso?: number | null;
  gps_latitude?: number | null;
  gps_longitude?: number | null;
  country_name?: string | null;
  admin1?: string | null;
  admin2?: string | null;
  city?: string | null;
  district?: string | null;
  formatted_address?: string | null;
  face_count?: number | null;
  matched_people?: Array<Record<string, unknown>>;
}

export interface SearchTraceStep {
  stage: string;
  [key: string]: unknown;
}

export interface SearchDebugPayload {
  query_plan?: {
    intent?: string;
    exact_terms?: string[];
    expanded_terms?: string[];
    semantic_query_text?: string;
    query_planner?: Record<string, unknown>;
  };
  query_planner?: Record<string, unknown>;
  original_query: string;
  normalized_query: string;
  semantic_query_text?: string;
  exact_terms: string[];
  expanded_terms: string[];
  broad_terms: string[];
  support_terms?: string[];
  negative_terms?: string[];
  intent_facets?: Record<string, string[]>;
  matched_keys?: string[];
  core_facets?: string[];
  query_constraints?: Record<string, unknown>;
  intent: string;
  recommended_profile?: string;
  mode: string;
  embedding_model: string;
  embedding_dimension: number;
  keyword_candidates: number;
  concept_candidates?: number;
  people_visual_candidates?: number;
  vector_candidates: number;
  merged_candidates: number;
  fallback_reason?: string;
  filtered_candidates?: number;
  stale_embedding_filtered?: number;
  filtered_out_samples?: Array<{
    photo_id: number;
    evidence_level: string;
    filter_reason: string;
    vector_score: number;
    keyword_score: number;
  }>;
  // Metadata filter debug
  metadata_filters?: Record<string, unknown>;
  metadata_candidates?: number;
  metadata_only?: boolean;
  metadata_filter_active?: boolean;
  metadata_filter_skipped_reason?: string | null;
  metadata_only_allowed?: boolean;
  matched_metadata_terms?: string[];
  concept_terms?: string[];
  concept_entity_terms?: string[];
  concept_debug?: {
    enabled: boolean;
    reason: string;
    concept_terms: string[];
    concept_facets?: string[];
    entity_terms: string[];
    candidates: number;
    top_scores?: number[];
  };
  trace?: SearchTraceStep[];
  settings_snapshot?: {
    default_mode: string;
    keyword_top_k: number;
    vector_top_k: number;
    rrf_k: number;
    keyword_weight: number;
    vector_weight: number;
    vector_min_score: number;
    vector_strict_score: number;
    min_display_evidence_level: string;
    enable_evidence_filter: boolean;
    enable_negative_penalty: boolean;
    evidence_weight: number;
    negative_term_penalty: number;
    keyword_field_weights: Record<string, number>;
    vector_field_weights: Record<string, number>;
    ocr_vector_field_weights: Record<string, number>;
    enable_query_understanding: boolean;
    enable_structured_filters: boolean;
    enable_semantic_tag_boost: boolean;
  };
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
  location_clues?: TagCount[];
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
  ai_worker_concurrency: number;
}

export interface SystemHealthCheck {
  name: string;
  status: "ok" | "warn" | "fail";
  message: string;
}

export interface SystemHealthResponse {
  status: "ok" | "warn" | "fail";
  version: string;
  checks: SystemHealthCheck[];
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

export interface ProjectFaceSettings {
  id: number;
  project_id: number;
  face_recognition_enabled: boolean;
  face_provider: string;
  face_detector_model: string;
  face_embedding_model: string;
  face_runtime: string;
  store_face_crops: boolean;
  face_crop_storage: string;
  auto_accept_threshold: number;
  review_threshold: number;
  cluster_threshold: number;
  min_face_size: number;
  min_detection_confidence: number;
  min_quality_for_prototype: number;
  max_positive_samples_per_person: number;
  allow_auto_assignment: boolean;
  require_human_confirmation_for_new_person: boolean;
  enable_negative_constraints: boolean;
  enable_person_cannot_links: boolean;
  created_at: string;
  updated_at: string;
}

export type ProjectFaceSettingsUpdate = Partial<
  Omit<ProjectFaceSettings, "id" | "project_id" | "created_at" | "updated_at">
>;

export interface FaceEmbedding {
  id: number;
  project_id: number;
  face_detection_id: number;
  model_provider: string | null;
  model_name: string;
  model_version: string;
  embedding_dim: number;
  embedding_hash: string | null;
  embedded_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface FaceDetection {
  id: number;
  project_id: number;
  photo_id: number;
  bbox_x: number;
  bbox_y: number;
  bbox_w: number;
  bbox_h: number;
  detection_confidence: number | null;
  face_quality_score: number | null;
  face_crop_path: string | null;
  face_crop_hash: string | null;
  status: string;
  error_message: string | null;
  detected_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface FaceDetectionDetail extends FaceDetection {
  embeddings: FaceEmbedding[];
}

export interface FaceDetectionListResponse {
  total: number;
  page: number;
  page_size: number;
  items: FaceDetection[];
}

export interface FaceScanResponse {
  project_id: number;
  photo_id: number;
  provider: string;
  detector_model: string;
  embedding_model: string;
  faces_detected: number;
  detections_created: number;
  detections_updated: number;
  embeddings_created: number;
  embeddings_updated: number;
  auto_assigned: number;
  review_pending: number;
  failures: number;
  message: string;
  scan_source: string;
  scan_quality_degraded: boolean;
}

export interface FaceScanProjectStartRequest {
  scope?: "missing" | "failed" | "stale" | "all" | "selected";
  photo_ids?: number[];
  force?: boolean;
  dry_run?: boolean;
}

export interface FaceScanProjectStartResponse {
  project_id: number;
  task_id?: number | null;
  task_created?: boolean;
  task_status?: string | null;
  created_jobs: number;
  skipped_active_jobs: number;
  scope: "missing" | "failed" | "stale" | "all" | "selected";
  total_photos: number;
  candidate_count: number;
  skipped_already_scanned: number;
  skipped_other_project: number;
  stale_count: number;
  failed_count: number;
  dry_run: boolean;
  message: string;
}

export interface FaceScanProjectStatusResponse {
  queued: number;
  running: number;
  success: number;
  failed: number;
  total: number;
  task_id?: number | null;
  task_status?: string | null;
}

export interface FaceClusterUnknownRequest {
  max_faces?: number;
}

export interface FaceClusterUnknownStatusResponse {
  project_id: number;
  task_id: number | null;
  status: string;
  running: boolean;
  max_faces: number;
  clusters_created: number;
  persons_created: number;
  faces_clustered: number;
  assignments_created: number;
  errors: number;
  recent_errors: string[];
  message: string;
}

export interface FaceClusterUnknownResponse {
  message: string;
  status: FaceClusterUnknownStatusResponse;
}

export interface FaceRematchUnknownRequest {
  max_faces?: number;
  scope?: "unknown" | "person" | "time_range" | "project";
  person_id?: number;
  start_time?: string;
  end_time?: string;
}

export interface FaceRematchUnknownStatusResponse {
  project_id: number;
  task_id: number | null;
  status: string;
  running: boolean;
  max_faces: number;
  scope: "unknown" | "person" | "time_range" | "project";
  person_id: number | null;
  start_time: string | null;
  end_time: string | null;
  faces_considered: number;
  matched_faces: number;
  auto_assigned: number;
  review_pending: number;
  skipped_reason?: string | null;
  errors: number;
  recent_errors: string[];
  message: string;
}

export interface FaceRematchUnknownResponse {
  message: string;
  status: FaceRematchUnknownStatusResponse;
}

export interface PersonSummary {
  id: number;
  project_id: number;
  display_name: string;
  normalized_name: string | null;
  name_tags?: string[];
  is_named: boolean;
  representative_face_detection_id: number | null;
  sample_count: number;
  confirmed_sample_count: number;
  auto_assigned_count: number;
  review_pending_count: number;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface PersonFaceAssignment {
  id: number;
  project_id: number;
  person_id: number;
  face_detection_id: number;
  assignment_status: string;
  assignment_source: string;
  confidence: number | null;
  similarity_score: number | null;
  is_positive_sample: boolean;
  is_training_candidate: boolean;
  created_at: string;
  updated_at: string;
  explanation?: PersonMatchExplanation;
  face_detection: FaceDetection;
}

export interface PersonMatchExplanation {
  similarity: number | null;
  source: string;
  is_auto: boolean;
  is_human_confirmed: boolean;
  negative_constraint_affected: boolean;
  negative_constraint_count: number;
}

export interface PersonFeedbackEffects {
  prototype_rebuilt: boolean;
  rebuilt_person_ids: number[];
  unknown_rematch_requested: boolean;
  unknown_rematch_scope: "unknown" | "person" | "time_range" | "project" | null;
  unknown_rematch_person_id: number | null;
  unknown_rematch_task_id: number | null;
  unknown_rematch_task_created: boolean;
}

export interface PersonDetail extends PersonSummary {
  assignments: PersonFaceAssignment[];
  assignments_total?: number;
  assignments_limit?: number;
  assignments_has_more?: boolean;
}

export interface PersonListResponse {
  total: number;
  items: PersonSummary[];
}

export interface PersonActionResponse {
  person: PersonSummary;
  feedback_effects?: PersonFeedbackEffects;
}

export interface PersonMoveFaceRequest {
  target_person_id: number;
}

export interface PersonCreateRequest {
  display_name?: string;
  is_named?: boolean;
}

export interface PersonMergeRequest {
  target_person_id: number;
}

export interface PersonSplitRequest {
  face_detection_ids: number[];
  new_display_name?: string;
}

export interface PersonMoveFaceResponse {
  source_person: PersonSummary;
  target_person: PersonSummary;
  feedback_effects?: PersonFeedbackEffects;
}

export interface PersonMergeResponse {
  moved_assignments: number;
  source_person: PersonSummary;
  target_person: PersonSummary;
  feedback_effects?: PersonFeedbackEffects;
}

export interface PersonSplitResponse {
  moved_assignments: number;
  source_person: PersonSummary;
  target_person: PersonSummary;
  feedback_effects?: PersonFeedbackEffects;
}

export interface PersonReviewListResponse {
  total: number;
  items: PersonFaceAssignment[];
}

export interface PersonBatchReviewRequest {
  face_detection_ids: number[];
  request_id?: string;
  operator?: string;
  max_retries?: number;
}

export interface PersonBatchMoveRequest extends PersonBatchReviewRequest {
  target_person_id: number;
}

export interface PersonBatchActionResponse {
  updated: number;
  person: PersonSummary;
  feedback_effects?: PersonFeedbackEffects;
  request_id?: string | null;
  operator?: string | null;
  attempts?: number;
}

export interface PersonBatchMoveResponse {
  updated: number;
  source_person: PersonSummary;
  target_person: PersonSummary;
  feedback_effects?: PersonFeedbackEffects;
  request_id?: string | null;
  operator?: string | null;
  attempts?: number;
}

export interface ProjectAISettings {
  id: number;
  project_id: number;
  ai_service_profile_id: number | null;
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

export type SearchMode = "keyword" | "vector" | "hybrid" | "auto";

export type TagField =
  | "scene_tags"
  | "object_tags"
  | "activity_tags"
  | "quality_tags"
  | "search_keywords"
  | "location_clues";

export interface ProjectEmbeddingSettings {
  id: number;
  project_id: number;
  ai_service_profile_id: number | null;
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
  ai_service_profile_id?: number | null;
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

// ─── Project Search Settings ──────────────────────────────────────────────────

export interface ProjectSearchSettings {
  id: number;
  project_id: number;
  default_mode: string;
  keyword_top_k: number;
  vector_top_k: number;
  page_size_default: number;
  page_size_max: number;
  rrf_k: number;
  keyword_weight: number;
  vector_weight: number;
  vector_min_score: number;
  keyword_field_weights: Record<string, number> | null;
  vector_field_weights: Record<string, number> | null;
  ocr_query_vector_field_weights: Record<string, number> | null;
  enable_query_understanding: boolean;
  enable_structured_filters: boolean;
  enable_semantic_tag_boost: boolean;
  search_quality_settings?: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export type ProjectSearchSettingsUpdate = Partial<
  Omit<ProjectSearchSettings, 'id' | 'project_id' | 'created_at' | 'updated_at'>
>;

export interface EffectiveSettingValue<T = unknown> {
  value: T;
  source: string;
}

export interface ProjectEffectiveSettings {
  search: Record<string, EffectiveSettingValue>;
  ai?: Record<string, Record<string, EffectiveSettingValue>>;
}

// ─── Project Query Planner Settings ─────────────────────────────────────────

export interface ProjectQueryPlannerSettings {
  id: number;
  project_id: number;
  ai_service_profile_id: number | null;
  enabled: boolean;
  provider: string;
  endpoint_url: string | null;
  api_key: string | null;
  model_name: string | null;
  temperature: number;
  top_p: number;
  max_tokens: number;
  timeout_seconds: number;
  json_parse_strategy: string;
  planner_version: string;
  prompt_template: string | null;
  system_prompt: string | null;
  fallback_mode: string;
  created_at: string;
  updated_at: string;
}

export type ProjectQueryPlannerSettingsUpdate = Partial<
  Omit<ProjectQueryPlannerSettings, "id" | "project_id" | "created_at" | "updated_at">
>;

export interface QueryPlannerTestResponse {
  query: string;
  planner_debug: Record<string, unknown>;
  parsed_query_plan: Record<string, unknown>;
}

// ─── Photo Quarantine ─────────────────────────────────────────────────

export interface ProjectPhotoQuarantineSettings {
  id: number;
  project_id: number;
  enabled: boolean;
  dry_run: boolean;
  start_hour: number;
  end_hour: number;
  timezone: string;
  model_name: string;
  retention_days: number;
  created_at: string;
  updated_at: string;
}

export type ProjectPhotoQuarantineSettingsUpdate = Omit<
  ProjectPhotoQuarantineSettings,
  "id" | "project_id" | "created_at" | "updated_at"
>;

export interface PhotoQuarantineItem {
  id: number;
  project_id: number;
  photo_id: number;
  status: string;
  decision: string;
  classification: string;
  confidence: number;
  reason: string;
  preservation_flags: string[];
  content_rating?: "SAFE" | "SENSITIVE" | "ADULT";
  sensitive_content_flags?: string[];
  first_result: Record<string, unknown>;
  verification_result: Record<string, unknown> | null;
  model_name: string;
  prompt_version: string;
  original_path: string;
  quarantine_path: string | null;
  content_hash: string | null;
  moved_at: string | null;
  restored_at: string | null;
  deleted_confirmed_at: string | null;
  human_label: "KEEP" | "TRASH" | null;
  human_label_note: string | null;
  human_labeled_by: string | null;
  human_labeled_at: string | null;
  last_error: string | null;
  created_at: string;
  updated_at: string;
}

export interface PhotoQuarantineListResponse {
  total: number;
  items: PhotoQuarantineItem[];
  classification_counts?: Record<string, number>;
}

export type PhotoQuarantineBatchAction =
  | "KEEP"
  | "REQUEST_DELETE"
  | "MOVE"
  | "RESTORE"
  | "RETRY_ANALYSIS"
  | "LABEL_KEEP"
  | "LABEL_TRASH";

export interface PhotoQuarantineBatchItemResult {
  item_id: number;
  succeeded: boolean;
  item: PhotoQuarantineItem | null;
  error_code: string | null;
  message: string | null;
}

export interface PhotoQuarantineBatchResponse {
  requested: number;
  succeeded: number;
  failed: number;
  results: PhotoQuarantineBatchItemResult[];
}

export interface PhotoQuarantineReconciliationResponse {
  checked: number;
  confirmed: number;
  remaining: number;
  failed: number;
}

export interface PhotoQuarantineCalibrationCategory {
  classification: string;
  labeled_total: number;
  human_keep: number;
  human_trash: number;
  true_positive: number;
  false_positive: number;
  true_negative: number;
  false_negative: number;
}

export interface PhotoQuarantineCalibrationResponse {
  labeled_total: number;
  human_keep: number;
  human_trash: number;
  true_positive: number;
  false_positive: number;
  true_negative: number;
  false_negative: number;
  precision: number | null;
  recall: number | null;
  false_positive_rate: number | null;
  target_sample_size: number;
  minimum_per_label: number;
  sample_target_met: boolean;
  class_balance_met: boolean;
  zero_false_positive_met: boolean;
  ready_for_auto_move: boolean;
  categories: PhotoQuarantineCalibrationCategory[];
}
