import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  Brain,
  FolderSearch,
  Loader2,
  Play,
  RefreshCw,
  AlertCircle,
  CheckCircle2,
  Clock,
  Settings2,
  RotateCcw,
} from "lucide-react";
import { ScanPanel } from "@/components/ScanPanel";
import { api, type AIJob } from "@/api";
import { queryKeys } from "@/api/queryKeys";
import { useScanStatus, useStartScan, useStartReindex } from "@/hooks/useScan";
import { useProjectContext } from "@/contexts/ProjectContext";
import { ProjectAISettingsPanel } from "./ProjectAISettingsPanel";

// ─── Stat tile ───────────────────────────────────────────────────────────────

function StatTile({
  label,
  value,
  color = "text-ink",
}: {
  label: string;
  value: number | string;
  color?: string;
}) {
  return (
    <div className="bg-canvas border border-hairline rounded-md px-4 py-3 text-center">
      <p className={`text-heading-md font-bold tabular-nums ${color}`}>{value}</p>
      <p className="text-caption-sm text-mute mt-0.5">{label}</p>
    </div>
  );
}

// ─── Failed jobs list ─────────────────────────────────────────────────────────

function FailedJobsSection({ projectId }: { projectId: number | null }) {
  const queryClient = useQueryClient();
  const [showAll, setShowAll] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data } = useQuery({
    queryKey: ["ai-jobs-failed", projectId],
    queryFn: () => api.projects.aiJobs(projectId!, "failed", 50),
    enabled: projectId != null,
    staleTime: 10_000,
  });

  const retryMutation = useMutation({
    mutationFn: () => api.projects.retryFailedAiJobs(projectId!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.aiStatus(projectId) });
      queryClient.invalidateQueries({ queryKey: ["ai-jobs-failed", projectId] });
    },
  });

  const clearFailedJobsMutation = useMutation({
    mutationFn: () => api.projects.clearFailedAiJobs(projectId!),
    onSuccess: () => {
      setError(null);
      queryClient.invalidateQueries({ queryKey: queryKeys.aiStatus(projectId) });
      queryClient.invalidateQueries({ queryKey: ["ai-jobs-failed", projectId] });
    },
    onError: (err: Error) => {
      setError(`清除失败记录失败：${err.message}`);
    },
  });

  const items = data?.items ?? [];
  if (items.length === 0) return null;

  const visible = showAll ? items : items.slice(0, 5);

  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <AlertCircle className="w-4 h-4 text-amber-500" />
          <h2 className="text-body-sm font-semibold text-ink">失败任务</h2>
          <span className="text-caption-sm text-mute">{items.length} 个</span>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => retryMutation.mutate()}
            disabled={retryMutation.isPending}
            className="flex items-center gap-1 text-btn-sm font-bold text-primary hover:text-primary-pressed disabled:text-stone transition-colors"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            {retryMutation.isPending ? "重试中…" : "全部重试"}
          </button>
          <button
            onClick={() => clearFailedJobsMutation.mutate()}
            disabled={clearFailedJobsMutation.isPending}
            className="flex items-center gap-1 text-btn-sm font-bold text-danger hover:text-danger-pressed disabled:text-stone transition-colors"
          >
            清除失败记录
          </button>
        </div>
      </div>

      <div className="space-y-1.5">
        {visible.map((job) => (
          <FailedJobRow key={job.id} job={job} />
        ))}
      </div>

      {error && <p className="text-caption-sm text-danger">{error}</p>}

      {items.length > 5 && (
        <button
          onClick={() => setShowAll((v) => !v)}
          className="text-btn-sm text-primary hover:text-primary-pressed"
        >
          {showAll ? "收起" : `显示全部 ${items.length} 个`}
        </button>
      )}
    </section>
  );
}

