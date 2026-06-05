import { qs, request } from "./client";
import type {
  FolderScope,
  SearchMode,
  SearchResponse,
  TagField,
  TagsResponse,
} from "./types";

export const projectSearchApi = {
  search: (
    projectId: number,
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
      `/projects/${projectId}/search${qs({
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

  tags: (projectId: number) => request<TagsResponse>(`/projects/${projectId}/tags`),
};
