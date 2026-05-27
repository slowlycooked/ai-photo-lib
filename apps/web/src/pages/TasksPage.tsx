import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link, Navigate, useSearchParams } from "react-router-dom";
import {
  Brain,
  FolderSearch,
  Play,
  RefreshCw,
  Clock,
  Settings2,
  RotateCcw,
  ScanFace,
} from "lucide-react";
import { ScanPanel } from "@/components/ScanPanel";
import { FailedJobsSection } from "@/components/tasks/FailedJobsSection";
import { TaskProgressStream } from "@/components/tasks/TaskProgressStream";
import { TaskStatusSummary } from "@/components/tasks/TaskStatusSummary";
import { api } from "@/api";
import { queryKeys } from "@/api/queryKeys";
import { CapabilityMaturityBadge } from "@/components/common/CapabilityMaturityBadge";
import { useProjectQueuedTaskStatus } from "@/hooks/useProjectQueuedTaskStatus";
import { useScanStatus, useStartScan, useStartReindex } from "@/hooks/useScan";
import { useProjectContext } from "@/contexts/ProjectContext";
import { CAPABILITY_MATURITY } from "@/lib/capabilityMaturity";

function AISection({ projectId }: { projectId: number | null }) {
  const queryClient = useQueryClient();
  const [message, setMessage] = useState<string | null>(null);
  const wasActiveRef = useRef(false);

  const { data: status, isLoading } = useProjectQueuedTaskStatus(
    queryKeys.aiStatus(projectId),
    () => api.projects.aiStatus(projectId!),
    projectId != null
  );

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

  const canRun = projectId != null;
  const isAnyPending =
    startMutation.isPending ||
    reanalyzeCompletedMutation.isPending ||
    reanalyzeAllMutation.isPending;

  const speed = status && status.success > 0 ? status.success : null;

  return (
    <section className="space-y-4">
      <TaskStatusSummary
        status={status}
        loading={isLoading}
        idleTitle="AI 图片分析"
        runningTitle="AI 分析进行中…"
        noun="任务"
      />

      {speed !== null && (
        <p className="text-caption-sm text-mute">累计已分析 {speed.toLocaleString()} 张照片</p>
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

      <TaskProgressStream
        projectId={projectId}
        title="AI 任务进度明细"
        jobType="analyze,reanalyze"
        listQueryKey="ai-jobs-progress"
      />

      {!canRun && <p className="text-caption-sm text-mute">请先选择项目后再执行 AI 分析。</p>}

      <FailedJobsSection
        projectId={projectId}
        title="AI 失败任务"
        jobType="analyze,reanalyze"
        listQueryKey="ai-jobs-failed"
      />
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
  const clusterWasActiveRef = useRef(false);
  const rematchWasActiveRef = useRef(false);
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
  const canRun = projectId != null;
  const peoplePath = canRun ? `/projects/${projectId}/people` : "/people";
  const reviewPath = canRun ? `/projects/${projectId}/people/review` : "/people";

  const { data: faceSettings, isLoading: settingsLoading } = useQuery({
    queryKey: ["project-face-settings", projectId],
    queryFn: () => api.projects.getFaceSettings(projectId!),
    enabled: canRun,
  });

  const { data: status, isLoading: statusLoading } = useProjectQueuedTaskStatus(
    ["face-scan-status", projectId],
    () => api.projects.projectFaceScanStatus(projectId!),
    canRun
  );

  const { data: clusterStatus } = useQuery({
    queryKey: ["face-cluster-unknown-status", projectId],
    queryFn: () => api.projects.projectFaceClusterUnknownStatus(projectId!),
    enabled: canRun,
    refetchInterval: (query) => {
      const d = query.state.data;
      return d && d.running ? 3000 : 15000;
    },
  });

  const { data: rematchStatus } = useQuery({
    queryKey: ["face-rematch-unknown-status", projectId],
    queryFn: () => api.projects.projectFaceRematchUnknownStatus(projectId!),
    enabled: canRun,
    refetchInterval: (query) => {
      const d = query.state.data;
      return d && d.running ? 3000 : 15000;
    },
  });

  useEffect(() => {
    const isActive = !!clusterStatus && clusterStatus.running;
    if (clusterWasActiveRef.current && !isActive && clusterStatus) {
      if (clusterStatus.status === "success") {
        setError(null);
        setMessage(
          `聚类完成：clusters=${clusterStatus.clusters_created} · persons=${clusterStatus.persons_created} · faces=${clusterStatus.faces_clustered}`
        );
        queryClient.invalidateQueries({ queryKey: ["project-people", projectId] });
        queryClient.invalidateQueries({ queryKey: ["project-review-page", projectId] });
        queryClient.invalidateQueries({ queryKey: queryKeys.projectFaces(projectId) });
      } else if (clusterStatus.status === "failed") {
        setError(`聚类失败：${clusterStatus.recent_errors[0] ?? clusterStatus.message}`);
      }
    }
    clusterWasActiveRef.current = isActive;
  }, [clusterStatus, projectId, queryClient]);

  useEffect(() => {
    const isActive = !!rematchStatus && rematchStatus.running;
    if (rematchWasActiveRef.current && !isActive && rematchStatus) {
      if (rematchStatus.status === "success") {
        setError(null);
        setMessage(
          `重匹配完成：considered=${rematchStatus.faces_considered} · matched=${rematchStatus.matched_faces} · review=${rematchStatus.review_pending}`
        );
        queryClient.invalidateQueries({ queryKey: ["project-people", projectId] });
        queryClient.invalidateQueries({ queryKey: ["project-review-page", projectId] });
        queryClient.invalidateQueries({ queryKey: queryKeys.projectFaces(projectId) });
      } else if (rematchStatus.status === "failed") {
        setError(`重匹配失败：${rematchStatus.recent_errors[0] ?? rematchStatus.message}`);
      }
    }
    rematchWasActiveRef.current = isActive;
  }, [rematchStatus, projectId, queryClient]);

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
        result.task_id
          ? `已提交全库人脸扫描任务 #${result.task_id}（scope=${result.scope}）`
          : result.created_jobs > 0
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
        result.status.status === "queued" || result.status.status === "running"
          ? `已提交未知人脸聚类任务（max_faces=${result.status.max_faces}）`
          : result.message
      );
      queryClient.invalidateQueries({ queryKey: ["face-cluster-unknown-status", projectId] });
    },
    onError: (err: Error) => {
      setError(`聚类失败：${err.message}`);
    },
  });

  const rematchMutation = useMutation({
    mutationFn: () => api.projects.rematchUnknownFaces(projectId!),
    onSuccess: (result) => {
      setError(null);
      setMessage(
        result.status.status === "queued" || result.status.status === "running"
          ? `已提交未知人脸重匹配任务（max_faces=${result.status.max_faces}）`
          : result.message
      );
      queryClient.invalidateQueries({ queryKey: ["face-rematch-unknown-status", projectId] });
    },
    onError: (err: Error) => {
      setError(`重匹配失败：${err.message}`);
    },
  });

  const statusLoadingNow = statusLoading || settingsLoading;

  return (
    <section className="space-y-4">
      <TaskStatusSummary
        status={status}
        loading={statusLoadingNow}
        idleTitle="人脸扫描任务"
        runningTitle="人脸扫描进行中…"
        noun="任务"
      />

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

      {clusterStatus && clusterStatus.status !== "idle" && (
        <div className="bg-surface-soft border border-hairline rounded-md px-4 py-3 space-y-1">
          <p className="text-body-sm font-medium text-ink">
            未知人脸聚类任务 · {clusterStatus.status}
          </p>
          <p className="text-caption-sm text-mute">
            task={clusterStatus.task_id ?? "-"} · max_faces={clusterStatus.max_faces} · errors={clusterStatus.errors}
          </p>
          <p className="text-caption-sm text-mute">
            clusters={clusterStatus.clusters_created} · persons={clusterStatus.persons_created} · faces={clusterStatus.faces_clustered} · assignments={clusterStatus.assignments_created}
          </p>
          <p className="text-caption-sm text-mute">{clusterStatus.message}</p>
          {clusterStatus.recent_errors.length > 0 && (
            <p className="text-caption-sm text-danger">
              最近错误：{clusterStatus.recent_errors[clusterStatus.recent_errors.length - 1]}
            </p>
          )}
        </div>
      )}

      {rematchStatus && rematchStatus.status !== "idle" && (
        <div className="bg-surface-soft border border-hairline rounded-md px-4 py-3 space-y-1">
          <p className="text-body-sm font-medium text-ink">
            未知人脸重匹配任务 · {rematchStatus.status}
          </p>
          <p className="text-caption-sm text-mute">
            task={rematchStatus.task_id ?? "-"} · max_faces={rematchStatus.max_faces} · errors={rematchStatus.errors}
          </p>
          <p className="text-caption-sm text-mute">
            considered={rematchStatus.faces_considered} · matched={rematchStatus.matched_faces} · auto={rematchStatus.auto_assigned} · review={rematchStatus.review_pending}
          </p>
          <p className="text-caption-sm text-mute">{rematchStatus.message}</p>
          {rematchStatus.recent_errors.length > 0 && (
            <p className="text-caption-sm text-danger">
              最近错误：{rematchStatus.recent_errors[rematchStatus.recent_errors.length - 1]}
            </p>
          )}
        </div>
      )}

      <p className="text-caption-sm text-mute flex flex-wrap items-center gap-2">
        <CapabilityMaturityBadge item={CAPABILITY_MATURITY.face_clustering} compact />
        <CapabilityMaturityBadge item={CAPABILITY_MATURITY.face_rematch_unknown} compact />
        <span>{CAPABILITY_MATURITY.face_clustering.hint}</span>
        <span>{CAPABILITY_MATURITY.face_rematch_unknown.hint}</span>
      </p>

      <div className="flex flex-wrap items-center gap-2">
        <button
          onClick={() => clusterMutation.mutate()}
          disabled={!canRun || clusterMutation.isPending || !!clusterStatus?.running}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-hairline text-btn-sm hover:bg-surface-card disabled:opacity-50 transition-colors"
        >
          <ScanFace className="w-3.5 h-3.5" />
          {clusterMutation.isPending
            ? "提交中…"
            : clusterStatus?.running
              ? "聚类任务进行中…"
              : "聚类未知人脸"}
        </button>
        <button
          onClick={() => rematchMutation.mutate()}
          disabled={!canRun || rematchMutation.isPending || !!rematchStatus?.running}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-hairline text-btn-sm hover:bg-surface-card disabled:opacity-50 transition-colors"
        >
          <RefreshCw className="w-3.5 h-3.5" />
          {rematchMutation.isPending
            ? "提交中…"
            : rematchStatus?.running
              ? "重匹配进行中…"
              : "重匹配未知人脸"}
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

      <TaskProgressStream
        projectId={projectId}
        title="人脸扫描任务进度明细"
        jobType="face_scan"
        listQueryKey="face-scan-jobs-progress"
      />

      {!canRun && <p className="text-caption-sm text-mute">请先选择项目后再执行人脸扫描任务。</p>}

      <FailedJobsSection
        projectId={projectId}
        title="Face Scan 失败任务"
        jobType="face_scan"
        listQueryKey="face-scan-failed-jobs"
      />
    </section>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

type TaskTab = "scan" | "ai" | "face-scan";

export function TasksPage() {
  const { currentProjectId } = useProjectContext();
  const { data: scanStatus, isLoading: scanLoading } = useScanStatus(currentProjectId);
  const { mutate: startScan, isPending, error: scanError } = useStartScan(currentProjectId);
  const { mutate: startReindex, isPending: isReindexPending } = useStartReindex(currentProjectId);
  const [searchParams, setSearchParams] = useSearchParams();

  const tabParam = searchParams.get("tab");
  if (tabParam === "ai-settings") {
    return (
      <Navigate
        to={currentProjectId != null ? `/projects/${currentProjectId}/settings/ai` : "/settings"}
        replace
      />
    );
  }

  const initialTab: TaskTab =
    tabParam === "scan" || tabParam === "ai" || tabParam === "face-scan"
      ? tabParam
      : "scan";
  const [tab, setTab] = useState<TaskTab>(initialTab);

  const handleTabChange = (next: TaskTab) => {
    setTab(next);
    setSearchParams(next === "scan" ? {} : { tab: next }, { replace: true });
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
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="space-y-1">
          <h1 className="text-heading-md font-semibold text-ink flex items-center gap-2">
            <Clock className="w-5 h-5" />
            任务中心
          </h1>
          <p className="text-caption-sm text-mute">
            这里只保留执行类操作；模型、Prompt、Embedding 与搜索参数已收敛到独立配置页。
          </p>
        </div>
        <Link
          to={currentProjectId != null ? `/projects/${currentProjectId}/settings/ai` : "/settings"}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-hairline text-btn-sm hover:bg-surface-card transition-colors"
        >
          <Settings2 className="w-3.5 h-3.5" />
          打开项目 AI 配置
        </Link>
      </div>

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
    </main>
  );
}
