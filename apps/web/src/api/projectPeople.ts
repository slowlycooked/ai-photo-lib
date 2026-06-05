import { request, qs } from "./client";
import type {
  PersonActionResponse,
  PersonBatchActionResponse,
  PersonBatchMoveRequest,
  PersonBatchMoveResponse,
  PersonBatchReviewRequest,
  PersonCreateRequest,
  PersonDetail,
  PersonListResponse,
  PersonMergeRequest,
  PersonMergeResponse,
  PersonMoveFaceRequest,
  PersonMoveFaceResponse,
  PersonReviewListResponse,
  PersonSplitRequest,
  PersonSplitResponse,
} from "./types";

export interface ProjectPeopleFilters {
  is_named?: boolean;
  has_review_pending?: boolean;
  min_sample_count?: number;
  min_auto_assigned_count?: number;
  q?: string;
}

export const projectPeopleApi = {
  list: (
    projectId: number,
    includeUnnamed = true,
    limit = 200,
    filters?: ProjectPeopleFilters,
  ) =>
    request<PersonListResponse>(
      `/projects/${projectId}/people${qs({
        include_unnamed: includeUnnamed,
        limit,
        is_named: filters?.is_named,
        has_review_pending: filters?.has_review_pending,
        min_sample_count: filters?.min_sample_count,
        min_auto_assigned_count: filters?.min_auto_assigned_count,
        q: filters?.q,
      })}`,
    ),

  create: (projectId: number, body: PersonCreateRequest) =>
    request<PersonActionResponse>(`/projects/${projectId}/people`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  get: (projectId: number, personId: number, assignmentLimit = 120) =>
    request<PersonDetail>(
      `/projects/${projectId}/people/${personId}${qs({ assignment_limit: assignmentLimit })}`,
    ),

  rename: (projectId: number, personId: number, displayName: string) =>
    request<PersonActionResponse>(`/projects/${projectId}/people/${personId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ display_name: displayName }),
    }),

  delete: (projectId: number, personId: number) =>
    request<{ deleted: boolean; message: string }>(
      `/projects/${projectId}/people/${personId}`,
      { method: "DELETE" },
    ),

  confirmFace: (projectId: number, personId: number, faceId: number) =>
    request<PersonActionResponse>(
      `/projects/${projectId}/people/${personId}/faces/${faceId}/confirm`,
      { method: "POST" },
    ),

  rejectFace: (projectId: number, personId: number, faceId: number) =>
    request<PersonActionResponse>(
      `/projects/${projectId}/people/${personId}/faces/${faceId}/reject`,
      { method: "POST" },
    ),

  moveFace: (
    projectId: number,
    personId: number,
    faceId: number,
    body: PersonMoveFaceRequest,
  ) =>
    request<PersonMoveFaceResponse>(
      `/projects/${projectId}/people/${personId}/faces/${faceId}/move`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      },
    ),

  merge: (projectId: number, sourcePersonId: number, body: PersonMergeRequest) =>
    request<PersonMergeResponse>(
      `/projects/${projectId}/people/${sourcePersonId}/merge`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      },
    ),

  split: (projectId: number, personId: number, body: PersonSplitRequest) =>
    request<PersonSplitResponse>(`/projects/${projectId}/people/${personId}/split`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  setRepresentativeFace: (projectId: number, personId: number, faceDetectionId: number) =>
    request<PersonActionResponse>(
      `/projects/${projectId}/people/${personId}/representative-face`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ face_detection_id: faceDetectionId }),
      },
    ),

  reviewPending: (
    projectId: number,
    personId?: number | null,
    limit = 200,
    offset = 0,
  ) =>
    request<PersonReviewListResponse>(
      `/projects/${projectId}/people/review${qs({
        person_id: personId ?? undefined,
        limit,
        offset,
      })}`,
    ),

  batchConfirmReview: (
    projectId: number,
    personId: number,
    body: PersonBatchReviewRequest,
  ) =>
    request<PersonBatchActionResponse>(
      `/projects/${projectId}/people/${personId}/review/batch-confirm`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      },
    ),

  batchRejectReview: (
    projectId: number,
    personId: number,
    body: PersonBatchReviewRequest,
  ) =>
    request<PersonBatchActionResponse>(
      `/projects/${projectId}/people/${personId}/review/batch-reject`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      },
    ),

  batchMoveReview: (
    projectId: number,
    personId: number,
    body: PersonBatchMoveRequest,
  ) =>
    request<PersonBatchMoveResponse>(
      `/projects/${projectId}/people/${personId}/review/batch-move`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      },
    ),
};
