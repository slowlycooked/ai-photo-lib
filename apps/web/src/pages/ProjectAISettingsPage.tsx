import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import { AlertCircle, Bot, Check, Clipboard, FlaskConical, Loader2, RotateCcw, Save, Settings2, Sparkles } from "lucide-react";
import {
  api,
  type Photo,
  type ProjectAISettingsUpdate,
  type PromptTemplate,
  type PromptTemplateTestResponse,
} from "@/lib/api";
import { useProjectContext } from "@/contexts/ProjectContext";

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

export function ProjectAISettingsPage() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { currentProjectId, currentProject } = useProjectContext();

  const routeProjectId = projectId ? Number(projectId) : NaN;
  const selectedProjectId = Number.isFinite(routeProjectId)
    ? routeProjectId
    : currentProjectId ?? null;

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
  }, [selectedProjectId]);

  const { data: settingsData, isLoading: settingsLoading } = useQuery({
    queryKey: ["project-ai-settings", selectedProjectId],
    queryFn: () => api.projects.getAiSettings(selectedProjectId!),
    enabled: selectedProjectId !== null,
    staleTime: 30_000,
  });

  const { data: templatesData, isLoading: templatesLoading } = useQuery({
    queryKey: ["project-prompt-templates", selectedProjectId],
    queryFn: () => api.projects.promptTemplates(selectedProjectId!),
    enabled: selectedProjectId !== null,
    staleTime: 15_000,
  });

  const { data: photosData } = useQuery({
    queryKey: ["project-test-photos", selectedProjectId],
    queryFn: () => api.projects.photos(selectedProjectId!, 1, 200),
    enabled: selectedProjectId !== null,
    staleTime: 30_000,
  });

  const { data: failedJobsData } = useQuery({
    queryKey: ["project-ai-failed-jobs-latest", selectedProjectId],
    queryFn: () => api.projects.aiJobs(selectedProjectId!, "failed", 10),
    enabled: selectedProjectId !== null,
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
    if (selectedProjectId == null) return;
    const key = `ai-photo-lib:prompt-test-history:${selectedProjectId}`;
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
  }, [selectedProjectId]);

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
      api.projects.updateAiSettings(selectedProjectId!, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["project-ai-settings", selectedProjectId] });
      setMessage("模型服务配置已保存");
    },
    onError: (err: Error) => setMessage(`保存失败：${err.message}`),
  });

  const savePromptMutation = useMutation({
    mutationFn: () => {
      if (!currentTemplate) {
        return api.projects.createPromptTemplate(selectedProjectId!, {
          name: templateName.trim() || "图片分析模板",
          task_type: "image_analysis",
          user_prompt: effectivePrompt,
          is_active: true,
        });
      }
      return api.projects.updatePromptTemplate(selectedProjectId!, currentTemplate.id, {
        name: templateName.trim() || currentTemplate.name,
        user_prompt: effectivePrompt,
        is_active: true,
      });
    },
    onSuccess: (newTemplate: PromptTemplate) => {
      setSelectedTemplateId(newTemplate.id);
      queryClient.invalidateQueries({ queryKey: ["project-prompt-templates", selectedProjectId] });
      queryClient.invalidateQueries({ queryKey: ["project-ai-settings", selectedProjectId] });
      setMessage(`Prompt 已保存为新版本 v${newTemplate.version}`);
    },
    onError: (err: Error) => setMessage(`保存 Prompt 失败：${err.message}`),
  });

  const activateTemplateMutation = useMutation({
    mutationFn: (templateId: number) =>
      api.projects.updateAiSettings(
        selectedProjectId!,
        toSettingsBody(modelForm, templateId)
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["project-ai-settings", selectedProjectId] });
      queryClient.invalidateQueries({ queryKey: ["project-prompt-templates", selectedProjectId] });
      setMessage("已设为启用模板");
    },
    onError: (err: Error) => setMessage(`设为启用失败：${err.message}`),
  });

  const resetPromptMutation = useMutation({
    mutationFn: () => api.projects.resetDefaultPromptTemplate(selectedProjectId!),
    onSuccess: (template) => {
      setSelectedTemplateId(template.id);
      queryClient.invalidateQueries({ queryKey: ["project-prompt-templates", selectedProjectId] });
      queryClient.invalidateQueries({ queryKey: ["project-ai-settings", selectedProjectId] });
      setMessage("已恢复默认 Prompt 并激活新版本");
    },
    onError: (err: Error) => setMessage(`恢复默认失败：${err.message}`),
  });

  const testPromptMutation = useMutation({
    mutationFn: () =>
      api.projects.testPromptTemplate(selectedProjectId!, {
        image_id: testPhotoId!,
        prompt_template_id: currentTemplate?.id,
        override_prompt: effectivePrompt,
      }),
    onSuccess: (res) => {
      setTestResult(res);
      const selectedPhoto = testPhotos.find((p) => p.id === testPhotoId);
      if (selectedProjectId != null && selectedPhoto && testPhotoId != null) {
        const item: PromptTestHistoryItem = {
          id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
          project_id: selectedProjectId,
          image_id: testPhotoId,
          file_name: selectedPhoto.file_name,
          template_id: currentTemplate?.id ?? null,
          template_version: currentTemplate?.version ?? null,
          tested_at: new Date().toISOString(),
          result: res,
        };
        const next = [item, ...testHistory].slice(0, TEST_HISTORY_MAX);
        setTestHistory(next);
        localStorage.setItem(`ai-photo-lib:prompt-test-history:${selectedProjectId}`, JSON.stringify(next));
      }
      setMessage(res.success ? "Prompt 测试成功" : "Prompt 测试返回解析失败");
    },
    onError: (err: Error) => {
      setMessage(`Prompt 测试失败：${err.message}`);
    },
  });

  if (selectedProjectId == null) {
    return (
      <main className="max-w-5xl mx-auto px-4 sm:px-6 py-6">
        <div className="bg-canvas border border-hairline rounded-md px-5 py-4 text-body-sm text-mute">
          请先选择一个项目，再进入 AI 配置页。
        </div>
      </main>
    );
  }

  const testPhotos: Photo[] = photosData?.items ?? [];
  const latestFailed = failedJobsData?.items ?? [];

  const clearTestHistory = () => {
    if (selectedProjectId == null) return;
    setTestHistory([]);
    localStorage.removeItem(`ai-photo-lib:prompt-test-history:${selectedProjectId}`);
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
    <main className="max-w-5xl mx-auto px-4 sm:px-6 py-6 space-y-6">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-heading-md font-semibold text-ink flex items-center gap-2">
            <Settings2 className="w-5 h-5" />
            项目 AI 配置
          </h1>
          <p className="text-caption-sm text-mute mt-1">
            项目：{currentProject?.id === selectedProjectId ? currentProject.name : `#${selectedProjectId}`}
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => navigate("/tasks")}
            className="px-3 py-1.5 text-btn-sm rounded-md border border-hairline hover:bg-surface-card"
          >
            返回任务中心
          </button>
          <Link
            to="/settings"
            className="px-3 py-1.5 text-btn-sm rounded-md border border-hairline hover:bg-surface-card"
          >
            系统设置
          </Link>
        </div>
      </div>

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
    </main>
  );
}
