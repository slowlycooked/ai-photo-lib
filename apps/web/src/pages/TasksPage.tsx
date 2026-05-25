import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
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
  ScanFace,
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
  const aiJobTypes = "analyze,reanalyze";

  const { data } = useQuery({
    queryKey: ["ai-jobs-failed", projectId],
    queryFn: () => api.projects.aiJobs(projectId!, "failed", 50, 0, aiJobTypes),
    enabled: projectId != null,
    staleTime: 10_000,
  });

  const retryMutation = useMutation({
    mutationFn: () => api.projects.retryFailedAiJobs(projectId!, aiJobTypes),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.aiStatus(projectId) });
      queryClient.invalidateQueries({ queryKey: ["ai-jobs-failed", projectId] });
    },
  });

  const clearFailedJobsMutation = useMutation({
    mutationFn: () => api.projects.clearFailedAiJobs(projectId!, aiJobTypes),
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

type FaceScanScope = "missing" | "failed" | "stale" | "all";
type FaceScanPreviewScope = FaceScanScope | "selected";

const FACE_SCAN_SCOPE_OPTIONS: Array<{
  scope: FaceScanScope;
  label: string;
  hint: string;
}> = [
  {
    scope: "missing",
    label: "扫描未处理",
    hint: "只处理未有人脸检测记录的照片",
  },
  {
    scope: "failed",
    label: "重扫失败",
    hint: "只重试历史失败的人脸扫描照片",
  },
  {
    scope: "stale",
    label: "扫描 stale",
    hint: "处理参数或衍生图变化后需要重扫的照片",
  },
  {
    scope: "all",
    label: "全量重扫",
    hint: "对所有照片重新创建人脸扫描任务",
  },
];

function FaceScanSection({ projectId }: { projectId: number | null }) {
  const queryClient = useQueryClient();
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<{
    scope: FaceScanPreviewScope;
    total_photos: number;
    candidate_count: number;
    skipped_active_jobs: number;
    skipped_already_scanned: number;
    stale_count: number;
    failed_count: number;
    dry_run: boolean;
  } | null>(null);
  const [showAllFailed, setShowAllFailed] = useState(false);

  const canRun = projectId != null;
  const peoplePath = canRun ? `/projects/${projectId}/people` : "/people";
  const reviewPath = canRun ? `/projects/${projectId}/people/review` : "/people";

  const { data: faceSettings, isLoading: settingsLoading } = useQuery({
    queryKey: ["project-face-settings", projectId],
    queryFn: () => api.projects.getFaceSettings(projectId!),
    enabled: canRun,
  });

  const { data: status, isLoading: statusLoading } = useQuery({
    queryKey: ["face-scan-status", projectId],
    queryFn: () => api.projects.projectFaceScanStatus(projectId!),
    enabled: canRun,
    refetchInterval: (query) => {
      const d = query.state.data;
      return d && (d.queued > 0 || d.running > 0) ? 3000 : 15000;
    },
  });

  const { data: failedJobsData } = useQuery({
    queryKey: ["face-scan-failed-jobs", projectId],
    queryFn: () => api.projects.aiJobs(projectId!, "failed", 50, 0, "face_scan"),
    enabled: canRun,
    staleTime: 10_000,
  });

  const previewMutation = useMutation({
    mutationFn: (scope: FaceScanScope) =>
      api.projects.startProjectFaceScan(projectId!, { scope, dry_run: true }),
    onSuccess: (result) => {
      setPreview({
        scope: result.scope,
        total_photos: result.total_photos,
        candidate_count: result.candidate_count,
        skipped_active_jobs: result.skipped_active_jobs,
        skipped_already_scanned: result.skipped_already_scanned,
        stale_count: result.stale_count,
        failed_count: result.failed_count,
        dry_run: result.dry_run,
      });
      setError(null);
      setMessage(`预览完成：${result.scope} 可创建 ${result.candidate_count} 个任务`);
    },
    onError: (err: Error) => {
      setError(`预览失败：${err.message}`);
    },
  });

  const startMutation = useMutation({
    mutationFn: (scope: FaceScanScope) =>
      api.projects.startProjectFaceScan(projectId!, { scope }),
    onSuccess: (result) => {
      setError(null);
      setMessage(
        result.created_jobs > 0
          ? `已创建 ${result.created_jobs} 个人脸扫描任务（scope=${result.scope}）`
          : `没有可创建的人脸扫描任务（scope=${result.scope}）`
      );
      queryClient.invalidateQueries({ queryKey: ["face-scan-status", projectId] });
      queryClient.invalidateQueries({ queryKey: ["face-scan-failed-jobs", projectId] });
    },
    onError: (err: Error) => {
      setError(`启动失败：${err.message}`);
    },
  });

  const clusterMutation = useMutation({
    mutationFn: () => api.projects.clusterUnknownFaces(projectId!),
    onSuccess: (result) => {
      setError(null);
      setMessage(
        `聚类完成：clusters=${result.clusters_created} · persons=${result.persons_created} · faces=${result.faces_clustered}`
      );
      queryClient.invalidateQueries({ queryKey: queryKeys.projectPeople(projectId, true) });
    },
    onError: (err: Error) => {
      setError(`聚类失败：${err.message}`);
    },
  });

  const retryFailedMutation = useMutation({
    mutationFn: () => api.projects.retryFailedAiJobs(projectId!, "face_scan"),
    onSuccess: (result) => {
      setError(null);
      setMessage(`已重试 ${result.retried_jobs} 个 face_scan 失败任务`);
      queryClient.invalidateQueries({ queryKey: ["face-scan-status", projectId] });
      queryClient.invalidateQueries({ queryKey: ["face-scan-failed-jobs", projectId] });
    },
    onError: (err: Error) => {
      setError(`重试失败：${err.message}`);
    },
  });

  const clearFailedMutation = useMutation({
    mutationFn: () => api.projects.clearFailedAiJobs(projectId!, "face_scan"),
    onSuccess: (result) => {
      setError(null);
      setMessage(`已清理 ${result.deleted_jobs} 个 face_scan 失败任务`);
      queryClient.invalidateQueries({ queryKey: ["face-scan-status", projectId] });
      queryClient.invalidateQueries({ queryKey: ["face-scan-failed-jobs", projectId] });
    },
    onError: (err: Error) => {
      setError(`清理失败：${err.message}`);
    },
  });

  const failedItems = failedJobsData?.items ?? [];
  const failedVisible = showAllFailed ? failedItems : failedItems.slice(0, 5);
  const statusLoadingNow = statusLoading || settingsLoading;

  return (
    <section className="space-y-4">
      <div className="flex items-center gap-2">
        {statusLoadingNow ? (
          <Loader2 className="w-4 h-4 animate-spin text-mute" />
        ) : status && (status.queued > 0 || status.running > 0) ? (
          <Loader2 className="w-4 h-4 animate-spin text-primary" />
        ) : (
          <ScanFace className="w-4 h-4 text-primary" />
        )}
        <h2 className="text-body-sm font-semibold text-ink">人脸扫描任务</h2>
      </div>

      {faceSettings && (
        <div className="bg-canvas border border-hairline rounded-md px-4 py-3 space-y-1.5">
          <p className="text-caption-sm text-mute">配置状态</p>
          <p className="text-body-sm text-ink">
            {faceSettings.face_recognition_enabled ? "已启用" : "未启用"} · provider={faceSettings.face_provider} · detector={faceSettings.face_detector_model} · embedding={faceSettings.face_embedding_model}
          </p>
          <p className="text-caption-sm text-mute">
            runtime={faceSettings.face_runtime} · min_face_size={faceSettings.min_face_size} · min_confidence={faceSettings.min_detection_confidence}
          </p>
        </div>
      )}

      {status && (
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
          <StatTile label="排队中" value={status.queued} />
          <StatTile label="进行中" value={status.running} color={status.running > 0 ? "text-primary" : "text-ink"} />
          <StatTile label="已完成" value={status.success} color="text-green-700" />
          <StatTile label="失败" value={status.failed} color={status.failed > 0 ? "text-amber-600" : "text-ink"} />
          <StatTile label="总计" value={status.total} />
        </div>
      )}

      <div className="space-y-2">
        {FACE_SCAN_SCOPE_OPTIONS.map((item) => {
          const isPending = previewMutation.isPending || startMutation.isPending;
          return (
            <div
              key={item.scope}
              className="bg-canvas border border-hairline rounded-md px-4 py-3 flex flex-wrap items-center justify-between gap-2"
            >
              <div>
                <p className="text-body-sm text-ink font-medium">{item.label}</p>
                <p className="text-caption-sm text-mute">{item.hint}</p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => previewMutation.mutate(item.scope)}
                  disabled={!canRun || isPending}
                  className="px-3 py-1.5 rounded-md border border-hairline text-btn-sm hover:bg-surface-card disabled:opacity-50 transition-colors"
                >
                  预览
                </button>
                <button
                  onClick={() => startMutation.mutate(item.scope)}
                  disabled={!canRun || isPending}
                  className="px-3 py-1.5 rounded-md bg-primary text-white text-btn-sm font-bold hover:bg-primary-pressed disabled:bg-stone transition-colors"
                >
                  启动
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {preview && (
        <div className="bg-surface-soft border border-hairline rounded-md px-4 py-3 space-y-1">
          <p className="text-body-sm font-medium text-ink">Dry-run 预览（scope={preview.scope}）</p>
          <p className="text-caption-sm text-mute">
            total={preview.total_photos} · candidate={preview.candidate_count} · skipped_active={preview.skipped_active_jobs} · skipped_scanned={preview.skipped_already_scanned}
          </p>
          <p className="text-caption-sm text-mute">
            stale={preview.stale_count} · failed={preview.failed_count} · dry_run={String(preview.dry_run)}
          </p>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <button
          onClick={() => clusterMutation.mutate()}
          disabled={!canRun || clusterMutation.isPending}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-hairline text-btn-sm hover:bg-surface-card disabled:opacity-50 transition-colors"
        >
          <ScanFace className="w-3.5 h-3.5" />
          {clusterMutation.isPending ? "聚类中…" : "聚类未知人脸"}
        </button>
        <Link
          to={reviewPath}
          className="px-3 py-1.5 rounded-md border border-hairline text-btn-sm hover:bg-surface-card transition-colors"
        >
          进入 Review Pending
        </Link>
        <Link
          to={peoplePath}
          className="px-3 py-1.5 rounded-md border border-hairline text-btn-sm hover:bg-surface-card transition-colors"
        >
          查看人物页
        </Link>
      </div>

      {message && <p className="text-caption-sm text-mute">{message}</p>}
      {error && <p className="text-caption-sm text-danger">{error}</p>}
      {!canRun && <p className="text-caption-sm text-mute">请先选择项目后再执行人脸扫描任务。</p>}

      {failedItems.length > 0 && (
        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <AlertCircle className="w-4 h-4 text-amber-500" />
              <h3 className="text-body-sm font-semibold text-ink">Face Scan 失败任务</h3>
              <span className="text-caption-sm text-mute">{failedItems.length} 个</span>
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => retryFailedMutation.mutate()}
                disabled={retryFailedMutation.isPending}
                className="flex items-center gap-1 text-btn-sm font-bold text-primary hover:text-primary-pressed disabled:text-stone transition-colors"
              >
                <RefreshCw className="w-3.5 h-3.5" />
                {retryFailedMutation.isPending ? "重试中…" : "全部重试"}
              </button>
              <button
                onClick={() => clearFailedMutation.mutate()}
                disabled={clearFailedMutation.isPending}
                className="flex items-center gap-1 text-btn-sm font-bold text-danger hover:text-danger-pressed disabled:text-stone transition-colors"
              >
                清除失败记录
              </button>
            </div>
          </div>

          <div className="space-y-1.5">
            {failedVisible.map((job) => (
              <FailedJobRow key={job.id} job={job} />
            ))}
          </div>

          {failedItems.length > 5 && (
            <button
              onClick={() => setShowAllFailed((v) => !v)}
              className="text-btn-sm text-primary hover:text-primary-pressed"
            >
              {showAllFailed ? "收起" : `显示全部 ${failedItems.length} 个`}
            </button>
          )}
        </section>
      )}
    </section>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

type TaskTab = "scan" | "ai" | "face-scan" | "ai-settings";

export function TasksPage() {
  const { currentProjectId } = useProjectContext();
  const { data: scanStatus, isLoading: scanLoading } = useScanStatus(currentProjectId);
  const { mutate: startScan, isPending, error: scanError } = useStartScan(currentProjectId);
  const { mutate: startReindex, isPending: isReindexPending } = useStartReindex(currentProjectId);
  const [searchParams, setSearchParams] = useSearchParams();

  const tabParam = searchParams.get("tab");
  const initialTab: TaskTab =
    tabParam === "scan" || tabParam === "ai" || tabParam === "face-scan" || tabParam === "ai-settings"
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
        <button onClick={() => handleTabChange("face-scan")} className={tabClass("face-scan")}>
          <span className="flex items-center gap-1.5">
            <ScanFace className="w-3.5 h-3.5" />
            人脸扫描
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

      {tab === "face-scan" && (
        <FaceScanSection projectId={currentProjectId} />
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
