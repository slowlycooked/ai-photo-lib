import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import type { PersonFaceAssignment } from "@/api";
import { api } from "@/api";
import { useProjectContext } from "@/contexts/ProjectContext";

const PAGE_SIZE = 80;

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
    queryFn: () => api.projects.people(selectedProjectId, true, 500),
    enabled: selectedProjectId > 0,
  });

  const { data: reviewData, isLoading, error } = useQuery({
    queryKey: ["project-review-page", selectedProjectId, page],
    queryFn: () =>
      api.projects.reviewPending(selectedProjectId, null, PAGE_SIZE, (page - 1) * PAGE_SIZE),
    enabled: selectedProjectId > 0,
  });

  const peopleById = useMemo(() => {
    const map = new Map<number, string>();
    for (const person of peopleData?.items ?? []) {
      map.set(person.id, person.display_name);
    }
    return map;
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

  const maxPage = Math.max(1, Math.ceil((reviewData?.total ?? 0) / PAGE_SIZE));

  const invalidateReviewQueries = () => {
    queryClient.invalidateQueries({ queryKey: ["project-review-page", selectedProjectId] });
    queryClient.invalidateQueries({ queryKey: ["project-people", selectedProjectId] });
  };

  const batchConfirmMutation = useMutation({
    mutationFn: (params: { personId: number; faceIds: number[] }) =>
      api.projects.batchConfirmReview(selectedProjectId, params.personId, {
        face_detection_ids: params.faceIds,
        request_id: buildRequestId(),
        operator: "web_review_page",
        max_retries: 3,
      }),
    onSuccess: (result) => {
      setStatusMessage(`批量确认成功：updated=${result.updated} attempts=${result.attempts ?? 1}`);
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
      api.projects.batchRejectReview(selectedProjectId, params.personId, {
        face_detection_ids: params.faceIds,
        request_id: buildRequestId(),
        operator: "web_review_page",
        max_retries: 3,
      }),
    onSuccess: (result) => {
      setStatusMessage(`批量排除成功：updated=${result.updated} attempts=${result.attempts ?? 1}`);
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
      api.projects.batchMoveReview(selectedProjectId, params.personId, {
        face_detection_ids: params.faceIds,
        target_person_id: params.targetPersonId,
        request_id: buildRequestId(),
        operator: "web_review_page",
        max_retries: 3,
      }),
    onSuccess: (result) => {
      setStatusMessage(`批量移动成功：updated=${result.updated} attempts=${result.attempts ?? 1}`);
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
    grouped,
    peopleData,
    peopleById,
    reviewData,
    isLoading,
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
