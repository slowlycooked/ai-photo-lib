import { useEffect, useState } from "react";
import {
  AlertCircle,
  Loader2,
  RefreshCw,
  ScanFace,
  UserRound,
  Users,
  X,
  ZoomIn,
} from "lucide-react";
import { Link } from "react-router-dom";
import { api, type PersonDetail, type PersonSummary } from "@/api";
import { formatDateTime } from "./formatDateTime";

function PersonOriginalPhotoLightbox({
  projectId,
  photoId,
  faceId,
  onClose,
}: {
  projectId: number;
  photoId: number;
  faceId: number;
  onClose: () => void;
}) {
  const [imgLoaded, setImgLoaded] = useState(false);
  const [imgError, setImgError] = useState<string | null>(null);

  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ backgroundColor: "rgba(0,0,0,0.85)" }}
      onClick={onClose}
    >
      <div
        className="relative max-w-[92vw] max-h-[92vh] flex flex-col items-center"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          type="button"
          onClick={onClose}
          className="absolute top-3 right-3 z-10 w-9 h-9 rounded-full bg-black/60 flex items-center justify-center hover:bg-black/80 transition-colors"
          aria-label="关闭预览"
        >
          <X className="w-4 h-4 text-white" />
        </button>

        {!imgLoaded && (
          <div className="flex items-center justify-center" style={{ minWidth: 220, minHeight: 220 }}>
            {imgError ? (
              <div className="max-w-[320px] text-center text-white/85 text-sm px-4">{imgError}</div>
            ) : (
              <Loader2 className="w-8 h-8 animate-spin text-white/70" />
            )}
          </div>
        )}

        <img
          src={api.projectPhotos.previewUrl(projectId, photoId)}
          alt={`face-${faceId}-photo-${photoId}`}
          decoding="async"
          className="rounded-md object-contain shadow-2xl"
          style={{
            maxWidth: "92vw",
            maxHeight: "84vh",
            opacity: imgLoaded ? 1 : 0,
            transition: "opacity 0.2s",
          }}
          onLoad={() => {
            setImgLoaded(true);
            setImgError(null);
          }}
          onError={() => {
            setImgLoaded(false);
            setImgError("原图预览加载失败，请确认文件仍在磁盘或稍后重试");
          }}
        />

        <div className="mt-3 px-3 py-1.5 rounded-md bg-black/60 text-white text-xs">
          face #{faceId} · photo #{photoId}
        </div>
      </div>
    </div>
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

