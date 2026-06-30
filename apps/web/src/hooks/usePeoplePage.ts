import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { api } from "@/api";
import { queryKeys } from "@/api/queryKeys";
import { useProjectContext } from "@/contexts/ProjectContext";
import { formatBatchFeedbackToast } from "@/lib/peopleFeedback";
import {
  archivePersonManually,
  forceManagePersonManually,
  getManualArchivedPersonIds,
  getManualManagedPersonIds,
  isArchivedPerson,
  unarchivePersonManually,
  unforceManagePersonManually,
} from "@/lib/personArchive";

const PERSON_DETAIL_ASSIGNMENT_PAGE_SIZE = 40;

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
  const [manualArchivedPersonIds, setManualArchivedPersonIds] = useState<Set<number>>(new Set());
  const [manualManagedPersonIds, setManualManagedPersonIds] = useState<Set<number>>(new Set());
  const [selectedPersonIds, setSelectedPersonIds] = useState<number[]>([]);
  const [personRematchTaskId, setPersonRematchTaskId] = useState<number | null>(null);
  const [personDetailAssignmentWindow, setPersonDetailAssignmentWindow] = useState<{
    personId: number | null;
    limit: number;
  }>({ personId: null, limit: PERSON_DETAIL_ASSIGNMENT_PAGE_SIZE });

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

  useEffect(() => {
    if (selectedProjectId == null) {
      setManualArchivedPersonIds(new Set());
      setManualManagedPersonIds(new Set());
      return;
    }
    setManualArchivedPersonIds(getManualArchivedPersonIds(selectedProjectId));
    setManualManagedPersonIds(getManualManagedPersonIds(selectedProjectId));
  }, [selectedProjectId]);

  const { data: faceSettings } = useQuery({
    queryKey: ["project-face-settings", selectedProjectId],
    queryFn: () => api.projectSettings.getFace(selectedProjectId!),
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
      api.projectPeople.list(selectedProjectId!, true, 200, {
        is_named: filterMode === "named" ? true : filterMode === "unnamed" ? false : undefined,
        has_review_pending: filterMode === "review_pending" ? true : undefined,
        min_auto_assigned_count: filterMode === "auto_assigned" ? 1 : undefined,
        q: searchText.trim() || undefined,
      }),
    enabled: selectedProjectId != null,
    staleTime: 15_000,
  });

  // Dedicated query for archive candidates — runs independently of the active filter
  // so the archive section stays visible even when named/review_pending/etc. filters are applied.
  const { data: archivePeopleData } = useQuery({
    queryKey: ["project-people-archive-candidates", selectedProjectId],
    queryFn: () => api.projectPeople.list(selectedProjectId!, true, 500),
    enabled: selectedProjectId != null,
    staleTime: 30_000,
  });

  const people = peopleData?.items ?? [];
  const archivedPeople = useMemo(
    () =>
      (archivePeopleData?.items ?? []).filter(
        (item) =>
          manualArchivedPersonIds.has(item.id) ||
          (isArchivedPerson(item) && !manualManagedPersonIds.has(item.id)),
      ),
    [archivePeopleData, manualArchivedPersonIds, manualManagedPersonIds],
  );
  const archivedPersonIds = useMemo(
    () => new Set(archivedPeople.map((person) => person.id)),
    [archivedPeople],
  );
  const managedPeople = useMemo(
    () =>
      people.filter(
        (item) =>
          !manualArchivedPersonIds.has(item.id) &&
          (!isArchivedPerson(item) || manualManagedPersonIds.has(item.id)),
      ),
    [manualArchivedPersonIds, manualManagedPersonIds, people],
  );
  const managedPersonIds = useMemo(
    () => new Set(managedPeople.map((person) => person.id)),
    [managedPeople],
  );
  const resolvedSelectedPersonId = useMemo(() => {
    if (
      selectedPersonId != null &&
      (managedPersonIds.has(selectedPersonId) || archivedPersonIds.has(selectedPersonId))
    ) {
      return selectedPersonId;
    }
    if (!managedPeople.length && !archivedPeople.length) return null;
    if (managedPeople.length > 0) return managedPeople[0].id;
    if (archivedPeople.length > 0) return archivedPeople[0].id;
    return managedPeople[0].id;
  }, [archivedPeople, archivedPersonIds, managedPeople, managedPersonIds, selectedPersonId]);
  const selectedPersonIsArchived =
    resolvedSelectedPersonId != null && archivedPersonIds.has(resolvedSelectedPersonId);
  const selectedPersonIsManageable =
    resolvedSelectedPersonId != null && managedPersonIds.has(resolvedSelectedPersonId);
  const personDetailAssignmentLimit =
    personDetailAssignmentWindow.personId === resolvedSelectedPersonId
      ? personDetailAssignmentWindow.limit
      : PERSON_DETAIL_ASSIGNMENT_PAGE_SIZE;

  useEffect(() => {
    const managedIds = new Set(managedPeople.map((person) => person.id));
    setSelectedPersonIds((prev) => prev.filter((id) => managedIds.has(id)));
  }, [managedPeople]);

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
    isFetching: personFetching,
    error: personError,
  } = useQuery({
    queryKey: [
      ...queryKeys.projectPerson(selectedProjectId, resolvedSelectedPersonId),
      personDetailAssignmentLimit,
    ],
    queryFn: () =>
      api.projectPeople.get(
        selectedProjectId!,
        resolvedSelectedPersonId!,
        personDetailAssignmentLimit,
      ),
    enabled: resolvedSelectedPersonId != null,
    staleTime: 15_000,
    placeholderData: (previousData) => previousData,
  });

  const { data: reviewData } = useQuery({
    queryKey: ["project-review-pending", selectedProjectId, resolvedSelectedPersonId],
    queryFn: () => api.projectPeople.reviewPending(selectedProjectId!, resolvedSelectedPersonId, 500, 0),
    enabled: resolvedSelectedPersonId != null,
    staleTime: 15_000,
  });

  const { data: rematchStatus } = useQuery({
    queryKey: ["face-rematch-unknown-status", selectedProjectId],
    queryFn: () => api.projectFaces.rematchUnknownStatus(selectedProjectId!),
    enabled: selectedProjectId != null,
    refetchInterval: (query) => {
      const d = query.state.data;
      return d && d.running ? 3000 : 15000;
    },
  });

  const refreshPeopleData = () => {
    queryClient.invalidateQueries({ queryKey: ["project-people", selectedProjectId] });
    queryClient.invalidateQueries({ queryKey: ["project-people-archive-candidates", selectedProjectId] });
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

  const feedbackSuffix = (
    effects:
      | {
          prototype_rebuilt: boolean;
          rebuilt_person_ids: number[];
          unknown_rematch_requested: boolean;
          unknown_rematch_scope: string | null;
          unknown_rematch_task_id: number | null;
          unknown_rematch_task_created: boolean;
        }
      | undefined,
  ) => {
    if (!effects) return "";
    const parts: string[] = [];
    if (effects.prototype_rebuilt) {
      parts.push(`prototype rebuild=${effects.rebuilt_person_ids.join(",") || "done"}`);
    }
    if (effects.unknown_rematch_requested) {
      const scope = effects.unknown_rematch_scope ?? "unknown";
      const mode = effects.unknown_rematch_task_created ? "queued" : "reused";
      const task = effects.unknown_rematch_task_id ?? "-";
      parts.push(`rematch(${scope}) ${mode} task=${task}`);
    }
    return parts.length > 0 ? `（${parts.join(" · ")}）` : "";
  };

  const handleError = (error: Error) => {
    setErrorMessage(error.message);
    setStatusMessage(null);
  };

  useEffect(() => {
    if (personRematchTaskId == null || !rematchStatus) return;
    if (rematchStatus.task_id !== personRematchTaskId || rematchStatus.running) return;

    if (rematchStatus.status === "success") {
      handleSuccess(
        `人物相似候选聚合完成：扫描 ${rematchStatus.faces_considered} 张，新增/更新待确认 ${rematchStatus.review_pending} 张`,
      );
    } else if (rematchStatus.status === "failed") {
      setErrorMessage(`人物相似候选聚合失败：${rematchStatus.message}`);
      setStatusMessage(null);
    }
    setPersonRematchTaskId(null);
  }, [personRematchTaskId, rematchStatus]);

  const renameMutation = useMutation({
    mutationFn: (displayName: string) =>
      api.projectPeople.rename(selectedProjectId!, resolvedSelectedPersonId!, displayName),
    onSuccess: (result) => handleSuccess(`人物名称已更新${feedbackSuffix(result.feedback_effects)}`),
    onError: handleError,
  });

  const confirmMutation = useMutation({
    mutationFn: (faceId: number) =>
      api.projectPeople.confirmFace(selectedProjectId!, resolvedSelectedPersonId!, faceId),
    onSuccess: (result) =>
      handleSuccess(`已确认这张脸属于当前人物${feedbackSuffix(result.feedback_effects)}`),
    onError: handleError,
  });

  const rejectMutation = useMutation({
    mutationFn: (faceId: number) =>
      api.projectPeople.rejectFace(selectedProjectId!, resolvedSelectedPersonId!, faceId),
    onSuccess: (result) => handleSuccess(`已标记为不是此人${feedbackSuffix(result.feedback_effects)}`),
    onError: handleError,
  });

  const moveMutation = useMutation({
    mutationFn: ({ faceId, targetPersonId }: { faceId: number; targetPersonId: number }) =>
      api.projectPeople.moveFace(selectedProjectId!, resolvedSelectedPersonId!, faceId, {
        target_person_id: targetPersonId,
      }),
    onSuccess: (result) => handleSuccess(`已移动到目标人物${feedbackSuffix(result.feedback_effects)}`),
    onError: handleError,
  });

  const representativeMutation = useMutation({
    mutationFn: (faceId: number) =>
      api.projectPeople.setRepresentativeFace(selectedProjectId!, resolvedSelectedPersonId!, faceId),
    onSuccess: (result) => handleSuccess(`代表头像已更新${feedbackSuffix(result.feedback_effects)}`),
    onError: handleError,
  });

  const batchConfirmMutation = useMutation({
    mutationFn: (faceIds: number[]) =>
      api.projectPeople.batchConfirmReview(selectedProjectId!, resolvedSelectedPersonId!, {
        face_detection_ids: faceIds,
      }),
    onSuccess: (result) =>
      handleSuccess(
        formatBatchFeedbackToast(
          "批量确认",
          result.updated,
          result.attempts ?? 1,
          result.feedback_effects,
        ),
      ),
    onError: handleError,
  });

  const batchRejectMutation = useMutation({
    mutationFn: (faceIds: number[]) =>
      api.projectPeople.batchRejectReview(selectedProjectId!, resolvedSelectedPersonId!, {
        face_detection_ids: faceIds,
      }),
    onSuccess: (result) =>
      handleSuccess(
        formatBatchFeedbackToast(
          "批量排除",
          result.updated,
          result.attempts ?? 1,
          result.feedback_effects,
        ),
      ),
    onError: handleError,
  });

  const batchMoveMutation = useMutation({
    mutationFn: ({ faceIds, targetPersonId }: { faceIds: number[]; targetPersonId: number }) =>
      api.projectPeople.batchMoveReview(selectedProjectId!, resolvedSelectedPersonId!, {
        face_detection_ids: faceIds,
        target_person_id: targetPersonId,
      }),
    onSuccess: (result) =>
      handleSuccess(
        formatBatchFeedbackToast(
          "批量移动",
          result.updated,
          result.attempts ?? 1,
          result.feedback_effects,
        ),
      ),
    onError: handleError,
  });

  const createPersonMutation = useMutation({
    mutationFn: (payload: { display_name?: string }) =>
      api.projectPeople.create(selectedProjectId!, {
        display_name: payload.display_name,
        is_named: !!payload.display_name,
      }),
    onSuccess: (result) => {
      handleSuccess(`已创建新人物${feedbackSuffix(result.feedback_effects)}`);
      setCreateDisplayName("");
      const next = new URLSearchParams(searchParams);
      next.set("person_id", String(result.person.id));
      setSearchParams(next, { replace: true });
    },
    onError: handleError,
  });

  const mergePersonMutation = useMutation({
    mutationFn: (targetPersonId: number) =>
      api.projectPeople.merge(selectedProjectId!, resolvedSelectedPersonId!, {
        target_person_id: targetPersonId,
      }),
    onSuccess: (result) => {
      handleSuccess(
        `已合并人物，迁移 ${result.moved_assignments} 张人脸${feedbackSuffix(result.feedback_effects)}`,
      );
      const next = new URLSearchParams(searchParams);
      next.set("person_id", String(result.target_person.id));
      setSearchParams(next, { replace: true });
    },
    onError: handleError,
  });

  const splitPersonMutation = useMutation({
    mutationFn: (payload: { faceIds: number[]; newDisplayName?: string }) =>
      api.projectPeople.split(selectedProjectId!, resolvedSelectedPersonId!, {
        face_detection_ids: payload.faceIds,
        new_display_name: payload.newDisplayName,
      }),
    onSuccess: (result) => {
      handleSuccess(
        `已拆分人物，迁移 ${result.moved_assignments} 张人脸${feedbackSuffix(result.feedback_effects)}`,
      );
      const next = new URLSearchParams(searchParams);
      next.set("person_id", String(result.target_person.id));
      setSearchParams(next, { replace: true });
    },
    onError: handleError,
  });

  const rematchPersonMutation = useMutation({
    mutationFn: () =>
      api.projectFaces.rematchUnknown(selectedProjectId!, {
        scope: "person",
        person_id: resolvedSelectedPersonId!,
        max_faces: 10000,
      }),
    onSuccess: (result) => {
      setErrorMessage(null);
      setStatusMessage(
        result.status.running
          ? `已提交人物相似候选聚合任务 #${result.status.task_id ?? "-"}`
          : result.message,
      );
      setPersonRematchTaskId(result.status.task_id ?? null);
      refreshPeopleData();
      queryClient.invalidateQueries({ queryKey: ["face-rematch-unknown-status", selectedProjectId] });
    },
    onError: handleError,
  });

  const selectNextManagedPerson = (removedPersonIds: Set<number>) => {
    const nextCandidate = managedPeople.find((person) => !removedPersonIds.has(person.id));
    const next = new URLSearchParams(searchParams);
    if (nextCandidate) {
      next.set("person_id", String(nextCandidate.id));
    } else {
      next.delete("person_id");
    }
    setSearchParams(next, { replace: true });
  };

  const deletePersonMutation = useMutation({
    mutationFn: (personId: number) => api.projectPeople.delete(selectedProjectId!, personId),
    onSuccess: (_result, deletedPersonId) => {
      handleSuccess("人物已删除");
      setSelectedPersonIds((prev) => prev.filter((id) => id !== deletedPersonId));
      if (resolvedSelectedPersonId === deletedPersonId) {
        selectNextManagedPerson(new Set([deletedPersonId]));
      }
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
    deletePersonMutation.isPending ||
    rematchPersonMutation.isPending;

  const moveCandidates = selectedPersonIsManageable
    ? managedPeople.filter((person) => person.id !== resolvedSelectedPersonId)
    : [];
  const reviewFaceIds = (reviewData?.items ?? []).map((item) => item.face_detection_id);
  const loadedAssignmentCount = personDetail?.assignments.length ?? 0;
  const totalAssignmentCount =
    personDetail?.assignments_total ?? personDetail?.sample_count ?? loadedAssignmentCount;
  const canLoadMoreAssignments =
    !!personDetail?.assignments_has_more && personDetailAssignmentLimit < 500;
  const personRematchRunning =
    !!rematchStatus?.running &&
    rematchStatus.scope === "person" &&
    rematchStatus.person_id === resolvedSelectedPersonId;
  const namedCount = managedPeople.filter((item) => item.is_named).length;
  const unnamedCount = Math.max(0, managedPeople.length - namedCount);

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

  const toggleSelectPerson = (personId: number, checked: boolean) => {
    setSelectedPersonIds((prev) => {
      if (checked) {
        if (prev.includes(personId)) return prev;
        return [...prev, personId];
      }
      return prev.filter((id) => id !== personId);
    });
  };

  const archiveSelectedPerson = () => {
    if (selectedProjectId == null || resolvedSelectedPersonId == null) return;
    const archivedPersonId = resolvedSelectedPersonId;
    const updated = archivePersonManually(selectedProjectId, archivedPersonId);
    const managedUpdated = unforceManagePersonManually(selectedProjectId, archivedPersonId);
    setManualArchivedPersonIds(updated);
    setManualManagedPersonIds(managedUpdated);
    setSelectedPersonIds((prev) => prev.filter((id) => id !== archivedPersonId));
    selectNextManagedPerson(new Set([archivedPersonId]));
    setStatusMessage("已加入 archive，后续不再出现在管理列表");
    setErrorMessage(null);
  };

  const archivePerson = (personId: number) => {
    if (selectedProjectId == null) return;
    const updated = archivePersonManually(selectedProjectId, personId);
    const managedUpdated = unforceManagePersonManually(selectedProjectId, personId);
    setManualArchivedPersonIds(updated);
    setManualManagedPersonIds(managedUpdated);
    setSelectedPersonIds((prev) => prev.filter((id) => id !== personId));
    if (resolvedSelectedPersonId === personId) {
      selectNextManagedPerson(new Set([personId]));
    }
    setStatusMessage("已加入 archive，后续不再出现在管理列表");
    setErrorMessage(null);
  };

  const archiveSelectedPeople = () => {
    if (selectedProjectId == null || selectedPersonIds.length === 0) return;
    let updated = getManualArchivedPersonIds(selectedProjectId);
    let managedUpdated = getManualManagedPersonIds(selectedProjectId);
    const archivedIds = new Set(selectedPersonIds);
    for (const personId of selectedPersonIds) {
      updated = archivePersonManually(selectedProjectId, personId);
      managedUpdated = unforceManagePersonManually(selectedProjectId, personId);
    }
    setManualArchivedPersonIds(updated);
    setManualManagedPersonIds(managedUpdated);
    setSelectedPersonIds([]);
    if (resolvedSelectedPersonId != null && archivedIds.has(resolvedSelectedPersonId)) {
      selectNextManagedPerson(archivedIds);
    }
    setStatusMessage(`已将 ${selectedPersonIds.length} 个人物加入 archive`);
    setErrorMessage(null);
  };

  const unarchivePerson = (personId: number) => {
    if (selectedProjectId == null) return;
    const updated = unarchivePersonManually(selectedProjectId, personId);
    const managedUpdated = forceManagePersonManually(selectedProjectId, personId);
    setManualArchivedPersonIds(updated);
    setManualManagedPersonIds(managedUpdated);
    setStatusMessage("已从 archive 恢复到管理列表");
    setErrorMessage(null);
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
    people: managedPeople,
    archivedPeople,
    peopleLoading,
    peopleError,
    resolvedSelectedPersonId,
    personDetail,
    selectedPersonIsArchived,
    selectedPersonIsManageable,
    personLoading,
    personFetching,
    personError,
    actionBusy,
    moveCandidates,
    reviewFaceIds,
    namedCount,
    unnamedCount,
    mergeTargetId,
    manualArchivedPersonIds,
    selectedPersonIds,
    setSelectedPersonId,
    setMergeTargetId,
    toggleSelectPerson,
    archivePerson,
    archiveSelectedPerson,
    archiveSelectedPeople,
    unarchivePerson,
    loadedAssignmentCount,
    totalAssignmentCount,
    canLoadMoreAssignments,
    loadMoreAssignments: () => {
      if (resolvedSelectedPersonId == null) return;
      setPersonDetailAssignmentWindow((current) => {
        const currentLimit =
          current.personId === resolvedSelectedPersonId
            ? current.limit
            : PERSON_DETAIL_ASSIGNMENT_PAGE_SIZE;
        return {
          personId: resolvedSelectedPersonId,
          limit: Math.min(500, currentLimit + PERSON_DETAIL_ASSIGNMENT_PAGE_SIZE),
        };
      });
    },
    createPerson: () =>
      createPersonMutation.mutate({ display_name: createDisplayName.trim() || undefined }),
    mergeSelectedPerson: () => {
      if (mergeTargetId == null) return;
      if (!moveCandidates.some((person) => person.id === mergeTargetId)) return;
      mergePersonMutation.mutate(mergeTargetId);
    },
    deletePerson: (personId: number) => deletePersonMutation.mutate(personId),
    deleteSelectedPerson: () => {
      if (resolvedSelectedPersonId == null) return;
      deletePersonMutation.mutate(resolvedSelectedPersonId);
    },
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
    rematchSelectedPerson: () => rematchPersonMutation.mutate(),
    personRematchRunning,
  };
}
