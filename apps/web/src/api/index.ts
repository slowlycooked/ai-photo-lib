/**
 * Main API entry point.
 *
 * Assembles the `api` object from all domain modules and re-exports all
 * types so existing imports of the form:
 *
 *   import { api, Photo, Project, ... } from "@/api"
 *
 * continue to work unchanged (backward-compatible via the re-export in
 * src/lib/api.ts).
 */

export { ApiError } from "./client";
export type {
  AIAnalysis,
  AIJob,
  AIJobListResponse,
  AIStatus,
  AppSettings,
  DebugMatrix,
  DebugMode,
  DebugPresetMode,
  DebugSettingsResponse,
  DebugSettingsUpdate,
  EmbeddingStatusResponse,
  EmbeddingTestRequest,
  EmbeddingTestResponse,
  EffectiveSettingValue,
  FaceDetection,
  FaceDetectionDetail,
  FaceDetectionListResponse,
  FaceEmbedding,
  FaceScanResponse,
  FolderBreadcrumbItem,
  FolderBreadcrumbResponse,
  FolderNode,
  FolderScope,
  FolderTreeResponse,
  LogLevel,
  Photo,
  PhotoBatchDeleteRequest,
  PhotoBatchDeleteResponse,
  PhotoDetail,
  PhotoListResponse,
  PhotoQuarantineItem,
  PhotoQuarantineBatchAction,
  PhotoQuarantineBatchItemResult,
  PhotoQuarantineBatchResponse,
  PhotoQuarantineListResponse,
  PersonDetail,
  PersonActionResponse,
  PersonBatchActionResponse,
  PersonBatchMoveRequest,
  PersonBatchMoveResponse,
  PersonBatchReviewRequest,
  PersonCreateRequest,
  PersonFaceAssignment,
  PersonListResponse,
  PersonMergeRequest,
  PersonMergeResponse,
  PersonMoveFaceRequest,
  PersonMoveFaceResponse,
  PersonReviewListResponse,
  PersonSplitRequest,
  PersonSplitResponse,
  PersonSummary,
  Project,
  ProjectAISettings,
  ProjectCreate,
  ProjectEmbeddingSettings,
  ProjectEmbeddingSettingsUpdate,
  ProjectEffectiveSettings,
  ProjectFaceSettings,
  ProjectFaceSettingsUpdate,
  ProjectListResponse,
  ProjectReadinessCheck,
  ProjectReadinessResponse,
  QueryPlannerTestResponse,
  ProjectQueryPlannerSettings,
  ProjectQueryPlannerSettingsUpdate,
  ProjectPhotoQuarantineSettings,
  ProjectPhotoQuarantineSettingsUpdate,
  ProjectSearchSettings,
  ProjectSearchSettingsUpdate,
  ProjectTask,
  ProjectTaskFailureDetail,
  ProjectTaskFailureListResponse,
  ProjectTaskListResponse,
  ProjectUpdate,
  PromptTemplate,
  PromptTemplateCreate,
  PromptTemplateListResponse,
  PromptTemplateTestRequest,
  PromptTemplateTestResponse,
  PromptTemplateUpdate,
  RebuildRequest,
  RebuildResponse,
  RebuildScope,
  ScanStatus,
  SearchDebugPayload,
  SearchMode,
  SearchResponse,
  SearchResultItem,
  SystemHealthCheck,
  SystemHealthResponse,
  TagCount,
  TagsResponse,
  TimelineItem,
  TimelineResponse,
} from "./types";
export type { AuthSession } from "./auth";
export type {
  AIServiceProfile,
  AIServiceProfileCreate,
  AIServiceProfileListResponse,
  AIServiceProfileUpdate,
  AICapability,
  ProjectMembershipListResponse,
  ProjectMembershipResponse,
  ProjectRole,
  SystemRole,
  UserCreate,
  UserListResponse,
  UserResponse,
  UserUpdate,
} from "./admin";
export {
  DEFAULT_DEBUG_PRESETS,
  normaliseDebugMode,
  normaliseDebugSettingsResponse,
  normaliseLogLevel,
  normaliseMatrix,
  normalisePresets,
} from "./settings.helpers";
export { foldersApi } from "./folders";
export { projectAiJobsApi } from "./projectAiJobs";
export { projectCoreApi } from "./projectCore";
export { projectFacesApi } from "./projectFaces";
export { projectPeopleApi } from "./projectPeople";
export { projectPhotosApi } from "./projectPhotos";
export { projectPromptsApi } from "./projectPrompts";
export { projectScansApi } from "./projectScans";
export { projectSearchApi } from "./projectSearch";
export { projectSettingsApi } from "./projectSettings";
export { projectTasksApi } from "./projectTasks";
export { photoQuarantineApi } from "./photoQuarantine";
export { settingsApi } from "./settings";
export { adminApi } from "./admin";

import * as authApi from "./auth";
import { adminApi } from "./admin";
import { foldersApi } from "./folders";
import { projectAiJobsApi } from "./projectAiJobs";
import { projectCoreApi } from "./projectCore";
import { projectFacesApi } from "./projectFaces";
import { projectPeopleApi } from "./projectPeople";
import { projectPhotosApi } from "./projectPhotos";
import { projectPromptsApi } from "./projectPrompts";
import { projectScansApi } from "./projectScans";
import { projectSearchApi } from "./projectSearch";
import { projectSettingsApi } from "./projectSettings";
import { projectTasksApi } from "./projectTasks";
import { photoQuarantineApi } from "./photoQuarantine";
import { settingsApi } from "./settings";

/**
 * Namespaced API object — preferred usage.
 *
 * api.projectCore.list()
 * api.projectPhotos.list(id, page, pageSize)
 * api.projectPrompts.list(id)
 * api.projectSearch.search(id, query)
 * api.projectScans.status(id)
 * api.projectAiJobs.status(id)
 * api.projectFaces.list(id)
 * api.projectPeople.list(id)
 * api.projectTasks.list(id)
 * api.projectSettings.getAi(id)
 * api.folders.tree(projectId)
 * api.settings.getDebug()
 */
export const api = {
  auth: authApi,
  projectCore: projectCoreApi,
  projectAiJobs: projectAiJobsApi,
  projectFaces: projectFacesApi,
  projectPeople: projectPeopleApi,
  projectPhotos: projectPhotosApi,
  projectPrompts: projectPromptsApi,
  projectScans: projectScansApi,
  projectSearch: projectSearchApi,
  projectSettings: projectSettingsApi,
  projectTasks: projectTasksApi,
  photoQuarantine: photoQuarantineApi,
  folders: foldersApi,
  settings: settingsApi,
  admin: adminApi,
} as const;

export { authApi };
