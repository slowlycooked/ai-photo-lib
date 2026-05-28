import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Save } from "lucide-react";

import { ApiError, api, type ProjectAISettingsUpdate } from "@/api";
import { PromptSettingsSection } from "@/components/project-ai-settings/PromptSettingsSection";
import { Label, SettingsCard } from "@/components/project-ai-settings/SettingsPrimitives";
import { ProjectFaceSettingsPanel } from "./ProjectFaceSettingsPanel";

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

export function ProjectVisionAISettingsPanel({ projectId }: { projectId: number }) {
  const queryClient = useQueryClient();

  const [message, setMessage] = useState<string | null>(null);
  const [modelForm, setModelForm] = useState<ModelForm>(DEFAULT_MODEL_FORM);

  const {
    data: settingsData,
    isLoading: settingsLoading,
    error: settingsError,
  } = useQuery({
    queryKey: ["project-ai-settings", projectId],
    queryFn: () => api.projects.getAiSettings(projectId),
    staleTime: 30_000,
  });

  const initSettingsMutation = useMutation({
    mutationFn: () => api.projects.initAiSettings(projectId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["project-ai-settings", projectId] });
      setMessage("已初始化项目 AI 配置，请继续完善模型参数并保存。");
    },
    onError: (err: Error) => setMessage(`初始化失败：${err.message}`),
  });

  const needsInitialization =
    settingsError instanceof ApiError && settingsError.status === 422;

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

  const saveSettingsMutation = useMutation({
    mutationFn: (body: ProjectAISettingsUpdate) =>
      api.projects.updateAiSettings(projectId, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["project-ai-settings", projectId] });
      setMessage("视觉 AI 模型配置已保存");
    },
    onError: (err: Error) => setMessage(`保存失败：${err.message}`),
  });

  return (
    <div className="space-y-6">
      {message && (
        <div className="bg-secondary-bg border border-hairline rounded-md px-4 py-2.5 text-body-sm text-ink">
          {message}
        </div>
      )}

      {needsInitialization && (
        <SettingsCard title="项目 AI 配置尚未初始化">
          <div className="space-y-3 text-body-sm text-mute">
            <p>当前项目缺少 AI 配置与默认 Prompt 模板。请先初始化，再继续编辑模型参数。</p>
            <button
              onClick={() => initSettingsMutation.mutate()}
              disabled={initSettingsMutation.isPending}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-primary text-white text-btn-sm font-bold disabled:bg-stone"
            >
              {initSettingsMutation.isPending ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Save className="w-3.5 h-3.5" />
              )}
              初始化项目 AI 配置
            </button>
          </div>
        </SettingsCard>
      )}

      <SettingsCard title="视觉 AI · 模型服务配置">
        {settingsLoading ? (
          <div className="flex items-center gap-2 text-mute">
            <Loader2 className="w-4 h-4 animate-spin" />
            加载中…
          </div>
        ) : !settingsData ? (
          <div className="text-body-sm text-mute">等待项目 AI 配置初始化后再编辑。</div>
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
                  onChange={(e) =>
                    setModelForm((x) => ({ ...x, temperature: Number(e.target.value) }))
                  }
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
                  onChange={(e) =>
                    setModelForm((x) => ({ ...x, max_tokens: Number(e.target.value) }))
                  }
                  className="w-full px-3 py-2 text-body-sm bg-surface-card border border-hairline rounded-md"
                />
              </div>
              <div>
                <Label>失败重试次数</Label>
                <input
                  type="number"
                  value={modelForm.retry_count}
                  onChange={(e) =>
                    setModelForm((x) => ({ ...x, retry_count: Number(e.target.value) }))
                  }
                  className="w-full px-3 py-2 text-body-sm bg-surface-card border border-hairline rounded-md"
                />
              </div>
              <div>
                <Label>输出语言</Label>
                <input
                  value={modelForm.output_language}
                  onChange={(e) =>
                    setModelForm((x) => ({ ...x, output_language: e.target.value }))
                  }
                  className="w-full px-3 py-2 text-body-sm bg-surface-card border border-hairline rounded-md"
                />
              </div>
              <div>
                <Label>JSON 解析策略</Label>
                <select
                  value={modelForm.json_parse_strategy}
                  onChange={(e) =>
                    setModelForm((x) => ({ ...x, json_parse_strategy: e.target.value }))
                  }
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
                {saveSettingsMutation.isPending ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <Save className="w-3.5 h-3.5" />
                )}
                保存模型配置
              </button>
            </div>
          </>
        )}
      </SettingsCard>

      <PromptSettingsSection projectId={projectId} modelForm={modelForm} onMessage={setMessage} />

      <ProjectFaceSettingsPanel projectId={projectId} />
    </div>
  );
}
