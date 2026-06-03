import { useMemo, useState } from "react";
import { Download, Loader2, SearchX } from "lucide-react";
import { useSearch } from "@/hooks/useSearch";
import { useInfiniteScrollSentinel } from "@/hooks/useInfiniteScrollSentinel";
import type { SearchDebugPayload, SearchMode, SearchResultItem, TagField } from "@/api/types";
import { SearchDebugPanel } from "@/components/search/SearchDebugPanel";
import { SearchPhotoLightbox } from "@/components/search/SearchPhotoLightbox";
import { SearchResultMasonry } from "@/components/search/SearchResultMasonry";

interface SearchResultGridProps {
  query: string;
  projectId?: number | null;
  mode?: SearchMode;
  debug?: boolean;
  tagField?: TagField | null;
  tagValue?: string | null;
  faceCountMin?: number | null;
  faceCountMax?: number | null;
  hasReviewPending?: boolean | null;
  hasUnnamedPeople?: boolean | null;
}

function buildExportJson({
  query,
  projectId,
  mode,
  allItems,
  total,
  debugPayload,
}: {
  query: string;
  projectId: number | null | undefined;
  mode: string;
  allItems: SearchResultItem[];
  total: number;
  debugPayload: SearchDebugPayload | null | undefined;
}) {
  return {
    exported_at: new Date().toISOString(),
    query: {
      query,
      mode,
      project_id: projectId ?? null,
    },
    total,
    loaded_count: allItems.length,
    debug: debugPayload ?? null,
    results: allItems.map((item, idx) => ({
      rank: idx + 1,
      photo_id: item.photo_id,
      file_name: item.file_name,
      caption: item.caption ?? null,
      taken_at: item.taken_at ?? null,
      location: {
        country_name: item.country_name ?? null,
        admin1: item.admin1 ?? null,
        admin2: item.admin2 ?? null,
        city: item.city ?? null,
        district: item.district ?? null,
        formatted_address: item.formatted_address ?? null,
      },
      width: item.width ?? null,
      height: item.height ?? null,
      scores: {
        final: item.score,
        rrf: item.rrf_score ?? null,
        keyword: item.keyword_score ?? null,
        vector: item.vector_score ?? null,
      },
      field_scores: item.field_scores ?? null,
      match_source: item.match_source ?? null,
      matched_tags: item.matched_tags,
      explain: item.explain ?? null,
    })),
  };
}

function downloadJson(data: unknown, filename: string) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export function SearchResultGrid({
  query,
  projectId,
  mode = "hybrid",
  debug = false,
  tagField,
  tagValue,
  faceCountMin,
  faceCountMax,
  hasReviewPending,
  hasUnnamedPeople,
}: SearchResultGridProps) {
  const {
    data,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
    isLoading,
    isError,
    error,
  } = useSearch(query, projectId ?? null, {
    mode,
    debug,
    tagField,
    tagValue,
    faceCountMin,
    faceCountMax,
    hasReviewPending,
    hasUnnamedPeople,
  });

  const [previewItem, setPreviewItem] = useState<SearchResultItem | null>(null);
  const sentinelRef = useInfiniteScrollSentinel<HTMLDivElement>({
    hasNextPage,
    isFetchingNextPage,
    fetchNextPage,
  });

  const allItems = useMemo(() => {
    const loaded = data?.pages.flatMap((page) => page.items) ?? [];
    const uniqueByPhotoId = new Map<number, SearchResultItem>();
    for (const item of loaded) {
      if (!uniqueByPhotoId.has(item.photo_id)) {
        uniqueByPhotoId.set(item.photo_id, item);
      }
    }
    return Array.from(uniqueByPhotoId.values());
  }, [data]);
  const total = data?.pages[0]?.total ?? 0;
  const debugPayload = data?.pages[0]?.debug;

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
      <div className="space-y-4">
        {debug && debugPayload && <SearchDebugPanel payload={debugPayload} />}
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
      </div>
    );
  }

  function handleExport() {
    const data = buildExportJson({ query, projectId, mode, allItems, total, debugPayload });
    const safeQuery = query.replace(/[^\w\u4e00-\u9fa5]/g, "_").slice(0, 40);
    downloadJson(data, `search_debug_${safeQuery}_${Date.now()}.json`);
  }

  return (
    <div className="space-y-4">
      {debug && debugPayload && <SearchDebugPanel payload={debugPayload} />}

      <div className="flex items-center justify-between gap-3">
        <p className="text-body-sm text-mute">
          「{query}」共找到{" "}
          <span className="font-semibold text-ink">{total.toLocaleString()}</span> 张照片
          {allItems.length < total && (
            <span className="text-caption-sm">（已加载 {allItems.length} 张）</span>
          )}
        </p>
        {debug && (
          <button
            onClick={handleExport}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded border border-amber-400/60 bg-amber-50 dark:bg-amber-950/40 text-amber-800 dark:text-amber-300 text-[11px] font-mono hover:bg-amber-100 dark:hover:bg-amber-900/50 transition-colors"
            title="导出搜索参数与结果为 JSON"
          >
            <Download className="w-3.5 h-3.5" />
            导出 JSON
          </button>
        )}
      </div>

      <SearchResultMasonry
        items={allItems}
        debug={debug}
        onPreview={setPreviewItem}
      />

      {previewItem && (
        <SearchPhotoLightbox
          item={previewItem}
          projectId={projectId}
          onDeleted={() => {
            setPreviewItem(null);
          }}
          onClose={() => setPreviewItem(null)}
        />
      )}

      <div ref={sentinelRef} className="h-4" />

      {isFetchingNextPage && (
        <div className="flex justify-center py-6">
          <Loader2 className="w-5 h-5 animate-spin text-mute" />
        </div>
      )}
    </div>
  );
}
