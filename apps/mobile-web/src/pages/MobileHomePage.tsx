import { useCallback, useMemo, useState } from "react";
import type { Photo } from "@/api";
import { EmptyState } from "@/components/EmptyState";
import { LoadingState } from "@/components/LoadingState";
import { MobileTopBar } from "@/components/MobileTopBar";
import { PhotoThumbGrid } from "@/components/PhotoThumbGrid";
import { ProjectSwitcherSheet } from "@/components/ProjectSwitcherSheet";
import { useProjectContext } from "@/contexts/ProjectContext";
import { useInfiniteScrollSentinel } from "@/hooks/useInfiniteScrollSentinel";
import { useMobilePhotos } from "@/hooks/useMobilePhotos";

function monthLabel(takenAt: string | null): string {
  if (!takenAt) return "未标注拍摄时间";
  const date = new Date(takenAt);
  if (Number.isNaN(date.getTime())) return "未标注拍摄时间";
  return `${date.getFullYear()}年${String(date.getMonth() + 1).padStart(2, "0")}月`;
}

export function MobileHomePage() {
  const { projects, currentProject, currentProjectId, setCurrentProjectId } = useProjectContext();
  const [sheetOpen, setSheetOpen] = useState(false);

  const query = useMobilePhotos(currentProjectId);

  const photos = useMemo(
    () => query.data?.pages.flatMap((page) => page.items) ?? [],
    [query.data],
  );
  const photoIds = useMemo(() => photos.map((photo) => photo.id), [photos]);

  const grouped = useMemo(() => {
    const map = new Map<string, Photo[]>();
    for (const photo of photos) {
      const key = monthLabel(photo.taken_at);
      const list = map.get(key) ?? [];
      list.push(photo);
      map.set(key, list);
    }
    return Array.from(map.entries());
  }, [photos]);

  const loadMore = useCallback(() => {
    if (!query.hasNextPage || query.isFetchingNextPage) return;
    query.fetchNextPage();
  }, [query]);

  const sentinelRef = useInfiniteScrollSentinel(
    loadMore,
    Boolean(query.hasNextPage),
  );

  return (
    <main className="mobile-page">
      <MobileTopBar
        title={currentProject?.name ?? "选择项目"}
        onOpenProjects={() => setSheetOpen(true)}
      />

      <section className="mx-auto max-w-3xl space-y-5 px-4 py-4 pb-20">
        {query.isLoading && <LoadingState label="正在加载照片..." />}

        {!query.isLoading && photos.length === 0 && (
          <EmptyState title="这个项目暂时没有照片" description="请先在桌面端扫描项目照片库。" />
        )}

        {grouped.map(([month, monthPhotos]) => (
          <section key={month} className="space-y-2">
            <h2 className="px-1 text-xs font-semibold uppercase tracking-wide text-mobileMute">
              {month}
            </h2>
            {currentProjectId != null && (
              <PhotoThumbGrid projectId={currentProjectId} photos={monthPhotos} photoIds={photoIds} />
            )}
          </section>
        ))}

        {query.isFetchingNextPage && <LoadingState label="正在加载更多..." />}
        <div ref={sentinelRef} className="h-2" />
      </section>

      <ProjectSwitcherSheet
        open={sheetOpen}
        projects={projects}
        currentProjectId={currentProjectId}
        onClose={() => setSheetOpen(false)}
        onSelect={setCurrentProjectId}
      />
    </main>
  );
}
