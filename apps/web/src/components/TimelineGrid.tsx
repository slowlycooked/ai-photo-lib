import { useEffect, useRef, useState } from "react";
import { Loader2, ImageOff } from "lucide-react";
import { usePhotos } from "@/hooks/usePhotos";
import { PhotoCard } from "./PhotoCard";
import { TimelineRail } from "./TimelineRail";
import type { Photo } from "@/lib/api";

interface TimelineGridProps {
  projectId?: number | null;
}

function formatGroupLabel(key: string): string {
  if (key === "unknown") return "未知日期";
  const [year, month] = key.split("-");
  const d = new Date(Number(year), Number(month) - 1);
  return d.toLocaleDateString("zh-CN", { year: "numeric", month: "long" });
}

function groupPhotosByMonth(photos: Photo[]): Map<string, Photo[]> {
  const groups = new Map<string, Photo[]>();
  for (const photo of photos) {
    const raw = photo.taken_at ?? photo.created_at;
    let key = "unknown";
    if (raw) {
      const d = new Date(raw);
      if (!isNaN(d.getTime())) {
        key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
      }
    }
    const bucket = groups.get(key) ?? [];
    bucket.push(photo);
    groups.set(key, bucket);
  }
  return new Map(
    [...groups.entries()].sort(([a], [b]) => {
      if (a === "unknown") return 1;
      if (b === "unknown") return -1;
      return b.localeCompare(a);
    })
  );
}

export function TimelineGrid({ projectId }: TimelineGridProps) {
  const [dateFrom, setDateFrom] = useState<string | null>(null);
  const [dateTo, setDateTo] = useState<string | null>(null);
  const [activeKey, setActiveKey] = useState<string | null>(null);

  const { data, fetchNextPage, hasNextPage, isFetchingNextPage, isLoading, isError } =
    usePhotos({ projectId, dateFrom, dateTo });

  const sentinelRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!sentinelRef.current || !hasNextPage) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && !isFetchingNextPage) fetchNextPage();
      },
      { rootMargin: "200px" }
    );
    observer.observe(sentinelRef.current);
    return () => observer.disconnect();
  }, [hasNextPage, isFetchingNextPage, fetchNextPage]);

  const allPhotos = data?.pages.flatMap((p) => p.items) ?? [];
  const total = data?.pages[0]?.total ?? 0;

  const handleMonthSelect = (key: string, from: string, to: string) => {
    if (activeKey === key) {
      // Clicking same month → clear filter
      setActiveKey(null);
      setDateFrom(null);
      setDateTo(null);
    } else {
      setActiveKey(key);
      setDateFrom(from);
      setDateTo(to);
    }
  };

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center py-24 gap-3 text-mute">
        <Loader2 className="w-8 h-8 animate-spin" />
        <p className="text-body-sm">加载照片中…</p>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="flex flex-col items-center justify-center py-24 gap-3 text-mute">
        <ImageOff className="w-8 h-8" />
        <p className="text-body-sm">无法连接 API，请确认后端服务已启动</p>
      </div>
    );
  }

  if (allPhotos.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-24 gap-4 text-mute">
        <div className="w-20 h-20 rounded-full bg-secondary-bg flex items-center justify-center">
          <ImageOff className="w-9 h-9 text-stone" />
        </div>
        <div className="text-center">
          <p className="text-heading-md font-semibold text-ink">还没有照片</p>
          <p className="text-body-sm text-mute mt-1">点击上方「重新扫描」或先启动扫描导入照片</p>
        </div>
      </div>
    );
  }

  const groups = groupPhotosByMonth(allPhotos);

  return (
    <div className="flex gap-4">
      {/* Photo grid */}
      <div className="flex-1 min-w-0 space-y-8">
        <div className="flex items-center gap-3">
          <p className="text-body-sm text-mute">
            共 <span className="font-semibold text-ink">{total.toLocaleString()}</span> 张照片
          </p>
          {activeKey && (
            <button
              onClick={() => {
                setActiveKey(null);
                setDateFrom(null);
                setDateTo(null);
              }}
              className="text-caption-sm text-primary hover:text-primary-pressed"
            >
              × 清除月份筛选
            </button>
          )}
        </div>

        {[...groups.entries()].map(([key, photos]) => (
          <section key={key}>
            <h2 className="text-heading-md font-semibold text-ink mb-3">
              {formatGroupLabel(key)}
              <span className="ml-2 text-body-sm font-normal text-mute">
                {photos.length} 张
              </span>
            </h2>
            <div className="masonry-grid">
              {photos.map((photo) => (
                <PhotoCard key={photo.id} photo={photo} />
              ))}
            </div>
          </section>
        ))}

        <div ref={sentinelRef} className="h-4" />

        {isFetchingNextPage && (
          <div className="flex justify-center py-6">
            <Loader2 className="w-5 h-5 animate-spin text-mute" />
          </div>
        )}
      </div>

      {/* Right-side timeline rail */}
      <TimelineRail
        projectId={projectId}
        activeKey={activeKey}
        onSelect={handleMonthSelect}
      />
    </div>
  );
}