/** Build a short summary and retain full detail text for expandable display. */
function parseErrorMessage(raw: string): { summary: string; detail: string } {
  const trimmed = raw.trim();
  const firstLine = trimmed.split(/\r?\n/, 1)[0] ?? "";

  // Try to extract an API-style nested message from embedded JSON.
  const jsonMatch = raw.match(/\{[\s\S]*\}/);
  if (jsonMatch) {
    try {
      const parsed = JSON.parse(jsonMatch[0]);
      const msg: string | undefined =
        parsed?.error?.message ?? parsed?.message ?? parsed?.detail;
      if (msg) {
        const prefix = raw.slice(0, jsonMatch.index).replace(/:\s*$/, "").trim();
        return {
          summary: prefix ? `${prefix}: ${msg}` : msg,
          detail: trimmed,
        };
      }
    } catch {
      // Keep fallback summary below.
    }
  }

  return {
    summary: firstLine || trimmed,
    detail: trimmed,
  };
}

function FailedJobRow({ job }: { job: AIJob }) {
  const [expanded, setExpanded] = useState(false);

  const errorInfo = job.error_message ? parseErrorMessage(job.error_message) : null;

  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text).catch(() => {
      // Ignore clipboard permission errors in non-secure contexts.
    });
  };

  return (
    <div className="bg-canvas border border-hairline rounded-md px-4 py-2.5 flex items-start gap-3">
      <AlertCircle className="w-4 h-4 text-amber-500 flex-shrink-0 mt-0.5" />
      <div className="min-w-0 flex-1 space-y-1">
        <p className="text-body-sm text-ink truncate">{job.file_name ?? `#${job.photo_id}`}</p>
        <p className="text-caption-sm text-mute">
          prompt v{job.prompt_version ?? "-"} · model {job.model_name ?? "-"}
        </p>
        {errorInfo && (
          <>
            <p className={`text-caption-sm text-mute mt-0.5 ${expanded ? "whitespace-pre-wrap break-all" : "truncate"}`}>
              {expanded ? errorInfo.detail : errorInfo.summary}
            </p>
            {errorInfo.detail && (
              <button
                onClick={() => setExpanded((v) => !v)}
                className="text-caption-sm text-primary hover:text-primary-pressed"
              >
                {expanded ? "收起" : "展开详情"}
              </button>
            )}
            {expanded && (
              <div className="mt-2 space-y-2">
                <div className="bg-surface-soft border border-hairline rounded-md p-2">
                  <div className="flex items-center justify-between gap-2 mb-1">
                    <p className="text-caption-sm text-mute">parse_error</p>
                    {job.parse_error && (
                      <button
                        onClick={() => handleCopy(job.parse_error || "")}
                        className="text-caption-sm text-primary hover:text-primary-pressed"
                      >
                        复制
                      </button>
                    )}
                  </div>
                  <pre className="text-caption-sm whitespace-pre-wrap break-all">
                    {job.parse_error || "(空)"}
                  </pre>
                </div>

                <div className="bg-surface-soft border border-hairline rounded-md p-2">
                  <div className="flex items-center justify-between gap-2 mb-1">
                    <p className="text-caption-sm text-mute">raw_model_output</p>
                    {job.raw_model_output && (
                      <button
                        onClick={() => handleCopy(job.raw_model_output || "")}
                        className="text-caption-sm text-primary hover:text-primary-pressed"
                      >
                        复制
                      </button>
                    )}
                  </div>
                  <pre className="text-caption-sm whitespace-pre-wrap break-all max-h-48 overflow-auto">
                    {job.raw_model_output || "(空)"}
                  </pre>
                </div>
              </div>
            )}
          </>
        )}
      </div>
      <span className="text-caption-sm text-stone flex-shrink-0">
        {job.retry_count > 0 ? `重试 ${job.retry_count}×` : ""}
      </span>
    </div>
  );
}

