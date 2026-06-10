import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { api } from "@/api";
import { DownloadButton } from "@/components/DownloadButton";
import { LoadingState } from "@/components/LoadingState";
import { PhotoViewer } from "@/components/PhotoViewer";
import { useProjectContext } from "@/contexts/ProjectContext";
import { useSwipePhotoNavigation } from "@/hooks/useSwipePhotoNavigation";

function infoRow(label: string, value: string | number | null | undefined) {
  if (value == null || value === "") return null;
  return (
    <div className="flex justify-between gap-3 border-b border-mobileHairline py-2 text-sm">
      <span className="text-mobileMute">{label}</span>
      <span className="text-right text-mobileInk">{value}</span>
    </div>
  );
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

  const photoIds = useMemo(() => {
    const state = location.state as { photoIds?: number[] } | null;
    return Array.isArray(state?.photoIds) ? state.photoIds : [];
  }, [location.state]);

  const currentIndex = photoIds.indexOf(id);
  const prevId = currentIndex > 0 ? photoIds[currentIndex - 1] : null;
  const nextId =
    currentIndex >= 0 && currentIndex < photoIds.length - 1
      ? photoIds[currentIndex + 1]
      : null;

  const goPrev = () => {
    if (prevId == null) return;
    navigate(`/photos/${prevId}`, { state: { photoIds }, replace: true });
  };
  const goNext = () => {
    if (nextId == null) return;
    navigate(`/photos/${nextId}`, { state: { photoIds }, replace: true });
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
          <Link to="/photos" className="inline-flex items-center gap-1 text-sm text-mobileInk">
            <ArrowLeft size={16} /> 返回
          </Link>
          <DownloadButton projectId={currentProjectId} photoId={photo.id} />
        </div>

        <PhotoViewer
          src={api.photos.previewUrl(currentProjectId, photo.id)}
          alt={photo.file_name}
          canPrev={prevId != null}
          canNext={nextId != null}
          onPrev={goPrev}
          onNext={goNext}
          swipeHandlers={swipeHandlers}
        />

        <section className="rounded-2xl border border-mobileHairline bg-mobileCard px-4 py-3">
          <h2 className="mb-1 text-sm font-semibold text-mobileInk">{photo.file_name}</h2>
          {infoRow("拍摄时间", photo.taken_at ? new Date(photo.taken_at).toLocaleString() : null)}
          {infoRow("地点", photo.formatted_address ?? photo.city ?? photo.country_name)}
          {infoRow("相机", [photo.camera_make, photo.camera_model].filter(Boolean).join(" "))}
          {infoRow("镜头", photo.lens_model)}
          {infoRow("分辨率", photo.width && photo.height ? `${photo.width} x ${photo.height}` : null)}
          {infoRow("文件大小", photo.file_size ? `${(photo.file_size / 1024 / 1024).toFixed(2)} MB` : null)}
        </section>
      </section>
    </main>
  );
}
