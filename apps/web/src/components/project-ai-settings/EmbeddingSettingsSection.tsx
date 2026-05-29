import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FlaskConical, Loader2, RefreshCw, RotateCcw, Save } from "lucide-react";

import { api, type EmbeddingTestResponse, type ProjectEmbeddingSettingsUpdate } from "@/api";
import { CapabilityMaturityBadge } from "@/components/common/CapabilityMaturityBadge";
import { ConfigTestResult } from "@/components/settings/ConfigTestResult";
import { CAPABILITY_MATURITY } from "@/lib/capabilityMaturity";
import { Label, SettingsCard } from "./SettingsPrimitives";

export function EmbeddingSettingsSection({ projectId }: { projectId: number }) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<ProjectEmbeddingSettingsUpdate>({});
  const [testText, setTestText] = useState("test embedding connection");
  const [testResult, setTestResult] = useState<EmbeddingTestResponse | null>(null);
  const [rebuildMsg, setRebuildMsg] = useState<string | null>(null);

  const { data: settings, isLoading } = useQuery({
    queryKey: ["project-embedding-settings", projectId],
    queryFn: () => api.projects.getEmbeddingSettings(projectId),
    staleTime: 30_000,
  });

  const { data: status, isLoading: statusLoading, refetch: refetchStatus } = useQuery({
    queryKey: ["project-embedding-status", projectId],
    queryFn: () => api.projects.getEmbeddingStatus(projectId),
    staleTime: 15_000,
  });

  useEffect(() => {
    if (!settings) return;
    setForm({
      provider: settings.provider,
      endpoint_url: settings.endpoint_url,
      model_name: settings.model_name,
      embedding_dimension: settings.embedding_dimension,
      batch_size: settings.batch_size,
      timeout_seconds: settings.timeout_seconds,
      input_prefix_query: settings.input_prefix_query,
      input_prefix_document: settings.input_prefix_document,
      enabled: settings.enabled,
      search_content_vector_weight: settings.search_content_vector_weight,
      search_tag_vector_weight: settings.search_tag_vector_weight,
      search_caption_vector_weight: settings.search_caption_vector_weight,
      search_ocr_vector_weight: settings.search_ocr_vector_weight,
    });
  }, [settings]);

  useEffect(() => {
    setTestResult(null);
    setRebuildMsg(null);
    setForm({});
  }, [projectId]);

  const saveMut = useMutation({
    mutationFn: (body: ProjectEmbeddingSettingsUpdate) =>
      api.projects.updateEmbeddingSettings(projectId, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["project-embedding-settings", projectId] });
      setRebuildMsg("保存成功");
      setTimeout(() => setRebuildMsg(null), 2000);
    },
  });

  const testMut = useMutation({
    mutationFn: (text: string) =>
      api.projects.testEmbeddingSettings(projectId, {
        text,
      }),
    onSuccess: (data) => setTestResult(data),
    onError: (error) =>
      setTestResult({
        success: false,
        model_name: "",
        embedding_dimension: 0,
        sample: [],
        duration_ms: 0,
        error: (error as Error).message,
      }),
  });

  const rebuildMut = useMutation({
    mutationFn: (scope: "all" | "stale" | "failed" | "missing") =>
      api.projects.rebuildEmbeddings(projectId, { scope }),
    onSuccess: (data, scope) => {
      setRebuildMsg(`已入队 ${data.created_jobs} 个任务 (${scope})`);
      queryClient.invalidateQueries({ queryKey: ["project-embedding-status", projectId] });
    },
    onError: (error) => setRebuildMsg(`失败: ${(error as Error).message}`),
  });

  if (isLoading) return null;

  const statusSummary = status
    ? [
        { label: "READY", value: String(status.ready) },
        { label: "MISSING", value: String(status.missing) },
        { label: "STALE", value: String(status.stale) },
        { label: "FAILED", value: String(status.failed) },
      ]
    : [];

  return (
    <SettingsCard
      title={
        <span className="flex flex-wrap items-center gap-2">
          <span>Embedding 语义向量配置</span>
          <CapabilityMaturityBadge item={CAPABILITY_MATURITY.embedding_rebuild} />
        </span>
      }
    >
      <div className="grid grid-cols-1 md:grid-cols-3 gap-2 mb-4">
        <div className="rounded border border-hairline bg-surface-soft px-3 py-2">
          <p className="text-caption-sm text-mute">Enabled</p>
          <p className="text-body-sm text-ink">{form.enabled === false ? "No" : "Yes"}</p>
        </div>
        <div className="rounded border border-hairline bg-surface-soft px-3 py-2">
          <p className="text-caption-sm text-mute">Provider</p>
          <p className="text-body-sm text-ink break-all">{form.provider ?? "-"}</p>
        </div>
        <div className="rounded border border-hairline bg-surface-soft px-3 py-2">
          <p className="text-caption-sm text-mute">Model / Dimension</p>
          <p className="text-body-sm text-ink break-all">
            {form.model_name ?? "-"} / {form.embedding_dimension ?? "-"}
          </p>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <Label>Endpoint URL</Label>
          <input
            className="input-base w-full"
            value={form.endpoint_url ?? ""}
            onChange={(e) => setForm((current) => ({ ...current, endpoint_url: e.target.value }))}
            placeholder="http://embedding-server/v1"
          />
        </div>
        <div>
          <Label>Model Name</Label>
          <input
            className="input-base w-full"
            value={form.model_name ?? ""}
            onChange={(e) => setForm((current) => ({ ...current, model_name: e.target.value }))}
            placeholder="Qwen3-Embedding-0.6B"
          />
        </div>
        <div>
          <Label>API Key (可留空)</Label>
          <input
            type="password"
            className="input-base w-full"
            value={form.api_key ?? ""}
            onChange={(e) =>
              setForm((current) => ({ ...current, api_key: e.target.value || null }))
            }
            placeholder="sk-..."
            autoComplete="off"
          />
        </div>
        <div>
          <Label>Dimension</Label>
          <input
            type="number"
            className="input-base w-full"
            value={form.embedding_dimension ?? ""}
            onChange={(e) =>
              setForm((current) => ({
                ...current,
                embedding_dimension: Number(e.target.value),
              }))
            }
          />
        </div>
        <div>
          <Label>Query Prefix</Label>
          <input
            className="input-base w-full"
            value={form.input_prefix_query ?? ""}
            onChange={(e) =>
              setForm((current) => ({ ...current, input_prefix_query: e.target.value }))
            }
            placeholder="Represent this search query for retrieving relevant photo descriptions"
          />
        </div>
        <div>
          <Label>Document Prefix</Label>
          <input
            className="input-base w-full"
            value={form.input_prefix_document ?? ""}
            onChange={(e) =>
              setForm((current) => ({ ...current, input_prefix_document: e.target.value }))
            }
            placeholder="Represent this photo description for retrieval"
          />
        </div>
      </div>

      <div className="flex gap-2 flex-wrap pt-1">
        <button
          onClick={() => saveMut.mutate(form)}
          disabled={saveMut.isPending}
          className="btn-primary flex items-center gap-1.5 text-sm"
        >
          {saveMut.isPending ? (
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
          ) : (
            <Save className="w-3.5 h-3.5" />
          )}
          保存配置
        </button>
      </div>

        <div>
          <Label>测试文本</Label>
          <div className="flex gap-2">
            <input
              className="input-base w-full"
              value={testText}
              onChange={(e) => setTestText(e.target.value)}
              placeholder="例如：去年 1 月 iPhone 拍的照片"
            />
            <button
              onClick={() => testMut.mutate(testText.trim())}
              disabled={testMut.isPending || !testText.trim()}
              className="btn-secondary flex items-center gap-1.5 text-sm whitespace-nowrap"
            >
              {testMut.isPending ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <FlaskConical className="w-3.5 h-3.5" />
              )}
              运行测试
            </button>
          </div>
        </div>

        {testResult && (
          <ConfigTestResult
            title="Embedding 测试结果"
            success={testResult.success}
            latencyMs={testResult.duration_ms}
            model={testResult.model_name}
            errorMessage={testResult.error}
            copyPayload={{ text: testText.trim() }}
            summary={[
              { label: "Dimension", value: String(testResult.embedding_dimension) },
              { label: "Sample Length", value: String(testResult.sample?.length ?? 0) },
            ]}
            requestPayload={{ text: testText.trim() }}
            rawOutput={testResult.sample}
            parsedOutput={{
              success: testResult.success,
              model_name: testResult.model_name,
              embedding_dimension: testResult.embedding_dimension,
            }}
          />
        )}

      <div className="border-t border-hairline pt-3 space-y-2">
        <div className="flex items-center justify-between">
          <h3 className="text-body-sm font-semibold text-ink">向量状态</h3>
          <button
            onClick={() => refetchStatus()}
            className="text-caption-sm text-primary hover:text-primary-pressed flex items-center gap-1"
          >
            <RefreshCw className="w-3 h-3" />
            刷新
          </button>
        </div>
        {statusLoading ? (
          <Loader2 className="w-4 h-4 animate-spin text-stone" />
        ) : status ? (
          <div className="grid grid-cols-4 gap-2 text-center">
            {[
              { label: "就绪", value: status.ready, color: "text-green-700" },
              { label: "缺失", value: status.missing, color: "text-amber-700" },
              { label: "过期", value: status.stale, color: "text-orange-600" },
              { label: "失败", value: status.failed, color: "text-red-600" },
            ].map((item) => (
              <div key={item.label} className="rounded-md bg-surface-soft p-2">
                <div className={`text-heading-md font-bold ${item.color}`}>{item.value}</div>
                <div className="text-caption-sm text-mute">{item.label}</div>
              </div>
            ))}
          </div>
        ) : null}

        {rebuildMsg && <p className="text-body-sm text-green-700">{rebuildMsg}</p>}

        <p className="text-caption-sm text-mute">{CAPABILITY_MATURITY.embedding_rebuild.hint}</p>

        <div className="flex gap-2 flex-wrap pt-1">
          <button
            onClick={() => rebuildMut.mutate("missing")}
            disabled={rebuildMut.isPending}
            className="btn-secondary text-xs flex items-center gap-1"
          >
            <RotateCcw className="w-3 h-3" /> 重建缺失
          </button>
          <button
            onClick={() => rebuildMut.mutate("failed")}
            disabled={rebuildMut.isPending}
            className="btn-secondary text-xs flex items-center gap-1"
          >
            <RotateCcw className="w-3 h-3" /> 重建失败
          </button>
          <button
            onClick={() => rebuildMut.mutate("stale")}
            disabled={rebuildMut.isPending}
            className="btn-secondary text-xs flex items-center gap-1"
          >
            <RotateCcw className="w-3 h-3" /> 重建过期
          </button>
          <button
            onClick={() => rebuildMut.mutate("all")}
            disabled={rebuildMut.isPending}
            className="btn-secondary text-xs text-danger flex items-center gap-1"
          >
            <RefreshCw className="w-3 h-3" /> 强制全量重建
          </button>
        </div>
      </div>

      <div className="border-t border-hairline pt-3 space-y-3">
        <div>
          <h3 className="text-body-sm font-semibold text-ink">语义检索权重</h3>
          <p className="text-caption-sm text-mute mt-0.5">
            控制向量搜索时不同字段的贡献比例，系统会按总和自动归一化。默认推荐：综合内容 0.50，标签
            0.25，描述 0.20，OCR 0.05。
          </p>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div>
            <Label>综合内容</Label>
            <input
              type="number"
              step="0.01"
              min="0"
              className="input-base w-full"
              value={form.search_content_vector_weight ?? 0.5}
              onChange={(e) =>
                setForm((current) => ({
                  ...current,
                  search_content_vector_weight: Number(e.target.value),
                }))
              }
            />
          </div>
          <div>
            <Label>标签</Label>
            <input
              type="number"
              step="0.01"
              min="0"
              className="input-base w-full"
              value={form.search_tag_vector_weight ?? 0.25}
              onChange={(e) =>
                setForm((current) => ({
                  ...current,
                  search_tag_vector_weight: Number(e.target.value),
                }))
              }
            />
          </div>
          <div>
            <Label>描述</Label>
            <input
              type="number"
              step="0.01"
              min="0"
              className="input-base w-full"
              value={form.search_caption_vector_weight ?? 0.2}
              onChange={(e) =>
                setForm((current) => ({
                  ...current,
                  search_caption_vector_weight: Number(e.target.value),
                }))
              }
            />
          </div>
          <div>
            <Label>OCR 文本</Label>
            <input
              type="number"
              step="0.01"
              min="0"
              className="input-base w-full"
              value={form.search_ocr_vector_weight ?? 0.05}
              onChange={(e) =>
                setForm((current) => ({
                  ...current,
                  search_ocr_vector_weight: Number(e.target.value),
                }))
              }
            />
          </div>
        </div>
        <p className="text-caption-sm text-mute">
          提示：搜索&quot;猫&quot;容易召回无关结果时，可适当提高标签权重；搜索发票、订单号、门牌号时，可提高
          OCR 权重。
        </p>
        <button
          onClick={() => saveMut.mutate(form)}
          disabled={saveMut.isPending}
          className="btn-primary flex items-center gap-1.5 text-sm"
        >
          {saveMut.isPending ? (
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
          ) : (
            <Save className="w-3.5 h-3.5" />
          )}
          保存权重
        </button>
        {rebuildMsg && <p className="text-body-sm text-green-700">{rebuildMsg}</p>}
      </div>
    </SettingsCard>
  );
}
