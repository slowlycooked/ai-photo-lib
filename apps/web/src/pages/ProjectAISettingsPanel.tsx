import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, Bot, Check, Clipboard, FlaskConical, Loader2, RefreshCw, RotateCcw, Save, Settings, Sparkles, Trash2 } from "lucide-react";
import {
  api,
  type Photo,
  type ProjectAISettingsUpdate,
  type ProjectEmbeddingSettingsUpdate,
  type PromptTemplate,
  type PromptTemplateTestResponse,
} from "@/api";
import ProjectSearchSettingsPanel from "./ProjectSearchSettingsPanel";

interface ModelForm {
  provider: string;
  endpoint_url: string;
  model_name: string;
  temperature: number;
  top_p: number;
  max_tokens: number;
  retry_count: number;
  output_language: string;
  json_parse_strategy: string;
}

interface PromptTestHistoryItem {
  id: string;
  project_id: number;
  image_id: number;
  file_name: string;
  template_id: number | null;
  template_version: number | null;
  tested_at: string;
  result: PromptTemplateTestResponse;
}

const DEFAULT_MODEL_FORM: ModelForm = {
  provider: "llama-server",
  endpoint_url: "",
  model_name: "",
  temperature: 0,
  top_p: 0.8,
  max_tokens: 1024,
  retry_count: 1,
  output_language: "中文",
  json_parse_strategy: "auto_extract",
};

const BASIC_FOCUS_DEFAULT = [
  "场景",
  "人物",
  "建筑",
  "地点线索",
  "OCR文字",
  "照片质量",
  "搜索关键词",
].join("\n");

const TEST_HISTORY_MAX = 12;

function buildPromptFromBasic(focus: string, extra: string) {
  const lines = focus
    .split(/\r?\n/)
    .map((x) => x.trim())
    .filter(Boolean);
  const bullets = lines.length ? lines.map((x) => `- ${x}`).join("\n") : "- 场景\n- 人物\n- 搜索关键词";
  const extraBlock = extra.trim() ? `\n\n额外要求：\n${extra.trim()}` : "";

  return `请重点分析以下内容：\n${bullets}${extraBlock}\n\n可使用上下文变量辅助判断：\n- 文件名：{{ filename }}\n- 文件夹路径：{{ folder_path }}\n- 拍摄时间：{{ taken_at }}\n- EXIF：{{ exif_json }}\n- GPS：{{ gps_text }}\n\n请确保字段完整，无法判断时给出低 confidence。`;
}

function parsePromptToBasic(prompt: string): { focus: string; extra: string } {
  const extraMatch = prompt.match(/额外要求：\s*([\s\S]*)$/);
  const extra = extraMatch ? extraMatch[1].trim() : "";

  const focusLines = prompt
    .split(/\r?\n/)
    .filter((line) => line.trim().startsWith("- "))
    .map((line) => line.replace(/^\s*-\s*/, "").trim())
    .filter(Boolean);

  return {
    focus: focusLines.length ? focusLines.join("\n") : BASIC_FOCUS_DEFAULT,
    extra,
  };
}

function toSettingsBody(form: ModelForm, activePromptTemplateId?: number | null): ProjectAISettingsUpdate {
  return {
    provider: form.provider,
    endpoint_url: form.endpoint_url,
    model_name: form.model_name,
    temperature: Number(form.temperature),
    top_p: Number(form.top_p),
    max_tokens: Number(form.max_tokens),
    retry_count: Number(form.retry_count),
    output_language: form.output_language,
    json_parse_strategy: form.json_parse_strategy,
    active_prompt_template_id: activePromptTemplateId,
  };
}

function copyText(text: string, onDone: (msg: string) => void) {
  navigator.clipboard
    .writeText(text)
    .then(() => onDone("已复制到剪贴板"))
    .catch(() => onDone("复制失败，请检查浏览器权限"));
}

function SettingsCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="bg-canvas border border-hairline rounded-md">
      <div className="px-5 py-3 border-b border-hairline">
        <h2 className="text-body-sm font-semibold text-ink">{title}</h2>
      </div>
      <div className="px-5 py-4 space-y-3">{children}</div>
    </section>
  );
}

function Label({ children }: { children: React.ReactNode }) {
  return <label className="block text-caption-sm text-mute mb-1">{children}</label>;
}

// ─── Embedding Settings Section ───────────────────────────────────────────────

