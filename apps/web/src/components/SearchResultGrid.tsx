import { useEffect, useRef, useState } from "react";
import { Loader2, SearchX, ImageIcon } from "lucide-react";
import { useSearch } from "@/hooks/useSearch";
import { api } from "@/lib/api";
import type { SearchDebugPayload, SearchMode, SearchResultItem } from "@/api/types";

interface SearchResultGridProps {
  query: string;
  projectId?: number | null;
  mode?: SearchMode;
  debug?: boolean;
}

function SearchCard({ item, debug }: { item: SearchResultItem; debug?: boolean }) {
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

          {/* Debug per-card scores */}
          {debug && (item.rrf_score != null || item.vector_score != null) && (
            <div className="text-[10px] font-mono text-muted-foreground space-y-0.5 border-t border-dashed border-border pt-1">
              {item.rrf_score != null && (
                <div>rrf: {item.rrf_score.toFixed(5)}</div>
              )}
              {item.keyword_score != null && (
                <div>kw: {item.keyword_score.toFixed(4)}</div>
              )}
              {item.vector_score != null && (
                <div>vec: {item.vector_score.toFixed(4)}</div>
              )}
              {item.field_scores && (
                <div>
                  {Object.entries(item.field_scores)
                    .map(([k, v]) => `${k}:${(v as number).toFixed(3)}`)
                    .join(" ")}
                </div>
              )}
              {item.explain?.keyword && (
                <div className="text-[9px] text-blue-600 dark:text-blue-400">
                  kw_rank:{item.explain.keyword.rank ?? "?"}{" "}
                  fields:{Object.keys(item.explain.keyword.matched_fields ?? {}).join(",")}
                </div>
              )}
              {item.explain?.vector && (
                <div className="text-[9px] text-purple-600 dark:text-purple-400">
                  vec_rank:{item.explain.vector.rank ?? "?"}{" "}
                  {Object.entries(item.explain.vector.field_scores ?? {})
                    .map(([k, v]) => `${k}:${(v as number).toFixed(3)}`)
                    .join(" ")}
                </div>
              )}
              {item.match_source && (
                <div className="text-[9px] text-stone">{item.match_source.join(" ")}</div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function DebugPanel({ payload }: { payload: SearchDebugPayload }) {
  return (
    <div className="rounded-md border border-amber-400/50 bg-amber-50 dark:bg-amber-950/30 p-3 text-[11px] font-mono space-y-1 text-amber-900 dark:text-amber-200">
      <div className="font-semibold text-xs mb-1.5">🔍 Search Debug</div>
      <div><span className="opacity-60">原始:</span> {payload.original_query}</div>
      <div><span className="opacity-60">规范化:</span> {payload.normalized_query}</div>
      {(payload.exact_terms?.length ?? 0) > 0 && (
        <div><span className="opacity-60">精确词:</span> {payload.exact_terms!.join(", ")}</div>
      )}
      {(payload.expanded_terms?.length ?? 0) > 0 && (
        <div><span className="opacity-60">近义词:</span> {payload.expanded_terms.join(", ")}</div>
      )}
      {(payload.broad_terms?.length ?? 0) > 0 && (
        <div><span className="opacity-60">宽泛词:</span> {payload.broad_terms!.join(", ")}</div>
      )}
      <div>
        <span className="opacity-60">意图:</span> {payload.intent}
        {payload.recommended_profile && (
          <> &nbsp; <span className="opacity-60">权重方案:</span> {payload.recommended_profile}</>
        )}
        &nbsp; <span className="opacity-60">模式:</span> {payload.mode}
      </div>
      <div><span className="opacity-60">模型:</span> {payload.embedding_model} ({payload.embedding_dimension}d)</div>
      <div>
        <span className="opacity-60">候选:</span>{" "}
        关键词 {payload.keyword_candidates} / 向量 {payload.vector_candidates} / 合并 {payload.merged_candidates}
      </div>
      {payload.settings_snapshot && (
        <details className="mt-1">
          <summary className="cursor-pointer opacity-70 text-[10px]">设置快照 (点击展开)</summary>
          <div className="mt-1 space-y-0.5 text-[10px] pl-2 border-l border-amber-400/30">
            <div>mode:{payload.settings_snapshot.default_mode} kw_k:{payload.settings_snapshot.keyword_top_k} vec_k:{payload.settings_snapshot.vector_top_k} rrf_k:{payload.settings_snapshot.rrf_k}</div>
            <div>kw_w:{payload.settings_snapshot.keyword_weight} vec_w:{payload.settings_snapshot.vector_weight} min_score:{payload.settings_snapshot.vector_min_score}</div>
            <div>vec_fields: {Object.entries(payload.settings_snapshot.vector_field_weights ?? {}).map(([k,v]) => `${k.replace('_embedding','')}:${(v as number).toFixed(2)}`).join(" ")}</div>
          </div>
        </details>
      )}
      {payload.fallback_reason && (
        <div className="text-red-600 dark:text-red-400">
          ⚠ Fallback: {payload.fallback_reason}
        </div>
      )}
    </div>
  );
}

export function SearchResultGrid({ query, projectId, mode = "hybrid", debug = false }: SearchResultGridProps) {
  const {
    data,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
    isLoading,
    isError,
    error,
  } = useSearch(query, projectId ?? null, { mode, debug });

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
      {debug && debugPayload && <DebugPanel payload={debugPayload} />}

      <p className="text-body-sm text-mute">
        「{query}」共找到{" "}
        <span className="font-semibold text-ink">{total.toLocaleString()}</span> 张照片
      </p>

      <div className="masonry-grid">
        {allItems.map((item) => (
          <SearchCard key={item.photo_id} item={item} debug={debug} />
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
