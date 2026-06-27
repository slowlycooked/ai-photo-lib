import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import type { PersonFaceAssignment } from "@/api";
import { api } from "@/api";
import { useProjectContext } from "@/contexts/ProjectContext";
import { formatBatchFeedbackToast } from "@/lib/peopleFeedback";
import { isArchivedPerson } from "@/lib/personArchive";

const PAGE_SIZE = 40;

function buildRequestId(): string {
  try {
    if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
      return crypto.randomUUID();
    }
  } catch {
    // Ignore and fallback.
  }
  return `req-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function usePeopleReviewPage() {
  const params = useParams<{ projectId: string }>();
  const routeProjectId = Number(params.projectId);
  const { currentProject } = useProjectContext();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [moveTargets, setMoveTargets] = useState<Record<number, number>>({});

  const selectedProjectId = Number.isFinite(routeProjectId)
    ? routeProjectId
    : (currentProject?.id ?? 0);

  const { data: peopleData } = useQuery({
    queryKey: ["project-people", selectedProjectId],
    queryFn: () => api.projectPeople.list(selectedProjectId, true, 500),
    enabled: selectedProjectId > 0,
  });

  const { data: reviewData, isLoading, isFetching, error } = useQuery({
    queryKey: ["project-review-page", selectedProjectId, page],
    queryFn: () =>
      api.projectPeople.reviewPending(selectedProjectId, null, PAGE_SIZE, (page - 1) * PAGE_SIZE),
    enabled: selectedProjectId > 0,
    placeholderData: (previousData) => previousData,
  });

  const peopleById = useMemo(() => {
    const map = new Map<number, string>();
    for (const person of peopleData?.items ?? []) {
      map.set(person.id, person.display_name);
    }
    return map;
  }, [peopleData?.items]);

  const archivedPersonIds = useMemo(() => {
    const ids = new Set<number>();
    for (const person of peopleData?.items ?? []) {
      if (isArchivedPerson(person)) {
        ids.add(person.id);
      }
    }
    return ids;
  }, [peopleData?.items]);

  const grouped = useMemo(() => {
    const map = new Map<number, PersonFaceAssignment[]>();
    for (const item of reviewData?.items ?? []) {
      const list = map.get(item.person_id) ?? [];
      list.push(item);
      map.set(item.person_id, list);
    }
    return Array.from(map.entries()).sort((a, b) => b[1].length - a[1].length);
  }, [reviewData?.items]);

  const groupedManaged = useMemo(
    () => grouped.filter(([personId]) => !archivedPersonIds.has(personId)),
    [archivedPersonIds, grouped],
  );

  const groupedArchived = useMemo(
    () => grouped.filter(([personId]) => archivedPersonIds.has(personId)),
    [archivedPersonIds, grouped],
  );

  const maxPage = Math.max(1, Math.ceil((reviewData?.total ?? 0) / PAGE_SIZE));

  const invalidateReviewQueries = () => {
    queryClient.invalidateQueries({ queryKey: ["project-review-page", selectedProjectId] });
    queryClient.invalidateQueries({ queryKey: ["project-people", selectedProjectId] });
  };

  const batchConfirmMutation = useMutation({
    mutationFn: (params: { personId: number; faceIds: number[] }) =>
      api.projectPeople.batchConfirmReview(selectedProjectId, params.personId, {
        face_detection_ids: params.faceIds,
        request_id: buildRequestId(),
        operator: "web_review_page",
        max_retries: 3,
      }),
    onSuccess: (result) => {
      setStatusMessage(
        formatBatchFeedbackToast(
          "批量确认",
          result.updated,
          result.attempts ?? 1,
          result.feedback_effects,
        ),
      );
      setErrorMessage(null);
      invalidateReviewQueries();
    },
    onError: (err) => {
      setStatusMessage(null);
      setErrorMessage((err as Error).message);
    },
  });

  const batchRejectMutation = useMutation({
    mutationFn: (params: { personId: number; faceIds: number[] }) =>
      api.projectPeople.batchRejectReview(selectedProjectId, params.personId, {
        face_detection_ids: params.faceIds,
        request_id: buildRequestId(),
        operator: "web_review_page",
        max_retries: 3,
      }),
    onSuccess: (result) => {
      setStatusMessage(
        formatBatchFeedbackToast(
          "批量排除",
          result.updated,
          result.attempts ?? 1,
          result.feedback_effects,
        ),
      );
      setErrorMessage(null);
      invalidateReviewQueries();
    },
    onError: (err) => {
      setStatusMessage(null);
      setErrorMessage((err as Error).message);
    },
  });

  const batchMoveMutation = useMutation({
    mutationFn: (params: { personId: number; targetPersonId: number; faceIds: number[] }) =>
      api.projectPeople.batchMoveReview(selectedProjectId, params.personId, {
        face_detection_ids: params.faceIds,
        target_person_id: params.targetPersonId,
        request_id: buildRequestId(),
        operator: "web_review_page",
        max_retries: 3,
      }),
    onSuccess: (result) => {
      setStatusMessage(
        formatBatchFeedbackToast(
          "批量移动",
          result.updated,
          result.attempts ?? 1,
          result.feedback_effects,
        ),
      );
      setErrorMessage(null);
      invalidateReviewQueries();
    },
    onError: (err) => {
      setStatusMessage(null);
      setErrorMessage((err as Error).message);
    },
  });

  const actionBusy =
    batchConfirmMutation.isPending ||
    batchRejectMutation.isPending ||
    batchMoveMutation.isPending;

  return {
    routeProjectId,
    currentProject,
    selectedProjectId,
    page,
    setPage,
    statusMessage,
    errorMessage,
    grouped: groupedManaged,
    groupedArchived,
    peopleData,
    peopleById,
    reviewData,
    isLoading,
    isFetching,
    error,
    maxPage,
    moveTargets,
    setMoveTargets,
    actionBusy,
    batchConfirmReview: (personId: number, faceIds: number[]) =>
      batchConfirmMutation.mutate({ personId, faceIds }),
    batchRejectReview: (personId: number, faceIds: number[]) =>
      batchRejectMutation.mutate({ personId, faceIds }),
    batchMoveReview: (personId: number, targetPersonId: number, faceIds: number[]) =>
      batchMoveMutation.mutate({ personId, targetPersonId, faceIds }),
  };
}
