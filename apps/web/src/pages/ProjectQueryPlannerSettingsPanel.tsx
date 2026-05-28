import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, Check, Loader2, Play, RotateCcw, Save, Sparkles } from "lucide-react";
import {
  api,
  type QueryPlannerTestResponse,
  type ProjectQueryPlannerSettings,
  type ProjectQueryPlannerSettingsUpdate,
} from "@/api";
import { ConfigTestResult } from "@/components/settings/ConfigTestResult";

interface Props {
  projectId: number;
}

export default function ProjectQueryPlannerSettingsPanel({ projectId }: Props) {
  const queryClient = useQueryClient();

  const { data: settings, isLoading, error } = useQuery({
    queryKey: ["project-query-planner-settings", projectId],
    queryFn: () => api.projects.getQueryPlannerSettings(projectId),
  });

  const [form, setForm] = useState<Partial<ProjectQueryPlannerSettingsUpdate>>({});
  const [saved, setSaved] = useState(false);
  const [testQuery, setTestQuery] = useState("动物");
  const [testResult, setTestResult] = useState<QueryPlannerTestResponse | null>(null);

  const effective = { ...(settings ?? {}), ...form } as ProjectQueryPlannerSettings;

  const updateMutation = useMutation({
    mutationFn: (body: ProjectQueryPlannerSettingsUpdate) =>
      api.projects.updateQueryPlannerSettings(projectId, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["project-query-planner-settings", projectId] });
      setForm({});
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    },
  });

  const resetMutation = useMutation({
    mutationFn: () => api.projects.resetQueryPlannerSettings(projectId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["project-query-planner-settings", projectId] });
      setForm({});
    },
  });

  const testMutation = useMutation({
    mutationFn: (query: string) => api.projects.testQueryPlanner(projectId, query),
    onSuccess: (result) => {
      setTestResult(result);
    },
  });

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 text-gray-500 p-4">
        <Loader2 className="animate-spin w-4 h-4" />
        <span>加载 Query Planner 设置...</span>
      </div>
    );
  }

  if (error || !settings) {
    return (
      <div className="flex items-center gap-2 text-red-500 p-4">
        <AlertCircle className="w-4 h-4" />
        <span>加载 Query Planner 设置失败</span>
      </div>
    );
  }

  function setField<K extends keyof ProjectQueryPlannerSettingsUpdate>(
    key: K,
    value: ProjectQueryPlannerSettingsUpdate[K],
  ) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  function handleSave() {
    if (Object.keys(form).length > 0) {
      updateMutation.mutate(form);
    }
  }

  const plannerDebug = (testResult?.planner_debug ?? {}) as Record<string, unknown>;
  const usedFallback = Boolean(plannerDebug.used_fallback);
  const fallbackReason =
    typeof plannerDebug.fallback_reason === "string" ? plannerDebug.fallback_reason : "";
  const plannerError =
    typeof plannerDebug.error === "string" ? plannerDebug.error : null;
  const latencyMs =
    typeof plannerDebug.latency_ms === "number" ? plannerDebug.latency_ms : null;
  const modelName =
    typeof plannerDebug.model === "string" ? plannerDebug.model : null;
  const rawOutput = plannerDebug.raw_output ?? plannerDebug.raw_output_preview ?? null;

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-gray-600" />
          <h3 className="font-medium text-gray-800">Query Planner 设置</h3>
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
            重置
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

      <section className="space-y-3">
        <label className="flex items-center gap-2 text-sm cursor-pointer">
          <input
            type="checkbox"
            checked={effective.enabled ?? false}
            onChange={(e) => setField("enabled", e.target.checked)}
          />
          <span className="text-gray-700">启用 LLM Query Planner（LLM-first）</span>
        </label>
      </section>

      {effective.enabled && <section className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <label className="flex flex-col gap-1 text-xs">
          <span className="text-gray-600">Provider</span>
          <input
            className="border rounded px-2 py-1"
            value={effective.provider ?? ""}
            onChange={(e) => setField("provider", e.target.value)}
          />
        </label>
        <label className="flex flex-col gap-1 text-xs">
          <span className="text-gray-600">Model Name</span>
          <input
            className="border rounded px-2 py-1"
            value={effective.model_name ?? ""}
            onChange={(e) => setField("model_name", e.target.value)}
          />
        </label>
        <label className="flex flex-col gap-1 text-xs md:col-span-2">
          <span className="text-gray-600">Endpoint URL</span>
          <input
            className="border rounded px-2 py-1"
            value={effective.endpoint_url ?? ""}
            onChange={(e) => setField("endpoint_url", e.target.value)}
          />
        </label>
        <label className="flex flex-col gap-1 text-xs">
          <span className="text-gray-600">Temperature</span>
          <input
            type="number"
            min="0"
            max="2"
            step="0.1"
            className="border rounded px-2 py-1"
            value={effective.temperature ?? 0}
            onChange={(e) => setField("temperature", parseFloat(e.target.value) || 0)}
          />
        </label>
        <label className="flex flex-col gap-1 text-xs">
          <span className="text-gray-600">Top P</span>
          <input
            type="number"
            min="0"
            max="1"
            step="0.1"
            className="border rounded px-2 py-1"
            value={effective.top_p ?? 0.8}
            onChange={(e) => setField("top_p", parseFloat(e.target.value) || 0.8)}
          />
        </label>
        <label className="flex flex-col gap-1 text-xs">
          <span className="text-gray-600">Max Tokens</span>
          <input
            type="number"
            min="1"
            max="4096"
            className="border rounded px-2 py-1"
            value={effective.max_tokens ?? 700}
            onChange={(e) => setField("max_tokens", parseInt(e.target.value, 10) || 700)}
          />
        </label>
        <label className="flex flex-col gap-1 text-xs">
          <span className="text-gray-600">Timeout Seconds</span>
          <input
            type="number"
            min="1"
            max="120"
            className="border rounded px-2 py-1"
            value={effective.timeout_seconds ?? 20}
            onChange={(e) => setField("timeout_seconds", parseInt(e.target.value, 10) || 20)}
          />
        </label>
        <label className="flex flex-col gap-1 text-xs">
          <span className="text-gray-600">JSON Parse Strategy</span>
          <input
            className="border rounded px-2 py-1"
            value={effective.json_parse_strategy ?? "strict_json_then_extract"}
            onChange={(e) => setField("json_parse_strategy", e.target.value)}
          />
        </label>
        <label className="flex flex-col gap-1 text-xs">
          <span className="text-gray-600">Planner Version</span>
          <input
            className="border rounded px-2 py-1"
            value={effective.planner_version ?? "llm_query_planner_v1"}
            onChange={(e) => setField("planner_version", e.target.value)}
          />
        </label>
        <label className="flex flex-col gap-1 text-xs">
          <span className="text-gray-600">Fallback Mode</span>
          <input
            className="border rounded px-2 py-1"
            value={effective.fallback_mode ?? "rule_fallback"}
            onChange={(e) => setField("fallback_mode", e.target.value)}
          />
        </label>
        <label className="flex flex-col gap-1 text-xs md:col-span-2">
          <span className="text-gray-600">System Prompt（可选）</span>
          <textarea
            rows={4}
            className="border rounded px-2 py-1"
            value={effective.system_prompt ?? ""}
            onChange={(e) => setField("system_prompt", e.target.value)}
          />
        </label>
        <label className="flex flex-col gap-1 text-xs md:col-span-2">
          <span className="text-gray-600">User Prompt Template（可选）</span>
          <textarea
            rows={5}
            className="border rounded px-2 py-1"
            value={effective.prompt_template ?? ""}
            onChange={(e) => setField("prompt_template", e.target.value)}
          />
        </label>
      </section>}

      {effective.enabled && updateMutation.isError && (
        <p className="text-xs text-red-500 flex items-center gap-1">
          <AlertCircle className="w-3 h-3" />
          保存失败，请重试
        </p>
      )}

      {effective.enabled && <section className="space-y-2 border-t border-gray-200 pt-4">
        <h4 className="text-sm font-semibold text-gray-700">测试 Query</h4>
        <div className="flex gap-2">
          <input
            className="flex-1 border rounded px-2 py-1 text-sm"
            placeholder="输入测试 query，例如：张三在海边的合照"
            value={testQuery}
            onChange={(e) => setTestQuery(e.target.value)}
          />
          <button
            className="flex items-center gap-1 text-xs text-white bg-emerald-600 rounded px-2 py-1 hover:bg-emerald-700 disabled:opacity-50"
            onClick={() => testMutation.mutate(testQuery.trim())}
            disabled={testMutation.isPending || !testQuery.trim()}
          >
            {testMutation.isPending ? (
              <Loader2 className="w-3 h-3 animate-spin" />
            ) : (
              <Play className="w-3 h-3" />
            )}
            测试
          </button>
        </div>
        {testMutation.isError && (
          <p className="text-xs text-red-500 flex items-center gap-1">
            <AlertCircle className="w-3 h-3" />
            测试失败，请检查 endpoint/model 配置
          </p>
        )}
        {testResult && (
          <ConfigTestResult
            title="Planner 测试结果"
            success={!usedFallback}
            latencyMs={latencyMs}
            model={modelName}
            errorMessage={usedFallback && plannerError ? plannerError : null}
            warningMessage={usedFallback ? `已触发 fallback${fallbackReason ? `：${fallbackReason}` : ""}` : null}
            summary={[
              { label: "Used Fallback", value: String(usedFallback) },
              { label: "Fallback Reason", value: fallbackReason || "—" },
              { label: "Parse Strategy", value: effective.json_parse_strategy ?? "—" },
            ]}
            requestPayload={{
              query: testResult.query,
              provider: effective.provider,
              endpoint_url: effective.endpoint_url,
              model_name: effective.model_name,
              planner_version: effective.planner_version,
              fallback_mode: effective.fallback_mode,
            }}
            rawOutput={rawOutput}
            parsedOutput={testResult.parsed_query_plan}
          />
        )}
      </section>}
    </div>
  );
}
