import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, Check, Loader2, RotateCcw, Save, Settings } from "lucide-react";
import { api, type ProjectSearchSettings, type ProjectSearchSettingsUpdate } from "@/lib/api";

interface Props {
  projectId: number;
}

const KEYWORD_FIELD_LABELS: Record<string, string> = {
  caption: "描述 (caption)",
  ocr_text: "OCR 文字",
  scene_tags: "场景标签",
  object_tags: "物体标签",
  activity_tags: "活动标签",
  search_keywords: "搜索关键词",
  quality_tags: "质量标签",
  location_clues: "地点线索",
  file_name: "文件名",
};

const VECTOR_FIELD_LABELS: Record<string, string> = {
  content_embedding: "内容向量 (content)",
  tag_embedding: "标签向量 (tag)",
  caption_embedding: "描述向量 (caption)",
  ocr_embedding: "OCR 向量",
};

function WeightsEditor({
  label,
  weights,
  fieldLabels,
  onChange,
}: {
  label: string;
  weights: Record<string, number> | null;
  fieldLabels: Record<string, string>;
  onChange: (w: Record<string, number>) => void;
}) {
  const current = weights ?? {};
  return (
    <div className="mb-4">
      <p className="text-sm font-medium text-gray-700 mb-2">{label}</p>
      <div className="grid grid-cols-2 gap-2">
        {Object.keys(fieldLabels).map((field) => (
          <label key={field} className="flex items-center gap-2 text-xs">
            <span className="w-40 text-gray-600">{fieldLabels[field]}</span>
            <input
              type="number"
              step="0.1"
              min="0"
              className="w-20 border rounded px-1 py-0.5 text-xs"
              value={current[field] ?? 0}
              onChange={(e) =>
                onChange({ ...current, [field]: parseFloat(e.target.value) || 0 })
              }
            />
          </label>
        ))}
      </div>
    </div>
  );
}