function EmbeddingSettingsSection({ projectId }: { projectId: number }) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<ProjectEmbeddingSettingsUpdate>({});
  const [testResult, setTestResult] = useState<{
    success: boolean; model_name: string; embedding_dimension: number;
    sample: number[]; duration_ms: number; error: string | null;
  } | null>(null);
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

  // Reset on project change
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
    mutationFn: () =>
      api.projects.testEmbeddingSettings(projectId, {
        text: "test embedding connection",
      }),
    onSuccess: (data) => setTestResult(data),
    onError: (e) => setTestResult({ success: false, model_name: "", embedding_dimension: 0, sample: [], duration_ms: 0, error: (e as Error).message }),
  });

  const rebuildMut = useMutation({
    mutationFn: (scope: "all" | "stale" | "failed" | "missing") =>
      api.projects.rebuildEmbeddings(projectId, { scope }),
    onSuccess: (data, scope) => {
      setRebuildMsg(`已入队 ${data.created_jobs} 个任务 (${scope})`);
      queryClient.invalidateQueries({ queryKey: ["project-embedding-status", projectId] });
    },
    onError: (e) => setRebuildMsg(`失败: ${(e as Error).message}`),
  });

  if (isLoading) return null;

  return (
    <SettingsCard title="Embedding 语义向量配置">
      {/* Provider / endpoint / model */}
      <div className="grid grid-cols-2 gap-3">
        <div>
          <Label>Endpoint URL</Label>
          <input
            className="input-base w-full"
            value={form.endpoint_url ?? ""}
            onChange={(e) => setForm((f) => ({ ...f, endpoint_url: e.target.value }))}
            placeholder="http://embedding-server/v1"
          />
        </div>
        <div>
          <Label>Model Name</Label>
          <input
            className="input-base w-full"
            value={form.model_name ?? ""}
            onChange={(e) => setForm((f) => ({ ...f, model_name: e.target.value }))}
            placeholder="Qwen3-Embedding-0.6B"
          />
        </div>
        <div>
          <Label>API Key (可留空)</Label>
          <input
            type="password"
            className="input-base w-full"
            value={form.api_key ?? ""}
            onChange={(e) => setForm((f) => ({ ...f, api_key: e.target.value || null }))}
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
            onChange={(e) => setForm((f) => ({ ...f, embedding_dimension: Number(e.target.value) }))}
          />
        </div>
        <div>
          <Label>Query Prefix</Label>
          <input
            className="input-base w-full"
            value={form.input_prefix_query ?? ""}
            onChange={(e) => setForm((f) => ({ ...f, input_prefix_query: e.target.value }))}
            placeholder="Represent this search query for retrieving relevant photo descriptions"
          />
        </div>
        <div>
          <Label>Document Prefix</Label>
          <input
            className="input-base w-full"
            value={form.input_prefix_document ?? ""}
            onChange={(e) => setForm((f) => ({ ...f, input_prefix_document: e.target.value }))}
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
          {saveMut.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
          保存配置
        </button>
        <button
          onClick={() => testMut.mutate()}
          disabled={testMut.isPending}
          className="btn-secondary flex items-center gap-1.5 text-sm"
        >
          {testMut.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <FlaskConical className="w-3.5 h-3.5" />}
          测试 Embedding
        </button>
      </div>

      {testResult && (
        <div className={`rounded-md p-2 text-sm ${testResult.success ? "bg-green-50 text-green-800" : "bg-red-50 text-red-800"}`}>
          {testResult.success
            ? `✓ 连接成功 · ${testResult.model_name} · ${testResult.embedding_dimension}d · ${testResult.duration_ms}ms`
            : `✗ ${testResult.error}`}
        </div>
      )}

      {/* Status */}
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

        {rebuildMsg && (
          <p className="text-body-sm text-green-700">{rebuildMsg}</p>
        )}

        <div className="flex gap-2 flex-wrap pt-1">
          <button onClick={() => rebuildMut.mutate("missing")} disabled={rebuildMut.isPending}
            className="btn-secondary text-xs flex items-center gap-1">
            <RotateCcw className="w-3 h-3" /> 重建缺失
          </button>
          <button onClick={() => rebuildMut.mutate("failed")} disabled={rebuildMut.isPending}
            className="btn-secondary text-xs flex items-center gap-1">
            <RotateCcw className="w-3 h-3" /> 重建失败
          </button>
          <button onClick={() => rebuildMut.mutate("stale")} disabled={rebuildMut.isPending}
            className="btn-secondary text-xs flex items-center gap-1">
            <RotateCcw className="w-3 h-3" /> 重建过期
          </button>
          <button onClick={() => rebuildMut.mutate("all")} disabled={rebuildMut.isPending}
            className="btn-secondary text-xs text-danger flex items-center gap-1">
            <RefreshCw className="w-3 h-3" /> 强制全量重建
          </button>
        </div>
      </div>

      {/* Vector search weights */}
      <div className="border-t border-hairline pt-3 space-y-3">
        <div>
          <h3 className="text-body-sm font-semibold text-ink">语义检索权重</h3>
          <p className="text-caption-sm text-mute mt-0.5">
            控制向量搜索时不同字段的贡献比例，系统会按总和自动归一化。默认推荐：综合内容 0.50，标签 0.25，描述 0.20，OCR 0.05。
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
                setForm((f) => ({ ...f, search_content_vector_weight: Number(e.target.value) }))
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
                setForm((f) => ({ ...f, search_tag_vector_weight: Number(e.target.value) }))
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
                setForm((f) => ({ ...f, search_caption_vector_weight: Number(e.target.value) }))
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
                setForm((f) => ({ ...f, search_ocr_vector_weight: Number(e.target.value) }))
              }
            />
          </div>
        </div>
        <p className="text-caption-sm text-mute">
          提示：搜索"猫"容易召回无关结果时，可适当提高标签权重；搜索发票、订单号、门牌号时，可提高 OCR 权重。
        </p>
        <button
          onClick={() => saveMut.mutate(form)}
          disabled={saveMut.isPending}
          className="btn-primary flex items-center gap-1.5 text-sm"
        >
          {saveMut.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
          保存权重
        </button>
        {rebuildMsg && (
          <p className="text-body-sm text-green-700">{rebuildMsg}</p>
        )}
      </div>
    </SettingsCard>
  );
}


