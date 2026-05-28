import { ApiError, request, qs, BASE } from "./client";
import type {
  AIAnalysis,
  AIJobListResponse,
  AIStatus,
  EmbeddingStatusResponse,
  EmbeddingTestRequest,
  EmbeddingTestResponse,
  FaceClusterUnknownRequest,
  FaceClusterUnknownResponse,
  FaceClusterUnknownStatusResponse,
  FaceDetectionDetail,
  FaceDetectionListResponse,
  FaceRematchUnknownRequest,
  FaceRematchUnknownResponse,
  FaceRematchUnknownStatusResponse,
  FaceScanProjectStartRequest,
  FaceScanProjectStartResponse,
  FaceScanProjectStatusResponse,
  FaceScanResponse,
  FolderScope,
  PhotoDetail,
  PhotoDeleteResponse,
  PhotoListResponse,
  PersonDetail,
  PersonActionResponse,
  PersonBatchActionResponse,
  PersonBatchMoveRequest,
  PersonBatchMoveResponse,
  PersonBatchReviewRequest,
  PersonCreateRequest,
  PersonMoveFaceRequest,
  PersonMergeRequest,
  PersonMergeResponse,
  PersonMoveFaceResponse,
  PersonReviewListResponse,
  PersonListResponse,
  PersonSplitRequest,
  PersonSplitResponse,
  ProjectAISettings,
  ProjectAISettingsUpdate,
  ProjectCreate,
  ProjectEmbeddingSettings,
  ProjectEmbeddingSettingsUpdate,
  ProjectReadinessResponse,
  ProjectFaceSettings,
  ProjectFaceSettingsUpdate,
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

  readiness: (id: number) =>
    request<ProjectReadinessResponse>(`/projects/${id}/readiness`),

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

  aiJobs: (
    id: number,
    status?: string,
    limit = 50,
    offset = 0,
    jobType?: string,
  ) =>
    request<AIJobListResponse>(
      `/projects/${id}/ai/jobs${qs({ status, limit, offset, job_type: jobType })}`,
    ),

  retryFailedAiJobs: (id: number, jobType?: string) =>
    request<{
      retried_jobs: number;
      message: string;
      task_id?: number | null;
      task_created?: boolean;
      task_status?: string | null;
    }>(
      `/projects/${id}/ai/jobs/retry-failed${qs({ job_type: jobType })}`,
      { method: "POST" },
    ),

  clearFailedAiJobs: (id: number, jobType?: string) =>
    request<{ deleted_jobs: number; message: string }>(
      `/projects/${id}/ai/jobs/failed${qs({ job_type: jobType })}`,
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

  initAiSettings: (id: number) =>
    request<ProjectAISettings>(`/projects/${id}/ai-settings/init`, {
      method: "POST",
    }),

  updateAiSettings: (id: number, body: ProjectAISettingsUpdate) =>
    request<ProjectAISettings>(`/projects/${id}/ai-settings`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  // ── Face Settings ─────────────────────────────────────────────────────────

  getFaceSettings: (id: number) =>
    request<ProjectFaceSettings>(`/projects/${id}/face-settings`),

  updateFaceSettings: (id: number, body: ProjectFaceSettingsUpdate) =>
    request<ProjectFaceSettings>(`/projects/${id}/face-settings`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  resetFaceSettings: (id: number) =>
    request<ProjectFaceSettings>(`/projects/${id}/face-settings/reset`, {
      method: "POST",
    }),

  scanPhotoFaces: (id: number, photoId: number) =>
    request<FaceScanResponse>(`/projects/${id}/photos/${photoId}/face-scan`, {
      method: "POST",
    }),

  startProjectFaceScan: (id: number, body: FaceScanProjectStartRequest = {}) =>
    request<FaceScanProjectStartResponse>(`/projects/${id}/face-scan-project/start`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  projectFaceScanStatus: (id: number) =>
    request<FaceScanProjectStatusResponse>(`/projects/${id}/face-scan-project/status`),

  clusterUnknownFaces: (id: number, body: FaceClusterUnknownRequest = {}) =>
    request<FaceClusterUnknownResponse>(`/projects/${id}/face-cluster-unknown`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  projectFaceClusterUnknownStatus: (id: number) =>
    request<FaceClusterUnknownStatusResponse>(`/projects/${id}/face-cluster-unknown/status`),

  rematchUnknownFaces: (id: number, body: FaceRematchUnknownRequest = {}) =>
    request<FaceRematchUnknownResponse>(`/projects/${id}/face-rematch-unknown`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  projectFaceRematchUnknownStatus: (id: number) =>
    request<FaceRematchUnknownStatusResponse>(`/projects/${id}/face-rematch-unknown/status`),

  faces: (
    id: number,
    page = 1,
    pageSize = 50,
    photoId?: number | null,
    status?: string | null,
  ) =>
    request<FaceDetectionListResponse>(
      `/projects/${id}/faces${qs({
        page,
        page_size: pageSize,
        photo_id: photoId,
        status: status ?? undefined,
      })}`,
    ),

  face: (id: number, faceId: number) =>
    request<FaceDetectionDetail>(`/projects/${id}/faces/${faceId}`),

  faceCropUrl: (id: number, faceId: number, updatedAt?: string | null) => {
    const base = `${BASE}/projects/${id}/faces/${faceId}/crop`;
    if (!updatedAt) return base;
    const version = Date.parse(updatedAt);
    return Number.isNaN(version) ? base : `${base}?v=${version}`;
  },

  people: (
    id: number,
    includeUnnamed = true,
    limit = 200,
    filters?: {
      is_named?: boolean;
      has_review_pending?: boolean;
      min_sample_count?: number;
      min_auto_assigned_count?: number;
      q?: string;
    },
  ) =>
    request<PersonListResponse>(
      `/projects/${id}/people${qs({
        include_unnamed: includeUnnamed,
        limit,
        is_named: filters?.is_named,
        has_review_pending: filters?.has_review_pending,
        min_sample_count: filters?.min_sample_count,
        min_auto_assigned_count: filters?.min_auto_assigned_count,
        q: filters?.q,
      })}`,
    ),

  createPerson: (id: number, body: PersonCreateRequest) =>
    request<PersonActionResponse>(`/projects/${id}/people`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  person: (id: number, personId: number, assignmentLimit = 120) =>
    request<PersonDetail>(
      `/projects/${id}/people/${personId}${qs({ assignment_limit: assignmentLimit })}`,
    ),

  renamePerson: (id: number, personId: number, displayName: string) =>
    request<PersonActionResponse>(`/projects/${id}/people/${personId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ display_name: displayName }),
    }),

  deletePerson: (id: number, personId: number) =>
    request<{ deleted: boolean; message: string }>(`/projects/${id}/people/${personId}`, {
      method: "DELETE",
    }),

  confirmPersonFace: (id: number, personId: number, faceId: number) =>
    request<PersonActionResponse>(`/projects/${id}/people/${personId}/faces/${faceId}/confirm`, {
      method: "POST",
    }),

  rejectPersonFace: (id: number, personId: number, faceId: number) =>
    request<PersonActionResponse>(`/projects/${id}/people/${personId}/faces/${faceId}/reject`, {
      method: "POST",
    }),

  movePersonFace: (
    id: number,
    personId: number,
    faceId: number,
    body: PersonMoveFaceRequest,
  ) =>
    request<PersonMoveFaceResponse>(`/projects/${id}/people/${personId}/faces/${faceId}/move`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  mergePerson: (id: number, sourcePersonId: number, body: PersonMergeRequest) =>
    request<PersonMergeResponse>(`/projects/${id}/people/${sourcePersonId}/merge`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  splitPerson: (id: number, personId: number, body: PersonSplitRequest) =>
    request<PersonSplitResponse>(`/projects/${id}/people/${personId}/split`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  setPersonRepresentativeFace: (id: number, personId: number, faceDetectionId: number) =>
    request<PersonActionResponse>(`/projects/${id}/people/${personId}/representative-face`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ face_detection_id: faceDetectionId }),
    }),

  reviewPending: (id: number, personId?: number | null, limit = 200, offset = 0) =>
    request<PersonReviewListResponse>(
      `/projects/${id}/people/review${qs({ person_id: personId ?? undefined, limit, offset })}`,
    ),

  batchConfirmReview: (id: number, personId: number, body: PersonBatchReviewRequest) =>
    request<PersonBatchActionResponse>(`/projects/${id}/people/${personId}/review/batch-confirm`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  batchRejectReview: (id: number, personId: number, body: PersonBatchReviewRequest) =>
    request<PersonBatchActionResponse>(`/projects/${id}/people/${personId}/review/batch-reject`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  batchMoveReview: (id: number, personId: number, body: PersonBatchMoveRequest) =>
    request<PersonBatchMoveResponse>(`/projects/${id}/people/${personId}/review/batch-move`, {
      method: "POST",
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
    faceCountMin?: number | null,
    faceCountMax?: number | null,
    hasReviewPending?: boolean | null,
    hasUnnamedPeople?: boolean | null,
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
        face_count_min: faceCountMin ?? undefined,
        face_count_max: faceCountMax ?? undefined,
        has_review_pending: hasReviewPending ?? undefined,
        has_unnamed_people: hasUnnamedPeople ?? undefined,
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

  deletePhotoRecord: async (id: number, photoId: number, deleteOriginal = false) => {
    const query = qs({ delete_original: deleteOriginal || undefined });
    try {
      return await request<PhotoDeleteResponse>(
        `/projects/${id}/photos/${photoId}${query}`,
        { method: "DELETE" },
      );
    } catch (error) {
      if (error instanceof ApiError && error.status === 405) {
        return request<PhotoDeleteResponse>(
          `/projects/${id}/photos/${photoId}/delete${query}`,
          { method: "POST" },
        );
      }
      throw error;
    }
  },

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
