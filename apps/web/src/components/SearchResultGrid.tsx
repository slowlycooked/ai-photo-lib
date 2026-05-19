import { useEffect, useRef, useState } from "react";
import { Loader2, SearchX, ImageIcon } from "lucide-react";
import { useSearch } from "@/hooks/useSearch";
import { api } from "@/lib/api";
import type { SearchResultItem } from "@/lib/api";

interface SearchResultGridProps {
  query: string;
  projectId?: number | null;
}

function SearchCard({ item }: { item: SearchResultItem }) {
  const [loaded, setLoaded] = useState(false);

  return (
    <div className="break-inside-avoid mb-3">
      <div className="bg-canvas rounded-md overflow-hidden border border-hairline hover:shadow-md transition-shadow">
        {/* Thumbnail */}
        <div className="relative bg-surface-card">
          {!loaded && (
            <div className="flex items-center justify-center h-32">
              <ImageIcon className="w-8 h-8 text-stone" />
            </div>
          )}
          <img
            src={item.thumbnail_url}
            alt={item.file_name}
            className="w-full object-cover"
            style={{ opacity: loaded ? 1 : 0, transition: "opacity 0.2s" }}
            onLoad={() => setLoaded(true)}
          />
        </div>

        {/* Info */}
        <div className="p-3 space-y-2">
          {item.caption && (
            <p className="text-body-sm text-ink line-clamp-2">{item.caption}</p>
          )}

          {/* Matched tags */}
          {item.matched_tags.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {item.matched_tags.slice(0, 6).map((tag) => (
                <span
                  key={tag}
                  className="px-2 py-0.5 rounded-full bg-primary/10 text-primary text-caption-md font-medium"
                >
                  {tag}
                </span>
              ))}
            </div>
          )}

          <p className="text-caption-sm text-ash truncate">{item.file_name}</p>
        </div>
      </div>
    </div>
  );
}

export function SearchResultGrid({ query, projectId }: SearchResultGridProps) {
  const {
    data,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
    isLoading,
    isError,
    error,
  } = useSearch(query, projectId);

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

  const allItems = data?.pages.flatMap((p) => p.items) ?? [];
  const total = data?.pages[0]?.total ?? 0;

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center py-24 gap-3 text-mute">
        <Loader2 className="w-8 h-8 animate-spin" />
        <p className="text-body-sm">搜索中…</p>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="flex flex-col items-center justify-center py-24 gap-3 text-mute">
        <SearchX className="w-8 h-8" />
        <p className="text-body-sm">搜索失败：{(error as Error).message}</p>
      </div>
    );
  }

  if (allItems.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-24 gap-4 text-mute">
        <div className="w-20 h-20 rounded-full bg-secondary-bg flex items-center justify-center">
          <SearchX className="w-9 h-9 text-stone" />
        </div>
        <div className="text-center">
          <p className="text-heading-md font-semibold text-ink">没有找到匹配的照片</p>
          <p className="text-body-sm text-mute mt-1">
            试试其他关键词，或确认已完成 AI 分析
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <p className="text-body-sm text-mute">
        「{query}」共找到{" "}
        <span className="font-semibold text-ink">{total.toLocaleString()}</span> 张照片
      </p>

      <div className="masonry-grid">
        {allItems.map((item) => (
          <SearchCard key={item.photo_id} item={item} />
        ))}
      </div>

      <div ref={sentinelRef} className="h-4" />

      {isFetchingNextPage && (
        <div className="flex justify-center py-6">
          <Loader2 className="w-5 h-5 animate-spin text-mute" />
        </div>
      )}
    </div>
  );
}
