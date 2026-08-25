import { useCallback, useEffect, useMemo, useState } from "react";
import { useInfiniteQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { useSearchParams } from "react-router-dom";
import { api } from "@/api";
import { EmptyState } from "@/components/EmptyState";
import { LoadingState } from "@/components/LoadingState";
import { PhotoThumbGrid } from "@/components/PhotoThumbGrid";
import { useProjectContext } from "@/contexts/ProjectContext";
import { useInfiniteScrollSentinel } from "@/hooks/useInfiniteScrollSentinel";

const STORAGE_KEY = "ai-photo-lib:mobile:recent-searches";

function readRecentSearches() {
  const raw = localStorage.getItem(STORAGE_KEY);
  if (!raw) return [] as string[];
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter((item) => typeof item === "string") : [];
  } catch {
    return [];
  }
}

function writeRecentSearches(items: string[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(items.slice(0, 8)));
}

export function MobileSearchPage() {
  const { currentProjectId } = useProjectContext();
  const [searchParams, setSearchParams] = useSearchParams();
  const query = searchParams.get("q") ?? "";
  const [input, setInput] = useState(query);
  const [recent, setRecent] = useState<string[]>(() => readRecentSearches());

  useEffect(() => setInput(query), [query]);

  const search = useInfiniteQuery({
    queryKey: ["mobile-search", currentProjectId, query],
    enabled: currentProjectId != null && query.trim().length > 0,
    initialPageParam: 1,
    queryFn: ({ pageParam }) =>
      api.search.search(currentProjectId!, query.trim(), pageParam as number, 50),
    getNextPageParam: (lastPage) => {
      const loaded = lastPage.page * lastPage.page_size;
      return loaded < lastPage.total ? lastPage.page + 1 : undefined;
    },
  });

  const photos = useMemo(
    () =>
      search.data?.pages.flatMap((page) =>
        page.items.map((item) => ({
          id: item.photo_id,
          project_id: currentProjectId ?? 0,
          file_name: item.file_name,
          mime_type: null,
          width: item.width,
          height: item.height,
          taken_at: item.taken_at,
          file_size: null,
          status: "ready",
          thumbnail_path: null,
          updated_at: item.updated_at,
        })),
      ) ?? [],
    [search.data, currentProjectId],
  );

  const photoIds = useMemo(() => photos.map((photo) => photo.id), [photos]);

  const submitQuery = useCallback(
    (value: string) => {
      const normalized = value.trim();
      if (!normalized) return;
      setSearchParams({ q: normalized });
      const nextRecent = [normalized, ...recent.filter((item) => item !== normalized)].slice(0, 8);
      setRecent(nextRecent);
      writeRecentSearches(nextRecent);
    },
    [recent, setSearchParams],
  );

  const loadMore = useCallback(() => {
    if (!search.hasNextPage || search.isFetchingNextPage) return;
    search.fetchNextPage();
  }, [search]);

  const sentinelRef = useInfiniteScrollSentinel(loadMore, Boolean(search.hasNextPage));

  return (
    <main className="mobile-page px-4 pb-20 pt-3">
      <section className="mx-auto max-w-3xl space-y-4">
        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            submitQuery(input);
          }}
        >
          <label className="relative flex-1">
            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-mobileMute" />
            <input
              type="search"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="搜索照片，例如：夜景、滑雪、家庭聚餐"
              className="h-11 w-full rounded-xl border border-mobileHairline bg-mobileCard pl-9 pr-3 text-sm outline-none ring-mobileAccent focus:ring-2"
            />
          </label>
          <button
            type="submit"
            className="h-11 rounded-xl bg-mobileAccent px-4 text-sm font-semibold text-white active:bg-mobileAccentPressed"
          >
            搜索
          </button>
        </form>

        {recent.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {recent.map((term) => (
              <button
                key={term}
                type="button"
                onClick={() => {
                  setInput(term);
                  submitQuery(term);
                }}
                className="rounded-full border border-mobileHairline bg-mobileCard px-3 py-1.5 text-xs text-mobileInk"
              >
                {term}
              </button>
            ))}
            <button
              type="button"
              onClick={() => {
                setRecent([]);
                writeRecentSearches([]);
              }}
              className="rounded-full border border-mobileHairline px-3 py-1.5 text-xs text-mobileMute"
            >
              清空
            </button>
          </div>
        )}

        {search.isLoading && <LoadingState label="正在搜索..." />}

        {!search.isLoading && query && photos.length === 0 && (
          <EmptyState title="没有匹配结果" description="换个关键词再试试。" />
        )}

        {currentProjectId != null && photos.length > 0 && (
          <PhotoThumbGrid projectId={currentProjectId} photos={photos} photoIds={photoIds} />
        )}

        {search.isFetchingNextPage && <LoadingState label="加载更多结果..." />}
        <div ref={sentinelRef} className="h-2" />
      </section>
    </main>
  );
}
