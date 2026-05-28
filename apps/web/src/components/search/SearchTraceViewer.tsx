import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import type { SearchTraceStep } from "@/api/types";

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
        {(rest as { error?: string }).error && <span className="ml-1 text-red-500">⚠</span>}
      </button>
      {open && hasDetails && (
        <div className="ml-6 mt-0.5 grid grid-cols-[auto_1fr] gap-x-2 gap-y-0.5 text-[10px] text-amber-800/80 dark:text-amber-300/70">
          {Object.entries(rest).map(([k, v]) => (
            <>
              <span key={`k-${k}`} className="opacity-60 text-right whitespace-nowrap">{k}:</span>
              <span key={`v-${k}`} className="break-all font-mono">
                {Array.isArray(v) ? (v as unknown[]).join(", ") || "—" : String(v ?? "—")}
              </span>
            </>
          ))}
        </div>
      )}
    </div>
  );
}

interface SearchTraceViewerProps {
  trace: SearchTraceStep[];
}

export function SearchTraceViewer({ trace }: SearchTraceViewerProps) {
  const [showTrace, setShowTrace] = useState(true);

  if (trace.length === 0) {
    return null;
  }

  return (
    <div className="mt-1.5">
      <button
        className="flex items-center gap-1 text-[10px] opacity-70 hover:opacity-100 mb-1"
        onClick={() => setShowTrace((v) => !v)}
      >
        {showTrace ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
        <span className="font-semibold">搜索流水线 ({trace.length} 步)</span>
      </button>
      {showTrace && (
        <div className="border border-amber-300/40 dark:border-amber-700/40 rounded px-2 py-1 space-y-0 text-[10px]">
          {trace.map((step, i) => (
            <TraceStepRow key={i} step={step} />
          ))}
        </div>
      )}
    </div>
  );
}
