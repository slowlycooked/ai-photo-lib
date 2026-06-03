import { useMemo } from "react";
import { Loader2, ImageOff } from "lucide-react";
import { usePhotos } from "@/hooks/usePhotos";
import { useInfiniteScrollSentinel } from "@/hooks/useInfiniteScrollSentinel";
import { PhotoCard } from "./PhotoCard";

export function PhotoGrid() {
  const { data, fetchNextPage, hasNextPage, isFetchingNextPage, isLoading, isError } = usePhotos();

  const sentinelRef = useInfiniteScrollSentinel<HTMLDivElement>({
    hasNextPage,
    isFetchingNextPage,
    fetchNextPage,
  });

  const allPhotos = useMemo(() => {
    const loaded = data?.pages.flatMap((page) => page.items) ?? [];
    const uniqueById = new Map<number, (typeof loaded)[number]>();
    for (const photo of loaded) {
      if (!uniqueById.has(photo.id)) {
        uniqueById.set(photo.id, photo);
      }
    }
    return Array.from(uniqueById.values());
  }, [data]);
  const total = data?.pages[0]?.total ?? 0;

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
          <p className="text-body-sm text-mute mt-1">点击右上角「开始扫描」导入照片目录</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Count */}
      <p className="text-body-sm text-mute">
        共 <span className="font-semibold text-ink">{total.toLocaleString()}</span> 张照片
      </p>

      {/* Masonry grid */}
      <div className="masonry-grid">
        {allPhotos.map((photo) => (
          <PhotoCard key={photo.id} photo={photo} />
        ))}
      </div>

      {/* Infinite scroll sentinel */}
      <div ref={sentinelRef} className="h-4" />

      {isFetchingNextPage && (
        <div className="flex justify-center py-6">
          <Loader2 className="w-5 h-5 animate-spin text-mute" />
        </div>
      )}
    </div>
  );
}
