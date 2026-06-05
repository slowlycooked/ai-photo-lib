import type { UseMutationResult } from "@tanstack/react-query";
import type { QueryObserverResult } from "@tanstack/react-query";
import { Loader2, RefreshCw, ScanFace, UserRound } from "lucide-react";
import { api } from "@/api";
import type { FaceDetectionListResponse, FaceScanResponse } from "@/api/types";

interface PhotoFacesSectionProps {
  projectId: number;
  photoId: number;
  facesData?: FaceDetectionListResponse;
  facesLoading: boolean;
  facesError: unknown;
  faceMessage: string | null;
  faceScanMutation: UseMutationResult<FaceScanResponse, Error, void>;
  refreshFaces: () => Promise<QueryObserverResult<FaceDetectionListResponse, Error>> | void;
}

export function PhotoFacesSection({
  projectId,
  photoId,
  facesData,
  facesLoading,
  facesError,
  faceMessage,
  faceScanMutation,
  refreshFaces,
}: PhotoFacesSectionProps) {
  return (
    <div>
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

      {faceMessage && <p className="text-caption-sm text-mute mb-2">{faceMessage}</p>}

      {facesError ? (
        <p className="text-caption-sm text-amber-700">{(facesError as Error).message}</p>
      ) : facesData && facesData.total > 0 ? (
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-caption-sm text-mute">
            <span>检测到 {facesData.total} 张脸</span>
            <button
              type="button"
              onClick={() => refreshFaces()}
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
                      src={api.projectFaces.cropUrl(projectId, face.id, face.updated_at)}
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
  );
}
