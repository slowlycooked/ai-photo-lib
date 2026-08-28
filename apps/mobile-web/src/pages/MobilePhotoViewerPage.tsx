import { useMemo, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { api } from "@/api";
import { DownloadButton } from "@/components/DownloadButton";
import { LoadingState } from "@/components/LoadingState";
import { PhotoViewer } from "@/components/PhotoViewer";
import { useProjectContext } from "@/contexts/ProjectContext";
import { useSwipePhotoNavigation } from "@/hooks/useSwipePhotoNavigation";

interface ViewerState {
  photoIds?: number[];
  returnTo?: string;
}

function infoRow(label: string, value: ReactNode) {
  if (value == null || value === "") return null;
  return (
    <div className="flex justify-between gap-3 border-b border-mobileHairline py-2 text-sm">
      <span className="text-mobileMute">{label}</span>
      <span className="text-right text-mobileInk">{value}</span>
    </div>
  );
}

function formatSize(bytes: number | null) {
  if (!bytes) return null;
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function formatExifDecimal(value: string | null, maximumFractionDigits = 2) {
  if (!value) return null;
  const [numeratorText, denominatorText, ...rest] = value.split("/");
  const numerator = Number(numeratorText);
  const denominator = denominatorText == null ? 1 : Number(denominatorText);
  if (rest.length > 0 || !Number.isFinite(numerator) || !Number.isFinite(denominator) || denominator === 0) {
    return value;
  }
  return (numerator / denominator).toLocaleString("zh-CN", {
    maximumFractionDigits,
    useGrouping: false,
  });
}

export function MobilePhotoViewerPage() {
  const { photoId } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const { currentProjectId } = useProjectContext();

  const id = Number(photoId);

  const query = useQuery({
    queryKey: ["mobile-photo-detail", currentProjectId, id],
    enabled: currentProjectId != null && Number.isFinite(id),
    queryFn: () => api.photos.get(currentProjectId!, id),
  });

  const viewerState = useMemo(() => (location.state as ViewerState | null) ?? {}, [location.state]);
  const photoIds = useMemo(
    () => (Array.isArray(viewerState.photoIds) ? viewerState.photoIds : []),
    [viewerState.photoIds],
  );

  const currentIndex = photoIds.indexOf(id);
  const prevId = currentIndex > 0 ? photoIds[currentIndex - 1] : null;
  const nextId =
    currentIndex >= 0 && currentIndex < photoIds.length - 1
      ? photoIds[currentIndex + 1]
      : null;

  const goPrev = () => {
    if (prevId == null) return;
    navigate(`/photos/${prevId}`, { state: viewerState, replace: true });
  };
  const goNext = () => {
    if (nextId == null) return;
    navigate(`/photos/${nextId}`, { state: viewerState, replace: true });
  };

  const goBack = () => {
    if (viewerState.returnTo) {
      navigate(-1);
      return;
    }
    navigate("/photos", { replace: true });
  };

  const swipeHandlers = useSwipePhotoNavigation({
    onPrev: goPrev,
    onNext: goNext,
  });

  if (query.isLoading || !query.data || currentProjectId == null) {
    return (
      <main className="mobile-page px-4 pb-20 pt-4">
        <LoadingState label="正在加载照片详情..." />
      </main>
    );
  }

  const photo = query.data;

  return (
    <main className="mobile-page px-4 pb-24 pt-3">
      <section className="mx-auto max-w-3xl space-y-4">
        <div className="flex items-center justify-between">
          <button type="button" onClick={goBack} className="inline-flex items-center gap-1 text-sm text-mobileInk">
            <ArrowLeft size={16} /> 返回
          </button>
          <DownloadButton projectId={currentProjectId} photoId={photo.id} />
        </div>

        <PhotoViewer
          src={api.photos.previewUrl(currentProjectId, photo.id)}
          poster={api.photos.thumbnailUrl(currentProjectId, photo.id, photo.updated_at)}
          alt={photo.file_name}
          mediaType={photo.mime_type}
          canPrev={prevId != null}
          canNext={nextId != null}
          onPrev={goPrev}
          onNext={goNext}
          swipeHandlers={swipeHandlers}
        />

        <section className="rounded-2xl border border-mobileHairline bg-mobileCard px-4 py-3">
          <h2 className="mb-3 break-all text-sm font-semibold text-mobileInk">{photo.file_name}</h2>

          <h3 className="pt-1 text-xs font-semibold uppercase tracking-wide text-mobileMute">
            {photo.mime_type?.startsWith("video/") ? "视频信息" : "照片信息"}
          </h3>
          {infoRow("拍摄时间", photo.taken_at ? new Date(photo.taken_at).toLocaleString("zh-CN") : null)}
          {infoRow("分辨率", photo.width && photo.height ? `${photo.width} x ${photo.height}` : null)}
          {infoRow("文件大小", formatSize(photo.file_size))}
          {infoRow("格式", photo.mime_type?.replace(/^(image|video)\//, "").toUpperCase())}

          {(photo.formatted_address || photo.city || photo.country_name) && (
            <>
              <h3 className="pt-4 text-xs font-semibold uppercase tracking-wide text-mobileMute">拍摄地点</h3>
              <p className="border-b border-mobileHairline py-2 text-sm leading-6 text-mobileInk">
                {photo.formatted_address ?? photo.city ?? photo.country_name}
              </p>
            </>
          )}

          <h3 className="pt-4 text-xs font-semibold uppercase tracking-wide text-mobileMute">EXIF 信息</h3>
          {photo.gps_latitude != null && photo.gps_longitude != null &&
            infoRow(
              "GPS",
              <a
                href={`https://maps.apple.com/?ll=${photo.gps_latitude},${photo.gps_longitude}`}
                target="_blank"
                rel="noopener noreferrer"
                className="text-mobileAccent underline underline-offset-2"
              >
                {photo.gps_latitude.toFixed(5)}, {photo.gps_longitude.toFixed(5)}
              </a>,
            )}
          {infoRow("相机", [photo.camera_make, photo.camera_model].filter(Boolean).join(" "))}
          {infoRow("镜头", photo.lens_model)}
          {infoRow(
            "曝光",
            [
              photo.aperture ? `f/${formatExifDecimal(photo.aperture)}` : null,
              photo.exposure_time ? `${photo.exposure_time}s` : null,
              photo.iso ? `ISO ${photo.iso}` : null,
              photo.focal_length ? `${formatExifDecimal(photo.focal_length)}mm` : null,
            ].filter(Boolean).join("  "),
          )}
        </section>
      </section>
    </main>
  );
}
