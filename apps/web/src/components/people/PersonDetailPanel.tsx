import { useEffect, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  Loader2,
  MoveRight,
  RefreshCw,
  ScanFace,
  Star,
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
        role="dialog"
        aria-modal="true"
        aria-label="查看人脸原图"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          type="button"
          onClick={onClose}
          className="absolute top-3 right-3 z-10 flex h-11 w-11 items-center justify-center rounded-full bg-black/60 transition-colors hover:bg-black/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white motion-reduce:transition-none"
          aria-label="关闭预览"
        >
          <X className="h-5 w-5 text-white" aria-hidden="true" />
        </button>

        {!imgLoaded && (
          <div className="flex items-center justify-center" style={{ minWidth: 220, minHeight: 220 }}>
            {imgError ? (
              <div className="max-w-[320px] text-center text-white/85 text-sm px-4">{imgError}</div>
            ) : (
              <Loader2 className="h-8 w-8 animate-spin text-white/70 motion-reduce:animate-none" aria-hidden="true" />
            )}
          </div>
        )}

        <img
          src={api.projectPhotos.previewUrl(projectId, photoId)}
          alt={`人脸 ${faceId} 的原始照片`}
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

function AssignmentOverview({
  total,
  positive,
  candidate,
  negative,
  autoAssigned,
  reviewPending,
}: {
  total: number;
  positive: number;
  candidate: number;
  negative: number;
  autoAssigned: number;
  reviewPending: number;
}) {
  const distributionTotal = Math.max(positive + candidate + negative, 1);
  const segments = [
    { label: "正样本", value: positive, className: "bg-success" },
    { label: "候选", value: candidate, className: "bg-warning" },
    { label: "负样本", value: negative, className: "bg-danger/70" },
  ];

  return (
    <section className="rounded-lg border border-hairline bg-surface-soft p-3" aria-labelledby="sample-overview-title">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-baseline gap-2">
          <h3 id="sample-overview-title" className="text-caption-sm font-medium text-mute">样本结构</h3>
          <strong className="text-heading-md font-semibold tabular-nums text-ink">{total.toLocaleString()}</strong>
        </div>
        <div className="flex flex-wrap gap-2 text-caption-sm text-secondary">
          <span>自动识别 <strong className="tabular-nums text-ink">{autoAssigned.toLocaleString()}</strong></span>
          <span>待确认 <strong className="tabular-nums text-ink">{reviewPending.toLocaleString()}</strong></span>
        </div>
      </div>
      <div
        className="mt-3 flex h-2.5 overflow-hidden rounded-full bg-secondary-bg"
        role="img"
        aria-label={`样本结构：正样本 ${positive}，候选 ${candidate}，负样本 ${negative}`}
      >
        {segments.map((segment) => (
          segment.value > 0 && (
            <span
              key={segment.label}
              className={segment.className}
              style={{ width: `${(segment.value / distributionTotal) * 100}%` }}
            />
          )
        ))}
      </div>
      <div className="mt-2 grid grid-cols-3 gap-2 text-caption-sm text-secondary">
        {segments.map((segment) => (
          <div key={segment.label} className="flex min-w-0 items-center gap-1.5">
            <span className={`h-2 w-2 shrink-0 rounded-full ${segment.className}`} aria-hidden="true" />
            <span className="truncate">{segment.label}</span>
            <strong className="ml-auto tabular-nums text-ink">{segment.value.toLocaleString()}</strong>
          </div>
        ))}
      </div>
    </section>
  );
}

const ASSIGNMENT_STATUS_LABELS: Record<string, string> = {
  human_confirmed: "人工确认",
  human_corrected: "人工修正",
  auto_assigned: "自动识别",
  review_pending: "待确认",
  rejected: "已排除",
};

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
        className="flex flex-col gap-3 rounded-lg border border-hairline bg-surface-soft p-3 sm:flex-row"
      >
        <button
          type="button"
          onClick={() => setPreviewTarget({ photoId: face.photo_id, faceId: face.id })}
          className="group relative h-24 w-24 flex-shrink-0 cursor-zoom-in overflow-hidden rounded-lg border border-hairline bg-canvas focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-outer"
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
            <div className="flex h-full w-full items-center justify-center text-mute">
              <ScanFace className="h-5 w-5" aria-hidden="true" />
            </div>
          )}
          <div className="absolute inset-0 bg-black/0 group-hover:bg-black/25 transition-colors flex items-center justify-center">
            <ZoomIn className="h-4 w-4 text-white opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100" aria-hidden="true" />
          </div>
        </button>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            {splitSelectable && (
              <label className="inline-flex min-h-9 cursor-pointer items-center gap-1.5 rounded-md px-1 text-caption-sm text-mute">
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
            <span className="text-body-sm font-semibold text-ink">face #{face.id}</span>
            <span className={`rounded-full border px-2 py-0.5 text-caption-sm font-medium ${assignment.assignment_status === "review_pending" ? "border-warning/30 bg-warning/10 text-secondary" : assignment.assignment_status === "rejected" ? "border-danger/20 bg-danger/5 text-danger" : "border-hairline bg-canvas text-secondary"}`}>
              {ASSIGNMENT_STATUS_LABELS[assignment.assignment_status] ?? assignment.assignment_status}
            </span>
          </div>
          <div className="mt-2 flex flex-wrap gap-2 text-caption-sm">
            {assignment.confidence != null && (
              <span className="rounded-full bg-canvas px-2 py-1 text-secondary">置信度 <strong className="tabular-nums text-ink">{(assignment.confidence * 100).toFixed(0)}%</strong></span>
            )}
            {assignment.similarity_score != null && (
              <span className="rounded-full bg-canvas px-2 py-1 text-secondary">相似度 <strong className="tabular-nums text-ink">{(assignment.similarity_score * 100).toFixed(0)}%</strong></span>
            )}
            {face.face_quality_score != null && (
              <span className="rounded-full bg-canvas px-2 py-1 text-secondary">质量 <strong className="tabular-nums text-ink">{(face.face_quality_score * 100).toFixed(0)}%</strong></span>
            )}
          </div>
          <details className="group mt-2 rounded-md border border-hairline bg-canvas px-2.5 py-1.5 text-caption-sm text-mute">
            <summary className="flex min-h-7 cursor-pointer list-none items-center justify-between text-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-outer [&::-webkit-details-marker]:hidden">
              技术信息
              <ChevronDown className="h-3.5 w-3.5 transition-transform group-open:rotate-180 motion-reduce:transition-none" aria-hidden="true" />
            </summary>
            <div className="space-y-1 border-t border-hairline pt-2">
              <p>来源：{explanation?.source ?? assignment.assignment_source}</p>
              <p>边界框：{face.bbox_x}, {face.bbox_y}, {face.bbox_w}, {face.bbox_h}</p>
              <p>自动匹配：{String(explanation?.is_auto ?? assignment.assignment_status === "auto_assigned")} · 人工确认：{String(explanation?.is_human_confirmed ?? ["human_confirmed", "human_corrected"].includes(assignment.assignment_status))}</p>
              <p>负样本约束：{String(explanation?.negative_constraint_affected ?? false)} · 命中 {explanation?.negative_constraint_count ?? 0}</p>
            </div>
          </details>
          <div className="mt-2 flex flex-wrap gap-2">
            <button
              type="button"
              disabled={actionBusy}
              onClick={() => onConfirmFace(face.id)}
              className="inline-flex min-h-11 items-center gap-1.5 rounded-md bg-primary px-3 text-btn-sm font-medium text-white hover:bg-primary/90 disabled:opacity-50"
            >
              <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
              确认属于此人
            </button>
            <button
              type="button"
              disabled={actionBusy}
              onClick={() => onRejectFace(face.id)}
              className="min-h-11 rounded-md border border-danger/30 bg-canvas px-3 text-btn-sm font-medium text-danger hover:bg-danger/10 disabled:opacity-50"
            >
              不是此人
            </button>
            <button
              type="button"
              disabled={actionBusy}
              onClick={() => onSetRepresentative(face.id)}
              className="inline-flex min-h-11 items-center gap-1.5 rounded-md border border-hairline bg-canvas px-3 text-btn-sm font-medium text-secondary hover:text-ink disabled:opacity-50"
            >
              <Star className="h-4 w-4" aria-hidden="true" />
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
                  aria-label={`face ${face.id} 移动目标`}
                  className="min-h-11 rounded-md border border-hairline bg-canvas px-3 text-body-sm text-ink"
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
                  className="inline-flex min-h-11 items-center gap-1.5 rounded-md border border-hairline bg-canvas px-3 text-btn-sm font-medium text-secondary hover:text-ink disabled:opacity-50"
                >
                  <MoveRight className="h-4 w-4" aria-hidden="true" />
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
    <div className="overflow-hidden rounded-xl border border-hairline bg-canvas">
      <div className="border-b border-hairline p-4 sm:p-5">
        {statusMessage && (
          <div role="status" aria-live="polite" className="mb-3 rounded-md border border-success/30 bg-success/5 px-3 py-2 text-caption-sm text-success">
            {statusMessage}
          </div>
        )}
        {errorMessage && (
          <div role="alert" className="mb-3 rounded-md border border-danger/30 bg-danger/5 px-3 py-2 text-caption-sm text-danger">
            {errorMessage}
          </div>
        )}
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start">
          <div className="h-20 w-20 flex-shrink-0 overflow-hidden rounded-xl border border-hairline bg-surface-soft">
            {faceCropEnabled && detail.representative_face_detection_id ? (
              <button
                type="button"
                onClick={() => {
                  if (!representativeFace) return;
                  setPreviewTarget({ photoId: representativeFace.photo_id, faceId: representativeFace.id });
                }}
                disabled={!representativeFace}
                className="group relative h-full w-full cursor-zoom-in disabled:cursor-default focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-outer"
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
                    <ZoomIn className="h-4 w-4 text-white opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100" aria-hidden="true" />
                  </div>
                )}
              </button>
            ) : (
              <div className="w-full h-full flex items-center justify-center text-mute">
                <UserRound className="h-8 w-8" aria-hidden="true" />
              </div>
            )}
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-heading-lg font-semibold text-ink">{detail.display_name}</h2>
              <span
                className={[
                  "rounded-full px-2 py-0.5 text-caption-sm font-medium",
                  detail.is_named
                    ? "bg-success/10 text-success"
                    : "bg-secondary-bg text-secondary",
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
              {detail.created_by === "system_cluster" ? "系统聚类创建" : `创建者 ${detail.created_by}`} · 更新于 {formatDateTime(detail.updated_at)}
            </p>

            <form
              className="mt-3 flex flex-wrap items-center gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                onRename(renameValue);
              }}
            >
              <label className="sr-only" htmlFor="person-display-name">人物名称</label>
              <input
                id="person-display-name"
                value={renameValue}
                onChange={(e) => setRenameValue(e.target.value)}
                className="min-h-11 w-full max-w-sm rounded-md border border-hairline bg-canvas px-3 text-body-sm text-ink focus:outline-none focus:ring-2 focus:ring-focus-outer"
                placeholder="输入人物名称，可追加 #标签"
              />
              <button
                type="submit"
                disabled={actionBusy || !renameValue.trim()}
                className="min-h-11 rounded-md border border-hairline px-3 text-btn-sm font-medium text-ink hover:bg-surface-card disabled:opacity-50"
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
                className="inline-flex min-h-11 items-center gap-2 rounded-md border border-hairline px-3 text-btn-sm font-medium text-ink hover:bg-surface-card disabled:opacity-50"
                title={
                  detail.is_named && detail.confirmed_sample_count > 0
                    ? "从已有扫描人脸中查找相似候选，并追加到候选样本"
                    : "需要已命名人物和至少一张正样本"
                }
              >
                <RefreshCw className={["h-4 w-4", rematchBusy ? "animate-spin motion-reduce:animate-none" : ""].join(" ")} aria-hidden="true" />
                {rematchBusy ? "聚合候选中..." : "从已扫描人脸找相似候选"}
              </button>
              <span className="text-caption-sm text-mute">结果将加入候选样本</span>
            </div>
          </div>
        </div>

        <div className="mt-4">
          <AssignmentOverview
            total={detail.sample_count}
            positive={confirmed}
            candidate={candidateAssignments.length}
            negative={negativeAssignments.length}
            autoAssigned={autoAssigned}
            reviewPending={reviewPending}
          />
        </div>
      </div>

      <div className="space-y-5 p-4 sm:p-5">
        {reviewFaceIds.length > 0 && (
          <aside className="rounded-lg border border-warning/40 bg-warning/10 p-3" aria-labelledby="review-pending-title">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex min-w-0 items-start gap-2">
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-warning" aria-hidden="true" />
                <div>
                <h3 id="review-pending-title" className="text-body-sm font-semibold text-ink">待确认人脸</h3>
                <p className="mt-0.5 text-caption-sm text-secondary">
                  当前人物仍有 {reviewFaceIds.length} 张待确认人脸，可批量排除或移动。
                </p>
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Link
                  to={`/projects/${projectId}/people/review?person_id=${detail.id}`}
                  className="inline-flex min-h-11 items-center rounded-md bg-primary px-3 text-btn-sm font-semibold text-white hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-outer"
                >
                  去 Review 页逐张审核
                </Link>
                <button
                  type="button"
                  disabled={actionBusy}
                  onClick={() => onBatchRejectReview(reviewFaceIds)}
                  className="min-h-11 rounded-md border border-hairline bg-canvas px-3 text-btn-sm font-medium text-ink hover:bg-surface-card disabled:opacity-50"
                >
                  排除待确认人脸
                </button>
                {reviewFaceIds.length > 0 && moveCandidates.length > 0 && batchMoveTargetId != null && (
                  <>
                    <select
                      value={batchMoveTargetId}
                      onChange={(e) => setBatchMoveTargetId(Number(e.target.value))}
                      aria-label="待确认人脸批量移动目标"
                      className="min-h-11 rounded-md border border-hairline bg-canvas px-3 text-body-sm text-ink"
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
                      className="min-h-11 rounded-md border border-hairline bg-canvas px-3 text-btn-sm font-medium text-ink hover:bg-surface-card disabled:opacity-50"
                    >
                      批量移动
                    </button>
                  </>
                )}
              </div>
            </div>
          </aside>
        )}

        <div className="flex items-center justify-between gap-3">
          <div>
            <h3 className="text-body-sm font-semibold text-ink">关联人脸</h3>
            <p className="mt-1 text-caption-sm text-mute">确认归属，整理这个人物的人脸样本。</p>
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
            <details className="group rounded-lg border border-hairline bg-canvas">
              <summary className="flex min-h-12 cursor-pointer list-none items-center justify-between gap-3 px-4 text-body-sm font-medium text-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-outer [&::-webkit-details-marker]:hidden">
                <span>拆分人物 <span className="ml-1 text-caption-sm text-mute">已选 {splitFaceIds.length} 张</span></span>
                <ChevronDown className="h-4 w-4 transition-transform group-open:rotate-180 motion-reduce:transition-none" aria-hidden="true" />
              </summary>
              <div className="flex flex-wrap items-end justify-between gap-3 border-t border-hairline p-4">
                <p className="max-w-xl text-caption-sm text-mute">勾选非 rejected 样本，将其拆分到一个新人物。</p>
                <div className="flex flex-wrap items-center gap-2">
                  <input
                    value={splitName}
                    onChange={(e) => setSplitName(e.target.value)}
                    className="min-h-11 rounded-md border border-hairline bg-canvas px-3 text-body-sm text-ink"
                    placeholder="新人物名称（可选）"
                  />
                  <button
                    type="button"
                    disabled={actionBusy || splitFaceIds.length === 0}
                    onClick={() => onSplitFaces(splitFaceIds, splitName.trim() || undefined)}
                    className="min-h-11 rounded-md border border-hairline px-3 text-btn-sm font-medium text-ink hover:bg-surface-card disabled:opacity-50"
                  >
                    拆分选中 {splitFaceIds.length} 张
                  </button>
                </div>
              </div>
            </details>

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
                      className="min-h-11 rounded-md border border-hairline px-3 text-caption-sm font-medium text-ink hover:bg-canvas focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-outer disabled:opacity-50"
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
                      <p className="text-caption-sm text-mute">待确认</p>
                      <p className="text-body-sm font-semibold text-ink mt-0.5">
                        {candidateReviewPendingAssignments.length}
                      </p>
                    </div>
                    <div className="rounded-lg border border-hairline bg-canvas px-3 py-2">
                      <p className="text-caption-sm text-mute">自动识别</p>
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
                          <p className="text-caption-sm text-mute">最高</p>
                          <p className="text-body-sm font-semibold text-ink">
                            {(similarityDistribution.top * 100).toFixed(1)}%
                          </p>
                        </div>
                        <div className="rounded-md border border-hairline px-2 py-1.5 text-center">
                          <p className="text-caption-sm text-mute">中位数</p>
                          <p className="text-body-sm font-semibold text-ink">
                            {(similarityDistribution.median * 100).toFixed(1)}%
                          </p>
                        </div>
                        <div className="rounded-md border border-hairline px-2 py-1.5 text-center">
                          <p className="text-caption-sm text-mute">最低</p>
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
                        <h5 className="text-caption-sm font-semibold text-ink">待确认</h5>
                        <span className="text-caption-sm text-mute">
                          {candidateReviewPendingAssignments.length} 条
                        </span>
                      </div>
                      {candidateReviewPendingAssignments.length === 0 ? (
                        <div className="rounded-lg border border-dashed border-hairline px-4 py-3 text-caption-sm text-mute">
                          暂无待确认候选
                        </div>
                      ) : (
                        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                          {candidateReviewPendingAssignments.map(renderAssignmentCard)}
                        </div>
                      )}
                    </div>

                    <div>
                      <div className="flex items-center justify-between mb-2">
                        <h5 className="text-caption-sm font-semibold text-ink">自动识别</h5>
                        <div className="flex items-center gap-2">
                          <span className="text-caption-sm text-mute">
                            {candidateAutoAssignedAssignments.length} 条
                          </span>
                        </div>
                      </div>
                      {candidateAutoAssignedAssignments.length === 0 ? (
                        <div className="rounded-lg border border-dashed border-hairline px-4 py-3 text-caption-sm text-mute">
                          暂无自动识别候选
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
                          <h5 className="text-caption-sm font-semibold text-ink">其他候选</h5>
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
                  className="min-h-11 rounded-md border border-hairline px-4 text-caption-sm font-medium text-ink hover:bg-surface-card focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-outer disabled:opacity-50"
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
