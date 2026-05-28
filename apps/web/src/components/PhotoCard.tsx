import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { X, Calendar, Ruler, Tag, ImageIcon, Brain, Loader2, Download, MapPin, Camera, Aperture, ScanFace, RefreshCw, UserRound, Trash2 } from "lucide-react";
import type { Photo } from "@/api";
import { api } from "@/api";
import { queryKeys } from "@/api/queryKeys";
import { formatLocationAddress, formatLocationSummary } from "@/lib/utils";

interface PhotoCardProps {
  photo: Photo;
}

// Format bytes to human-readable
function formatSize(bytes: number | null): string {
  if (!bytes) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function formatDate(iso: string | null): string {
  if (!iso) return "未知日期";
  const d = new Date(iso);
  return d.toLocaleDateString("zh-CN", { year: "numeric", month: "short", day: "numeric" });
}

interface DetailModalProps {
  photo: Photo;
  onClose: () => void;
}

function DetailModal({ photo, onClose }: DetailModalProps) {
  const [loaded, setLoaded] = useState(false);
  const [faceMessage, setFaceMessage] = useState<string | null>(null);
  const [deleteOriginal, setDeleteOriginal] = useState(false);
  const [deleteMessage, setDeleteMessage] = useState<string | null>(null);
  const projectId = photo.project_id;
  const queryClient = useQueryClient();

  const { data: detail } = useQuery({
    queryKey: queryKeys.projectPhotoDetail(projectId, photo.id),
    queryFn: () => api.projects.photo(projectId, photo.id),
    enabled: projectId != null,
    staleTime: 30_000,
  });

  const { data: aiData, isLoading: aiLoading } = useQuery({
    queryKey: queryKeys.projectPhotoAi(projectId, photo.id),
    queryFn: () => api.projects.photoAI(projectId, photo.id),
    enabled: projectId != null,
    retry: false,
  });
  const {
    data: facesData,
    isLoading: facesLoading,
    error: facesError,
  } = useQuery({
    queryKey: queryKeys.projectFaces(projectId, photo.id),
    queryFn: () => api.projects.faces(projectId, 1, 50, photo.id),
    enabled: projectId != null,
    staleTime: 10_000,
  });

  const faceScanMutation = useMutation({
    mutationFn: () => api.projects.scanPhotoFaces(projectId, photo.id),
    onSuccess: (result) => {
      let detail = "";
      if (result.message && result.message !== "Face scan completed") {
        detail = `；${result.message}`;
      } else if (result.review_pending === 0 && result.auto_assigned === 0 && result.faces_detected > 0) {
        detail = "；未产生待审核，可能是后端未重启到最新版本，或缺少 persons/person_face_assignments 表（请执行 alembic upgrade head）";
      }
      setFaceMessage(
        `已扫描 ${result.faces_detected} 张脸，新增待审核 ${result.review_pending} 条，自动归入 ${result.auto_assigned} 条${detail}`
      );
      queryClient.invalidateQueries({ queryKey: queryKeys.projectFaces(projectId, photo.id) });
      queryClient.invalidateQueries({ queryKey: queryKeys.projectPhotoDetail(projectId, photo.id) });
      queryClient.invalidateQueries({ queryKey: ["project-review-page", projectId] });
      queryClient.invalidateQueries({ queryKey: ["project-people", projectId] });
    },
    onError: (error: Error) => {
      setFaceMessage(error.message);
    },
  });

  const deletePhotoMutation = useMutation({
    mutationFn: () => api.projects.deletePhotoRecord(projectId, photo.id, deleteOriginal),
    onSuccess: () => {
      setDeleteMessage(deleteOriginal ? "已删除库记录、缩略图和本地原图" : "已删除库记录和缩略图");
      queryClient.invalidateQueries({ queryKey: queryKeys.photosBase(projectId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.timeline(projectId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.tags(projectId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.projectPhotoDetail(projectId, photo.id) });
      queryClient.invalidateQueries({ queryKey: queryKeys.projectPhotoAi(projectId, photo.id) });
      queryClient.invalidateQueries({ queryKey: ["search"] });
      onClose();
    },
    onError: (error: Error) => {
      setDeleteMessage(`删除失败：${error.message}`);
    },
  });

  function handleDeleteRecord() {
    const actionText = deleteOriginal ? "删除库记录、缩略图并尝试删除本地原图" : "仅删除库记录和缩略图";
    if (!window.confirm(`确认${actionText}吗？`)) {
      return;
    }
    deletePhotoMutation.mutate();
  }
  const locationSummary = formatLocationSummary(detail, { short: true });
  const locationAddress = formatLocationAddress(detail);

  return (
    // Scrim
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ backgroundColor: "rgba(0,0,0,0.5)" }}
      onClick={onClose}
    >
      {/* Modal card — rounded-lg 32px per DESIGN.md */}
      <div
        className="bg-canvas rounded-lg shadow-2xl max-w-lg w-full overflow-hidden overflow-y-auto"
        style={{ maxHeight: "90vh" }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Image */}
        <div className="relative bg-surface-card">
          {!loaded && (
            <div className="absolute inset-0 flex items-center justify-center">
              <ImageIcon className="w-10 h-10 text-stone" />
            </div>
          )}
          <img
            src={api.projects.thumbnailUrl(projectId, photo.id, photo.updated_at)}
            alt={photo.file_name}
            className="w-full object-cover"
            style={{ maxHeight: "40vh", opacity: loaded ? 1 : 0, transition: "opacity 0.2s" }}
            onLoad={() => setLoaded(true)}
          />
          {/* Close button — circular icon button */}
          <button
            onClick={onClose}
            className="absolute top-3 right-3 w-9 h-9 rounded-full bg-canvas flex items-center justify-center shadow-md hover:bg-surface-card transition-colors"
            aria-label="关闭"
          >
            <X className="w-4 h-4 text-ink" />
          </button>
          {/* Download button */}
          <a
            href={api.projects.originalUrl(projectId, photo.id)}
            download={photo.file_name}
            onClick={(e) => e.stopPropagation()}
            className="absolute top-3 right-14 w-9 h-9 rounded-full bg-canvas flex items-center justify-center shadow-md hover:bg-surface-card transition-colors"
            aria-label="下载原图"
            title="下载原图"
          >
            <Download className="w-4 h-4 text-ink" />
          </a>
          <button
            type="button"
            onClick={handleDeleteRecord}
            disabled={deletePhotoMutation.isPending}
            className="absolute top-3 right-24 w-9 h-9 rounded-full bg-canvas flex items-center justify-center shadow-md hover:bg-surface-card transition-colors disabled:opacity-60"
            aria-label="删除库记录"
            title={deleteOriginal ? "删除库记录、缩略图和本地原图" : "仅删除库记录和缩略图"}
          >
            {deletePhotoMutation.isPending ? (
              <Loader2 className="w-4 h-4 text-danger animate-spin" />
            ) : (
              <Trash2 className="w-4 h-4 text-danger" />
            )}
          </button>
        </div>

        {/* Info */}
        <div className="p-6 space-y-3">
          <h2 className="text-heading-md font-semibold text-ink truncate">{photo.file_name}</h2>

          <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-body-sm">
            <InfoRow icon={<Calendar className="w-3.5 h-3.5" />} label="拍摄时间" value={formatDate(photo.taken_at)} />
            <InfoRow
              icon={<Ruler className="w-3.5 h-3.5" />}
              label="尺寸"
              value={photo.width && photo.height ? `${photo.width} × ${photo.height}` : "—"}
            />
            <InfoRow icon={<Tag className="w-3.5 h-3.5" />} label="文件大小" value={formatSize(photo.file_size)} />
            <InfoRow
              icon={<ImageIcon className="w-3.5 h-3.5" />}
              label="格式"
              value={photo.mime_type?.replace("image/", "").toUpperCase() ?? "—"}
            />
          </div>

          {/* GPS + Camera + Exposure from PhotoDetail */}
          {detail && (locationSummary || detail.gps_latitude != null || detail.camera_make || detail.aperture) && (
            <div className="space-y-3 pt-1 border-t border-hairline">
              {locationSummary && (
                <div className="rounded-md border border-emerald-200 bg-emerald-50/70 p-3">
                  <div className="flex items-start gap-2">
                    <span className="mt-0.5 text-emerald-700">
                      <MapPin className="h-4 w-4" />
                    </span>
                    <div className="min-w-0">
                      <p className="text-caption-sm text-emerald-700">拍摄地点</p>
                      <p className="text-body-sm font-semibold text-emerald-950">{locationSummary}</p>
                      {locationAddress && locationAddress !== locationSummary && (
                        <p className="mt-1 break-words text-caption-sm text-emerald-800">{locationAddress}</p>
                      )}
                    </div>
                  </div>
                </div>
              )}

              <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-body-sm">
                {detail.gps_latitude != null && detail.gps_longitude != null && (
                  <InfoRow
                    icon={<MapPin className="w-3.5 h-3.5" />}
                    label="GPS"
                    value={
                      <a
                        href={`https://maps.apple.com/?ll=${detail.gps_latitude},${detail.gps_longitude}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-primary underline underline-offset-2"
                        onClick={(e) => e.stopPropagation()}
                      >
                        {detail.gps_latitude.toFixed(5)}, {detail.gps_longitude.toFixed(5)}
                      </a>
                    }
                  />
                )}
                {(detail.camera_make || detail.camera_model) && (
                  <InfoRow
                    icon={<Camera className="w-3.5 h-3.5" />}
                    label="相机"
                    value={[detail.camera_make, detail.camera_model].filter(Boolean).join(" ")}
                  />
                )}
                {detail.lens_model && (
                  <InfoRow
                    icon={<Aperture className="w-3.5 h-3.5" />}
                    label="镜头"
                    value={detail.lens_model}
                  />
                )}
                {(detail.aperture || detail.exposure_time || detail.iso) && (
                  <InfoRow
                    icon={<Aperture className="w-3.5 h-3.5" />}
                    label="曝光"
                    value={[
                      detail.aperture ? `f/${detail.aperture}` : null,
                      detail.exposure_time ? `${detail.exposure_time}s` : null,
                      detail.iso ? `ISO ${detail.iso}` : null,
                      detail.focal_length ? `${detail.focal_length}mm` : null,
                    ].filter(Boolean).join("  ")}
                  />
                )}
              </div>
            </div>
          )}

          {/* Status badge */}
          <div className="flex items-center gap-2 pt-1">
            <span
              className={[
                "px-3 py-1 rounded-full text-caption-md font-semibold",
                photo.status === "ai_indexed"
                  ? "bg-blue-100 text-blue-800"
                  : photo.status === "indexed"
                  ? "bg-green-100 text-green-800"
                  : photo.status === "pending"
                  ? "bg-secondary-bg text-mute"
                  : "bg-amber-100 text-amber-800",
              ].join(" ")}
            >
              {photo.status === "ai_indexed"
                ? "AI 已分析"
                : photo.status === "indexed"
                ? "已索引"
                : photo.status === "pending"
                ? "待分析"
                : photo.status}
            </span>
          </div>

          {/* AI Analysis Section */}
          <div className="pt-2 border-t border-hairline">
            <div className="flex items-center gap-2 mb-3">
              <Brain className="w-4 h-4 text-primary" />
              <span className="text-body-sm font-semibold text-ink">AI 分析结果</span>
              {aiLoading && <Loader2 className="w-3.5 h-3.5 animate-spin text-mute" />}
            </div>

            {aiLoading ? (
              <p className="text-caption-sm text-mute">加载中…</p>
            ) : aiData ? (
              <div className="space-y-3">
                {/* Caption */}
                {aiData.caption && (
                  <div>
                    <p className="text-caption-sm text-mute mb-1">描述</p>
                    <p className="text-body-sm text-ink">{aiData.caption}</p>
                  </div>
                )}

                {/* Tags */}
                {[
                  { label: "场景", tags: aiData.scene_tags },
                  { label: "物体", tags: aiData.object_tags },
                  { label: "活动", tags: aiData.activity_tags },
                  { label: "画质", tags: aiData.quality_tags },
                ].map(
                  ({ label, tags }) =>
                    tags && tags.length > 0 && (
                      <div key={label}>
                        <p className="text-caption-sm text-mute mb-1">{label}</p>
                        <div className="flex flex-wrap gap-1">
                          {tags.map((tag) => (
                            <span
                              key={tag}
                              className="px-2 py-0.5 bg-secondary-bg rounded-full text-caption-sm text-ink"
                            >
                              {tag}
                            </span>
                          ))}
                        </div>
                      </div>
                    )
                )}

                {/* OCR */}
                {aiData.ocr_text && aiData.ocr_text.trim() && (
                  <div>
                    <p className="text-caption-sm text-mute mb-1">OCR 文字</p>
                    <p className="text-caption-sm text-ink whitespace-pre-wrap bg-secondary-bg rounded p-2">
                      {aiData.ocr_text}
                    </p>
                  </div>
                )}

                {/* Meta row */}
                <div className="flex flex-wrap gap-x-4 gap-y-1 text-caption-sm text-mute">
                  {aiData.people_count !== null && aiData.people_count !== undefined && (
                    <span>人物：{aiData.people_count} 人</span>
                  )}
                  {aiData.confidence !== null && aiData.confidence !== undefined && (
                    <span>置信度：{(aiData.confidence * 100).toFixed(0)}%</span>
                  )}
                  {aiData.model_name && <span>模型：{aiData.model_name}</span>}
                </div>
              </div>
            ) : (
              <p className="text-caption-sm text-mute">尚未分析 — 请点击「开始分析」按钮。</p>
            )}
          </div>

          <div className="pt-2 border-t border-hairline">
            <div className="mb-3 rounded-md border border-danger/30 bg-danger/5 p-3">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-body-sm font-semibold text-danger">手动清理</p>
                  <p className="text-caption-sm text-mute mt-1">
                    默认仅删除库记录与缩略图，不会删除本地原图。
                  </p>
                </div>
                <button
                  type="button"
                  onClick={handleDeleteRecord}
                  disabled={deletePhotoMutation.isPending}
                  className="inline-flex items-center gap-1.5 rounded-md border border-danger/40 px-3 py-1.5 text-body-sm text-danger hover:bg-danger/10 disabled:opacity-60"
                >
                  {deletePhotoMutation.isPending ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <Trash2 className="w-3.5 h-3.5" />
                  )}
                  删除记录
                </button>
              </div>
              <label className="mt-2 flex items-center gap-2 text-caption-sm text-ink">
                <input
                  type="checkbox"
                  checked={deleteOriginal}
                  onChange={(e) => setDeleteOriginal(e.target.checked)}
                  className="h-4 w-4"
                />
                同时删除本地原图（hard copy 删除，谨慎操作）
              </label>
              {deleteMessage && <p className="mt-2 text-caption-sm text-mute">{deleteMessage}</p>}
            </div>

            <div className="flex items-center justify-between gap-3 mb-3">
              <div className="flex items-center gap-2">
                <UserRound className="w-4 h-4 text-primary" />
                <span className="text-body-sm font-semibold text-ink">人脸识别</span>
                {facesLoading && <Loader2 className="w-3.5 h-3.5 animate-spin text-mute" />}
              </div>
              <button
                type="button"
                onClick={() => faceScanMutation.mutate()}
                disabled={faceScanMutation.isPending}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-hairline text-body-sm text-ink hover:bg-surface-card disabled:opacity-60"
              >
                {faceScanMutation.isPending ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <ScanFace className="w-3.5 h-3.5" />
                )}
                手动扫描
              </button>
            </div>

            {faceMessage && (
              <p className="text-caption-sm text-mute mb-2">{faceMessage}</p>
            )}

            {facesError ? (
              <p className="text-caption-sm text-amber-700">
                {(facesError as Error).message}
              </p>
            ) : facesData && facesData.total > 0 ? (
              <div className="space-y-2">
                <div className="flex items-center gap-2 text-caption-sm text-mute">
                  <span>检测到 {facesData.total} 张脸</span>
                  <button
                    type="button"
                    onClick={() => queryClient.invalidateQueries({ queryKey: queryKeys.projectFaces(projectId, photo.id) })}
                    className="inline-flex items-center gap-1 text-primary hover:text-primary-pressed"
                  >
                    <RefreshCw className="w-3 h-3" />
                    刷新
                  </button>
                </div>
                <div className="grid grid-cols-1 gap-2">
                  {facesData.items.map((face) => (
                    <div
                      key={face.id}
                      className="rounded-md border border-hairline bg-surface-soft p-2 flex gap-3"
                    >
                      <div className="w-20 h-20 flex-shrink-0 rounded-md overflow-hidden bg-canvas border border-hairline">
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
                      <div className="min-w-0 flex-1 space-y-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-body-sm font-medium text-ink">face #{face.id}</span>
                          <span className="px-2 py-0.5 rounded-full bg-secondary-bg text-caption-sm text-ink">
                            {face.status}
                          </span>
                        </div>
                        <p className="text-caption-sm text-mute">
                          bbox: {face.bbox_x}, {face.bbox_y}, {face.bbox_w}, {face.bbox_h}
                        </p>
                        <div className="flex flex-wrap gap-x-3 gap-y-1 text-caption-sm text-mute">
                          {face.detection_confidence != null && (
                            <span>检测置信度 {(face.detection_confidence * 100).toFixed(0)}%</span>
                          )}
                          {face.face_quality_score != null && (
                            <span>质量 {(face.face_quality_score * 100).toFixed(0)}%</span>
                          )}
                        </div>
                        {face.error_message && (
                          <p className="text-caption-sm text-danger break-all">{face.error_message}</p>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <p className="text-caption-sm text-mute">
                还没有人脸结果。先在项目配置里启用人脸识别，再点击“手动扫描”。
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function InfoRow({ icon, label, value }: { icon: React.ReactNode; label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-start gap-1.5">
      <span className="text-mute mt-0.5 flex-shrink-0">{icon}</span>
      <div>
        <p className="text-caption-sm text-mute">{label}</p>
        <p className="text-body-sm text-ink font-medium">{value}</p>
      </div>
    </div>
  );
}

export function PhotoCard({ photo }: PhotoCardProps) {
  const [loaded, setLoaded] = useState(false);
  const [errored, setErrored] = useState(false);
  const [showDetail, setShowDetail] = useState(false);
  const locationSummary = formatLocationSummary(photo, { short: true });
  const locationAddress = formatLocationAddress(photo);
  const gpsFallback =
    photo.gps_latitude != null && photo.gps_longitude != null
      ? `${photo.gps_latitude.toFixed(5)}, ${photo.gps_longitude.toFixed(5)}`
      : null;

  return (
    <>
      {/* Pin card — rounded-md 16px, no padding, full-bleed image */}
      <div
        className="masonry-item cursor-pointer group relative bg-surface-card"
        onClick={() => setShowDetail(true)}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => e.key === "Enter" && setShowDetail(true)}
        aria-label={`查看照片 ${photo.file_name}`}
      >
        {errored ? (
          <div className="w-full h-32 flex flex-col items-center justify-center gap-1 bg-surface-card">
            <ImageIcon className="w-6 h-6 text-stone" />
            <span className="text-caption-sm text-stone">无法加载</span>
          </div>
        ) : (
          /* Wrapper maintains aspect ratio so the card never collapses while loading */
          <div
            className="relative w-full"
            style={{ aspectRatio: photo.width && photo.height ? `${photo.width}/${photo.height}` : "4/3" }}
          >
            {/* Skeleton overlay — shown until image is ready */}
            {!loaded && (
              <div className="absolute inset-0 bg-secondary-bg animate-pulse" />
            )}
            {/* img is always in the DOM (not display:none) so onLoad fires with lazy loading */}
            <img
              src={api.projects.thumbnailUrl(photo.project_id, photo.id, photo.updated_at)}
              alt={photo.file_name}
              className="w-full block"
              style={{ opacity: loaded ? 1 : 0, transition: "opacity 0.2s" }}
              loading="lazy"
              onLoad={() => setLoaded(true)}
              onError={() => setErrored(true)}
            />
          </div>
        )}

        {/* Hover overlay — appears on group hover */}
        <div className="absolute inset-0 rounded-md opacity-0 group-hover:opacity-100 transition-opacity duration-150 pointer-events-none"
          style={{ background: "linear-gradient(to bottom, transparent 50%, rgba(0,0,0,0.35) 100%)" }}
        />

        {/* Date pill overlay — top-left, visible on hover */}
        {photo.taken_at && (
          <div className="absolute left-2 top-2 opacity-0 group-hover:opacity-100 transition-opacity duration-150">
            <span className="bg-canvas text-ink text-btn-sm font-bold px-3 py-1 rounded-full shadow-sm whitespace-nowrap">
              {new Date(photo.taken_at).toLocaleDateString("zh-CN", { month: "short", year: "numeric" })}
            </span>
          </div>
        )}
        {(locationSummary || gpsFallback) && (
          <div className="absolute right-2 bottom-2 max-w-[62%] opacity-95 group-hover:opacity-100 transition-opacity duration-150 overflow-hidden">
            <span
              className="flex items-center gap-1.5 bg-black/72 text-white text-[11px] font-medium px-3 py-1 rounded-full shadow-sm overflow-hidden border border-white/12 backdrop-blur-sm"
              title={locationAddress ?? locationSummary ?? gpsFallback ?? ""}
            >
              <MapPin className="w-3.5 h-3.5 shrink-0" />
              <span className="truncate min-w-0">{locationSummary ?? gpsFallback}</span>
            </span>
          </div>
        )}
      </div>

      {showDetail && <DetailModal photo={photo} onClose={() => setShowDetail(false)} />}
    </>
  );
}