export function PersonDetailPanel({
  projectId,
  faceCropEnabled,
  detail,
  isLoading,
  isFetching,
  error,
  moveCandidates,
  reviewFaceIds,
  statusMessage,
  errorMessage,
  actionBusy,
  loadedAssignmentCount,
  totalAssignmentCount,
  canLoadMoreAssignments,
  onRename,
  onConfirmFace,
  onRejectFace,
  onMoveFace,
  onBatchConfirmReview,
  onBatchRejectReview,
  onBatchMoveReview,
  onSplitFaces,
  onSetRepresentative,
  onRematchPersonFaces,
  rematchBusy,
  onLoadMoreAssignments,
}: {
  projectId: number;
  faceCropEnabled: boolean;
  detail: PersonDetail | undefined;
  isLoading: boolean;
  isFetching: boolean;
  error: Error | null;
  moveCandidates: PersonSummary[];
  reviewFaceIds: number[];
  statusMessage: string | null;
  errorMessage: string | null;
  actionBusy: boolean;
  loadedAssignmentCount: number;
  totalAssignmentCount: number;
  canLoadMoreAssignments: boolean;
  onRename: (displayName: string) => void;
  onConfirmFace: (faceId: number) => void;
  onRejectFace: (faceId: number) => void;
  onMoveFace: (faceId: number, targetPersonId: number) => void;
  onBatchConfirmReview: (faceIds: number[]) => void;
  onBatchRejectReview: (faceIds: number[]) => void;
  onBatchMoveReview: (faceIds: number[], targetPersonId: number) => void;
  onSplitFaces: (faceIds: number[], newDisplayName?: string) => void;
  onSetRepresentative: (faceId: number) => void;
  onRematchPersonFaces: () => void;
  rematchBusy: boolean;
  onLoadMoreAssignments: () => void;
}) {
  const [renameValue, setRenameValue] = useState("");
  const [moveTargets, setMoveTargets] = useState<Record<number, number>>({});
  const [batchMoveTargetId, setBatchMoveTargetId] = useState<number | null>(null);
  const [splitFaceIds, setSplitFaceIds] = useState<number[]>([]);
  const [splitName, setSplitName] = useState("");
  const [previewTarget, setPreviewTarget] = useState<{ photoId: number; faceId: number } | null>(
    null,
  );

  useEffect(() => {
    setRenameValue(detail?.display_name ?? "");
  }, [detail?.id, detail?.display_name]);

  useEffect(() => {
    setBatchMoveTargetId(moveCandidates[0]?.id ?? null);
  }, [moveCandidates]);

  useEffect(() => {
    setSplitFaceIds([]);
    setSplitName("");
  }, [detail?.id]);

  useEffect(() => {
    if (!detail) return;
    const activeFaceIds = new Set(
      detail.assignments
        .filter((item) => item.assignment_status !== "rejected")
        .map((item) => item.face_detection.id),
    );
    setSplitFaceIds((prev) => prev.filter((faceId) => activeFaceIds.has(faceId)));
  }, [detail]);

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

  const positiveAssignments = detail.assignments.filter(
    (item) => item.is_positive_sample && item.assignment_status !== "rejected",
  );
  const candidateAssignments = detail.assignments.filter(
    (item) => !item.is_positive_sample && item.assignment_status !== "rejected",
  );
  const candidateReviewPendingAssignments = candidateAssignments.filter(
    (item) => item.assignment_status === "review_pending",
  );
  const candidateReviewPendingFaceIds = candidateReviewPendingAssignments.map(
    (item) => item.face_detection.id,
  );
  const candidateAutoAssignedAssignments = candidateAssignments.filter(
    (item) => item.assignment_status === "auto_assigned",
  );
  const candidateAutoAssignedFaceIds = candidateAutoAssignedAssignments.map(
    (item) => item.face_detection.id,
  );
  const allConfirmableCandidateFaceIds = Array.from(
    new Set([...candidateReviewPendingFaceIds, ...candidateAutoAssignedFaceIds]),
  );
  const candidateOtherAssignments = candidateAssignments.filter(
    (item) =>
      item.assignment_status !== "review_pending" && item.assignment_status !== "auto_assigned",
  );
  const negativeAssignments = detail.assignments.filter(
    (item) => item.assignment_status === "rejected",
  );

  const confirmed = positiveAssignments.length;
  const autoAssigned = detail.assignments.filter(
    (item) => item.assignment_status === "auto_assigned",
  ).length;
  const reviewPending = detail.assignments.filter(
    (item) => item.assignment_status === "review_pending",
  ).length;

  const similarityDistribution = (() => {
    const scores = candidateAssignments
      .map((item) => item.similarity_score)
      .filter((value): value is number => value != null)
      .sort((a, b) => b - a);
    if (scores.length === 0) {
      return null;
    }
    const medianIndex = Math.floor(scores.length / 2);
    const top = scores[0];
    const median = scores[medianIndex];
    const bottom = scores[scores.length - 1];
    return {
      top,
      median,
      bottom,
      count: scores.length,
    };
  })();

  const representativeFace =
    detail.representative_face_detection_id == null
      ? null
      : detail.assignments.find(
          (item) => item.face_detection.id === detail.representative_face_detection_id,
        )?.face_detection ?? null;

  const renderAssignmentCard = (assignment: PersonDetail["assignments"][number]) => {
    const face = assignment.face_detection;
    const explanation = assignment.explanation;
    const splitSelectable = assignment.assignment_status !== "rejected";
    const splitChecked = splitFaceIds.includes(face.id);
    return (
      <div
        key={assignment.id}
        className="rounded-xl border border-hairline bg-surface-soft p-3 flex gap-3"
      >
        <button
          type="button"
          onClick={() => setPreviewTarget({ photoId: face.photo_id, faceId: face.id })}
          className="w-24 h-24 rounded-lg overflow-hidden border border-hairline bg-canvas flex-shrink-0 relative group cursor-zoom-in"
          title="预览原始照片"
          aria-label={`预览 face ${face.id} 的原始照片`}
        >
          {faceCropEnabled && face.face_crop_path ? (
            <img
              src={api.projectFaces.cropUrl(projectId, face.id, face.updated_at)}
              alt={`face-${face.id}`}
              loading="lazy"
              decoding="async"
              className="w-full h-full object-cover"
            />
          ) : (
            <div className="w-full h-full flex items-center justify-center text-mute">
              <ScanFace className="w-5 h-5" />
            </div>
          )}
          <div className="absolute inset-0 bg-black/0 group-hover:bg-black/25 transition-colors flex items-center justify-center">
            <ZoomIn className="w-4 h-4 text-white opacity-0 group-hover:opacity-100 transition-opacity" />
          </div>
        </button>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            {splitSelectable && (
              <label className="inline-flex items-center gap-1 text-caption-sm text-mute">
                <input
                  type="checkbox"
                  checked={splitChecked}
                  onChange={(e) => {
                    setSplitFaceIds((prev) => {
                      if (e.target.checked) return [...prev, face.id];
                      return prev.filter((id) => id !== face.id);
                    });
                  }}
                />
                拆分
              </label>
            )}
            <span className="text-body-sm font-medium text-ink">face #{face.id}</span>
            <span className="px-2 py-0.5 rounded-full bg-canvas text-caption-sm text-ink border border-hairline">
              {assignment.assignment_status}
            </span>
          </div>
          <p className="mt-1 text-caption-sm text-mute">source: {assignment.assignment_source}</p>
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
          <div className="mt-2 rounded-md border border-hairline bg-canvas px-2.5 py-2 text-caption-sm text-mute space-y-1">
            <p>
              匹配解释：source={explanation?.source ?? assignment.assignment_source}
              {" · auto="}
              {String(explanation?.is_auto ?? assignment.assignment_status === "auto_assigned")}
              {" · human_confirmed="}
              {String(
                explanation?.is_human_confirmed ??
                  ["human_confirmed", "human_corrected"].includes(assignment.assignment_status),
              )}
            </p>
            <p>
              similarity=
              {explanation?.similarity != null
                ? `${(explanation.similarity * 100).toFixed(0)}%`
                : assignment.similarity_score != null
                  ? `${(assignment.similarity_score * 100).toFixed(0)}%`
                  : "n/a"}
              {" · negative_constraint="}
              {String(explanation?.negative_constraint_affected ?? false)}
              {" · negative_count="}
              {explanation?.negative_constraint_count ?? 0}
            </p>
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
                  value={moveTargets[face.id] ?? moveCandidates[0].id}
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
                    onMoveFace(face.id, moveTargets[face.id] ?? moveCandidates[0].id)
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
  };

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
            {faceCropEnabled && detail.representative_face_detection_id ? (
              <button
                type="button"
                onClick={() => {
                  if (!representativeFace) return;
                  setPreviewTarget({ photoId: representativeFace.photo_id, faceId: representativeFace.id });
                }}
                disabled={!representativeFace}
                className="w-full h-full relative group cursor-zoom-in disabled:cursor-default"
                title={representativeFace ? "预览原始照片" : "无可预览原图"}
                aria-label={representativeFace ? "预览代表头像对应原图" : "无可预览原图"}
              >
                <img
                  src={api.projectFaces.cropUrl(
                    projectId,
                    detail.representative_face_detection_id,
                    detail.updated_at,
                  )}
                  alt={detail.display_name}
                  loading="lazy"
                  decoding="async"
                  className="w-full h-full object-cover"
                  onError={(e) => {
                    e.currentTarget.style.display = "none";
                  }}
                />
                {representativeFace && (
                  <div className="absolute inset-0 bg-black/0 group-hover:bg-black/25 transition-colors flex items-center justify-center">
                    <ZoomIn className="w-4 h-4 text-white opacity-0 group-hover:opacity-100 transition-opacity" />
                  </div>
                )}
              </button>
            ) : (
              <div className="w-full h-full flex items-center justify-center text-mute">
                <UserRound className="w-8 h-8" />
              </div>
            )}
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 flex-wrap">
              <h2 className="text-heading-md font-semibold text-ink">{detail.display_name}</h2>
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
            {detail.name_tags && detail.name_tags.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1">
                {detail.name_tags.map((tag) => (
                  <span
                    key={tag}
                    className="rounded-full bg-primary/10 px-2 py-0.5 text-caption-sm font-medium text-primary"
                  >
                    #{tag}
                  </span>
                ))}
              </div>
            )}
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
                placeholder="输入人物名称，可追加 #标签"
              />
              <button
                type="submit"
                disabled={actionBusy || !renameValue.trim()}
                className="px-3 py-1.5 rounded-md border border-hairline text-body-sm text-ink hover:bg-surface-card disabled:opacity-50"
              >
                重命名
              </button>
            </form>

            <div className="mt-3 flex flex-wrap items-center gap-2">
              <button
                type="button"
                disabled={
                  actionBusy ||
                  rematchBusy ||
                  !detail.is_named ||
                  detail.confirmed_sample_count === 0
                }
                onClick={onRematchPersonFaces}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-hairline text-body-sm text-ink hover:bg-surface-card disabled:opacity-50"
                title={
                  detail.is_named && detail.confirmed_sample_count > 0
                    ? "从已有扫描人脸中查找相似候选，并追加到候选样本"
                    : "需要已命名人物和至少一张正样本"
                }
              >
                <RefreshCw className={["w-3.5 h-3.5", rematchBusy ? "animate-spin" : ""].join(" ")} />
                {rematchBusy ? "聚合候选中..." : "从已扫描人脸找相似候选"}
              </button>
              <span className="text-caption-sm text-mute">
                命中的相似人脸会追加到当前详情页的候选样本。
              </span>
            </div>
          </div>
        </div>

        <div className="mt-4 grid grid-cols-2 md:grid-cols-6 gap-3">
          <AssignmentChip label="总样本" value={detail.sample_count} />
          <AssignmentChip label="正样本" value={confirmed} />
          <AssignmentChip label="候选" value={candidateAssignments.length} />
          <AssignmentChip label="负样本" value={negativeAssignments.length} />
          <AssignmentChip label="自动识别" value={autoAssigned} />
          <AssignmentChip label="待确认" value={reviewPending} />
        </div>
      </div>

      <div className="px-6 py-5 space-y-4">
        {reviewFaceIds.length > 0 && (
          <div className="sticky top-3 z-10 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 shadow-sm">
            <div className="flex items-center justify-between gap-3 flex-wrap">
              <div>
                <h3 className="text-body-sm font-semibold text-amber-900">Review Pending 快速处理</h3>
                <p className="text-caption-sm text-amber-800 mt-1">
                  当前人物仍有 {reviewFaceIds.length} 张 review_pending 人脸，可批量排除或移动。
                </p>
              </div>
              <div className="flex items-center gap-2 flex-wrap">
                <Link
                  to={`/projects/${projectId}/people/review?person_id=${detail.id}`}
                  className="px-2.5 py-1 rounded-md border border-amber-300 bg-canvas text-caption-sm text-ink hover:bg-white"
                >
                  去 Review 页逐张审核
                </Link>
                <button
                  type="button"
                  disabled={actionBusy}
                  onClick={() => onBatchRejectReview(reviewFaceIds)}
                  className="px-2.5 py-1 rounded-md border border-hairline text-caption-sm text-ink hover:bg-canvas disabled:opacity-50"
                >
                  排除 review_pending
                </button>
                {reviewFaceIds.length > 0 && moveCandidates.length > 0 && batchMoveTargetId != null && (
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
              当前支持人物命名、确认、排除、移动和代表头像设置。
            </p>
          </div>
          <span className="text-caption-sm text-mute">
            已加载 {loadedAssignmentCount} / {totalAssignmentCount} 条
          </span>
        </div>

        {detail.assignments.length === 0 ? (
          <div className="rounded-lg border border-dashed border-hairline p-6 text-center text-mute">
            这个人物还没有关联的人脸样本
          </div>
        ) : (
          <>
            <div className="rounded-lg border border-hairline bg-canvas px-4 py-3">
              <div className="flex items-center justify-between gap-3 flex-wrap">
                <div>
                  <p className="text-body-sm font-medium text-ink">拆分人物</p>
                  <p className="text-caption-sm text-mute mt-1">
                    仅可选择 active 样本（非 rejected）拆分到新人物。
                  </p>
                </div>
                <div className="flex items-center gap-2 flex-wrap">
                  <input
                    value={splitName}
                    onChange={(e) => setSplitName(e.target.value)}
                    className="px-3 py-1.5 rounded-md border border-hairline bg-canvas text-caption-sm"
                    placeholder="新人物名称（可选）"
                  />
                  <button
                    type="button"
                    disabled={actionBusy || splitFaceIds.length === 0}
                    onClick={() => onSplitFaces(splitFaceIds, splitName.trim() || undefined)}
                    className="px-2.5 py-1 rounded-md border border-hairline text-caption-sm text-ink hover:bg-surface-card disabled:opacity-50"
                  >
                    拆分选中 {splitFaceIds.length} 张
                  </button>
                </div>
              </div>
            </div>

            <section className="space-y-2">
              <div className="flex items-center justify-between">
                <h4 className="text-body-sm font-semibold text-ink">正样本</h4>
                <span className="text-caption-sm text-mute">{positiveAssignments.length} 条</span>
              </div>
              {positiveAssignments.length === 0 ? (
                <div className="rounded-lg border border-dashed border-hairline px-4 py-3 text-caption-sm text-mute">
                  暂无正样本
                </div>
              ) : (
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                  {positiveAssignments.map(renderAssignmentCard)}
                </div>
              )}
            </section>

            <section className="space-y-2">
              <div className="flex items-center justify-between gap-3">
                <h4 className="text-body-sm font-semibold text-ink">候选样本</h4>
                <div className="flex items-center gap-2">
                  <span className="text-caption-sm text-mute">{candidateAssignments.length} 条</span>
                  {allConfirmableCandidateFaceIds.length > 0 && (
                    <button
                      type="button"
                      disabled={actionBusy}
                      onClick={() => onBatchConfirmReview(allConfirmableCandidateFaceIds)}
                      className="px-2.5 py-1 rounded-md border border-hairline text-caption-sm text-ink hover:bg-canvas disabled:opacity-50"
                    >
                      全部确认候选
                    </button>
                  )}
                </div>
              </div>
              {candidateAssignments.length === 0 ? (
                <div className="rounded-lg border border-dashed border-hairline px-4 py-3 text-caption-sm text-mute">
                  暂无候选样本
                </div>
              ) : (
                <>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <div className="rounded-lg border border-hairline bg-canvas px-3 py-2">
                      <p className="text-caption-sm text-mute">review_pending</p>
                      <p className="text-body-sm font-semibold text-ink mt-0.5">
                        {candidateReviewPendingAssignments.length}
                      </p>
                    </div>
                    <div className="rounded-lg border border-hairline bg-canvas px-3 py-2">
                      <p className="text-caption-sm text-mute">auto_assigned</p>
                      <p className="text-body-sm font-semibold text-ink mt-0.5">
                        {candidateAutoAssignedAssignments.length}
                      </p>
                    </div>
                  </div>

                  {similarityDistribution && (
                    <div className="rounded-lg border border-hairline bg-canvas px-4 py-3 space-y-2">
                      <div className="flex items-center justify-between">
                        <p className="text-body-sm font-medium text-ink">相似度分布</p>
                        <span className="text-caption-sm text-mute">样本 {similarityDistribution.count}</span>
                      </div>
                      <div className="grid grid-cols-3 gap-2">
                        <div className="rounded-md border border-hairline px-2 py-1.5 text-center">
                          <p className="text-caption-sm text-mute">top</p>
                          <p className="text-body-sm font-semibold text-ink">
                            {(similarityDistribution.top * 100).toFixed(1)}%
                          </p>
                        </div>
                        <div className="rounded-md border border-hairline px-2 py-1.5 text-center">
                          <p className="text-caption-sm text-mute">median</p>
                          <p className="text-body-sm font-semibold text-ink">
                            {(similarityDistribution.median * 100).toFixed(1)}%
                          </p>
                        </div>
                        <div className="rounded-md border border-hairline px-2 py-1.5 text-center">
                          <p className="text-caption-sm text-mute">bottom</p>
                          <p className="text-body-sm font-semibold text-ink">
                            {(similarityDistribution.bottom * 100).toFixed(1)}%
                          </p>
                        </div>
                      </div>
                    </div>
                  )}

                  <div className="space-y-3">
                    <div>
                      <div className="flex items-center justify-between mb-2">
                        <h5 className="text-caption-sm font-semibold text-ink">Review Pending</h5>
                        <span className="text-caption-sm text-mute">
                          {candidateReviewPendingAssignments.length} 条
                        </span>
                      </div>
                      {candidateReviewPendingAssignments.length === 0 ? (
                        <div className="rounded-lg border border-dashed border-hairline px-4 py-3 text-caption-sm text-mute">
                          暂无 review_pending 候选
                        </div>
                      ) : (
                        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                          {candidateReviewPendingAssignments.map(renderAssignmentCard)}
                        </div>
                      )}
                    </div>

                    <div>
                      <div className="flex items-center justify-between mb-2">
                        <h5 className="text-caption-sm font-semibold text-ink">Auto Assigned</h5>
                        <div className="flex items-center gap-2">
                          <span className="text-caption-sm text-mute">
                            {candidateAutoAssignedAssignments.length} 条
                          </span>
                        </div>
                      </div>
                      {candidateAutoAssignedAssignments.length === 0 ? (
                        <div className="rounded-lg border border-dashed border-hairline px-4 py-3 text-caption-sm text-mute">
                          暂无 auto_assigned 候选
                        </div>
                      ) : (
                        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                          {candidateAutoAssignedAssignments.map(renderAssignmentCard)}
                        </div>
                      )}
                    </div>

                    {candidateOtherAssignments.length > 0 && (
                      <div>
                        <div className="flex items-center justify-between mb-2">
                          <h5 className="text-caption-sm font-semibold text-ink">
                            Other Candidate Status
                          </h5>
                          <span className="text-caption-sm text-mute">
                            {candidateOtherAssignments.length} 条
                          </span>
                        </div>
                        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                          {candidateOtherAssignments.map(renderAssignmentCard)}
                        </div>
                      </div>
                    )}
                  </div>
                </>
              )}
            </section>

            <section className="space-y-2">
              <div className="flex items-center justify-between">
                <h4 className="text-body-sm font-semibold text-ink">负样本</h4>
                <span className="text-caption-sm text-mute">{negativeAssignments.length} 条</span>
              </div>
              {negativeAssignments.length === 0 ? (
                <div className="rounded-lg border border-dashed border-hairline px-4 py-3 text-caption-sm text-mute">
                  暂无负样本
                </div>
              ) : (
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                  {negativeAssignments.map(renderAssignmentCard)}
                </div>
              )}
            </section>

            {canLoadMoreAssignments && (
              <div className="flex justify-center pt-2">
                <button
                  type="button"
                  disabled={isFetching}
                  onClick={onLoadMoreAssignments}
                  className="px-3 py-1.5 rounded-md border border-hairline text-caption-sm text-ink hover:bg-surface-card disabled:opacity-50"
                >
                  {isFetching ? "正在加载更多..." : "加载更多人脸"}
                </button>
              </div>
            )}
          </>
        )}
      </div>

      {previewTarget && (
        <PersonOriginalPhotoLightbox
          projectId={projectId}
          photoId={previewTarget.photoId}
          faceId={previewTarget.faceId}
          onClose={() => setPreviewTarget(null)}
        />
      )}
    </div>
  );
}