export default function ProjectSearchSettingsPanel({ projectId }: Props) {
  const queryClient = useQueryClient();

  const { data: settings, isLoading, error } = useQuery({
    queryKey: ["project-search-settings", projectId],
    queryFn: () => api.projects.getSearchSettings(projectId),
  });

  const [form, setForm] = useState<Partial<ProjectSearchSettingsUpdate>>({});
  const [saved, setSaved] = useState(false);

  const effective = { ...(settings ?? {}), ...form } as ProjectSearchSettings;

  const updateMutation = useMutation({
    mutationFn: (body: ProjectSearchSettingsUpdate) =>
      api.projects.updateSearchSettings(projectId, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["project-search-settings", projectId] });
      setForm({});
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    },
  });

  const resetMutation = useMutation({
    mutationFn: () => api.projects.resetSearchSettings(projectId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["project-search-settings", projectId] });
      setForm({});
    },
  });

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 text-gray-500 p-4">
        <Loader2 className="animate-spin w-4 h-4" />
        <span>加载搜索设置...</span>
      </div>
    );
  }

  if (error || !settings) {
    return (
      <div className="flex items-center gap-2 text-red-500 p-4">
        <AlertCircle className="w-4 h-4" />
        <span>加载搜索设置失败</span>
      </div>
    );
  }

  function setField<K extends keyof ProjectSearchSettingsUpdate>(
    key: K,
    value: ProjectSearchSettingsUpdate[K],
  ) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  function handleSave() {
    if (Object.keys(form).length > 0) {
      updateMutation.mutate(form);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Settings className="w-4 h-4 text-gray-600" />
          <h3 className="font-medium text-gray-800">搜索参数配置</h3>
        </div>
        <div className="flex gap-2">
          <button
            className="flex items-center gap-1 text-xs text-gray-500 border rounded px-2 py-1 hover:bg-gray-50"
            onClick={() => resetMutation.mutate()}
            disabled={resetMutation.isPending}
          >
            {resetMutation.isPending ? (
              <Loader2 className="w-3 h-3 animate-spin" />
            ) : (
              <RotateCcw className="w-3 h-3" />
            )}
            重置为默认
          </button>
          <button
            className="flex items-center gap-1 text-xs text-white bg-blue-600 rounded px-2 py-1 hover:bg-blue-700 disabled:opacity-50"
            onClick={handleSave}
            disabled={updateMutation.isPending || Object.keys(form).length === 0}
          >
            {updateMutation.isPending ? (
              <Loader2 className="w-3 h-3 animate-spin" />
            ) : saved ? (
              <Check className="w-3 h-3" />
            ) : (
              <Save className="w-3 h-3" />
            )}
            {saved ? "已保存" : "保存"}
          </button>
        </div>
      </div>

      {/* A. Search mode & recall sizing */}
      <section>
        <h4 className="text-sm font-semibold text-gray-700 mb-3 border-b pb-1">
          A. 搜索模式与召回量
        </h4>
        <div className="grid grid-cols-2 gap-4">
          <label className="flex flex-col gap-1 text-xs">
            <span className="text-gray-600">默认搜索模式</span>
            <select
              className="border rounded px-2 py-1 text-xs"
              value={effective.default_mode ?? "hybrid"}
              onChange={(e) => setField("default_mode", e.target.value)}
            >
              <option value="hybrid">混合 (hybrid)</option>
              <option value="keyword">关键词 (keyword)</option>
              <option value="vector">向量 (vector)</option>
              <option value="auto">自动 (auto)</option>
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs">
            <span className="text-gray-600">关键词召回量 keyword_top_k</span>
            <input
              type="number"
              className="border rounded px-2 py-1 text-xs"
              value={effective.keyword_top_k ?? 2000}
              onChange={(e) => setField("keyword_top_k", parseInt(e.target.value) || 2000)}
            />
          </label>
          <label className="flex flex-col gap-1 text-xs">
            <span className="text-gray-600">向量召回量 vector_top_k</span>
            <input
              type="number"
              className="border rounded px-2 py-1 text-xs"
              value={effective.vector_top_k ?? 200}
              onChange={(e) => setField("vector_top_k", parseInt(e.target.value) || 200)}
            />
          </label>
          <label className="flex flex-col gap-1 text-xs">
            <span className="text-gray-600">每页默认数量 page_size_default</span>
            <input
              type="number"
              className="border rounded px-2 py-1 text-xs"
              value={effective.page_size_default ?? 50}
              onChange={(e) => setField("page_size_default", parseInt(e.target.value) || 50)}
            />
          </label>
        </div>
      </section>

      {/* B. RRF fusion */}
      <section>
        <h4 className="text-sm font-semibold text-gray-700 mb-3 border-b pb-1">
          B. 混合融合参数 (RRF)
        </h4>
        <div className="grid grid-cols-2 gap-4">
          {(
            [
              { key: "rrf_k", label: "RRF K 常数", step: 1, min: 1 },
              {
                key: "keyword_weight",
                label: "关键词权重 keyword_weight",
                step: 0.05,
                min: 0,
              },
              {
                key: "vector_weight",
                label: "向量权重 vector_weight",
                step: 0.05,
                min: 0,
              },
              {
                key: "vector_min_score",
                label: "向量最小分 vector_min_score",
                step: 0.01,
                min: 0,
              },
            ] as const
          ).map(({ key, label, step, min }) => (
            <label key={key} className="flex flex-col gap-1 text-xs">
              <span className="text-gray-600">{label}</span>
              <input
                type="number"
                step={step}
                min={min}
                className="border rounded px-2 py-1 text-xs"
                value={(effective as Record<string, number | undefined>)[key] ?? 0}
                onChange={(e) =>
                  setField(
                    key,
                    key === "rrf_k" ? parseInt(e.target.value) : parseFloat(e.target.value),
                  )
                }
              />
            </label>
          ))}
        </div>
      </section>

      {/* C. Vector field weights (normal) */}
      <section>
        <h4 className="text-sm font-semibold text-gray-700 mb-3 border-b pb-1">
          C. 向量字段权重（普通查询）
        </h4>
        <WeightsEditor
          label="各向量字段权重（将自动归一化）"
          weights={effective.vector_field_weights ?? null}
          fieldLabels={VECTOR_FIELD_LABELS}
          onChange={(w) => setField("vector_field_weights", w)}
        />
      </section>

      {/* D. OCR vector field weights */}
      <section>
        <h4 className="text-sm font-semibold text-gray-700 mb-3 border-b pb-1">
          D. 向量字段权重（OCR / 号码查询）
        </h4>
        <WeightsEditor
          label="OCR 类查询的向量字段权重"
          weights={effective.ocr_query_vector_field_weights ?? null}
          fieldLabels={VECTOR_FIELD_LABELS}
          onChange={(w) => setField("ocr_query_vector_field_weights", w)}
        />
      </section>

      {/* E. Keyword field weights */}
      <section>
        <h4 className="text-sm font-semibold text-gray-700 mb-3 border-b pb-1">
          E. 关键词字段权重
        </h4>
        <WeightsEditor
          label="各文本字段的关键词匹配权重"
          weights={effective.keyword_field_weights ?? null}
          fieldLabels={KEYWORD_FIELD_LABELS}
          onChange={(w) => setField("keyword_field_weights", w)}
        />
      </section>

      {/* F. Feature flags */}
      <section>
        <h4 className="text-sm font-semibold text-gray-700 mb-3 border-b pb-1">
          F. 功能开关
        </h4>
        <div className="space-y-2">
          {(
            [
              {
                key: "enable_query_understanding" as const,
                label: "启用查询理解 (三层词扩展)",
              },
              {
                key: "enable_structured_filters" as const,
                label: "启用结构化过滤条件 (实验性)",
              },
              {
                key: "enable_semantic_tag_boost" as const,
                label: "启用语义标签加权 (实验性)",
              },
            ]
          ).map(({ key, label }) => (
            <label key={key} className="flex items-center gap-2 text-xs cursor-pointer">
              <input
                type="checkbox"
                checked={(effective as Record<string, boolean | undefined>)[key] ?? false}
                onChange={(e) => setField(key, e.target.checked)}
              />
              <span className="text-gray-700">{label}</span>
            </label>
          ))}
        </div>
      </section>

      {updateMutation.isError && (
        <p className="text-xs text-red-500 flex items-center gap-1">
          <AlertCircle className="w-3 h-3" />
          保存失败，请重试
        </p>
      )}

      {/* G. Search quality settings */}
      <section>
        <h4 className="text-sm font-semibold text-gray-700 mb-3 border-b pb-1">
          G. 搜索质量控制
        </h4>
        <div className="grid grid-cols-2 gap-4">
          <label className="flex flex-col gap-1 text-xs">
            <span className="text-gray-600">向量严格阈值 vector_strict_score (0–1)</span>
            <input
              type="number"
              step="0.01"
              min="0"
              max="1"
              className="border rounded px-2 py-1 text-xs"
              value={(effective.search_quality_settings?.["vector_strict_score"] as number) ?? 0.42}
              onChange={(e) =>
                setField("search_quality_settings", {
                  ...(effective.search_quality_settings ?? {}),
                  vector_strict_score: parseFloat(e.target.value) || 0,
                })
              }
            />
          </label>
          <label className="flex flex-col gap-1 text-xs">
            <span className="text-gray-600">最低展示证据等级 min_display_evidence_level</span>
            <select
              className="border rounded px-2 py-1 text-xs"
              value={(effective.search_quality_settings?.["min_display_evidence_level"] as string) ?? "C"}
              onChange={(e) =>
                setField("search_quality_settings", {
                  ...(effective.search_quality_settings ?? {}),
                  min_display_evidence_level: e.target.value,
                })
              }
            >
              <option value="A">A — 仅精确匹配</option>
              <option value="B">B — 精确 + 强扩展</option>
              <option value="C">C — 含向量严格匹配 (推荐)</option>
              <option value="D">D — 弱证据也展示</option>
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs">
            <span className="text-gray-600">证据权重 evidence_weight</span>
            <input
              type="number"
              step="0.001"
              min="0"
              className="border rounded px-2 py-1 text-xs"
              value={(effective.search_quality_settings?.["evidence_weight"] as number) ?? 0.02}
              onChange={(e) =>
                setField("search_quality_settings", {
                  ...(effective.search_quality_settings ?? {}),
                  evidence_weight: parseFloat(e.target.value) || 0,
                })
              }
            />
          </label>
          <label className="flex flex-col gap-1 text-xs">
            <span className="text-gray-600">负向词惩罚 negative_term_penalty</span>
            <input
              type="number"
              step="0.001"
              min="0"
              className="border rounded px-2 py-1 text-xs"
              value={(effective.search_quality_settings?.["negative_term_penalty"] as number) ?? 0.01}
              onChange={(e) =>
                setField("search_quality_settings", {
                  ...(effective.search_quality_settings ?? {}),
                  negative_term_penalty: parseFloat(e.target.value) || 0,
                })
              }
            />
          </label>
        </div>
        <div className="mt-3 space-y-2">
          {(
            [
              { key: "enable_evidence_filter", label: "启用证据等级过滤" },
              { key: "enable_negative_penalty", label: "启用负向词惩罚" },
              { key: "require_core_facet_match", label: "强制核心意图证据匹配 (夜景/天气等)" },
              { key: "allow_vector_only_for_facet_query", label: "高置信向量可绕过核心意图证据门槛" },
            ] as { key: string; label: string }[]
          ).map(({ key, label }) => (
            <label key={key} className="flex items-center gap-2 text-xs cursor-pointer">
              <input
                type="checkbox"
                checked={(effective.search_quality_settings?.[key] as boolean | undefined) ?? (key === "allow_vector_only_for_facet_query" ? true : key === "enable_evidence_filter" || key === "enable_negative_penalty")}
                onChange={(e) =>
                  setField("search_quality_settings", {
                    ...(effective.search_quality_settings ?? {}),
                    [key]: e.target.checked,
                  })
                }
              />
              <span className="text-gray-700">{label}</span>
            </label>
          ))}
        </div>
      </section>
    </div>
  );
}