function AISection({ projectId }: { projectId: number | null }) {
  const queryClient = useQueryClient();
  const [message, setMessage] = useState<string | null>(null);
  const wasActiveRef = useRef(false);

  const { data: status, isLoading } = useQuery({
    queryKey: queryKeys.aiStatus(projectId),
    queryFn: () => api.projects.aiStatus(projectId!),
    enabled: projectId != null,
    refetchInterval: (query) => {
      const d = query.state.data;
      return d && (d.queued > 0 || d.running > 0) ? 3000 : 15000;
    },
  });

  useEffect(() => {
    const isActive = !!status && (status.queued > 0 || status.running > 0);
    if (wasActiveRef.current && !isActive && status) {
      queryClient.invalidateQueries({ queryKey: queryKeys.photosBase(projectId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.projectPhotoAiBase(projectId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.tags(projectId) });
    }
    wasActiveRef.current = isActive;
  }, [status, queryClient]);

  const startMutation = useMutation({
    mutationFn: () => api.projects.startAI(projectId!),
    onSuccess: (data) => {
      setMessage(
        data.created_jobs > 0
          ? `已创建 ${data.created_jobs} 个分析任务`
          : "所有照片已在分析队列中"
      );
      queryClient.invalidateQueries({ queryKey: queryKeys.aiStatus(projectId) });
      setTimeout(() => setMessage(null), 5000);
    },
    onError: (err: Error) => setMessage(`启动失败：${err.message}`),
  });

  const reanalyzeCompletedMutation = useMutation({
    mutationFn: () =>
      api.projects.reanalyze(projectId!, {
        scope: "completed",
        clear_existing_analysis: true,
      }),
    onSuccess: (data) => {
      setMessage(
        data.created_jobs > 0
          ? `已创建 ${data.created_jobs} 个重新分析任务`
          : "没有已完成的照片需要重新分析"
      );
      queryClient.invalidateQueries({ queryKey: queryKeys.aiStatus(projectId) });
      setTimeout(() => setMessage(null), 5000);
    },
    onError: (err: Error) => setMessage(`重新分析失败：${err.message}`),
  });

  const reanalyzeAllMutation = useMutation({
    mutationFn: () =>
      api.projects.reanalyze(projectId!, {
        scope: "all",
        clear_existing_analysis: true,
      }),
    onSuccess: (data) => {
      setMessage(
        data.created_jobs > 0
          ? `已创建 ${data.created_jobs} 个重新分析任务`
          : "没有照片需要重新分析"
      );
      queryClient.invalidateQueries({ queryKey: queryKeys.aiStatus(projectId) });
      setTimeout(() => setMessage(null), 5000);
    },
    onError: (err: Error) => setMessage(`重新分析失败：${err.message}`),
  });

  const isRunning = status && status.running > 0;
  const canRun = projectId != null;
  const isAnyPending =
    startMutation.isPending ||
    reanalyzeCompletedMutation.isPending ||
    reanalyzeAllMutation.isPending;

  // Rough speed: success / (age of oldest running job in hours) — simplified
  const speed = status && status.success > 0 ? status.success : null;

  return (
    <section className="space-y-4">
      {/* Header */}
      <div className="flex items-center gap-2">
        {isLoading ? (
          <Loader2 className="w-4 h-4 animate-spin text-mute" />
        ) : isRunning ? (
          <Loader2 className="w-4 h-4 animate-spin text-primary" />
        ) : (
          <Brain className="w-4 h-4 text-primary" />
        )}
        <h2 className="text-body-sm font-semibold text-ink">
          {isRunning ? "AI 分析进行中…" : "AI 图片分析"}
        </h2>
      </div>

      {/* Stats */}
      {status && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <StatTile label="排队中" value={status.queued} />
          <StatTile label="进行中" value={status.running} color={status.running > 0 ? "text-primary" : "text-ink"} />
          <StatTile label="已完成" value={status.success} color="text-green-700" />
          <StatTile label="失败" value={status.failed} color={status.failed > 0 ? "text-amber-600" : "text-ink"} />
        </div>
      )}

      {speed !== null && (
        <p className="text-caption-sm text-mute flex items-center gap-1">
          <CheckCircle2 className="w-3.5 h-3.5 text-green-600" />
          累计已分析 {speed.toLocaleString()} 张照片
        </p>
      )}

      {/* Action buttons */}
      <div className="flex flex-wrap gap-2">
        <button
          onClick={() => startMutation.mutate()}
          disabled={isAnyPending || !canRun}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-primary text-white text-btn-sm font-bold hover:bg-primary-pressed disabled:bg-stone transition-colors"
        >
          <Play className="w-3.5 h-3.5" />
          {startMutation.isPending ? "启动中…" : "开始分析"}
        </button>
        <button
          onClick={() => reanalyzeCompletedMutation.mutate()}
          disabled={isAnyPending || !canRun}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-hairline text-btn-sm hover:bg-surface-card disabled:opacity-50 transition-colors"
        >
          <RotateCcw className="w-3.5 h-3.5" />
          {reanalyzeCompletedMutation.isPending ? "处理中…" : "重新分析已完成"}
        </button>
        <button
          onClick={() => {
            if (!window.confirm("这会清除当前项目已有 AI 分析结果并重新生成，确认继续？")) return;
            reanalyzeAllMutation.mutate();
          }}
          disabled={isAnyPending || !canRun}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-hairline text-btn-sm hover:bg-surface-card disabled:opacity-50 transition-colors"
        >
          <RefreshCw className="w-3.5 h-3.5" />
          {reanalyzeAllMutation.isPending ? "处理中…" : "重新分析全部"}
        </button>
      </div>

      <div className="text-caption-sm text-mute space-y-0.5">
        <p>开始分析：只处理没有 AI 结果的照片</p>
        <p>重新分析：会删除旧 AI 分析结果并重新生成</p>
      </div>

      {message && <p className="text-caption-sm text-mute">{message}</p>}

      {!canRun && <p className="text-caption-sm text-mute">请先选择项目后再执行 AI 分析。</p>}

      <FailedJobsSection projectId={projectId} />
    </section>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

type TaskTab = "scan" | "ai" | "ai-settings";

export function TasksPage() {
  const { currentProjectId } = useProjectContext();
  const { data: scanStatus, isLoading: scanLoading } = useScanStatus(currentProjectId);
  const { mutate: startScan, isPending, error: scanError } = useStartScan(currentProjectId);
  const { mutate: startReindex, isPending: isReindexPending } = useStartReindex(currentProjectId);
  const [searchParams, setSearchParams] = useSearchParams();

  const tabParam = searchParams.get("tab");
  const initialTab: TaskTab =
    tabParam === "scan" || tabParam === "ai" || tabParam === "ai-settings"
      ? tabParam
      : "ai";
  const [tab, setTab] = useState<TaskTab>(initialTab);

  const handleTabChange = (next: TaskTab) => {
    setTab(next);
    setSearchParams(next === "ai" ? {} : { tab: next }, { replace: true });
  };

  const tabClass = (t: TaskTab) =>
    [
      "px-4 py-2 text-btn-sm font-medium transition-colors border-b-2",
      tab === t
        ? "border-primary text-primary"
        : "border-transparent text-mute hover:text-ink",
    ].join(" ");

  return (
    <main className="max-w-3xl mx-auto px-4 sm:px-6 py-6 space-y-6">
      <h1 className="text-heading-md font-semibold text-ink flex items-center gap-2">
        <Clock className="w-5 h-5" />
        任务中心
      </h1>

      {/* Tab nav */}
      <div className="flex gap-0 border-b border-hairline -mb-2">
        <button onClick={() => handleTabChange("scan")} className={tabClass("scan")}>
          <span className="flex items-center gap-1.5">
            <FolderSearch className="w-3.5 h-3.5" />
            照片扫描
          </span>
        </button>
        <button onClick={() => handleTabChange("ai")} className={tabClass("ai")}>
          <span className="flex items-center gap-1.5">
            <Brain className="w-3.5 h-3.5" />
            AI 分析任务
          </span>
        </button>
        <button onClick={() => handleTabChange("ai-settings")} className={tabClass("ai-settings")}>
          <span className="flex items-center gap-1.5">
            <Settings2 className="w-3.5 h-3.5" />
            AI 配置
          </span>
        </button>
      </div>

      {/* Tab content */}
      {tab === "scan" && (
        <section className="space-y-3">
          <ScanPanel
            status={scanStatus}
            isLoading={scanLoading}
            onStart={() => startScan()}
            isPending={isPending}
            mutationError={scanError?.message ?? null}
            onReindex={(scope) => startReindex(scope)}
            isReindexPending={isReindexPending}
          />
        </section>
      )}

      {tab === "ai" && (
        <AISection projectId={currentProjectId} />
      )}

      {tab === "ai-settings" && (
        currentProjectId != null ? (
          <ProjectAISettingsPanel projectId={currentProjectId} />
        ) : (
          <div className="bg-canvas border border-hairline rounded-md px-5 py-4 text-body-sm text-mute">
            请先选择项目后再查看 AI 配置。
          </div>
        )
      )}
    </main>
  );
}
