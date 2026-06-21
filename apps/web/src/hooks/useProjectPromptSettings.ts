import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  api,
  type Photo,
  type PromptTemplate,
  type PromptTemplateTestResponse,
} from "@/api";

export interface ModelFormSnapshot {
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

function resolveStorage(): Storage | null {
  const storage = globalThis.localStorage;
  if (
    !storage ||
    typeof storage.getItem !== "function" ||
    typeof storage.setItem !== "function" ||
    typeof storage.removeItem !== "function"
  ) {
    return null;
  }
  return storage;
}

export function useProjectPromptSettings({
  projectId,
  modelForm,
  onMessage,
}: {
  projectId: number;
  modelForm: ModelFormSnapshot;
  onMessage: (message: string) => void;
}) {
  const queryClient = useQueryClient();

  const [selectedTemplateId, setSelectedTemplateId] = useState<number | null>(null);
  const [templateName, setTemplateName] = useState("图片分析模板");
  const [advancedMode, setAdvancedMode] = useState(false);
  const [basicFocus, setBasicFocus] = useState(BASIC_FOCUS_DEFAULT);
  const [basicExtra, setBasicExtra] = useState("");
  const [advancedPrompt, setAdvancedPrompt] = useState("");

  const [testPhotoId, setTestPhotoId] = useState<number | null>(null);
  const [testResult, setTestResult] = useState<PromptTemplateTestResponse | null>(null);
  const [testHistory, setTestHistory] = useState<PromptTestHistoryItem[]>([]);

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

  const { data: templatesData, isLoading: templatesLoading } = useQuery({
    queryKey: ["project-prompt-templates", projectId],
    queryFn: () => api.projectPrompts.list(projectId),
    staleTime: 15_000,
  });

  const {
    data: photosData,
    error: photosError,
    isError: photosIsError,
  } = useQuery({
    queryKey: ["project-test-photos", projectId],
    queryFn: () => api.projectPhotos.list(projectId, 1, 100),
    staleTime: 30_000,
  });

  const { data: failedJobsData } = useQuery({
    queryKey: ["project-ai-failed-jobs-latest", projectId],
    queryFn: () => api.projectAiJobs.list(projectId, "failed", 10),
    staleTime: 10_000,
  });

  const templates = templatesData?.items ?? [];

  useEffect(() => {
    const key = `ai-photo-lib:prompt-test-history:${projectId}`;
    const storage = resolveStorage();
    if (!storage) {
      setTestHistory([]);
      return;
    }
    const raw = storage.getItem(key);
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

  const savePromptMutation = useMutation({
    mutationFn: () => {
      if (!currentTemplate) {
        return api.projectPrompts.create(projectId, {
          name: templateName.trim() || "图片分析模板",
          task_type: "image_analysis",
          user_prompt: effectivePrompt,
          is_active: true,
        });
      }
      return api.projectPrompts.update(projectId, currentTemplate.id, {
        name: templateName.trim() || currentTemplate.name,
        user_prompt: effectivePrompt,
        is_active: true,
      });
    },
    onSuccess: (newTemplate: PromptTemplate) => {
      setSelectedTemplateId(newTemplate.id);
      queryClient.invalidateQueries({ queryKey: ["project-prompt-templates", projectId] });
      queryClient.invalidateQueries({ queryKey: ["project-ai-settings", projectId] });
      onMessage(`Prompt 已保存为新版本 v${newTemplate.version}`);
    },
    onError: (err: Error) => onMessage(`保存 Prompt 失败：${err.message}`),
  });

  const activateTemplateMutation = useMutation({
    mutationFn: (templateId: number) => {
      const template = templates.find((item) => item.id === templateId);
      if (!template) {
        throw new Error("模板不存在或已被删除");
      }
      // Activate by creating a new active version from the selected template.
      return api.projectPrompts.update(projectId, templateId, {
        name: template.name,
        user_prompt: template.user_prompt,
        output_schema: template.output_schema,
        is_active: true,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["project-ai-settings", projectId] });
      queryClient.invalidateQueries({ queryKey: ["project-prompt-templates", projectId] });
      onMessage("已设为启用模板");
    },
    onError: (err: Error) => onMessage(`设为启用失败：${err.message}`),
  });

  const resetPromptMutation = useMutation({
    mutationFn: () => api.projectPrompts.resetDefault(projectId),
    onSuccess: (template) => {
      setSelectedTemplateId(template.id);
      queryClient.invalidateQueries({ queryKey: ["project-prompt-templates", projectId] });
      queryClient.invalidateQueries({ queryKey: ["project-ai-settings", projectId] });
      onMessage("已恢复默认 Prompt 并激活新版本");
    },
    onError: (err: Error) => onMessage(`恢复默认失败：${err.message}`),
  });

  const deletePromptMutation = useMutation({
    mutationFn: (templateId: number) => api.projectPrompts.delete(projectId, templateId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["project-prompt-templates", projectId] });
      queryClient.invalidateQueries({ queryKey: ["project-ai-settings", projectId] });
      onMessage("模板已删除");
    },
    onError: (err: Error) => onMessage(`删除模板失败：${err.message}`),
  });

  const testPromptMutation = useMutation({
    mutationFn: () =>
      api.projectPrompts.test(projectId, {
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
        const storage = resolveStorage();
        if (storage) {
          storage.setItem(`ai-photo-lib:prompt-test-history:${projectId}`, JSON.stringify(next));
        }
      }
      onMessage(res.success ? "Prompt 测试成功" : "Prompt 测试返回解析失败");
    },
    onError: (err: Error) => {
      onMessage(`Prompt 测试失败：${err.message}`);
    },
  });

  const testPhotos: Photo[] = photosData?.items ?? [];
  const latestFailed = failedJobsData?.items ?? [];

  const clearTestHistory = () => {
    setTestHistory([]);
    const storage = resolveStorage();
    if (storage) {
      storage.removeItem(`ai-photo-lib:prompt-test-history:${projectId}`);
    }
    onMessage("已清空测试历史");
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
    onMessage(`已载入测试历史：${item.file_name}`);
  };

  return {
    templatesLoading,
    templates,
    selectedTemplateId,
    setSelectedTemplateId,
    templateName,
    setTemplateName,
    advancedMode,
    setAdvancedMode,
    basicFocus,
    setBasicFocus,
    basicExtra,
    setBasicExtra,
    advancedPrompt,
    setAdvancedPrompt,
    generatedPrompt,
    effectivePrompt,
    currentTemplate,
    savePrompt: () => savePromptMutation.mutate(),
    savePromptPending: savePromptMutation.isPending,
    activateTemplate: (templateId: number) => activateTemplateMutation.mutate(templateId),
    activateTemplatePending: activateTemplateMutation.isPending,
    resetPrompt: () => resetPromptMutation.mutate(),
    resetPromptPending: resetPromptMutation.isPending,
    deletePrompt: (templateId: number) => deletePromptMutation.mutate(templateId),
    deletePromptPending: deletePromptMutation.isPending,
    testPhotoId,
    setTestPhotoId,
    testPhotos,
    photosIsError,
    photosError,
    testPrompt: () => testPromptMutation.mutate(),
    testPromptPending: testPromptMutation.isPending,
    testResult,
    testHistory,
    clearTestHistory,
    loadHistoryResult,
    latestFailed,
  };
}
