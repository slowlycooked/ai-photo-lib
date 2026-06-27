import { AlertCircle, Loader2, ScanFace } from "lucide-react";
import { useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { api } from "@/api";
import { usePeopleReviewPage } from "@/hooks/usePeopleReviewPage";

export function PeopleReviewPage() {
  const [movePickerPersonId, setMovePickerPersonId] = useState<number | null>(null);
  const {
    routeProjectId,
    currentProject,
    selectedProjectId,
    page,
    setPage,
    statusMessage,
    errorMessage,
    grouped,
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
    batchConfirmReview,
    batchRejectReview,
    batchMoveReview,
  } = usePeopleReviewPage();

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
          </p>
        </div>
        <div className="flex items-center gap-2">
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
      ) : grouped.length === 0 && groupedArchived.length === 0 ? (
        <div className="bg-canvas rounded-xl border border-hairline p-8 text-center text-mute">
          当前没有 review_pending 人脸
        </div>
      ) : (
        <div className="space-y-4">
          {grouped.map(([personId, items]) => {
            const faceIds = items.map((item) => item.face_detection_id);
            const targetCandidates = (peopleData?.items ?? []).filter((item) => item.id !== personId);
            const currentMoveTarget = moveTargets[personId] ?? targetCandidates[0]?.id ?? null;
            const movePickerOpen = movePickerPersonId === personId;
            const personName = peopleById.get(personId) ?? "未命名";

            return (
              <section key={personId} className="bg-canvas rounded-xl border border-hairline">
                <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_300px]">
                  <div className="min-w-0 p-4 space-y-3">
                    <div className="flex items-center justify-between gap-3 flex-wrap">
                      <div>
                        <h2 className="text-body-sm font-semibold text-ink">
                          人物 #{personId} · {personName}
                        </h2>
                        <p className="text-caption-sm text-mute mt-1">
                          当前页待确认 {items.length} 张，批量操作仅作用于本组。
                        </p>
                      </div>
                      <Link
                        to={`/projects/${selectedProjectId}/people?person_id=${personId}`}
                        className="px-2.5 py-1 rounded-md border border-hairline text-caption-sm text-ink hover:bg-surface-card"
                      >
                        查看人物页
                      </Link>
                    </div>

                    <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-5 gap-2">
                      {items.map((assignment) => (
                        <div
                          key={assignment.id}
                          className="rounded-lg border border-hairline bg-surface-soft p-2"
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
                            {assignment.similarity_score != null && (
                              <span>{Math.round(assignment.similarity_score * 100)}%</span>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  <aside className="sticky bottom-0 z-10 border-t border-hairline bg-surface-soft/95 p-4 backdrop-blur lg:bottom-auto lg:top-4 lg:self-start lg:border-l lg:border-t-0">
                    <div className="space-y-3">
                      <div>
                        <p className="text-caption-sm text-mute">当前批量目标</p>
                        <p className="text-body-sm font-semibold text-ink mt-0.5">
                          {personName} · {items.length} 张
                        </p>
                      </div>

                      <div className="grid grid-cols-2 gap-2">
                        <button
                          type="button"
                          disabled={actionBusy}
                          onClick={() => batchConfirmReview(personId, faceIds)}
                          className="px-2.5 py-2 rounded-md border border-emerald-200 bg-emerald-50 text-caption-sm text-emerald-800 hover:bg-emerald-100 disabled:opacity-50"
                        >
                          批量确认
                        </button>
                        <button
                          type="button"
                          disabled={actionBusy}
                          onClick={() => batchRejectReview(personId, faceIds)}
                          className="px-2.5 py-2 rounded-md border border-red-200 bg-red-50 text-caption-sm text-red-800 hover:bg-red-100 disabled:opacity-50"
                        >
                          批量排除
                        </button>
                      </div>

                      {targetCandidates.length > 0 && currentMoveTarget != null && (
                        <div className="space-y-2">
                          {!movePickerOpen ? (
                            <button
                              type="button"
                              disabled={actionBusy}
                              onClick={() => setMovePickerPersonId(personId)}
                              className="w-full px-2.5 py-2 rounded-md border border-hairline text-caption-sm text-ink hover:bg-canvas disabled:opacity-50"
                            >
                              移动到...
                            </button>
                          ) : (
                            <>
                              <select
                                className="w-full px-2 py-2 rounded-md border border-hairline bg-canvas text-caption-sm"
                                value={currentMoveTarget}
                                onChange={(e) => {
                                  setMoveTargets((prev) => ({
                                    ...prev,
                                    [personId]: Number(e.target.value),
                                  }));
                                }}
                              >
                                {targetCandidates.map((candidate) => (
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
                                    batchMoveReview(personId, currentMoveTarget, faceIds)
                                  }
                                  className="px-2.5 py-2 rounded-md border border-hairline text-caption-sm text-ink hover:bg-canvas disabled:opacity-50"
                                >
                                  批量移动
                                </button>
                                <button
                                  type="button"
                                  onClick={() => setMovePickerPersonId(null)}
                                  className="px-2.5 py-2 rounded-md border border-hairline text-caption-sm text-ink hover:bg-canvas"
                                >
                                  收起
                                </button>
                              </div>
                            </>
                          )}
                        </div>
                      )}
                    </div>
                  </aside>
                </div>
              </section>
            );
          })}

          {groupedArchived.length > 0 && (
            <section className="bg-canvas rounded-xl border border-hairline p-4 space-y-3">
              <div>
                <h2 className="text-body-sm font-semibold text-mute">archive 文件夹（不再管理）</h2>
                <p className="text-caption-sm text-mute mt-1">
                  以下系统人物页已归档，仅展示，不提供批量确认/排除/移动操作。
                </p>
              </div>

              <div className="space-y-3">
                {groupedArchived.map(([personId, items]) => (
                  <div key={personId} className="rounded-lg border border-hairline bg-surface-soft p-3">
                    <div className="text-caption-sm text-mute mb-2">
                      人物 #{personId} · {peopleById.get(personId) ?? "未命名"} · 当前页 {items.length} 张
                    </div>
                    <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-6 gap-2">
                      {items.map((assignment) => (
                        <div
                          key={assignment.id}
                          className="rounded-lg border border-hairline bg-canvas p-2"
                        >
                          <div className="w-full aspect-square rounded-md overflow-hidden border border-hairline bg-surface-soft mb-2">
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
                          <div className="text-[11px] text-mute">
                            face #{assignment.face_detection_id}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}
        </div>
      )}
    </main>
  );
}
