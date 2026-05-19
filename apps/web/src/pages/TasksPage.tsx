import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  Brain,
  FolderSearch,
  Loader2,
  Play,
  RefreshCw,
  AlertCircle,
  CheckCircle2,
  Clock,
} from "lucide-react";
import { ScanPanel } from "@/components/ScanPanel";
import { api, type AIJob } from "@/lib/api";
import { useScanStatus, useStartScan } from "@/hooks/useScan";
import { useProjectContext } from "@/contexts/ProjectContext";

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
      queryClient.invalidateQueries({ queryKey: ["ai-status", projectId] });
      queryClient.invalidateQueries({ queryKey: ["ai-jobs-failed", projectId] });
    },
  });

  const clearFailedJobsMutation = useMutation({
    mutationFn: () => api.projects.clearFailedAiJobs(projectId!),
    onSuccess: () => {
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["ai-status", projectId] });
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

// ─── AI section ───────────────────────────────────────────────────────────────

function AISection({ projectId }: { projectId: number | null }) {
  const queryClient = useQueryClient();
  const [message, setMessage] = useState<string | null>(null);
  const wasActiveRef = useRef(false);

  const { data: status, isLoading } = useQuery({
    queryKey: ["ai-status", projectId],
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
      queryClient.invalidateQueries({ queryKey: ["photos"] });
      queryClient.invalidateQueries({ queryKey: ["photo-ai"] });
      queryClient.invalidateQueries({ queryKey: ["tags"] });
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
      queryClient.invalidateQueries({ queryKey: ["ai-status"] });
      setTimeout(() => setMessage(null), 5000);
    },
    onError: (err: Error) => setMessage(`启动失败：${err.message}`),
  });

  const isRunning = status && status.running > 0;
  const canRun = projectId != null;

  // Rough speed: success / (age of oldest running job in hours) — simplified
  const speed = status && status.success > 0 ? status.success : null;

  return (
    <section className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
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
          {projectId != null && (
            <Link
              to={`/project/${projectId}/settings/ai`}
              className="text-caption-sm text-primary hover:text-primary-pressed"
            >
              项目 AI 配置
            </Link>
          )}
        </div>
        <button
          onClick={() => startMutation.mutate()}
          disabled={startMutation.isPending || !canRun}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-primary text-white text-btn-sm font-bold hover:bg-primary-pressed disabled:bg-stone transition-colors"
        >
          <Play className="w-3.5 h-3.5" />
          {startMutation.isPending ? "启动中…" : "开始分析"}
        </button>
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

      {message && <p className="text-caption-sm text-mute">{message}</p>}

      {!canRun && <p className="text-caption-sm text-mute">请先选择项目后再执行 AI 分析。</p>}

      <FailedJobsSection projectId={projectId} />
    </section>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export function TasksPage() {
  const { currentProjectId } = useProjectContext();
  const { data: scanStatus, isLoading: scanLoading } = useScanStatus(currentProjectId);
  const { mutate: startScan, isPending } = useStartScan(currentProjectId);

  return (
    <main className="max-w-3xl mx-auto px-4 sm:px-6 py-6 space-y-8">
      <h1 className="text-heading-md font-semibold text-ink flex items-center gap-2">
        <Clock className="w-5 h-5" />
        任务中心
      </h1>

      {/* Scan section */}
      <section className="space-y-3">
        <div className="flex items-center gap-2">
          <FolderSearch className="w-4 h-4 text-mute" />
          <h2 className="text-body-sm font-semibold text-ink">照片扫描</h2>
        </div>
        <ScanPanel
          status={scanStatus}
          isLoading={scanLoading}
          onStart={() => startScan()}
          isPending={isPending}
        />
      </section>

      <div className="border-t border-hairline" />

      {/* AI section */}
      <AISection projectId={currentProjectId} />
    </main>
  );
}
