/**
 * Main API entry point.
 *
 * Assembles the `api` object from all domain modules and re-exports all
 * types so existing imports of the form:
 *
 *   import { api, Photo, Project, ... } from "@/lib/api"
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
  FolderBreadcrumbItem,
  FolderBreadcrumbResponse,
  FolderNode,
  FolderScope,
  FolderTreeResponse,
  LogLevel,
  Photo,
  PhotoDetail,
  PhotoListResponse,
  Project,
  ProjectAISettings,
  ProjectAISettingsUpdate,
  ProjectCreate,
  ProjectEmbeddingSettings,
  ProjectEmbeddingSettingsUpdate,
  ProjectListResponse,
  ProjectSearchSettings,
  ProjectSearchSettingsUpdate,
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
  TagCount,
  TagsResponse,
  TimelineItem,
  TimelineResponse,
} from "./types";
export {
  DEFAULT_DEBUG_PRESETS,
  normaliseDebugMode,
  normaliseDebugSettingsResponse,
  normaliseLogLevel,
  normaliseMatrix,
  normalisePresets,
} from "./settings.helpers";
export { foldersApi } from "./folders";
export { projectsApi } from "./projects";
export { settingsApi } from "./settings";

import { foldersApi } from "./folders";
import { projectsApi } from "./projects";
import { settingsApi } from "./settings";

/**
 * Namespaced API object — preferred usage.
 *
 * api.projects.list()
 * api.projects.photos(id, page, pageSize)
 * api.folders.tree(projectId)
 * api.settings.getDebug()
 */
export const api = {
  projects: projectsApi,
  folders: foldersApi,
  settings: settingsApi,
} as const;
