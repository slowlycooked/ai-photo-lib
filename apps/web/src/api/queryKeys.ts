export const queryKeys = {
  projects: () => ["projects"] as const,
  settings: () => ["settings"] as const,
  settingsDebug: () => ["settings", "debug"] as const,
  aiStatus: (projectId: number | null) => ["ai-status", projectId] as const,
  photosBase: (projectId: number | null) => ["photos", projectId] as const,
  projectPhotoAiBase: (projectId: number | null) => ["project-photo-ai", projectId] as const,
  projectPhotoAi: (projectId: number | null, photoId: number | null) =>
    ["project-photo-ai", projectId, photoId] as const,
  projectScanStatus: (projectId: number | null) => ["project-scan-status", projectId] as const,
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
