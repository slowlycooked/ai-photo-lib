import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { api } from "@/api";
import { queryKeys } from "@/api/queryKeys";
import { useProjectContext } from "@/contexts/ProjectContext";

export type PeopleFilterMode =
  | "all"
  | "named"
  | "unnamed"
  | "review_pending"
  | "auto_assigned";

function parsePositiveIntParam(value: string | null): number | null {
  if (!value) return null;
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null;
}

export function usePeoplePage() {
  const { projectId } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const { currentProjectId, currentProject, setCurrentProjectId } = useProjectContext();
  const queryClient = useQueryClient();
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [createDisplayName, setCreateDisplayName] = useState("");
  const [filterMode, setFilterMode] = useState<PeopleFilterMode>("all");
  const [searchText, setSearchText] = useState("");

  const routeProjectId = projectId ? Number(projectId) : NaN;
  const normalizedRouteProjectId = Number.isFinite(routeProjectId) ? routeProjectId : null;
  const normalizedCurrentProjectId =
    currentProjectId !== null && Number.isFinite(currentProjectId) ? currentProjectId : null;

  useEffect(() => {
    if (normalizedCurrentProjectId !== null) return;
    if (normalizedRouteProjectId === null) return;
    setCurrentProjectId(normalizedRouteProjectId);
  }, [normalizedCurrentProjectId, normalizedRouteProjectId, setCurrentProjectId]);

  const selectedProjectId = normalizedRouteProjectId ?? normalizedCurrentProjectId;

  const { data: faceSettings } = useQuery({
    queryKey: ["project-face-settings", selectedProjectId],
    queryFn: () => api.projects.getFaceSettings(selectedProjectId!),
    enabled: selectedProjectId != null,
    staleTime: 30_000,
  });
  const faceCropEnabled = faceSettings?.store_face_crops === true;

  const selectedPersonIdRaw = searchParams.get("person_id");
  const selectedPersonId = selectedPersonIdRaw ? Number(selectedPersonIdRaw) : null;

  const {
    data: peopleData,
    isLoading: peopleLoading,
    error: peopleError,
  } = useQuery({
    queryKey: [...queryKeys.projectPeople(selectedProjectId, true), filterMode, searchText.trim()],
    queryFn: () =>
      api.projects.people(selectedProjectId!, true, 200, {
        is_named: filterMode === "named" ? true : filterMode === "unnamed" ? false : undefined,
        has_review_pending: filterMode === "review_pending" ? true : undefined,
        min_auto_assigned_count: filterMode === "auto_assigned" ? 1 : undefined,
        q: searchText.trim() || undefined,
      }),
    enabled: selectedProjectId != null,
    staleTime: 15_000,
  });

  const people = peopleData?.items ?? [];
  const resolvedSelectedPersonId = useMemo(() => {
    if (!people.length) return null;
    if (selectedPersonId != null && people.some((item) => item.id === selectedPersonId)) {
      return selectedPersonId;
    }
    return people[0].id;
  }, [people, selectedPersonId]);

  useEffect(() => {
    if (!resolvedSelectedPersonId) return;
    if (selectedPersonId === resolvedSelectedPersonId) return;
    const next = new URLSearchParams(searchParams);
    next.set("person_id", String(resolvedSelectedPersonId));
    setSearchParams(next, { replace: true });
  }, [resolvedSelectedPersonId, searchParams, selectedPersonId, setSearchParams]);

  const {
    data: personDetail,
    isLoading: personLoading,
    error: personError,
  } = useQuery({
    queryKey: queryKeys.projectPerson(selectedProjectId, resolvedSelectedPersonId),
    queryFn: () => api.projects.person(selectedProjectId!, resolvedSelectedPersonId!),
    enabled: resolvedSelectedPersonId != null,
    staleTime: 15_000,
  });

  const { data: reviewData } = useQuery({
    queryKey: ["project-review-pending", selectedProjectId, resolvedSelectedPersonId],
    queryFn: () => api.projects.reviewPending(selectedProjectId!, resolvedSelectedPersonId, 500, 0),
    enabled: resolvedSelectedPersonId != null,
    staleTime: 15_000,
  });

  const refreshPeopleData = () => {
    queryClient.invalidateQueries({ queryKey: ["project-people", selectedProjectId] });
    queryClient.invalidateQueries({
      queryKey: queryKeys.projectPerson(selectedProjectId, resolvedSelectedPersonId),
    });
    queryClient.invalidateQueries({
      queryKey: ["project-review-pending", selectedProjectId, resolvedSelectedPersonId],
    });
  };

  const handleSuccess = (message: string) => {
    setStatusMessage(message);
    setErrorMessage(null);
    refreshPeopleData();
  };

  const handleError = (error: Error) => {
    setErrorMessage(error.message);
    setStatusMessage(null);
  };

  const renameMutation = useMutation({
    mutationFn: (displayName: string) =>
      api.projects.renamePerson(selectedProjectId!, resolvedSelectedPersonId!, displayName),
    onSuccess: () => handleSuccess("人物名称已更新"),
    onError: handleError,
  });

  const confirmMutation = useMutation({
    mutationFn: (faceId: number) =>
      api.projects.confirmPersonFace(selectedProjectId!, resolvedSelectedPersonId!, faceId),
    onSuccess: () => handleSuccess("已确认这张脸属于当前人物"),
    onError: handleError,
  });

  const rejectMutation = useMutation({
    mutationFn: (faceId: number) =>
      api.projects.rejectPersonFace(selectedProjectId!, resolvedSelectedPersonId!, faceId),
    onSuccess: () => handleSuccess("已标记为不是此人"),
    onError: handleError,
  });

  const moveMutation = useMutation({
    mutationFn: ({ faceId, targetPersonId }: { faceId: number; targetPersonId: number }) =>
      api.projects.movePersonFace(selectedProjectId!, resolvedSelectedPersonId!, faceId, {
        target_person_id: targetPersonId,
      }),
    onSuccess: () => handleSuccess("已移动到目标人物"),
    onError: handleError,
  });

  const representativeMutation = useMutation({
    mutationFn: (faceId: number) =>
      api.projects.setPersonRepresentativeFace(selectedProjectId!, resolvedSelectedPersonId!, faceId),
    onSuccess: () => handleSuccess("代表头像已更新"),
    onError: handleError,
  });

  const batchConfirmMutation = useMutation({
    mutationFn: (faceIds: number[]) =>
      api.projects.batchConfirmReview(selectedProjectId!, resolvedSelectedPersonId!, {
        face_detection_ids: faceIds,
      }),
    onSuccess: (result) => handleSuccess(`已批量确认 ${result.updated} 张待确认人脸`),
    onError: handleError,
  });

  const batchRejectMutation = useMutation({
    mutationFn: (faceIds: number[]) =>
      api.projects.batchRejectReview(selectedProjectId!, resolvedSelectedPersonId!, {
        face_detection_ids: faceIds,
      }),
    onSuccess: (result) => handleSuccess(`已批量排除 ${result.updated} 张待确认人脸`),
    onError: handleError,
  });

  const batchMoveMutation = useMutation({
    mutationFn: ({ faceIds, targetPersonId }: { faceIds: number[]; targetPersonId: number }) =>
      api.projects.batchMoveReview(selectedProjectId!, resolvedSelectedPersonId!, {
        face_detection_ids: faceIds,
        target_person_id: targetPersonId,
      }),
    onSuccess: (result) => handleSuccess(`已批量移动 ${result.updated} 张待确认人脸`),
    onError: handleError,
  });

  const createPersonMutation = useMutation({
    mutationFn: (payload: { display_name?: string }) =>
      api.projects.createPerson(selectedProjectId!, {
        display_name: payload.display_name,
        is_named: !!payload.display_name,
      }),
    onSuccess: (result) => {
      handleSuccess("已创建新人物");
      setCreateDisplayName("");
      const next = new URLSearchParams(searchParams);
      next.set("person_id", String(result.person.id));
      setSearchParams(next, { replace: true });
    },
    onError: handleError,
  });

  const mergePersonMutation = useMutation({
    mutationFn: (targetPersonId: number) =>
      api.projects.mergePerson(selectedProjectId!, resolvedSelectedPersonId!, {
        target_person_id: targetPersonId,
      }),
    onSuccess: (result) => {
      handleSuccess(`已合并人物，迁移 ${result.moved_assignments} 张人脸`);
      const next = new URLSearchParams(searchParams);
      next.set("person_id", String(result.target_person.id));
      setSearchParams(next, { replace: true });
    },
    onError: handleError,
  });

  const splitPersonMutation = useMutation({
    mutationFn: (payload: { faceIds: number[]; newDisplayName?: string }) =>
      api.projects.splitPerson(selectedProjectId!, resolvedSelectedPersonId!, {
        face_detection_ids: payload.faceIds,
        new_display_name: payload.newDisplayName,
      }),
    onSuccess: (result) => {
      handleSuccess(`已拆分人物，迁移 ${result.moved_assignments} 张人脸`);
      const next = new URLSearchParams(searchParams);
      next.set("person_id", String(result.target_person.id));
      setSearchParams(next, { replace: true });
    },
    onError: handleError,
  });

  const deletePersonMutation = useMutation({
    mutationFn: () => api.projects.deletePerson(selectedProjectId!, resolvedSelectedPersonId!),
    onSuccess: () => {
      handleSuccess("人物已删除");
      const nextCandidate = people.find((person) => person.id !== resolvedSelectedPersonId);
      const next = new URLSearchParams(searchParams);
      if (nextCandidate) {
        next.set("person_id", String(nextCandidate.id));
      } else {
        next.delete("person_id");
      }
      setSearchParams(next, { replace: true });
    },
    onError: handleError,
  });

  const actionBusy =
    renameMutation.isPending ||
    confirmMutation.isPending ||
    rejectMutation.isPending ||
    moveMutation.isPending ||
    representativeMutation.isPending ||
    batchConfirmMutation.isPending ||
    batchRejectMutation.isPending ||
    batchMoveMutation.isPending ||
    createPersonMutation.isPending ||
    mergePersonMutation.isPending ||
    splitPersonMutation.isPending ||
    deletePersonMutation.isPending;

  const moveCandidates = people.filter((person) => person.id !== resolvedSelectedPersonId);
  const reviewFaceIds = (reviewData?.items ?? []).map((item) => item.face_detection_id);
  const namedCount = people.filter((item) => item.is_named).length;
  const unnamedCount = Math.max(0, people.length - namedCount);

  const mergeTargetIdParam = parsePositiveIntParam(searchParams.get("merge_target_id"));
  const mergeTargetId =
    mergeTargetIdParam != null && moveCandidates.some((person) => person.id === mergeTargetIdParam)
      ? mergeTargetIdParam
      : (moveCandidates[0]?.id ?? null);

  useEffect(() => {
    const rawTargetId = searchParams.get("merge_target_id");
    if (mergeTargetId == null) {
      if (!rawTargetId) return;
      const next = new URLSearchParams(searchParams);
      next.delete("merge_target_id");
      setSearchParams(next, { replace: true });
      return;
    }
    if (rawTargetId === String(mergeTargetId)) return;
    const next = new URLSearchParams(searchParams);
    next.set("merge_target_id", String(mergeTargetId));
    setSearchParams(next, { replace: true });
  }, [mergeTargetId, searchParams, setSearchParams]);

  const setSelectedPersonId = (personId: number) => {
    const next = new URLSearchParams(searchParams);
    next.set("person_id", String(personId));
    setSearchParams(next);
  };

  const setMergeTargetId = (personId: number) => {
    const next = new URLSearchParams(searchParams);
    next.set("merge_target_id", String(personId));
    setSearchParams(next, { replace: true });
  };

  return {
    currentProject,
    selectedProjectId,
    normalizedRouteProjectId,
    faceCropEnabled,
    statusMessage,
    errorMessage,
    createDisplayName,
    setCreateDisplayName,
    filterMode,
    setFilterMode,
    searchText,
    setSearchText,
    people,
    peopleLoading,
    peopleError,
    resolvedSelectedPersonId,
    personDetail,
    personLoading,
    personError,
    actionBusy,
    moveCandidates,
    reviewFaceIds,
    namedCount,
    unnamedCount,
    mergeTargetId,
    setSelectedPersonId,
    setMergeTargetId,
    createPerson: () =>
      createPersonMutation.mutate({ display_name: createDisplayName.trim() || undefined }),
    mergeSelectedPerson: () => {
      if (mergeTargetId == null) return;
      if (!moveCandidates.some((person) => person.id === mergeTargetId)) return;
      mergePersonMutation.mutate(mergeTargetId);
    },
    deleteSelectedPerson: () => deletePersonMutation.mutate(),
    renameSelectedPerson: (displayName: string) => renameMutation.mutate(displayName.trim()),
    confirmFace: (faceId: number) => confirmMutation.mutate(faceId),
    rejectFace: (faceId: number) => rejectMutation.mutate(faceId),
    moveFace: (faceId: number, targetPersonId: number) =>
      moveMutation.mutate({ faceId, targetPersonId }),
    batchConfirmReview: (faceIds: number[]) => batchConfirmMutation.mutate(faceIds),
    batchRejectReview: (faceIds: number[]) => batchRejectMutation.mutate(faceIds),
    batchMoveReview: (faceIds: number[], targetPersonId: number) =>
      batchMoveMutation.mutate({ faceIds, targetPersonId }),
    splitFaces: (faceIds: number[], newDisplayName?: string) =>
      splitPersonMutation.mutate({ faceIds, newDisplayName }),
    setRepresentativeFace: (faceId: number) => representativeMutation.mutate(faceId),
  };
}
