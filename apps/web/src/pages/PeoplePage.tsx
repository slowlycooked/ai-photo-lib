import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, Loader2, ScanFace, UserRound, Users } from "lucide-react";
import { Link, Navigate, useParams, useSearchParams } from "react-router-dom";
import { api, type PersonDetail, type PersonSummary } from "@/api";
import { queryKeys } from "@/api/queryKeys";
import { useProjectContext } from "@/contexts/ProjectContext";

function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  return date.toLocaleString("zh-CN", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function PersonCard({
  projectId,
  person,
  selected,
  onSelect,
}: {
  projectId: number;
  person: PersonSummary;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={[
        "w-full text-left rounded-xl border p-4 transition-colors",
        selected
          ? "border-primary bg-primary/5 shadow-sm"
          : "border-hairline bg-canvas hover:bg-surface-card",
      ].join(" ")}
    >
      <div className="flex gap-3">
        <div className="w-16 h-16 rounded-lg overflow-hidden border border-hairline bg-surface-soft flex-shrink-0">
          {person.representative_face_detection_id ? (
            <img
              src={api.projects.faceCropUrl(projectId, person.representative_face_detection_id, person.updated_at)}
              alt={person.display_name}
              className="w-full h-full object-cover"
              onError={(e) => {
                e.currentTarget.style.display = "none";
              }}
            />
          ) : (
            <div className="w-full h-full flex items-center justify-center text-mute">
              <UserRound className="w-6 h-6" />
            </div>
          )}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h3 className="text-body-sm font-semibold text-ink truncate">
              {person.display_name}
            </h3>
            <span
              className={[
                "px-2 py-0.5 rounded-full text-caption-sm",
                person.is_named
                  ? "bg-emerald-100 text-emerald-800"
                  : "bg-secondary-bg text-mute",
              ].join(" ")}
            >
              {person.is_named ? "已命名" : "未命名"}
            </span>
          </div>
          <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-caption-sm text-mute">
            <span>样本 {person.sample_count}</span>
            <span>已确认 {person.confirmed_sample_count}</span>
            <span>自动识别 {person.auto_assigned_count}</span>
            <span>待确认 {person.review_pending_count}</span>
          </div>
          <p className="mt-2 text-caption-sm text-mute">
            最近更新 {formatDateTime(person.updated_at)}
          </p>
        </div>
      </div>
    </button>
  );
}

function AssignmentChip({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg bg-surface-soft border border-hairline px-3 py-2">
      <div className="text-caption-sm text-mute">{label}</div>
      <div className="text-body-sm font-semibold text-ink mt-0.5">{value}</div>
    </div>
  );
}

function PersonDetailPanel({
  projectId,
  detail,
  isLoading,
  error,
  moveCandidates,
  reviewFaceIds,
  statusMessage,
  errorMessage,
  actionBusy,
  onRename,
  onConfirmFace,
  onRejectFace,
  onMoveFace,
  onBatchConfirmReview,
  onBatchRejectReview,
  onBatchMoveReview,
  onSetRepresentative,
}: {
  projectId: number;
  detail: PersonDetail | undefined;
  isLoading: boolean;
  error: Error | null;
  moveCandidates: PersonSummary[];
  reviewFaceIds: number[];
  statusMessage: string | null;
  errorMessage: string | null;
  actionBusy: boolean;
  onRename: (displayName: string) => void;
  onConfirmFace: (faceId: number) => void;
  onRejectFace: (faceId: number) => void;
  onMoveFace: (faceId: number, targetPersonId: number) => void;
  onBatchConfirmReview: (faceIds: number[]) => void;
  onBatchRejectReview: (faceIds: number[]) => void;
  onBatchMoveReview: (faceIds: number[], targetPersonId: number) => void;
  onSetRepresentative: (faceId: number) => void;
}) {
  const [renameValue, setRenameValue] = useState("");
  const [moveTargets, setMoveTargets] = useState<Record<number, number>>({});
  const [batchMoveTargetId, setBatchMoveTargetId] = useState<number | null>(null);

  useEffect(() => {
    setRenameValue(detail?.display_name ?? "");
  }, [detail?.id, detail?.display_name]);

  useEffect(() => {
    setBatchMoveTargetId(moveCandidates[0]?.id ?? null);
  }, [moveCandidates]);

  if (isLoading) {
    return (
      <div className="bg-canvas rounded-xl border border-hairline p-6 flex items-center gap-3 text-mute">
        <Loader2 className="w-4 h-4 animate-spin" />
        正在加载人物详情...
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-canvas rounded-xl border border-hairline p-6 flex items-center gap-3 text-danger">
        <AlertCircle className="w-4 h-4" />
        {error.message}
      </div>
    );
  }

  if (!detail) {
    return (
      <div className="bg-canvas rounded-xl border border-hairline p-8 text-center text-mute">
        <Users className="w-8 h-8 mx-auto mb-3" />
        请选择左侧人物查看详情
      </div>
    );
  }

  const confirmed = detail.assignments.filter((item) => item.is_positive_sample).length;
  const autoAssigned = detail.assignments.filter(
    (item) => item.assignment_status === "auto_assigned",
  ).length;
  const reviewPending = detail.assignments.filter(
    (item) => item.assignment_status === "review_pending",
  ).length;

  return (
    <div className="bg-canvas rounded-xl border border-hairline overflow-hidden">
      <div className="px-6 py-5 border-b border-hairline">
        {statusMessage && (
          <div className="mb-3 rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-caption-sm text-emerald-800">
            {statusMessage}
          </div>
        )}
        {errorMessage && (
          <div className="mb-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-caption-sm text-red-800">
            {errorMessage}
          </div>
        )}
        <div className="flex items-start gap-4">
          <div className="w-20 h-20 rounded-xl overflow-hidden border border-hairline bg-surface-soft flex-shrink-0">
            {detail.representative_face_detection_id ? (
              <img
                src={api.projects.faceCropUrl(projectId, detail.representative_face_detection_id, detail.updated_at)}
                alt={detail.display_name}
                className="w-full h-full object-cover"
                onError={(e) => {
                  e.currentTarget.style.display = "none";
                }}
              />
            ) : (
              <div className="w-full h-full flex items-center justify-center text-mute">
                <UserRound className="w-8 h-8" />
              </div>
            )}
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 flex-wrap">
              <h2 className="text-heading-md font-semibold text-ink">
                {detail.display_name}
              </h2>
              <span
                className={[
                  "px-2 py-0.5 rounded-full text-caption-sm",
                  detail.is_named
                    ? "bg-emerald-100 text-emerald-800"
                    : "bg-secondary-bg text-mute",
                ].join(" ")}
              >
                {detail.is_named ? "已命名人物" : "系统人物"}
              </span>
            </div>
            <p className="mt-1 text-caption-sm text-mute">
              created by {detail.created_by} · 最近更新 {formatDateTime(detail.updated_at)}
            </p>

            <form
              className="mt-3 flex items-center gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                onRename(renameValue);
              }}
            >
              <input
                value={renameValue}
                onChange={(e) => setRenameValue(e.target.value)}
                className="w-full max-w-xs px-3 py-1.5 rounded-md border border-hairline bg-canvas text-body-sm"
                placeholder="输入人物名称"
              />
              <button
                type="submit"
                disabled={actionBusy || !renameValue.trim()}
                className="px-3 py-1.5 rounded-md border border-hairline text-body-sm text-ink hover:bg-surface-card disabled:opacity-50"
              >
                重命名
              </button>
            </form>
          </div>
        </div>

        <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-3">
          <AssignmentChip label="总样本" value={detail.sample_count} />
          <AssignmentChip label="已确认" value={confirmed} />
          <AssignmentChip label="自动识别" value={autoAssigned} />
          <AssignmentChip label="待确认" value={reviewPending} />
        </div>
      </div>

      <div className="px-6 py-5 space-y-4">
        {reviewFaceIds.length > 0 && (
          <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3">
            <div className="flex items-center justify-between gap-3 flex-wrap">
              <div>
                <h3 className="text-body-sm font-semibold text-amber-900">待确认批量处理</h3>
                <p className="text-caption-sm text-amber-800 mt-1">
                  当前人物有 {reviewFaceIds.length} 张 review_pending 人脸。
                </p>
              </div>
              <div className="flex items-center gap-2 flex-wrap">
                <button
                  type="button"
                  disabled={actionBusy}
                  onClick={() => onBatchConfirmReview(reviewFaceIds)}
                  className="px-2.5 py-1 rounded-md border border-hairline text-caption-sm text-ink hover:bg-canvas disabled:opacity-50"
                >
                  全部确认
                </button>
                <button
                  type="button"
                  disabled={actionBusy}
                  onClick={() => onBatchRejectReview(reviewFaceIds)}
                  className="px-2.5 py-1 rounded-md border border-hairline text-caption-sm text-ink hover:bg-canvas disabled:opacity-50"
                >
                  全部排除
                </button>
                {moveCandidates.length > 0 && batchMoveTargetId != null && (
                  <>
                    <select
                      value={batchMoveTargetId}
                      onChange={(e) => setBatchMoveTargetId(Number(e.target.value))}
                      className="px-2 py-1 rounded-md border border-hairline bg-canvas text-caption-sm"
                    >
                      {moveCandidates.map((candidate) => (
                        <option key={candidate.id} value={candidate.id}>
                          移动到：{candidate.display_name}
                        </option>
                      ))}
                    </select>
                    <button
                      type="button"
                      disabled={actionBusy}
                      onClick={() => onBatchMoveReview(reviewFaceIds, batchMoveTargetId)}
                      className="px-2.5 py-1 rounded-md border border-hairline text-caption-sm text-ink hover:bg-canvas disabled:opacity-50"
                    >
                      批量移动
                    </button>
                  </>
                )}
              </div>
            </div>
          </div>
        )}

        <div className="flex items-center justify-between gap-3">
          <div>
            <h3 className="text-body-sm font-semibold text-ink">关联人脸</h3>
            <p className="text-caption-sm text-mute mt-1">
              当前先展示只读详情，后续这里会接确认、移动和拆分操作。
            </p>
          </div>
          <span className="text-caption-sm text-mute">
            {detail.assignments.length} 条
          </span>
        </div>

        {detail.assignments.length === 0 ? (
          <div className="rounded-lg border border-dashed border-hairline p-6 text-center text-mute">
            这个人物还没有关联的人脸样本
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
            {detail.assignments.map((assignment) => {
              const face = assignment.face_detection;
              return (
                <div
                  key={assignment.id}
                  className="rounded-xl border border-hairline bg-surface-soft p-3 flex gap-3"
                >
                  <div className="w-24 h-24 rounded-lg overflow-hidden border border-hairline bg-canvas flex-shrink-0">
                    {face.face_crop_path ? (
                      <img
                        src={api.projects.faceCropUrl(projectId, face.id, face.updated_at)}
                        alt={`face-${face.id}`}
                        className="w-full h-full object-cover"
                      />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center text-mute">
                        <ScanFace className="w-5 h-5" />
                      </div>
                    )}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-body-sm font-medium text-ink">
                        face #{face.id}
                      </span>
                      <span className="px-2 py-0.5 rounded-full bg-canvas text-caption-sm text-ink border border-hairline">
                        {assignment.assignment_status}
                      </span>
                    </div>
                    <p className="mt-1 text-caption-sm text-mute">
                      source: {assignment.assignment_source}
                    </p>
                    <p className="mt-1 text-caption-sm text-mute">
                      bbox {face.bbox_x}, {face.bbox_y}, {face.bbox_w}, {face.bbox_h}
                    </p>
                    <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-caption-sm text-mute">
                      {assignment.confidence != null && (
                        <span>置信度 {(assignment.confidence * 100).toFixed(0)}%</span>
                      )}
                      {assignment.similarity_score != null && (
                        <span>相似度 {(assignment.similarity_score * 100).toFixed(0)}%</span>
                      )}
                      {face.face_quality_score != null && (
                        <span>质量 {(face.face_quality_score * 100).toFixed(0)}%</span>
                      )}
                    </div>
                    <div className="mt-2 flex flex-wrap gap-2">
                      <button
                        type="button"
                        disabled={actionBusy}
                        onClick={() => onConfirmFace(face.id)}
                        className="px-2.5 py-1 rounded-md border border-hairline text-caption-sm text-ink hover:bg-canvas disabled:opacity-50"
                      >
                        确认属于此人
                      </button>
                      <button
                        type="button"
                        disabled={actionBusy}
                        onClick={() => onRejectFace(face.id)}
                        className="px-2.5 py-1 rounded-md border border-hairline text-caption-sm text-ink hover:bg-canvas disabled:opacity-50"
                      >
                        不是此人
                      </button>
                      <button
                        type="button"
                        disabled={actionBusy}
                        onClick={() => onSetRepresentative(face.id)}
                        className="px-2.5 py-1 rounded-md border border-hairline text-caption-sm text-ink hover:bg-canvas disabled:opacity-50"
                      >
                        设为代表头像
                      </button>
                      {moveCandidates.length > 0 && (
                        <>
                          <select
                            value={
                              moveTargets[face.id] ??
                              moveCandidates[0].id
                            }
                            onChange={(e) =>
                              setMoveTargets((prev) => ({
                                ...prev,
                                [face.id]: Number(e.target.value),
                              }))
                            }
                            className="px-2 py-1 rounded-md border border-hairline bg-canvas text-caption-sm"
                          >
                            {moveCandidates.map((candidate) => (
                              <option key={candidate.id} value={candidate.id}>
                                移动到：{candidate.display_name}
                              </option>
                            ))}
                          </select>
                          <button
                            type="button"
                            disabled={actionBusy}
                            onClick={() =>
                              onMoveFace(
                                face.id,
                                moveTargets[face.id] ?? moveCandidates[0].id,
                              )
                            }
                            className="px-2.5 py-1 rounded-md border border-hairline text-caption-sm text-ink hover:bg-canvas disabled:opacity-50"
                          >
                            移动
                          </button>
                        </>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

export function PeoplePage() {
  const { projectId } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const { currentProjectId, currentProject, setCurrentProjectId } = useProjectContext();
  const queryClient = useQueryClient();
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const routeProjectId = projectId ? Number(projectId) : NaN;
  const normalizedRouteProjectId = Number.isFinite(routeProjectId) ? routeProjectId : null;
  const normalizedCurrentProjectId =
    currentProjectId !== null && Number.isFinite(currentProjectId)
      ? currentProjectId
      : null;

  useEffect(() => {
    if (normalizedCurrentProjectId !== null) return;
    if (normalizedRouteProjectId === null) return;
    setCurrentProjectId(normalizedRouteProjectId);
  }, [normalizedCurrentProjectId, normalizedRouteProjectId, setCurrentProjectId]);

  const selectedProjectId = normalizedRouteProjectId ?? normalizedCurrentProjectId;

  if (selectedProjectId == null) {
    return (
      <main className="max-w-[1440px] mx-auto px-4 sm:px-6 py-6">
        <div className="bg-canvas border border-hairline rounded-xl p-6 text-mute">
          请先选择一个项目，再查看人物页。
        </div>
      </main>
    );
  }

  if (normalizedRouteProjectId == null) {
    return <Navigate to={`/projects/${selectedProjectId}/people`} replace />;
  }

  const selectedPersonIdRaw = searchParams.get("person_id");
  const selectedPersonId = selectedPersonIdRaw ? Number(selectedPersonIdRaw) : null;

  const {
    data: peopleData,
    isLoading: peopleLoading,
    error: peopleError,
  } = useQuery({
    queryKey: queryKeys.projectPeople(selectedProjectId, true),
    queryFn: () => api.projects.people(selectedProjectId, true),
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
    queryFn: () => api.projects.person(selectedProjectId, resolvedSelectedPersonId!),
    enabled: resolvedSelectedPersonId != null,
    staleTime: 15_000,
  });

  const { data: reviewData } = useQuery({
    queryKey: ["project-review-pending", selectedProjectId, resolvedSelectedPersonId],
    queryFn: () => api.projects.reviewPending(selectedProjectId, resolvedSelectedPersonId, 500, 0),
    enabled: resolvedSelectedPersonId != null,
    staleTime: 15_000,
  });

  const refreshPeopleData = () => {
    queryClient.invalidateQueries({ queryKey: queryKeys.projectPeople(selectedProjectId, true) });
    queryClient.invalidateQueries({ queryKey: queryKeys.projectPerson(selectedProjectId, resolvedSelectedPersonId) });
    queryClient.invalidateQueries({ queryKey: ["project-review-pending", selectedProjectId, resolvedSelectedPersonId] });
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
      api.projects.renamePerson(selectedProjectId, resolvedSelectedPersonId!, displayName),
    onSuccess: () => handleSuccess("人物名称已更新"),
    onError: handleError,
  });

  const confirmMutation = useMutation({
    mutationFn: (faceId: number) =>
      api.projects.confirmPersonFace(selectedProjectId, resolvedSelectedPersonId!, faceId),
    onSuccess: () => handleSuccess("已确认这张脸属于当前人物"),
    onError: handleError,
  });

  const rejectMutation = useMutation({
    mutationFn: (faceId: number) =>
      api.projects.rejectPersonFace(selectedProjectId, resolvedSelectedPersonId!, faceId),
    onSuccess: () => handleSuccess("已标记为不是此人"),
    onError: handleError,
  });

  const moveMutation = useMutation({
    mutationFn: ({ faceId, targetPersonId }: { faceId: number; targetPersonId: number }) =>
      api.projects.movePersonFace(selectedProjectId, resolvedSelectedPersonId!, faceId, {
        target_person_id: targetPersonId,
      }),
    onSuccess: () => handleSuccess("已移动到目标人物"),
    onError: handleError,
  });

  const representativeMutation = useMutation({
    mutationFn: (faceId: number) =>
      api.projects.setPersonRepresentativeFace(selectedProjectId, resolvedSelectedPersonId!, faceId),
    onSuccess: () => handleSuccess("代表头像已更新"),
    onError: handleError,
  });

  const batchConfirmMutation = useMutation({
    mutationFn: (faceIds: number[]) =>
      api.projects.batchConfirmReview(selectedProjectId, resolvedSelectedPersonId!, {
        face_detection_ids: faceIds,
      }),
    onSuccess: (result) => handleSuccess(`已批量确认 ${result.updated} 张待确认人脸`),
    onError: handleError,
  });

  const batchRejectMutation = useMutation({
    mutationFn: (faceIds: number[]) =>
      api.projects.batchRejectReview(selectedProjectId, resolvedSelectedPersonId!, {
        face_detection_ids: faceIds,
      }),
    onSuccess: (result) => handleSuccess(`已批量排除 ${result.updated} 张待确认人脸`),
    onError: handleError,
  });

  const batchMoveMutation = useMutation({
    mutationFn: ({ faceIds, targetPersonId }: { faceIds: number[]; targetPersonId: number }) =>
      api.projects.batchMoveReview(selectedProjectId, resolvedSelectedPersonId!, {
        face_detection_ids: faceIds,
        target_person_id: targetPersonId,
      }),
    onSuccess: (result) => handleSuccess(`已批量移动 ${result.updated} 张待确认人脸`),
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
    batchMoveMutation.isPending;
  const moveCandidates = people.filter((person) => person.id !== resolvedSelectedPersonId);
  const reviewFaceIds = (reviewData?.items ?? []).map((item) => item.face_detection_id);

  const namedCount = people.filter((item) => item.is_named).length;
  const unnamedCount = Math.max(0, people.length - namedCount);

  return (
    <main className="max-w-[1440px] mx-auto px-4 sm:px-6 py-6 space-y-6">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-heading-md font-semibold text-ink">人物</h1>
          <p className="text-body-sm text-mute mt-1">
            项目：{currentProject?.id === selectedProjectId ? currentProject.name : `#${selectedProjectId}`} ·
            共 {people.length} 个分组
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <span className="px-3 py-1 rounded-full bg-emerald-50 text-emerald-800 text-caption-md">
            已命名 {namedCount}
          </span>
          <span className="px-3 py-1 rounded-full bg-secondary-bg text-mute text-caption-md">
            未命名 {unnamedCount}
          </span>
          <Link
            to={`/projects/${selectedProjectId}/settings/ai`}
            className="px-3 py-1.5 rounded-md border border-hairline text-body-sm text-ink hover:bg-surface-card"
          >
            打开 AI / Face 配置
          </Link>
          <Link
            to={`/projects/${selectedProjectId}/people/review`}
            className="px-3 py-1.5 rounded-md border border-hairline text-body-sm text-ink hover:bg-surface-card"
          >
            打开 Review 页
          </Link>
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[360px_minmax(0,1fr)] gap-5">
        <section className="space-y-3">
          <div className="bg-canvas rounded-xl border border-hairline p-4">
            <div className="flex items-center gap-2 mb-2">
              <Users className="w-4 h-4 text-primary" />
              <h2 className="text-body-sm font-semibold text-ink">人物列表</h2>
            </div>
            <p className="text-caption-sm text-mute">
              先展示当前项目里已有的人物分组。后续会在这里接合并、拆分、待确认筛选。
            </p>
          </div>

          {peopleLoading ? (
            <div className="bg-canvas rounded-xl border border-hairline p-6 flex items-center gap-3 text-mute">
              <Loader2 className="w-4 h-4 animate-spin" />
              正在加载人物列表...
            </div>
          ) : peopleError ? (
            <div className="bg-canvas rounded-xl border border-hairline p-6 flex items-center gap-3 text-danger">
              <AlertCircle className="w-4 h-4" />
              {(peopleError as Error).message}
            </div>
          ) : people.length === 0 ? (
            <div className="bg-canvas rounded-xl border border-hairline p-8 text-center text-mute">
              <ScanFace className="w-8 h-8 mx-auto mb-3" />
              还没有人物分组。先去照片详情里执行手动人脸扫描，或者后续接项目级批量扫描。
            </div>
          ) : (
            <div className="space-y-3">
              {people.map((person) => (
                <PersonCard
                  key={person.id}
                  projectId={selectedProjectId}
                  person={person}
                  selected={resolvedSelectedPersonId === person.id}
                  onSelect={() => {
                    const next = new URLSearchParams(searchParams);
                    next.set("person_id", String(person.id));
                    setSearchParams(next);
                  }}
                />
              ))}
            </div>
          )}
        </section>

        <section>
          <PersonDetailPanel
            projectId={selectedProjectId}
            detail={personDetail}
            isLoading={personLoading}
            error={personError as Error | null}
            moveCandidates={moveCandidates}
            reviewFaceIds={reviewFaceIds}
            statusMessage={statusMessage}
            errorMessage={errorMessage}
            actionBusy={actionBusy}
            onRename={(displayName) => {
              if (!resolvedSelectedPersonId) return;
              renameMutation.mutate(displayName.trim());
            }}
            onConfirmFace={(faceId) => {
              if (!resolvedSelectedPersonId) return;
              confirmMutation.mutate(faceId);
            }}
            onRejectFace={(faceId) => {
              if (!resolvedSelectedPersonId) return;
              rejectMutation.mutate(faceId);
            }}
            onMoveFace={(faceId, targetPersonId) => {
              if (!resolvedSelectedPersonId) return;
              moveMutation.mutate({ faceId, targetPersonId });
            }}
            onBatchConfirmReview={(faceIds) => {
              if (!resolvedSelectedPersonId || faceIds.length === 0) return;
              batchConfirmMutation.mutate(faceIds);
            }}
            onBatchRejectReview={(faceIds) => {
              if (!resolvedSelectedPersonId || faceIds.length === 0) return;
              batchRejectMutation.mutate(faceIds);
            }}
            onBatchMoveReview={(faceIds, targetPersonId) => {
              if (!resolvedSelectedPersonId || faceIds.length === 0) return;
              batchMoveMutation.mutate({ faceIds, targetPersonId });
            }}
            onSetRepresentative={(faceId) => {
              if (!resolvedSelectedPersonId) return;
              representativeMutation.mutate(faceId);
            }}
          />
        </section>
      </div>
    </main>
  );
}
