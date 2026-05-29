import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import type { SearchDebugPayload } from "@/api/types";
import { SearchTraceViewer } from "@/components/search/SearchTraceViewer";

interface SearchDebugPanelProps {
  payload: SearchDebugPayload;
}

export function SearchDebugPanel({ payload }: SearchDebugPanelProps) {
  const [showSettings, setShowSettings] = useState(false);
  const [copyStatus, setCopyStatus] = useState<"idle" | "copied" | "error">("idle");
  const queryPlan = payload.query_plan ?? {};
  const planner = (payload.query_planner ?? queryPlan.query_planner ?? {}) as Record<string, unknown>;

  const handleCopyAll = async () => {
    const content = JSON.stringify(payload, null, 2);
    try {
      if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(content);
      } else if (typeof document !== "undefined") {
        const textarea = document.createElement("textarea");
        textarea.value = content;
        textarea.style.position = "fixed";
        textarea.style.left = "-9999px";
        document.body.appendChild(textarea);
        textarea.focus();
        textarea.select();
        const ok = document.execCommand("copy");
        document.body.removeChild(textarea);
        if (!ok) {
          throw new Error("copy failed");
        }
      } else {
        throw new Error("clipboard unavailable");
      }
      setCopyStatus("copied");
    } catch {
      setCopyStatus("error");
    } finally {
      setTimeout(() => setCopyStatus("idle"), 1600);
    }
  };

  return (
    <div className="relative rounded-md border border-amber-400/50 bg-amber-50 dark:bg-amber-950/30 p-3 text-[11px] font-mono space-y-1.5 text-amber-900 dark:text-amber-200">
      <button
        type="button"
        className="absolute right-3 top-3 rounded border border-amber-400/70 bg-white/80 px-2 py-0.5 text-[10px] leading-none text-amber-900 hover:bg-white dark:bg-black/20 dark:text-amber-100 dark:hover:bg-black/30"
        onClick={handleCopyAll}
      >
        {copyStatus === "copied" ? "已复制" : copyStatus === "error" ? "复制失败" : "复制全部"}
      </button>

      <div className="font-semibold text-xs mb-1.5 pr-20">🔍 Search Debug</div>

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

      {Object.keys(planner).length > 0 && (
        <div className="rounded border border-indigo-400/50 bg-indigo-50 dark:bg-indigo-950/30 px-2 py-1 text-[10px] text-indigo-900 dark:text-indigo-200 space-y-0.5">
          <div className="font-semibold text-[11px]">🧭 Query Planner</div>
          <div><span className="opacity-70">provider:</span> {String(planner.provider ?? "—")}</div>
          <div><span className="opacity-70">model:</span> {String(planner.model ?? "—")}</div>
          <div><span className="opacity-70">planner_version:</span> {String(planner.planner_version ?? "—")}</div>
          <div><span className="opacity-70">latency_ms:</span> {String(planner.latency_ms ?? "—")}</div>
          <div><span className="opacity-70">used_fallback:</span> {String(planner.used_fallback ?? false)}</div>
          <div><span className="opacity-70">fallback_reason:</span> {String(planner.fallback_reason ?? "") || "—"}</div>
          <div><span className="opacity-70">parsed:</span> {String(planner.parsed ?? false)}</div>
          <div><span className="opacity-70">confidence:</span> {String(planner.confidence ?? "—")}</div>
          <div><span className="opacity-70">raw_output_preview:</span> {String(planner.raw_output_preview ?? "") || "—"}</div>
        </div>
      )}

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

      <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-[10px]">
        <span><span className="opacity-60">原始:</span> {payload.original_query}</span>
        <span><span className="opacity-60">规范化:</span> {payload.normalized_query}</span>
        {payload.semantic_query_text && (
          <span><span className="opacity-60">语义查询:</span> {payload.semantic_query_text}</span>
        )}
        {(payload.exact_terms?.length ?? 0) > 0 && (
          <span className="text-blue-700 dark:text-blue-300"><span className="opacity-60">精确词:</span> {payload.exact_terms.join(", ")}</span>
        )}
        {(payload.expanded_terms?.length ?? 0) > 0 && (
          <span className="text-violet-700 dark:text-violet-300"><span className="opacity-60">近义词:</span> {payload.expanded_terms.join(", ")}</span>
        )}
        {(payload.broad_terms?.length ?? 0) > 0 && (
          <span className="text-stone-600 dark:text-stone-400"><span className="opacity-60">宽泛词:</span> {payload.broad_terms.join(", ")}</span>
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

      {payload.metadata_filters && Object.keys(payload.metadata_filters).length > 0 && (
        <div className="rounded border border-teal-400/50 bg-teal-50 dark:bg-teal-950/30 px-2 py-1 text-[10px] text-teal-800 dark:text-teal-200 space-y-0.5">
          <div className="font-semibold text-[11px]">
            🗓 元数据过滤{payload.metadata_only ? " (仅元数据)" : " (混合)"} — 匹配 {payload.metadata_candidates ?? 0} 张
          </div>
          {(payload.matched_metadata_terms?.length ?? 0) > 0 && (
            <div><span className="opacity-60">识别词:</span> {(payload.matched_metadata_terms ?? []).join("、")}</div>
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

      <SearchTraceViewer trace={payload.trace ?? []} />

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
