export const queryKeys = {
  projects: () => ["projects"] as const,
  settings: () => ["settings"] as const,
  settingsDebug: () => ["settings", "debug"] as const,
  aiStatus: (projectId: number | null) => ["ai-status", projectId] as const,
  photosBase: (projectId: number | null) => ["photos", projectId] as const,
  projectPhotoAiBase: (projectId: number | null) => ["project-photo-ai", projectId] as const,
  projectPhotoAi: (projectId: number | null, photoId: number | null) =>
    ["project-photo-ai", projectId, photoId] as const,
  projectPhotoDetail: (projectId: number | null, photoId: number | null) =>
    ["project-photo-detail", projectId, photoId] as const,
  projectFaces: (projectId: number | null, photoId?: number | null, status?: string | null) =>
    ["project-faces", projectId, photoId ?? null, status ?? null] as const,
  projectFace: (projectId: number | null, faceId: number | null) =>
    ["project-face", projectId, faceId] as const,
  projectPeople: (projectId: number | null, includeUnnamed?: boolean) =>
    ["project-people", projectId, includeUnnamed ?? true] as const,
  projectPerson: (projectId: number | null, personId: number | null) =>
    ["project-person", projectId, personId] as const,
  projectScanStatus: (projectId: number | null) => ["project-scan-status", projectId] as const,
  projectTasks: (projectId: number | null, limit = 20) =>
    ["project-tasks", projectId, limit] as const,
  photoQuarantineSettings: (projectId: number | null) =>
    ["photo-quarantine-settings", projectId] as const,
  photoQuarantineItems: (projectId: number | null, status?: string, offset = 0) =>
    ["photo-quarantine-items", projectId, status ?? null, offset] as const,
  projectTaskFailures: (projectId: number | null, taskId: number | null, limit = 20, offset = 0) =>
    ["project-task-failures", projectId, taskId, limit, offset] as const,
  photos: (
    projectId: number | null,
    dateFrom?: string | null,
    dateTo?: string | null,
    folderId?: number | null,
    folderScope?: string,
  ) => ["photos", projectId, dateFrom ?? null, dateTo ?? null, folderId ?? null, folderScope ?? null] as const,
  timeline: (projectId: number | null, folderId?: number | null, folderScope?: string) =>
    ["timeline", projectId, folderId ?? null, folderScope ?? null] as const,
  tags: (projectId: number | null) => ["tags", projectId] as const,
};
