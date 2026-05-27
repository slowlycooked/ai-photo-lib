import { useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, SearchX, ImageIcon, ChevronDown, ChevronRight, Download, X, ZoomIn, MapPin, Calendar, Trash2 } from "lucide-react";
import { useSearch } from "@/hooks/useSearch";
import { api } from "@/api";
import type { SearchDebugPayload, SearchMode, SearchResultItem, SearchTraceStep, TagField } from "@/api/types";
import { queryKeys } from "@/api/queryKeys";
import { formatLocationAddress, formatLocationSummary } from "@/lib/utils";

interface SearchResultGridProps {
  query: string;
  projectId?: number | null;
  mode?: SearchMode;
  debug?: boolean;
  tagField?: TagField | null;
  tagValue?: string | null;
}

// ── Lightbox ──────────────────────────────────────────────────────────────
function SearchPhotoLightbox({
  item,
  projectId,
  onClose,
  onDeleted,
}: {
  item: SearchResultItem;
  projectId: number | null | undefined;
  onClose: () => void;
  onDeleted?: () => void;
}) {
  const [imgLoaded, setImgLoaded] = useState(false);
  const [deleteOriginal, setDeleteOriginal] = useState(false);
  const [deleteMessage, setDeleteMessage] = useState<string | null>(null);
  const queryClient = useQueryClient();
  const locationSummary = formatLocationSummary(item, { short: true });
  const takenAtLabel = item.taken_at
    ? new Date(item.taken_at).toLocaleDateString("zh-CN", {
        year: "numeric",
        month: "short",
        day: "numeric",
      })
    : null;

  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [onClose]);

  const previewUrl =
    projectId != null
      ? api.projects.previewUrl(projectId, item.photo_id)
      : item.thumbnail_url;

  const downloadUrl =
    projectId != null
      ? api.projects.originalUrl(projectId, item.photo_id)
      : undefined;

  const deletePhotoMutation = useMutation({
    mutationFn: () => api.projects.deletePhotoRecord(projectId!, item.photo_id, deleteOriginal),
    onSuccess: () => {
      setDeleteMessage(deleteOriginal ? "已删除库记录、缩略图和本地原图" : "已删除库记录和缩略图");
      if (projectId != null) {
        queryClient.invalidateQueries({ queryKey: queryKeys.photosBase(projectId) });
        queryClient.invalidateQueries({ queryKey: queryKeys.timeline(projectId) });
        queryClient.invalidateQueries({ queryKey: queryKeys.tags(projectId) });
      }
      queryClient.invalidateQueries({ queryKey: ["search"] });
      onDeleted?.();
      onClose();
    },
    onError: (error: Error) => setDeleteMessage(`删除失败：${error.message}`),
  });

  function handleDeleteRecord() {
    if (projectId == null) return;
    const actionText = deleteOriginal ? "删除库记录、缩略图并尝试删除本地原图" : "仅删除库记录和缩略图";
    if (!window.confirm(`确认${actionText}吗？`)) {
      return;
    }
    deletePhotoMutation.mutate();
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ backgroundColor: "rgba(0,0,0,0.85)" }}
      onClick={onClose}
    >
      <div
        className="relative max-w-[90vw] max-h-[90vh] flex flex-col items-center"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Action buttons */}
        <div className="absolute top-3 right-3 flex gap-2 z-10">
          {downloadUrl && (
            <a
              href={downloadUrl}
              download={item.file_name}
              onClick={(e) => e.stopPropagation()}
              className="w-9 h-9 rounded-full bg-black/60 flex items-center justify-center hover:bg-black/80 transition-colors"
              aria-label="下载原图"
              title="下载原图"
            >
              <Download className="w-4 h-4 text-white" />
            </a>
          )}
          {projectId != null && (
            <button
              type="button"
              onClick={handleDeleteRecord}
              disabled={deletePhotoMutation.isPending}
              className="w-9 h-9 rounded-full bg-black/60 flex items-center justify-center hover:bg-black/80 transition-colors disabled:opacity-60"
              aria-label="删除库记录"
              title={deleteOriginal ? "删除库记录、缩略图和本地原图" : "仅删除库记录和缩略图"}
            >
              {deletePhotoMutation.isPending ? (
                <Loader2 className="w-4 h-4 text-red-300 animate-spin" />
              ) : (
                <Trash2 className="w-4 h-4 text-red-300" />
              )}
            </button>
          )}
          <button
            onClick={onClose}
            className="w-9 h-9 rounded-full bg-black/60 flex items-center justify-center hover:bg-black/80 transition-colors"
            aria-label="关闭预览"
          >
            <X className="w-4 h-4 text-white" />
          </button>
        </div>

        {/* Image */}
        {!imgLoaded && (
          <div className="flex items-center justify-center" style={{ minWidth: 200, minHeight: 200 }}>
            <Loader2 className="w-8 h-8 animate-spin text-white/60" />
          </div>
        )}
        <img
          src={previewUrl}
          alt={item.file_name}
          className="rounded-md object-contain shadow-2xl"
          style={{
            maxWidth: "90vw",
            maxHeight: "80vh",
            opacity: imgLoaded ? 1 : 0,
            transition: "opacity 0.2s",
          }}
          onLoad={() => setImgLoaded(true)}
        />

        {/* Caption bar */}
        {(item.caption || item.file_name) && (
          <div className="mt-3 px-4 py-2 rounded-md bg-black/60 text-white text-sm max-w-lg text-center space-y-1">
            {item.caption && <p className="line-clamp-2">{item.caption}</p>}
            {(locationSummary || takenAtLabel) && (
              <div className="flex flex-wrap items-center justify-center gap-x-3 gap-y-1 text-xs text-white/80">
                {locationSummary && <span>{locationSummary}</span>}
                {takenAtLabel && <span>{takenAtLabel}</span>}
              </div>
            )}
            <p className="text-white/60 text-xs truncate">{item.file_name}</p>
            {projectId != null && (
              <div className="border-t border-white/15 pt-2 mt-2 space-y-2 text-left">
                <label className="flex items-center gap-2 text-xs text-white/85">
                  <input
                    type="checkbox"
                    checked={deleteOriginal}
                    onChange={(e) => setDeleteOriginal(e.target.checked)}
                    className="h-3.5 w-3.5"
                  />
                  同时删除本地原图（hard copy 删除）
                </label>
                <p className="text-[11px] text-white/65">默认只清理库记录与缩略图。</p>
                {deleteMessage && <p className="text-[11px] text-white/70">{deleteMessage}</p>}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function SearchCard({
  item,
  debug,
  projectId,
  onPreview,
}: {
  item: SearchResultItem;
  debug?: boolean;
  projectId?: number | null;
  onPreview?: (item: SearchResultItem) => void;
}) {
  const [loaded, setLoaded] = useState(false);
  const locationSummary = formatLocationSummary(item, { short: true });
  const locationAddress = formatLocationAddress(item);
  const takenAtLabel = item.taken_at
    ? new Date(item.taken_at).toLocaleDateString("zh-CN", {
        year: "numeric",
        month: "short",
        day: "numeric",
      })
    : null;

  return (
    <div className="break-inside-avoid mb-3">
      <div className="bg-canvas rounded-md overflow-hidden border border-hairline hover:shadow-md transition-shadow">
        {/* Thumbnail */}
        <div
          className="relative bg-surface-card cursor-zoom-in group"
          onClick={() => onPreview?.(item)}
          role="button"
          aria-label={`预览 ${item.file_name}`}
          tabIndex={0}
          onKeyDown={(e) => e.key === "Enter" && onPreview?.(item)}
        >
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
          {/* Hover overlay */}
          <div className="absolute inset-0 bg-black/0 group-hover:bg-black/20 transition-colors flex items-center justify-center">
            <ZoomIn className="w-6 h-6 text-white opacity-0 group-hover:opacity-100 transition-opacity drop-shadow" />
          </div>
        </div>

        {/* Info */}
        <div className="p-3 space-y-2">
          {item.caption && (
            <p className="text-body-sm text-ink line-clamp-2">{item.caption}</p>
          )}

          {(locationSummary || takenAtLabel) && (
            <div className="flex flex-wrap gap-1.5">
              {locationSummary && (
                <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2.5 py-1 text-[11px] font-medium text-emerald-800">
                  <MapPin className="h-3.5 w-3.5" />
                  <span className="max-w-[180px] truncate" title={locationAddress ?? locationSummary}>
                    {locationSummary}
                  </span>
                </span>
              )}
              {takenAtLabel && (
                <span className="inline-flex items-center gap-1 rounded-full bg-surface-card px-2.5 py-1 text-[11px] font-medium text-mute">
                  <Calendar className="h-3.5 w-3.5" />
                  {takenAtLabel}
                </span>
              )}
            </div>
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
          {debug && (
            <div className="text-[10px] font-mono text-muted-foreground space-y-0.5 border-t border-dashed border-border pt-1">
              {/* EXIF / metadata row */}
              {(item.taken_at || item.camera_make || item.camera_model || item.iso != null || item.gps_latitude != null) && (
                <div className="text-[9px] text-teal-700 dark:text-teal-300 space-y-0">
                  {item.taken_at && <div>📅 {new Date(item.taken_at).toLocaleDateString("zh-CN")}</div>}
                  {locationSummary && <div>📍 {locationSummary}</div>}
                  {(item.camera_make || item.camera_model) && (
                    <div>📷 {[item.camera_make, item.camera_model].filter(Boolean).join(" ")}</div>
                  )}
                  {item.iso != null && <div>ISO {item.iso}</div>}
                  {item.gps_latitude != null && <div>📍 GPS</div>}
                </div>
              )}
              {item.match_source?.includes("metadata") && (
                <div className="text-teal-600 dark:text-teal-400 font-semibold">metadata match</div>
              )}
              {(item.rrf_score != null || item.vector_score != null) && (
                <>
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
                </>
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

// ── Trace step renderer ────────────────────────────────────────────────────
const STAGE_LABELS: Record<string, string> = {
  input: "① 输入参数",
  query_plan: "② 查询理解",
  settings: "③ 搜索配置",
  folder_filter: "④ 文件夹过滤",
  keyword_recall: "⑤ 关键词召回",
  concept_recall: "⑤.5 概念召回",
  people_visual_recall: "⑤.7 人像结构召回",
  vector_recall: "⑥ 向量召回",
  rrf_merge: "⑦ RRF 融合",
  result: "⑧ 结果",
};

const STAGE_COLORS: Record<string, string> = {
  input: "text-sky-700 dark:text-sky-300",
  query_plan: "text-violet-700 dark:text-violet-300",
  settings: "text-slate-600 dark:text-slate-300",
  folder_filter: "text-teal-700 dark:text-teal-300",
  keyword_recall: "text-blue-700 dark:text-blue-300",
  concept_recall: "text-indigo-700 dark:text-indigo-300",
  people_visual_recall: "text-fuchsia-700 dark:text-fuchsia-300",
  vector_recall: "text-purple-700 dark:text-purple-300",
  rrf_merge: "text-orange-700 dark:text-orange-300",
  result: "text-green-700 dark:text-green-300",
};

function TraceStepRow({ step }: { step: SearchTraceStep }) {
  const [open, setOpen] = useState(true);
  const { stage, ...rest } = step;
  const label = STAGE_LABELS[stage] ?? stage;
  const color = STAGE_COLORS[stage] ?? "text-stone-600";
  const hasDetails = Object.keys(rest).length > 0;

  // Render a compact summary line from the step's key fields
  const summary = (() => {
    if (stage === "input") return `query="${rest.query}" mode=${rest.mode} page=${rest.page}/${rest.page_size}`;
    if (stage === "query_plan") {
      const exact = (rest.exact_terms as string[])?.join(", ") || "—";
      const expanded = (rest.expanded_terms as string[])?.join(", ") || "—";
      const broad = (rest.broad_terms as string[])?.join(", ") || "—";
      return `intent=${rest.intent}  精确:[${exact}]  近义:[${expanded}]  宽泛:[${broad}]`;
    }
    if (stage === "settings") return `mode=${rest.default_mode}  kw_k=${rest.keyword_top_k}  vec_k=${rest.vector_top_k}  rrf_k=${rest.rrf_k}  kw_w=${rest.keyword_weight}  vec_w=${rest.vector_weight}`;
    if (stage === "folder_filter") return `folder_id=${rest.folder_id}  scope=${rest.scope}  photos=${rest.photo_ids_count ?? "?"}`;
    if (stage === "keyword_recall") return `candidates=${rest.candidates}  top=[${(rest.top_scores as number[])?.join(", ")}]`;
    if (stage === "concept_recall") return `concepts=[${(rest.concept_terms as string[])?.join(", ") || ""}] candidates=${rest.candidates}`;
    if (stage === "people_visual_recall") return `candidates=${rest.candidates}  top=[${(rest.top_scores as number[])?.join(", ") || ""}]`;
    if (stage === "vector_recall") {
      if (rest.error) return `⚠ FALLBACK: ${rest.error}`;
      return `candidates=${rest.candidates}  model=${rest.embedding_model}  is_ocr=${rest.is_ocr}`;
    }
    if (stage === "rrf_merge") return `kw=${rest.kw_candidates}  vec=${rest.vec_candidates}  merged=${rest.merged}  top=[${(rest.top_final_scores as number[])?.join(", ")}]`;
    if (stage === "result") return `path=${rest.path}  total=${rest.total}  page=${rest.page}  items=${rest.items_in_page}`;
    return JSON.stringify(rest);
  })();

  return (
    <div className="border-b border-amber-200/40 dark:border-amber-700/30 last:border-0 py-1">
      <button
        className="flex items-start gap-1.5 w-full text-left"
        onClick={() => hasDetails && setOpen((v) => !v)}
      >
        {hasDetails ? (
          open ? <ChevronDown className="w-3 h-3 mt-0.5 shrink-0 opacity-50" /> : <ChevronRight className="w-3 h-3 mt-0.5 shrink-0 opacity-50" />
        ) : (
          <span className="w-3 h-3 shrink-0" />
        )}
        <span className={`font-semibold ${color} w-28 shrink-0`}>{label}</span>
        <span className="opacity-75 break-all">{summary}</span>
        {(rest as { error?: string }).error && (
          <span className="ml-1 text-red-500">⚠</span>
        )}
      </button>
      {open && hasDetails && (
        <div className="ml-6 mt-0.5 grid grid-cols-[auto_1fr] gap-x-2 gap-y-0.5 text-[10px] text-amber-800/80 dark:text-amber-300/70">
          {Object.entries(rest).map(([k, v]) => (
            <><span key={`k-${k}`} className="opacity-60 text-right whitespace-nowrap">{k}:</span>
            <span key={`v-${k}`} className="break-all font-mono">
              {Array.isArray(v) ? (v as unknown[]).join(", ") || "—" : String(v ?? "—")}
            </span></>
          ))}
        </div>
      )}
    </div>
  );
}

function DebugPanel({ payload }: { payload: SearchDebugPayload }) {
  const [showSettings, setShowSettings] = useState(false);
  const [showTrace, setShowTrace] = useState(true);
  const queryPlan = payload.query_plan ?? {};

  return (
    <div className="rounded-md border border-amber-400/50 bg-amber-50 dark:bg-amber-950/30 p-3 text-[11px] font-mono space-y-1.5 text-amber-900 dark:text-amber-200">
      <div className="font-semibold text-xs mb-1.5">🔍 Search Debug</div>

      <div className="rounded border border-amber-300/50 bg-white/60 dark:bg-black/20 px-2 py-1 text-[10px] space-y-0.5">
        <div>query_plan.intent: {String(queryPlan.intent ?? payload.intent ?? "")}</div>
        <div>query_plan.exact_terms: {(queryPlan.exact_terms ?? payload.exact_terms ?? []).join(", ") || "—"}</div>
        <div>query_plan.expanded_terms: {(queryPlan.expanded_terms ?? payload.expanded_terms ?? []).join(", ") || "—"}</div>
        <div>query_plan.semantic_query_text: {String(queryPlan.semantic_query_text ?? payload.semantic_query_text ?? "") || "—"}</div>
        <div>keyword_candidates: {payload.keyword_candidates}</div>
        <div>vector_candidates: {payload.vector_candidates}</div>
        <div>merged_candidates: {payload.merged_candidates}</div>
        <div>filtered_candidates: {payload.filtered_candidates ?? 0}</div>
        <div>filtered_out_samples: {(payload.filtered_out_samples ?? []).map((it) => `${it.photo_id}:${it.filter_reason}`).join(" | ") || "—"}</div>
        <div>stale_embedding_filtered: {payload.stale_embedding_filtered ?? 0}</div>
        <div>metadata_filter_active: {String(payload.metadata_filter_active ?? false)}</div>
        <div>metadata_filter_skipped_reason: {payload.metadata_filter_skipped_reason ?? "—"}</div>
        <div>metadata_only_allowed: {String(payload.metadata_only_allowed ?? true)}</div>
        <div>concept_terms: {(payload.concept_terms ?? []).join(", ") || "—"}</div>
        <div>concept_entity_terms: {(payload.concept_entity_terms ?? []).join(", ") || "—"}</div>
      </div>

      {/* Summary row */}
      <div className="flex flex-wrap gap-x-4 gap-y-0.5">
        <span><span className="opacity-60">意图:</span> {payload.intent}</span>
        <span><span className="opacity-60">模式:</span> {payload.mode}</span>
        <span><span className="opacity-60">关键词候选:</span> {payload.keyword_candidates}</span>
        <span><span className="opacity-60">概念候选:</span> {payload.concept_candidates ?? 0}</span>
        <span><span className="opacity-60">人像结构候选:</span> {payload.people_visual_candidates ?? 0}</span>
        <span><span className="opacity-60">向量候选:</span> {payload.vector_candidates}</span>
        <span><span className="opacity-60">合并后:</span> {payload.merged_candidates}</span>
        {payload.embedding_model && (
          <span><span className="opacity-60">模型:</span> {payload.embedding_model} ({payload.embedding_dimension}d)</span>
        )}
      </div>

      {/* Terms row */}
      <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-[10px]">
        <span><span className="opacity-60">原始:</span> {payload.original_query}</span>
        <span><span className="opacity-60">规范化:</span> {payload.normalized_query}</span>
        {payload.semantic_query_text && (
          <span><span className="opacity-60">语义查询:</span> {payload.semantic_query_text}</span>
        )}
        {(payload.exact_terms?.length ?? 0) > 0 && (
          <span className="text-blue-700 dark:text-blue-300"><span className="opacity-60">精确词:</span> {payload.exact_terms!.join(", ")}</span>
        )}
        {(payload.expanded_terms?.length ?? 0) > 0 && (
          <span className="text-violet-700 dark:text-violet-300"><span className="opacity-60">近义词:</span> {payload.expanded_terms.join(", ")}</span>
        )}
        {(payload.broad_terms?.length ?? 0) > 0 && (
          <span className="text-stone-600 dark:text-stone-400"><span className="opacity-60">宽泛词:</span> {payload.broad_terms!.join(", ")}</span>
        )}
        {payload.recommended_profile && (
          <span><span className="opacity-60">权重方案:</span> {payload.recommended_profile}</span>
        )}
      </div>

      {payload.fallback_reason && (
        <div className="text-red-600 dark:text-red-400">
          ⚠ Fallback: {payload.fallback_reason}
        </div>
      )}

      {/* Metadata filters section */}
      {payload.metadata_filters && Object.keys(payload.metadata_filters).length > 0 && (
        <div className="rounded border border-teal-400/50 bg-teal-50 dark:bg-teal-950/30 px-2 py-1 text-[10px] text-teal-800 dark:text-teal-200 space-y-0.5">
          <div className="font-semibold text-[11px]">
            🗓 元数据过滤{payload.metadata_only ? " (仅元数据)" : " (混合)"} — 匹配 {payload.metadata_candidates ?? 0} 张
          </div>
          {(payload.matched_metadata_terms?.length ?? 0) > 0 && (
            <div><span className="opacity-60">识别词:</span> {payload.matched_metadata_terms!.join("、")}</div>
          )}
          <div className="flex flex-wrap gap-x-3 gap-y-0">
            {!!payload.metadata_filters.date_from && (
              <span><span className="opacity-60">日期:</span> {String(payload.metadata_filters.date_from)} ~ {String(payload.metadata_filters.date_to ?? "")}</span>
            )}
            {!payload.metadata_filters.date_from && !!payload.metadata_filters.year && (
              <span><span className="opacity-60">年份:</span> {String(payload.metadata_filters.year)}</span>
            )}
            {!payload.metadata_filters.date_from && !!payload.metadata_filters.month && (
              <span><span className="opacity-60">月份:</span> {String(payload.metadata_filters.month)}月</span>
            )}
            {((payload.metadata_filters.months as number[] | undefined)?.length ?? 0) > 0 && (
              <span><span className="opacity-60">季节月份:</span> {(payload.metadata_filters.months as number[]).join("、")}月</span>
            )}
            {payload.metadata_filters.has_gps != null && (
              <span><span className="opacity-60">GPS:</span> {payload.metadata_filters.has_gps ? "有" : "无"}</span>
            )}
            {!!payload.metadata_filters.camera_make && (
              <span><span className="opacity-60">相机品牌:</span> {String(payload.metadata_filters.camera_make)}</span>
            )}
            {!!payload.metadata_filters.camera_model && (
              <span><span className="opacity-60">相机型号:</span> {String(payload.metadata_filters.camera_model)}</span>
            )}
            {payload.metadata_filters.iso_min != null && (
              <span><span className="opacity-60">ISO:</span> {String(payload.metadata_filters.iso_min)}{payload.metadata_filters.iso_max !== payload.metadata_filters.iso_min ? `~${String(payload.metadata_filters.iso_max)}` : ""}</span>
            )}
            {((payload.metadata_filters.place_terms as string[] | undefined)?.length ?? 0) > 0 && (
              <span><span className="opacity-60">地点:</span> {(payload.metadata_filters.place_terms as string[]).join("、")}</span>
            )}
          </div>
        </div>
      )}

      {payload.concept_debug && (
        <div className="rounded border border-cyan-400/50 bg-cyan-50 dark:bg-cyan-950/30 px-2 py-1 text-[10px] text-cyan-900 dark:text-cyan-200 space-y-0.5">
          <div className="font-semibold text-[11px]">🧠 Concept Recall</div>
          <div><span className="opacity-60">enabled:</span> {String(payload.concept_debug.enabled)}</div>
          <div><span className="opacity-60">reason:</span> {payload.concept_debug.reason}</div>
          <div><span className="opacity-60">concept_terms:</span> {payload.concept_debug.concept_terms.join("、") || "—"}</div>
          <div><span className="opacity-60">concept_facets:</span> {(payload.concept_debug.concept_facets ?? []).join("、") || "—"}</div>
          <div><span className="opacity-60">entity_terms:</span> {payload.concept_debug.entity_terms.join("、") || "—"}</div>
          <div><span className="opacity-60">candidates:</span> {payload.concept_debug.candidates}</div>
          <div><span className="opacity-60">top_scores:</span> {(payload.concept_debug.top_scores ?? []).join("、") || "—"}</div>
        </div>
      )}

      {/* Pipeline trace */}
      {(payload.trace?.length ?? 0) > 0 && (
        <div className="mt-1.5">
          <button
            className="flex items-center gap-1 text-[10px] opacity-70 hover:opacity-100 mb-1"
            onClick={() => setShowTrace((v) => !v)}
          >
            {showTrace ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
            <span className="font-semibold">搜索流水线 ({payload.trace!.length} 步)</span>
          </button>
          {showTrace && (
            <div className="border border-amber-300/40 dark:border-amber-700/40 rounded px-2 py-1 space-y-0 text-[10px]">
              {payload.trace!.map((step, i) => (
                <TraceStepRow key={i} step={step} />
              ))}
            </div>
          )}
        </div>
      )}

      {/* Settings snapshot */}
      {payload.settings_snapshot && (
        <div className="mt-1">
          <button
            className="flex items-center gap-1 text-[10px] opacity-70 hover:opacity-100"
            onClick={() => setShowSettings((v) => !v)}
          >
            {showSettings ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
            <span>设置快照</span>
          </button>
          {showSettings && (
            <div className="mt-1 space-y-0.5 text-[10px] pl-4 border-l border-amber-400/30">
              <div>mode:{payload.settings_snapshot.default_mode} kw_k:{payload.settings_snapshot.keyword_top_k} vec_k:{payload.settings_snapshot.vector_top_k} rrf_k:{payload.settings_snapshot.rrf_k}</div>
              <div>kw_w:{payload.settings_snapshot.keyword_weight} vec_w:{payload.settings_snapshot.vector_weight} min_score:{payload.settings_snapshot.vector_min_score}</div>
              <div>vec_fields: {Object.entries(payload.settings_snapshot.vector_field_weights ?? {}).map(([k,v]) => `${k.replace('_embedding','')}:${(v as number).toFixed(2)}`).join(" ")}</div>
              <div>kw_fields: {Object.entries(payload.settings_snapshot.keyword_field_weights ?? {}).map(([k,v]) => `${k}:${(v as number).toFixed(1)}`).join(" ")}</div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Export helper ─────────────────────────────────────────────────────────────
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

export function SearchResultGrid({ query, projectId, mode = "hybrid", debug = false, tagField, tagValue }: SearchResultGridProps) {
  const {
    data,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
    isLoading,
    isError,
    error,
  } = useSearch(query, projectId ?? null, { mode, debug, tagField, tagValue });

  const [previewItem, setPreviewItem] = useState<SearchResultItem | null>(null);
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
      <div className="space-y-4">
        {debug && debugPayload && <DebugPanel payload={debugPayload} />}
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
      {debug && debugPayload && <DebugPanel payload={debugPayload} />}

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

      <div className="masonry-grid">
        {allItems.map((item) => (
          <SearchCard
            key={item.photo_id}
            item={item}
            debug={debug}
            projectId={projectId}
            onPreview={setPreviewItem}
          />
        ))}
      </div>

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
