import { AlertCircle, Loader2, ScanFace } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { api } from "@/api";
import { usePeopleReviewPage } from "@/hooks/usePeopleReviewPage";

export function PeopleReviewPage() {
  const [movePickerPersonId, setMovePickerPersonId] = useState<number | null>(null);
  const {
    routeProjectId,
    currentProject,
    selectedProjectId,
    selectedReviewPersonId,
    page,
    setPage,
    statusMessage,
    errorMessage,
    grouped,
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
    archivePerson,
    deletePerson,
    batchConfirmReview,
    batchRejectReview,
    batchMoveReview,
  } = usePeopleReviewPage();
  const [activePersonId, setActivePersonId] = useState<number | null>(null);
  const [selectedFaceIdsByPerson, setSelectedFaceIdsByPerson] = useState<Record<number, number[]>>(
    {},
  );

  const activeEntry =
    grouped.find(([personId]) => personId === activePersonId) ?? grouped[0] ?? null;
  const activePersonIdResolved = activeEntry?.[0] ?? null;
  const activeItems = activeEntry?.[1] ?? [];
  const activeFaceIds = activeItems.map((item) => item.face_detection_id);
  const activeSelectedFaceIds =
    activePersonIdResolved == null
      ? []
      : (selectedFaceIdsByPerson[activePersonIdResolved] ?? []).filter((faceId) =>
          activeFaceIds.includes(faceId),
        );
  const activeActionFaceIds =
    activeSelectedFaceIds.length > 0 ? activeSelectedFaceIds : activeFaceIds;
  const activeSelectionLabel =
    activeSelectedFaceIds.length > 0
      ? `已选 ${activeSelectedFaceIds.length} / ${activeFaceIds.length} 张`
      : "未选择时将操作当前目标全部人脸";
  const activePersonName =
    activePersonIdResolved == null
      ? null
      : (peopleById.get(activePersonIdResolved) ?? "未命名");
  const selectedReviewPersonName =
    selectedReviewPersonId == null
      ? null
      : (peopleById.get(selectedReviewPersonId) ?? `#${selectedReviewPersonId}`);
  const activeTargetCandidates =
    activePersonIdResolved == null
      ? []
      : (peopleData?.items ?? []).filter((item) => item.id !== activePersonIdResolved);
  const activeMoveTarget =
    activePersonIdResolved == null
      ? null
      : (moveTargets[activePersonIdResolved] ?? activeTargetCandidates[0]?.id ?? null);
  const movePickerOpen =
    activePersonIdResolved != null && movePickerPersonId === activePersonIdResolved;

  useEffect(() => {
    if (grouped.length === 0) {
      setActivePersonId(null);
      return;
    }
    if (activePersonId != null && grouped.some(([personId]) => personId === activePersonId)) {
      return;
    }
    setActivePersonId(grouped[0][0]);
  }, [activePersonId, grouped]);

  useEffect(() => {
    const visibleFaceIds = new Set(
      grouped.flatMap(([, items]) => items.map((item) => item.face_detection_id)),
    );
    setSelectedFaceIdsByPerson((prev) => {
      let changed = false;
      const next: Record<number, number[]> = {};
      for (const [personId, faceIds] of Object.entries(prev)) {
        const filtered = faceIds.filter((faceId) => visibleFaceIds.has(faceId));
        if (filtered.length > 0) {
          next[Number(personId)] = filtered;
        }
        if (filtered.length !== faceIds.length) {
          changed = true;
        }
      }
      return changed ? next : prev;
    });
  }, [grouped]);

  const toggleFaceSelection = (personId: number, faceId: number) => {
    setSelectedFaceIdsByPerson((prev) => {
      const current = prev[personId] ?? [];
      const exists = current.includes(faceId);
      const nextForPerson = exists
        ? current.filter((id) => id !== faceId)
        : [...current, faceId];
      return {
        ...prev,
        [personId]: nextForPerson,
      };
    });
  };

  const selectAllFaces = (personId: number, faceIds: number[]) => {
    setSelectedFaceIdsByPerson((prev) => ({
      ...prev,
      [personId]: faceIds,
    }));
  };

  const clearFaceSelection = (personId: number) => {
    setSelectedFaceIdsByPerson((prev) => {
      const next = { ...prev };
      delete next[personId];
      return next;
    });
  };

  if (!Number.isFinite(routeProjectId) || routeProjectId <= 0) {
    return <Navigate to="/photos" replace />;
  }

  return (
    <main className="max-w-[1440px] mx-auto px-4 sm:px-6 py-6 space-y-5">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-heading-md font-semibold text-ink">Review Pending</h1>
          <p className="text-body-sm text-mute mt-1">
            项目 {currentProject?.id === selectedProjectId ? currentProject.name : `#${selectedProjectId}`} · 共 {reviewData?.total ?? 0} 条待确认
            {selectedReviewPersonId != null &&
              ` · 只看 ${selectedReviewPersonName} (#${selectedReviewPersonId})`}
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {selectedReviewPersonId != null && (
            <>
              <Link
                to={`/projects/${selectedProjectId}/people?person_id=${selectedReviewPersonId}`}
                className="px-3 py-1.5 rounded-md border border-hairline text-body-sm text-ink hover:bg-surface-card"
              >
                返回当前人物
              </Link>
              <Link
                to={`/projects/${selectedProjectId}/people/review`}
                className="px-3 py-1.5 rounded-md border border-hairline text-body-sm text-ink hover:bg-surface-card"
              >
                查看全部 review
              </Link>
            </>
          )}
          <Link
            to={`/projects/${selectedProjectId}/people`}
            className="px-3 py-1.5 rounded-md border border-hairline text-body-sm text-ink hover:bg-surface-card"
          >
            返回人物页
          </Link>
        </div>
      </div>

      {statusMessage && (
        <div className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-caption-sm text-emerald-800">
          {statusMessage}
        </div>
      )}
      {errorMessage && (
        <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-caption-sm text-red-800">
          {errorMessage}
        </div>
      )}

      <div className="flex items-center justify-between gap-3 bg-canvas border border-hairline rounded-xl p-3">
        <button
          type="button"
          className="px-3 py-1.5 rounded-md border border-hairline text-body-sm disabled:opacity-50"
          disabled={page <= 1}
          onClick={() => setPage((prev) => Math.max(1, prev - 1))}
        >
          上一页
        </button>
        <span className="text-caption-sm text-mute">第 {page} / {maxPage} 页</span>
        <button
          type="button"
          className="px-3 py-1.5 rounded-md border border-hairline text-body-sm disabled:opacity-50"
          disabled={page >= maxPage || isFetching}
          onClick={() => setPage((prev) => Math.min(maxPage, prev + 1))}
        >
          {isFetching ? "加载中..." : "下一页"}
        </button>
      </div>

      {isLoading ? (
        <div className="bg-canvas rounded-xl border border-hairline p-6 flex items-center gap-3 text-mute">
          <Loader2 className="w-4 h-4 animate-spin" />
          正在加载待确认列表...
        </div>
      ) : error ? (
        <div className="bg-canvas rounded-xl border border-hairline p-6 flex items-center gap-3 text-danger">
          <AlertCircle className="w-4 h-4" />
          {(error as Error).message}
        </div>
      ) : grouped.length === 0 ? (
        <div className="bg-canvas rounded-xl border border-hairline p-8 text-center text-mute">
          {selectedReviewPersonId == null
            ? "当前没有 review_pending 人脸"
            : "当前人物没有 review_pending 人脸"}
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_340px] gap-4 h-[calc(100vh-220px)] min-h-[520px] overflow-hidden">
          <section className="min-h-0 overflow-y-auto pr-1 space-y-3">
            {grouped.map(([personId, items]) => {
              const personName = peopleById.get(personId) ?? "未命名";
              const selected = personId === activePersonIdResolved;
              const selectedFaceIds = selectedFaceIdsByPerson[personId] ?? [];

              return (
                <article
                  key={personId}
                  className={[
                    "bg-canvas rounded-xl border p-4 space-y-3",
                    selected ? "border-primary shadow-sm" : "border-hairline",
                  ].join(" ")}
                >
                  <div className="flex items-start justify-between gap-3 flex-wrap">
                    <button
                      type="button"
                      onClick={() => setActivePersonId(personId)}
                      className="min-w-0 text-left"
                    >
                      <h2 className="text-body-sm font-semibold text-ink">
                        人物 #{personId} · {personName}
                      </h2>
                      <p className="text-caption-sm text-mute mt-1">
                        当前页待确认 {items.length} 张，点击卡片设为右侧操作目标；勾选后仅处理已选人脸。
                      </p>
                    </button>
                    <div className="flex items-center gap-2 flex-wrap justify-end">
                      {selectedFaceIds.length > 0 && (
                        <span className="px-2 py-0.5 rounded-full bg-surface-soft text-caption-sm text-mute">
                          已选 {selectedFaceIds.length}
                        </span>
                      )}
                      {selected && (
                        <span className="px-2 py-0.5 rounded-full bg-primary/10 text-caption-sm text-primary">
                          当前目标
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-5 gap-2">
                    {items.map((assignment) => {
                      const faceSelected = selectedFaceIds.includes(assignment.face_detection_id);

                      return (
                        <button
                          type="button"
                          key={assignment.id}
                          onClick={() => {
                            setActivePersonId(personId);
                            toggleFaceSelection(personId, assignment.face_detection_id);
                          }}
                          aria-pressed={faceSelected}
                          aria-label={`选择 face #${assignment.face_detection_id}`}
                          className={[
                            "rounded-lg border bg-surface-soft p-2 text-left transition",
                            faceSelected
                              ? "border-primary ring-2 ring-primary/20"
                              : "border-hairline",
                          ].join(" ")}
                        >
                          <div className="w-full aspect-square rounded-md overflow-hidden border border-hairline bg-canvas mb-2">
                            {assignment.face_detection.face_crop_path ? (
                              <img
                                src={api.projectFaces.cropUrl(
                                  selectedProjectId,
                                  assignment.face_detection.id,
                                  assignment.face_detection.updated_at,
                                )}
                                alt={`face-${assignment.face_detection.id}`}
                                loading="lazy"
                                decoding="async"
                                className="w-full h-full object-cover"
                              />
                            ) : (
                              <div className="w-full h-full flex items-center justify-center text-mute">
                                <ScanFace className="w-4 h-4" />
                              </div>
                            )}
                          </div>
                          <div className="flex items-center justify-between gap-2 text-[11px] text-mute">
                            <span>face #{assignment.face_detection_id}</span>
                            {faceSelected && <span className="text-primary">已选</span>}
                            {assignment.similarity_score != null && (
                              <span>{Math.round(assignment.similarity_score * 100)}%</span>
                            )}
                          </div>
                        </button>
                      );
                    })}
                  </div>

                  <div className="flex items-center gap-2 flex-wrap border-t border-hairline pt-3">
                    <button
                      type="button"
                      onClick={() => setActivePersonId(personId)}
                      className="px-2.5 py-1 rounded-md border border-hairline text-caption-sm text-ink hover:bg-surface-card"
                    >
                      设为目标
                    </button>
                    <button
                      type="button"
                      onClick={() =>
                        selectedFaceIds.length === items.length
                          ? clearFaceSelection(personId)
                          : selectAllFaces(
                              personId,
                              items.map((item) => item.face_detection_id),
                            )
                      }
                      className="px-2.5 py-1 rounded-md border border-hairline text-caption-sm text-ink hover:bg-surface-card"
                    >
                      {selectedFaceIds.length === items.length ? "清除选择" : "全选"}
                    </button>
                    <Link
                      to={`/projects/${selectedProjectId}/people?person_id=${personId}`}
                      className="px-2.5 py-1 rounded-md border border-hairline text-caption-sm text-ink hover:bg-surface-card"
                    >
                      查看人物页
                    </Link>
                    <button
                      type="button"
                      onClick={() => archivePerson(personId)}
                      className="px-2.5 py-1 rounded-md border border-hairline text-caption-sm text-ink hover:bg-surface-card"
                    >
                      archive
                    </button>
                    <button
                      type="button"
                      disabled={actionBusy}
                      onClick={() => {
                        if (!window.confirm("删除人物前，请确保没有 active assignment。确认继续？")) return;
                        deletePerson(personId);
                      }}
                      className="px-2.5 py-1 rounded-md border border-red-200 text-caption-sm text-red-700 hover:bg-red-50 disabled:opacity-50"
                    >
                      delete
                    </button>
                  </div>
                </article>
              );
            })}

          </section>

          <aside className="min-h-0 rounded-xl border border-hairline bg-canvas p-4">
            <div className="h-full overflow-y-auto space-y-4">
              <div>
                <p className="text-caption-sm text-mute">右侧功能框</p>
                {activePersonIdResolved == null ? (
                  <h2 className="text-body-sm font-semibold text-ink mt-0.5">请选择左侧卡片</h2>
                ) : (
                  <>
                    <h2 className="text-body-sm font-semibold text-ink mt-0.5">
                      人物 #{activePersonIdResolved} · {activePersonName}
                    </h2>
                    <p className="text-caption-sm text-mute mt-1">
                      当前目标 {activeItems.length} 张待确认人脸。
                    </p>
                    <p className="text-caption-sm text-mute mt-1">{activeSelectionLabel}</p>
                  </>
                )}
              </div>

              {activePersonIdResolved != null && (
                <>
                  <div className="grid grid-cols-2 gap-2">
                    <button
                      type="button"
                      disabled={actionBusy || activeActionFaceIds.length === 0}
                      onClick={() => batchConfirmReview(activePersonIdResolved, activeActionFaceIds)}
                      className="px-2.5 py-2 rounded-md border border-emerald-200 bg-emerald-50 text-caption-sm text-emerald-800 hover:bg-emerald-100 disabled:opacity-50"
                    >
                      {activeSelectedFaceIds.length > 0
                        ? `确认已选 (${activeSelectedFaceIds.length})`
                        : "批量确认"}
                    </button>
                    <button
                      type="button"
                      disabled={actionBusy || activeActionFaceIds.length === 0}
                      onClick={() => batchRejectReview(activePersonIdResolved, activeActionFaceIds)}
                      className="px-2.5 py-2 rounded-md border border-red-200 bg-red-50 text-caption-sm text-red-800 hover:bg-red-100 disabled:opacity-50"
                    >
                      {activeSelectedFaceIds.length > 0
                        ? `排除已选 (${activeSelectedFaceIds.length})`
                        : "批量排除"}
                    </button>
                  </div>

                  {activeTargetCandidates.length > 0 && activeMoveTarget != null && (
                    <div className="space-y-2">
                      {!movePickerOpen ? (
                        <button
                          type="button"
                          disabled={actionBusy}
                          onClick={() => setMovePickerPersonId(activePersonIdResolved)}
                          className="w-full px-2.5 py-2 rounded-md border border-hairline text-caption-sm text-ink hover:bg-surface-card disabled:opacity-50"
                        >
                          移动到...
                        </button>
                      ) : (
                        <>
                          <select
                            className="w-full px-2 py-2 rounded-md border border-hairline bg-canvas text-caption-sm"
                            value={activeMoveTarget}
                            onChange={(e) => {
                              setMoveTargets((prev) => ({
                                ...prev,
                                [activePersonIdResolved]: Number(e.target.value),
                              }));
                            }}
                          >
                            {activeTargetCandidates.map((candidate) => (
                              <option key={candidate.id} value={candidate.id}>
                                移动到：{candidate.display_name}
                              </option>
                            ))}
                          </select>
                          <div className="grid grid-cols-2 gap-2">
                            <button
                              type="button"
                              disabled={actionBusy}
                              onClick={() =>
                                batchMoveReview(
                                  activePersonIdResolved,
                                  activeMoveTarget,
                                  activeActionFaceIds,
                                )
                              }
                              className="px-2.5 py-2 rounded-md border border-hairline text-caption-sm text-ink hover:bg-surface-card disabled:opacity-50"
                            >
                              {activeSelectedFaceIds.length > 0
                                ? `移动已选 (${activeSelectedFaceIds.length})`
                                : "批量移动"}
                            </button>
                            <button
                              type="button"
                              onClick={() => setMovePickerPersonId(null)}
                              className="px-2.5 py-2 rounded-md border border-hairline text-caption-sm text-ink hover:bg-surface-card"
                            >
                              收起
                            </button>
                          </div>
                        </>
                      )}
                    </div>
                  )}
                </>
              )}
            </div>
          </aside>
        </div>
      )}
    </main>
  );
}