export function ProjectAISettingsPanel({ projectId }: { projectId: number }) {
  const queryClient = useQueryClient();

  const [message, setMessage] = useState<string | null>(null);
  const [modelForm, setModelForm] = useState<ModelForm>(DEFAULT_MODEL_FORM);

  const [selectedTemplateId, setSelectedTemplateId] = useState<number | null>(null);
  const [templateName, setTemplateName] = useState("图片分析模板");
  const [advancedMode, setAdvancedMode] = useState(false);
  const [basicFocus, setBasicFocus] = useState(BASIC_FOCUS_DEFAULT);
  const [basicExtra, setBasicExtra] = useState("");
  const [advancedPrompt, setAdvancedPrompt] = useState("");

  const [testPhotoId, setTestPhotoId] = useState<number | null>(null);
  const [testResult, setTestResult] = useState<PromptTemplateTestResponse | null>(null);
  const [testHistory, setTestHistory] = useState<PromptTestHistoryItem[]>([]);

  // Prevent prompt/template state from leaking across projects.
  useEffect(() => {
    setSelectedTemplateId(null);
    setTemplateName("图片分析模板");
    setAdvancedMode(false);
    setBasicFocus(BASIC_FOCUS_DEFAULT);
    setBasicExtra("");
    setAdvancedPrompt("");
    setTestPhotoId(null);
    setTestResult(null);
  }, [projectId]);

  const { data: settingsData, isLoading: settingsLoading } = useQuery({
    queryKey: ["project-ai-settings", projectId],
    queryFn: () => api.projects.getAiSettings(projectId),
    staleTime: 30_000,
  });

  const { data: templatesData, isLoading: templatesLoading } = useQuery({
    queryKey: ["project-prompt-templates", projectId],
    queryFn: () => api.projects.promptTemplates(projectId),
    staleTime: 15_000,
  });

  const {
    data: photosData,
    error: photosError,
    isError: photosIsError,
  } = useQuery({
    queryKey: ["project-test-photos", projectId],
    queryFn: () => api.projects.photos(projectId, 1, 100),
    staleTime: 30_000,
  });

  const { data: failedJobsData } = useQuery({
    queryKey: ["project-ai-failed-jobs-latest", projectId],
    queryFn: () => api.projects.aiJobs(projectId, "failed", 10),
    staleTime: 10_000,
  });

  useEffect(() => {
    if (!settingsData) return;
    setModelForm({
      provider: settingsData.provider,
      endpoint_url: settingsData.endpoint_url,
      model_name: settingsData.model_name,
      temperature: settingsData.temperature,
      top_p: settingsData.top_p,
      max_tokens: settingsData.max_tokens,
      retry_count: settingsData.retry_count,
      output_language: settingsData.output_language,
      json_parse_strategy: settingsData.json_parse_strategy,
    });
  }, [settingsData]);

  const templates = templatesData?.items ?? [];

  useEffect(() => {
    const key = `ai-photo-lib:prompt-test-history:${projectId}`;
    const raw = localStorage.getItem(key);
    if (!raw) {
      setTestHistory([]);
      return;
    }
    try {
      const parsed = JSON.parse(raw) as PromptTestHistoryItem[];
      if (!Array.isArray(parsed)) {
        setTestHistory([]);
        return;
      }
      setTestHistory(parsed.slice(0, TEST_HISTORY_MAX));
    } catch {
      setTestHistory([]);
    }
  }, [projectId]);

  useEffect(() => {
    if (!templates.length) {
      setSelectedTemplateId(null);
      return;
    }

    const active = templates.find((t) => t.is_active) ?? templates[0];
    const current = selectedTemplateId
      ? templates.find((t) => t.id === selectedTemplateId)
      : null;
    const resolved = current ?? active;

    setSelectedTemplateId(resolved.id);
    setTemplateName(resolved.name);
    setAdvancedPrompt(resolved.user_prompt);

    const basic = parsePromptToBasic(resolved.user_prompt);
    setBasicFocus(basic.focus);
    setBasicExtra(basic.extra);
  }, [templates, selectedTemplateId]);

  const currentTemplate = useMemo(
    () => templates.find((t) => t.id === selectedTemplateId) ?? null,
    [templates, selectedTemplateId]
  );

  const generatedPrompt = useMemo(
    () => buildPromptFromBasic(basicFocus, basicExtra),
    [basicFocus, basicExtra]
  );

  const effectivePrompt = advancedMode ? advancedPrompt : generatedPrompt;

  const saveSettingsMutation = useMutation({
    mutationFn: (body: ProjectAISettingsUpdate) =>
      api.projects.updateAiSettings(projectId, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["project-ai-settings", projectId] });
      setMessage("模型服务配置已保存");
    },
    onError: (err: Error) => setMessage(`保存失败：${err.message}`),
  });

  const savePromptMutation = useMutation({
    mutationFn: () => {
      if (!currentTemplate) {
        return api.projects.createPromptTemplate(projectId, {
          name: templateName.trim() || "图片分析模板",
          task_type: "image_analysis",
          user_prompt: effectivePrompt,
          is_active: true,
        });
      }
      return api.projects.updatePromptTemplate(projectId, currentTemplate.id, {
        name: templateName.trim() || currentTemplate.name,
        user_prompt: effectivePrompt,
        is_active: true,
      });
    },
    onSuccess: (newTemplate: PromptTemplate) => {
      setSelectedTemplateId(newTemplate.id);
      queryClient.invalidateQueries({ queryKey: ["project-prompt-templates", projectId] });
      queryClient.invalidateQueries({ queryKey: ["project-ai-settings", projectId] });
      setMessage(`Prompt 已保存为新版本 v${newTemplate.version}`);
    },
    onError: (err: Error) => setMessage(`保存 Prompt 失败：${err.message}`),
  });

  const activateTemplateMutation = useMutation({
    mutationFn: (templateId: number) =>
      api.projects.updateAiSettings(
        projectId,
        toSettingsBody(modelForm, templateId)
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["project-ai-settings", projectId] });
      queryClient.invalidateQueries({ queryKey: ["project-prompt-templates", projectId] });
      setMessage("已设为启用模板");
    },
    onError: (err: Error) => setMessage(`设为启用失败：${err.message}`),
  });

  const resetPromptMutation = useMutation({
    mutationFn: () => api.projects.resetDefaultPromptTemplate(projectId),
    onSuccess: (template) => {
      setSelectedTemplateId(template.id);
      queryClient.invalidateQueries({ queryKey: ["project-prompt-templates", projectId] });
      queryClient.invalidateQueries({ queryKey: ["project-ai-settings", projectId] });
      setMessage("已恢复默认 Prompt 并激活新版本");
    },
    onError: (err: Error) => setMessage(`恢复默认失败：${err.message}`),
  });

  const deletePromptMutation = useMutation({
    mutationFn: (templateId: number) => api.projects.deletePromptTemplate(projectId, templateId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["project-prompt-templates", projectId] });
      queryClient.invalidateQueries({ queryKey: ["project-ai-settings", projectId] });
      setMessage("模板已删除");
    },
    onError: (err: Error) => setMessage(`删除模板失败：${err.message}`),
  });

  const testPromptMutation = useMutation({
    mutationFn: () =>
      api.projects.testPromptTemplate(projectId, {
        image_id: testPhotoId!,
        prompt_template_id: currentTemplate?.id,
        override_prompt: effectivePrompt,
      }),
    onSuccess: (res) => {
      setTestResult(res);
      const selectedPhoto = testPhotos.find((p) => p.id === testPhotoId);
      if (selectedPhoto && testPhotoId != null) {
        const item: PromptTestHistoryItem = {
          id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
          project_id: projectId,
          image_id: testPhotoId,
          file_name: selectedPhoto.file_name,
          template_id: currentTemplate?.id ?? null,
          template_version: currentTemplate?.version ?? null,
          tested_at: new Date().toISOString(),
          result: res,
        };
        const next = [item, ...testHistory].slice(0, TEST_HISTORY_MAX);
        setTestHistory(next);
        localStorage.setItem(`ai-photo-lib:prompt-test-history:${projectId}`, JSON.stringify(next));
      }
      setMessage(res.success ? "Prompt 测试成功" : "Prompt 测试返回解析失败");
    },
    onError: (err: Error) => {
      setMessage(`Prompt 测试失败：${err.message}`);
    },
  });

  const testPhotos: Photo[] = photosData?.items ?? [];
  const latestFailed = failedJobsData?.items ?? [];

  const clearTestHistory = () => {
    setTestHistory([]);
    localStorage.removeItem(`ai-photo-lib:prompt-test-history:${projectId}`);
    setMessage("已清空测试历史");
  };

  const loadHistoryResult = (item: PromptTestHistoryItem) => {
    setTestPhotoId(item.image_id);
    setTestResult(item.result);
    const template = templates.find((t) => t.id === item.template_id);
    if (template) {
      setSelectedTemplateId(template.id);
      setTemplateName(template.name);
      setAdvancedPrompt(template.user_prompt);
      const basic = parsePromptToBasic(template.user_prompt);
      setBasicFocus(basic.focus);
      setBasicExtra(basic.extra);
    }
    setMessage(`已载入测试历史：${item.file_name}`);
  };

  return (
    <div className="space-y-6">
      {message && (
        <div className="bg-secondary-bg border border-hairline rounded-md px-4 py-2.5 text-body-sm text-ink">
          {message}
        </div>
      )}

      <SettingsCard title="1. 模型服务配置">
        {settingsLoading ? (
          <div className="flex items-center gap-2 text-mute"><Loader2 className="w-4 h-4 animate-spin" />加载中…</div>
        ) : (
          <>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div className="md:col-span-2">
                <Label>模型服务地址</Label>
                <input
                  value={modelForm.endpoint_url}
                  onChange={(e) => setModelForm((x) => ({ ...x, endpoint_url: e.target.value }))}
                  className="w-full px-3 py-2 text-body-sm bg-surface-card border border-hairline rounded-md"
                />
              </div>
              <div>
                <Label>模型名称</Label>
                <input
                  value={modelForm.model_name}
                  onChange={(e) => setModelForm((x) => ({ ...x, model_name: e.target.value }))}
                  className="w-full px-3 py-2 text-body-sm bg-surface-card border border-hairline rounded-md"
                />
              </div>
              <div>
                <Label>provider</Label>
                <input
                  value={modelForm.provider}
                  onChange={(e) => setModelForm((x) => ({ ...x, provider: e.target.value }))}
                  className="w-full px-3 py-2 text-body-sm bg-surface-card border border-hairline rounded-md"
                />
              </div>
              <div>
                <Label>temperature</Label>
                <input
                  type="number"
                  step="0.1"
                  value={modelForm.temperature}
                  onChange={(e) => setModelForm((x) => ({ ...x, temperature: Number(e.target.value) }))}
                  className="w-full px-3 py-2 text-body-sm bg-surface-card border border-hairline rounded-md"
                />
              </div>
              <div>
                <Label>top_p</Label>
                <input
                  type="number"
                  step="0.1"
                  value={modelForm.top_p}
                  onChange={(e) => setModelForm((x) => ({ ...x, top_p: Number(e.target.value) }))}
                  className="w-full px-3 py-2 text-body-sm bg-surface-card border border-hairline rounded-md"
                />
              </div>
              <div>
                <Label>max_tokens</Label>
                <input
                  type="number"
                  value={modelForm.max_tokens}
                  onChange={(e) => setModelForm((x) => ({ ...x, max_tokens: Number(e.target.value) }))}
                  className="w-full px-3 py-2 text-body-sm bg-surface-card border border-hairline rounded-md"
                />
              </div>
              <div>
                <Label>失败重试次数</Label>
                <input
                  type="number"
                  value={modelForm.retry_count}
                  onChange={(e) => setModelForm((x) => ({ ...x, retry_count: Number(e.target.value) }))}
                  className="w-full px-3 py-2 text-body-sm bg-surface-card border border-hairline rounded-md"
                />
              </div>
              <div>
                <Label>输出语言</Label>
                <input
                  value={modelForm.output_language}
                  onChange={(e) => setModelForm((x) => ({ ...x, output_language: e.target.value }))}
                  className="w-full px-3 py-2 text-body-sm bg-surface-card border border-hairline rounded-md"
                />
              </div>
              <div>
                <Label>JSON 解析策略</Label>
                <select
                  value={modelForm.json_parse_strategy}
                  onChange={(e) => setModelForm((x) => ({ ...x, json_parse_strategy: e.target.value }))}
                  className="w-full px-3 py-2 text-body-sm bg-surface-card border border-hairline rounded-md"
                >
                  <option value="auto_extract">auto_extract（推荐）</option>
                  <option value="strip_markdown">strip_markdown</option>
                  <option value="strict_json">strict_json</option>
                </select>
              </div>
            </div>
            <div className="pt-1">
              <button
                onClick={() =>
                  saveSettingsMutation.mutate(
                    toSettingsBody(modelForm, settingsData?.active_prompt_template_id)
                  )
                }
                disabled={saveSettingsMutation.isPending}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-primary text-white text-btn-sm font-bold disabled:bg-stone"
              >
                {saveSettingsMutation.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
                保存模型配置
              </button>
            </div>
          </>
        )}
      </SettingsCard>

      <SettingsCard title="2. Prompt 模板与版本管理">
        {templatesLoading ? (
          <div className="flex items-center gap-2 text-mute"><Loader2 className="w-4 h-4 animate-spin" />加载中…</div>
        ) : (
          <>
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
              <div className="space-y-2 lg:col-span-1">
                <Label>当前模板版本</Label>
                <div className="max-h-72 overflow-y-auto border border-hairline rounded-md divide-y divide-hairline">
                  {templates.map((template) => (
                    <button
                      key={template.id}
                      onClick={() => setSelectedTemplateId(template.id)}
                      className={[
                        "w-full px-3 py-2 text-left text-body-sm",
                        selectedTemplateId === template.id ? "bg-secondary-bg" : "hover:bg-surface-card",
                      ].join(" ")}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-medium text-ink truncate">v{template.version} · {template.name}</span>
                        {template.is_active && <span className="text-caption-sm text-primary">启用中</span>}
                      </div>
                    </button>
                  ))}
                </div>
              </div>

              <div className="space-y-3 lg:col-span-2">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <div>
                    <Label>模板名称</Label>
                    <input
                      value={templateName}
                      onChange={(e) => setTemplateName(e.target.value)}
                      className="w-full px-3 py-2 text-body-sm bg-surface-card border border-hairline rounded-md"
                    />
                  </div>
                  <div>
                    <Label>编辑模式</Label>
                    <div className="flex gap-2">
                      <button
                        onClick={() => setAdvancedMode(false)}
                        className={[
                          "px-3 py-1.5 rounded-md text-btn-sm border",
                          !advancedMode ? "bg-secondary-bg border-primary text-primary" : "border-hairline",
                        ].join(" ")}
                      >
                        基础模式
                      </button>
                      <button
                        onClick={() => setAdvancedMode(true)}
                        className={[
                          "px-3 py-1.5 rounded-md text-btn-sm border",
                          advancedMode ? "bg-secondary-bg border-primary text-primary" : "border-hairline",
                        ].join(" ")}
                      >
                        高级模式
                      </button>
                    </div>
                  </div>
                </div>

                {!advancedMode ? (
                  <div className="space-y-3">
                    <div>
                      <Label>分析重点（每行一项）</Label>
                      <textarea
                        value={basicFocus}
                        onChange={(e) => setBasicFocus(e.target.value)}
                        rows={6}
                        className="w-full px-3 py-2 text-body-sm bg-surface-card border border-hairline rounded-md"
                      />
                    </div>
                    <div>
                      <Label>额外要求</Label>
                      <textarea
                        value={basicExtra}
                        onChange={(e) => setBasicExtra(e.target.value)}
                        rows={3}
                        placeholder="例如：优先识别旅行、户外、家庭聚会、城市地标。"
                        className="w-full px-3 py-2 text-body-sm bg-surface-card border border-hairline rounded-md"
                      />
                    </div>
                    <div>
                      <Label>生成后的 Prompt 预览</Label>
                      <pre className="max-h-52 overflow-auto text-caption-sm bg-surface-soft border border-hairline rounded-md px-3 py-2 whitespace-pre-wrap break-all">
                        {generatedPrompt}
                      </pre>
                    </div>
                  </div>
                ) : (
                  <div>
                    <Label>完整 Prompt（高级模式）</Label>
                    <div className="mb-2 text-caption-sm text-amber-600 flex items-center gap-1">
                      <AlertCircle className="w-3.5 h-3.5" />
                      高级模式可能导致模型输出无法解析，仅建议用于调试。
                    </div>
                    <textarea
                      value={advancedPrompt}
                      onChange={(e) => setAdvancedPrompt(e.target.value)}
                      rows={14}
                      className="w-full px-3 py-2 text-body-sm bg-surface-card border border-hairline rounded-md font-mono"
                    />
                  </div>
                )}

                <div className="flex flex-wrap gap-2">
                  <button
                    onClick={() => savePromptMutation.mutate()}
                    disabled={savePromptMutation.isPending}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-primary text-white text-btn-sm font-bold disabled:bg-stone"
                  >
                    {savePromptMutation.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
                    保存为新版本
                  </button>
                  <button
                    onClick={() => currentTemplate && activateTemplateMutation.mutate(currentTemplate.id)}
                    disabled={!currentTemplate || activateTemplateMutation.isPending}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-hairline text-btn-sm hover:bg-surface-card disabled:opacity-50"
                  >
                    <Check className="w-3.5 h-3.5" />
                    设为启用
                  </button>
                  <button
                    onClick={() => resetPromptMutation.mutate()}
                    disabled={resetPromptMutation.isPending}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-hairline text-btn-sm hover:bg-surface-card disabled:opacity-50"
                  >
                    <RotateCcw className="w-3.5 h-3.5" />
                    恢复默认
                  </button>
                  <button
                    onClick={() => {
                      if (!currentTemplate) return;
                      if (!window.confirm(`确认删除模板「v${currentTemplate.version} · ${currentTemplate.name}」？`)) {
                        return;
                      }
                      deletePromptMutation.mutate(currentTemplate.id);
                    }}
                    disabled={!currentTemplate || currentTemplate.is_active || deletePromptMutation.isPending}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-danger text-danger text-btn-sm hover:bg-danger/5 disabled:opacity-50"
                    title={currentTemplate?.is_active ? "启用中的模板不能删除，请先切换到其他模板" : "删除当前模板"}
                  >
                    {deletePromptMutation.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}
                    删除模板
                  </button>
                  <button
                    onClick={() => copyText(effectivePrompt, setMessage)}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-hairline text-btn-sm hover:bg-surface-card"
                  >
                    <Clipboard className="w-3.5 h-3.5" />
                    复制当前 Prompt
                  </button>
                </div>
              </div>
            </div>
          </>
        )}
      </SettingsCard>

      <SettingsCard title="3. Prompt 测试区">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          <div>
            <Label>选择测试图片</Label>
            <select
              value={testPhotoId ?? ""}
              onChange={(e) => setTestPhotoId(e.target.value ? Number(e.target.value) : null)}
              className="w-full px-3 py-2 text-body-sm bg-surface-card border border-hairline rounded-md"
            >
              <option value="">请选择图片</option>
              {testPhotos.map((photo) => (
                <option key={photo.id} value={photo.id}>
                  #{photo.id} · {photo.file_name}
                </option>
              ))}
            </select>
            {photosIsError ? (
              <p className="text-caption-sm text-danger mt-1">
                测试图片加载失败：{photosError instanceof Error ? photosError.message : "未知错误"}
              </p>
            ) : testPhotos.length === 0 ? (
              <p className="text-caption-sm text-mute mt-1">
                当前项目暂无可测试图片，请先在任务中心扫描该项目照片库。
              </p>
            ) : null}
          </div>

          <div className="flex items-end gap-2">
            <button
              onClick={() => testPromptMutation.mutate()}
              disabled={testPromptMutation.isPending || !testPhotoId}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-primary text-white text-btn-sm font-bold disabled:bg-stone"
            >
              {testPromptMutation.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <FlaskConical className="w-3.5 h-3.5" />}
              测试当前 Prompt
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
          <div className="border border-hairline rounded-md p-3 bg-surface-soft">
            <p className="text-caption-sm text-mute mb-2 flex items-center gap-1"><Bot className="w-3.5 h-3.5" />模型原始输出</p>
            <pre className="max-h-64 overflow-auto text-caption-sm whitespace-pre-wrap break-all">
              {testResult?.raw_output || "(暂无)"}
            </pre>
          </div>
          <div className="border border-hairline rounded-md p-3 bg-surface-soft">
            <p className="text-caption-sm text-mute mb-2 flex items-center gap-1"><Sparkles className="w-3.5 h-3.5" />JSON 解析结果</p>
            <pre className="max-h-64 overflow-auto text-caption-sm whitespace-pre-wrap break-all">
              {testResult?.parsed_json ? JSON.stringify(testResult.parsed_json, null, 2) : "(暂无)"}
            </pre>
          </div>
          <div className="border border-hairline rounded-md p-3 bg-surface-soft">
            <p className="text-caption-sm text-mute mb-2">校验状态</p>
            {testResult ? (
              <div className="space-y-2 text-body-sm">
                <p className={testResult.success ? "text-green-700" : "text-amber-700"}>
                  {testResult.success ? "解析成功" : "解析失败"}
                </p>
                <p className="text-mute">耗时：{testResult.duration_ms} ms</p>
                {!testResult.success && (
                  <p className="text-danger whitespace-pre-wrap break-all">{testResult.error}</p>
                )}
              </div>
            ) : (
              <p className="text-body-sm text-mute">(暂无)</p>
            )}
          </div>
        </div>

        <div className="pt-2 border-t border-hairline">
          <div className="flex items-center justify-between gap-2 mb-2">
            <h3 className="text-body-sm font-semibold text-ink">最近测试历史</h3>
            <button
              onClick={clearTestHistory}
              disabled={testHistory.length === 0}
              className="text-caption-sm text-danger hover:text-danger-pressed disabled:text-stone"
            >
              清空历史
            </button>
          </div>
          {testHistory.length === 0 ? (
            <p className="text-caption-sm text-mute mb-3">暂无测试历史</p>
          ) : (
            <div className="space-y-2 mb-3">
              {testHistory.map((item) => (
                <details key={item.id} className="bg-surface-soft border border-hairline rounded-md px-3 py-2">
                  <summary className="cursor-pointer text-body-sm text-ink flex items-center justify-between gap-2">
                    <span>
                      {new Date(item.tested_at).toLocaleString()} · {item.file_name}
                    </span>
                    <span className={item.result.success ? "text-green-700 text-caption-sm" : "text-amber-700 text-caption-sm"}>
                      {item.result.success ? "解析成功" : "解析失败"}
                    </span>
                  </summary>
                  <div className="mt-2 space-y-2">
                    <p className="text-caption-sm text-mute">
                      image #{item.image_id} · template v{item.template_version ?? "-"} · {item.result.duration_ms}ms
                    </p>
                    <div className="flex gap-2">
                      <button
                        onClick={() => loadHistoryResult(item)}
                        className="text-caption-sm text-primary hover:text-primary-pressed"
                      >
                        载入结果
                      </button>
                      <button
                        onClick={() => copyText(item.result.raw_output, setMessage)}
                        className="text-caption-sm text-primary hover:text-primary-pressed"
                      >
                        复制原始输出
                      </button>
                    </div>
                    {item.result.error && (
                      <p className="text-caption-sm text-danger whitespace-pre-wrap break-all">{item.result.error}</p>
                    )}
                  </div>
                </details>
              ))}
            </div>
          )}

          <h3 className="text-body-sm font-semibold text-ink mb-2">最近失败输出</h3>
          {latestFailed.length === 0 ? (
            <p className="text-caption-sm text-mute">暂无失败任务记录</p>
          ) : (
            <div className="space-y-2">
              {latestFailed.slice(0, 3).map((job) => (
                <details key={job.id} className="bg-surface-soft border border-hairline rounded-md px-3 py-2">
                  <summary className="cursor-pointer text-body-sm text-ink">
                    #{job.id} · {job.file_name ?? `photo:${job.photo_id}`} · prompt v{job.prompt_version ?? "-"}
                  </summary>
                  <div className="mt-2 space-y-2">
                    <div>
                      <p className="text-caption-sm text-mute">parse_error</p>
                      <pre className="text-caption-sm whitespace-pre-wrap break-all">{job.parse_error || "(空)"}</pre>
                    </div>
                    <div>
                      <p className="text-caption-sm text-mute">raw_model_output</p>
                      <pre className="max-h-40 overflow-auto text-caption-sm whitespace-pre-wrap break-all">{job.raw_model_output || "(空)"}</pre>
                    </div>
                  </div>
                </details>
              ))}
            </div>
          )}
        </div>
      </SettingsCard>

      {/* Embedding Settings Section */}
      <EmbeddingSettingsSection projectId={projectId} />

      {/* Search Settings Section */}
      <SettingsCard title="搜索参数设置">
        <ProjectSearchSettingsPanel projectId={projectId} />
      </SettingsCard>
    </div>
  );
}
