import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link, Navigate, useSearchParams } from "react-router-dom";
import {
  Brain,
  FolderSearch,
  Play,
  RefreshCw,
  Clock,
  RotateCcw,
  ScanFace,
  XCircle,
} from "lucide-react";
import { ScanPanel } from "@/components/ScanPanel";
import { FailedJobsSection } from "@/components/tasks/FailedJobsSection";
import { ProjectTaskFailureDetails } from "@/components/tasks/ProjectTaskFailureDetails";
import { ProjectTaskHistorySection } from "@/components/tasks/ProjectTaskHistorySection";
import { TaskProgressStream } from "@/components/tasks/TaskProgressStream";
import { TaskStatusSummary } from "@/components/tasks/TaskStatusSummary";
import { api } from "@/api";
import { queryKeys } from "@/api/queryKeys";
import { CapabilityMaturityBadge } from "@/components/common/CapabilityMaturityBadge";
import { useProjectQueuedTaskStatus } from "@/hooks/useProjectQueuedTaskStatus";
import { useCancelScan, useScanStatus, useStartScan, useStartReindex } from "@/hooks/useScan";
import { useProjectContext } from "@/contexts/ProjectContext";
import { CAPABILITY_MATURITY } from "@/lib/capabilityMaturity";

function AISection({ projectId }: { projectId: number | null }) {
  const queryClient = useQueryClient();
  const [message, setMessage] = useState<string | null>(null);
  const wasActiveRef = useRef(false);

  const { data: status, isLoading } = useProjectQueuedTaskStatus(
    queryKeys.aiStatus(projectId),
    () => api.projectAiJobs.status(projectId!),
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
    mutationFn: () => api.projectAiJobs.startAnalysis(projectId!),
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
      api.projectAiJobs.reanalyze(projectId!, {
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
      api.projectAiJobs.reanalyze(projectId!, {
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

  const forceStopMutation = useMutation({
    mutationFn: () => api.projectAiJobs.forceStop(projectId!, "analyze,reanalyze"),
    onSuccess: (data) => {
      setMessage(
        data.stopped_jobs > 0
          ? `已强制停止 ${data.stopped_jobs} 个任务（queued=${data.stopped_queued}, running=${data.stopped_running}）`
          : "当前没有可停止的 AI 任务"
      );
      queryClient.invalidateQueries({ queryKey: queryKeys.aiStatus(projectId) });
      queryClient.invalidateQueries({ queryKey: ["ai-jobs-progress", projectId] });
      queryClient.invalidateQueries({ queryKey: ["ai-jobs-failed", projectId] });
      setTimeout(() => setMessage(null), 5000);
    },
    onError: (err: Error) => setMessage(`强制停止失败：${err.message}`),
  });

  const canRun = projectId != null;
  const isAnyPending =
    startMutation.isPending ||
    reanalyzeCompletedMutation.isPending ||
    reanalyzeAllMutation.isPending;

  const analyzedCount = status?.analyzed_count ?? null;
  const totalPhotos = status?.total_photos ?? null;
  const analysisCoverage =
    analyzedCount !== null && totalPhotos !== null && totalPhotos > 0
      ? Math.min(100, Math.max(0, Math.round((analyzedCount / totalPhotos) * 100)))
      : null;

  return (
    <section className="space-y-4">
      <TaskStatusSummary
        status={status}
        loading={isLoading}
        idleTitle="AI 图片分析"
        runningTitle="AI 分析进行中…"
        noun="任务"
      />

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(320px,0.72fr)] lg:items-start">
        <section className="rounded-md border border-hairline bg-canvas p-4 sm:p-5" aria-labelledby="ai-actions-title">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h3 id="ai-actions-title" className="text-body-sm font-semibold text-ink">
                分析操作
              </h3>
              <p className="mt-0.5 text-caption-sm text-mute">增量处理优先，重跑会替换已有结果。</p>
            </div>
            {analysisCoverage !== null && (
              <span className="text-body-sm font-semibold tabular-nums text-ink">
                {analysisCoverage}%
              </span>
            )}
          </div>

          {analyzedCount !== null && analyzedCount > 0 && (
            <div
              className="mt-4"
              role={analysisCoverage !== null ? "img" : undefined}
              aria-label={analysisCoverage !== null ? `照片分析覆盖率 ${analysisCoverage}%` : undefined}
            >
              {analysisCoverage !== null && (
                <div className="h-2 overflow-hidden rounded-full bg-secondary-bg">
                  <div
                    className="h-full rounded-full bg-primary transition-[width] duration-300 motion-reduce:transition-none"
                    style={{ width: `${analysisCoverage}%` }}
                  />
                </div>
              )}
              <p className="mt-1.5 text-caption-sm tabular-nums text-mute">
                {analyzedCount.toLocaleString()}
                {totalPhotos !== null && totalPhotos > 0
                  ? ` / ${totalPhotos.toLocaleString()} 张照片`
                  : " 张照片已分析"}
              </p>
            </div>
          )}

          <div className="mt-4 grid gap-2 sm:grid-cols-2">
            <button
              type="button"
              onClick={() => startMutation.mutate()}
              disabled={isAnyPending || !canRun}
              className="inline-flex min-h-11 items-center justify-center gap-1.5 rounded-md bg-primary px-3 text-btn-sm font-bold text-white transition-colors hover:bg-primary-pressed disabled:bg-stone focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-outer"
            >
              <Play className="h-3.5 w-3.5" aria-hidden="true" />
              {startMutation.isPending ? "启动中…" : "开始分析"}
            </button>
            <button
              type="button"
              onClick={() => reanalyzeCompletedMutation.mutate()}
              disabled={isAnyPending || !canRun}
              className="inline-flex min-h-11 items-center justify-center gap-1.5 rounded-md border border-hairline px-3 text-btn-sm text-ink transition-colors hover:bg-surface-soft disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-outer"
            >
              <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
              {reanalyzeCompletedMutation.isPending ? "处理中…" : "重跑已完成"}
            </button>
            <button
              type="button"
              onClick={() => {
                if (!window.confirm("这会清除当前项目已有 AI 分析结果并重新生成，确认继续？")) return;
                reanalyzeAllMutation.mutate();
              }}
              disabled={isAnyPending || !canRun}
              className="inline-flex min-h-11 items-center justify-center gap-1.5 rounded-md border border-hairline px-3 text-btn-sm text-ink transition-colors hover:bg-surface-soft disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-outer"
            >
              <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
              {reanalyzeAllMutation.isPending ? "处理中…" : "重跑全部"}
            </button>
            {!!status && (status.queued > 0 || status.running > 0) && (
          <button
            type="button"
            onClick={() => {
              if (!window.confirm("将强制停止当前项目中进行中的 AI 分析任务，确认继续？")) return;
              forceStopMutation.mutate();
            }}
            disabled={forceStopMutation.isPending || !canRun}
                className="inline-flex min-h-11 items-center justify-center gap-1.5 rounded-md border border-red-200 px-3 text-btn-sm text-danger transition-colors hover:bg-red-50 disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-outer"
          >
                <XCircle className="h-3.5 w-3.5" aria-hidden="true" />
            {forceStopMutation.isPending ? "停止中…" : "强制停止分析"}
          </button>
        )}
          </div>

          {message && (
            <p className="mt-3 rounded-sm bg-surface-soft px-3 py-2 text-caption-sm text-secondary" aria-live="polite">
              {message}
            </p>
          )}
          {!canRun && <p className="mt-3 text-caption-sm text-mute">请先选择项目。</p>}
        </section>

        <TaskProgressStream
          projectId={projectId}
          title="AI 任务进度明细"
          jobType="analyze,reanalyze"
          listQueryKey="ai-jobs-progress"
        />
      </div>

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
const DEFAULT_FACE_REMATCH_MAX_FACES = 10000;
const MAX_FACE_REMATCH_MAX_FACES = 10000;

type FaceRematchMutationPayload =
  | { scope: "unknown" }
  | { scope: "project"; maxFaces: number };

function parseFaceRematchMaxFaces(value: string): number | null {
  const parsed = Number(value);
  if (!Number.isInteger(parsed)) return null;
  if (parsed < 1 || parsed > MAX_FACE_REMATCH_MAX_FACES) return null;
  return parsed;
}

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
  const [projectRematchMaxFaces, setProjectRematchMaxFaces] = useState(
    String(DEFAULT_FACE_REMATCH_MAX_FACES)
  );
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
  const peoplePath = canRun ? `/projects/${projectId}/people` : "/photos";
  const reviewPath = canRun ? `/projects/${projectId}/people/review` : "/photos";
  const parsedProjectRematchMaxFaces = parseFaceRematchMaxFaces(projectRematchMaxFaces);
  const hasInvalidProjectRematchMaxFaces = parsedProjectRematchMaxFaces == null;

  const { data: faceSettings, isLoading: settingsLoading } = useQuery({
    queryKey: ["project-face-settings", projectId],
    queryFn: () => api.projectSettings.getFace(projectId!),
    enabled: canRun,
  });

  const { data: status, isLoading: statusLoading } = useProjectQueuedTaskStatus(
    ["face-scan-status", projectId],
    () => api.projectFaces.projectScanStatus(projectId!),
    canRun
  );

  const { data: clusterStatus } = useQuery({
    queryKey: ["face-cluster-unknown-status", projectId],
    queryFn: () => api.projectFaces.clusterUnknownStatus(projectId!),
    enabled: canRun,
    refetchInterval: (query) => {
      const d = query.state.data;
      return d && d.running ? 3000 : 15000;
    },
  });

  const { data: rematchStatus } = useQuery({
    queryKey: ["face-rematch-unknown-status", projectId],
    queryFn: () => api.projectFaces.rematchUnknownStatus(projectId!),
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
        setError(`聚类失败：${clusterStatus.message}`);
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
        setError(`重匹配失败：${rematchStatus.message}`);
      }
    }
    rematchWasActiveRef.current = isActive;
  }, [rematchStatus, projectId, queryClient]);

  const previewMutation = useMutation({
    mutationFn: (scope: FaceScanScope) =>
      api.projectFaces.startProjectScan(projectId!, { scope, dry_run: true }),
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
      api.projectFaces.startProjectScan(projectId!, { scope }),
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
    mutationFn: () => api.projectFaces.clusterUnknown(projectId!),
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
    mutationFn: (payload: FaceRematchMutationPayload = { scope: "unknown" }) =>
      api.projectFaces.rematchUnknown(
        projectId!,
        payload.scope === "project"
          ? { scope: "project", max_faces: payload.maxFaces }
          : undefined,
      ),
    onSuccess: (result) => {
      setError(null);
      const label = result.status.scope === "project" ? "全项目已打标人物聚合" : "未知人脸重匹配";
      setMessage(
        result.status.status === "queued" || result.status.status === "running"
          ? `已提交${label}任务（max_faces=${result.status.max_faces}）`
          : result.message
      );
      queryClient.invalidateQueries({ queryKey: ["face-rematch-unknown-status", projectId] });
    },
    onError: (err: Error) => {
      setError(`重匹配失败：${err.message}`);
    },
  });

  const cancelFaceScanMutation = useMutation({
    mutationFn: () => api.projectFaces.cancelProjectScan(projectId!),
    onSuccess: () => {
      setError(null);
      setMessage("已请求取消人脸扫描任务");
      queryClient.invalidateQueries({ queryKey: ["face-scan-status", projectId] });
    },
    onError: (err: Error) => setError(`取消失败：${err.message}`),
  });

  const forceStopFaceJobsMutation = useMutation({
    mutationFn: () => api.projectAiJobs.forceStop(projectId!, "face_scan"),
    onSuccess: (result) => {
      setError(null);
      setMessage(
        result.stopped_jobs > 0
          ? `已强制停止 ${result.stopped_jobs} 个人脸分析任务（queued=${result.stopped_queued}, running=${result.stopped_running}）`
          : "当前没有可停止的人脸分析任务"
      );
      queryClient.invalidateQueries({ queryKey: ["face-scan-status", projectId] });
      queryClient.invalidateQueries({ queryKey: ["face-scan-jobs-progress", projectId] });
      queryClient.invalidateQueries({ queryKey: ["face-scan-failed-jobs", projectId] });
      queryClient.invalidateQueries({ queryKey: queryKeys.aiStatus(projectId) });
    },
    onError: (err: Error) => setError(`强制停止失败：${err.message}`),
  });

  const cancelClusterMutation = useMutation({
    mutationFn: () => api.projectFaces.cancelClusterUnknown(projectId!),
    onSuccess: () => {
      setError(null);
      setMessage("已请求取消未知人脸聚类任务");
      queryClient.invalidateQueries({ queryKey: ["face-cluster-unknown-status", projectId] });
    },
    onError: (err: Error) => setError(`取消失败：${err.message}`),
  });

  const cancelRematchMutation = useMutation({
    mutationFn: () => api.projectFaces.cancelRematchUnknown(projectId!),
    onSuccess: () => {
      setError(null);
      setMessage("已请求取消未知人脸重匹配任务");
      queryClient.invalidateQueries({ queryKey: ["face-rematch-unknown-status", projectId] });
    },
    onError: (err: Error) => setError(`取消失败：${err.message}`),
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
          <ProjectTaskFailureDetails
            projectId={projectId}
            taskId={clusterStatus.task_id}
            expectedCount={clusterStatus.errors}
            title="聚类失败明细"
            compact
          />
        </div>
      )}

      {rematchStatus && rematchStatus.status !== "idle" && (
        <div className="bg-surface-soft border border-hairline rounded-md px-4 py-3 space-y-1">
          <p className="text-body-sm font-medium text-ink">
            {rematchStatus.scope === "project" ? "全项目已打标人物聚合任务" : "未知人脸重匹配任务"} · {rematchStatus.status}
          </p>
          <p className="text-caption-sm text-mute">
            task={rematchStatus.task_id ?? "-"} · scope={rematchStatus.scope} · max_faces={rematchStatus.max_faces} · errors={rematchStatus.errors}
          </p>
          <p className="text-caption-sm text-mute">
            considered={rematchStatus.faces_considered} · matched={rematchStatus.matched_faces} · auto={rematchStatus.auto_assigned} · review={rematchStatus.review_pending}
          </p>
          <p className="text-caption-sm text-mute">{rematchStatus.message}</p>
          <ProjectTaskFailureDetails
            projectId={projectId}
            taskId={rematchStatus.task_id}
            expectedCount={rematchStatus.errors}
            title="重匹配失败明细"
            compact
          />
        </div>
      )}

      <p className="text-caption-sm text-mute flex flex-wrap items-center gap-2">
        <CapabilityMaturityBadge item={CAPABILITY_MATURITY.face_clustering} compact />
        <CapabilityMaturityBadge item={CAPABILITY_MATURITY.face_rematch_unknown} compact />
        <span>{CAPABILITY_MATURITY.face_clustering.hint}</span>
        <span>{CAPABILITY_MATURITY.face_rematch_unknown.hint}</span>
      </p>

      <div className="flex flex-wrap items-center gap-2">
        {!!status?.running && (
          <button
            onClick={() => cancelFaceScanMutation.mutate()}
            disabled={!canRun || cancelFaceScanMutation.isPending}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-red-200 text-danger text-btn-sm hover:bg-red-50 disabled:opacity-50 transition-colors"
          >
            <XCircle className="w-3.5 h-3.5" />
            {cancelFaceScanMutation.isPending ? "取消中…" : "取消人脸扫描"}
          </button>
        )}
        {!!status && (status.queued > 0 || status.running > 0) && (
          <button
            onClick={() => {
              if (!window.confirm("将强制停止当前项目的人脸分析任务，确认继续？")) return;
              forceStopFaceJobsMutation.mutate();
            }}
            disabled={!canRun || forceStopFaceJobsMutation.isPending}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-red-200 text-danger text-btn-sm hover:bg-red-50 disabled:opacity-50 transition-colors"
          >
            <XCircle className="w-3.5 h-3.5" />
            {forceStopFaceJobsMutation.isPending ? "停止中…" : "强制停止人脸分析"}
          </button>
        )}
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
        {!!clusterStatus?.running && (
          <button
            onClick={() => cancelClusterMutation.mutate()}
            disabled={!canRun || cancelClusterMutation.isPending}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-red-200 text-danger text-btn-sm hover:bg-red-50 disabled:opacity-50 transition-colors"
          >
            <XCircle className="w-3.5 h-3.5" />
            {cancelClusterMutation.isPending ? "取消中…" : "取消聚类"}
          </button>
        )}
        <button
          onClick={() => rematchMutation.mutate({ scope: "unknown" })}
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
        <label className="flex items-center gap-1.5 text-caption-sm text-mute">
          <span>max_faces</span>
          <input
            aria-label="全项目聚合 max_faces"
            type="number"
            min={1}
            max={MAX_FACE_REMATCH_MAX_FACES}
            step={1}
            value={projectRematchMaxFaces}
            onChange={(event) => setProjectRematchMaxFaces(event.target.value)}
            disabled={!canRun || rematchMutation.isPending || !!rematchStatus?.running}
            aria-invalid={hasInvalidProjectRematchMaxFaces}
            className="w-28 rounded-md border border-hairline bg-canvas px-2 py-1 text-body-sm text-ink disabled:opacity-50"
            title={`本次最多处理的人脸数，范围 1-${MAX_FACE_REMATCH_MAX_FACES}`}
          />
        </label>
        <button
          onClick={() => {
            if (parsedProjectRematchMaxFaces == null) {
              setError(`max_faces 必须是 1-${MAX_FACE_REMATCH_MAX_FACES} 的整数`);
              return;
            }
            rematchMutation.mutate({
              scope: "project",
              maxFaces: parsedProjectRematchMaxFaces,
            });
          }}
          disabled={
            !canRun ||
            rematchMutation.isPending ||
            !!rematchStatus?.running ||
            hasInvalidProjectRematchMaxFaces
          }
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-primary text-white text-btn-sm font-bold hover:bg-primary-pressed disabled:bg-stone transition-colors"
          title="扫描已有 embedding 的人脸，把相似候选聚合到已命名人物下面"
        >
          <RefreshCw className="w-3.5 h-3.5" />
          {rematchMutation.isPending
            ? "提交中…"
            : rematchStatus?.running
              ? "聚合任务进行中…"
              : "聚合到已打标人物"}
        </button>
        {!!rematchStatus?.running && (
          <button
            onClick={() => cancelRematchMutation.mutate()}
            disabled={!canRun || cancelRematchMutation.isPending}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-red-200 text-danger text-btn-sm hover:bg-red-50 disabled:opacity-50 transition-colors"
          >
            <XCircle className="w-3.5 h-3.5" />
            {cancelRematchMutation.isPending ? "取消中…" : "取消重匹配"}
          </button>
        )}
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
  const { mutate: cancelScan, isPending: isCancelScanPending } = useCancelScan(currentProjectId);
  const [searchParams, setSearchParams] = useSearchParams();

  const tabParam = searchParams.get("tab");
  if (tabParam === "ai-settings") {
    return (
      <Navigate
        to={currentProjectId != null ? `/projects/${currentProjectId}/settings/vision-ai` : "/photos"}
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
      "inline-flex min-h-11 items-center justify-center gap-1.5 rounded-md px-3 text-btn-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-outer",
      tab === t
        ? "bg-canvas text-primary shadow-sm"
        : "text-mute hover:bg-canvas/70 hover:text-ink",
    ].join(" ");

  return (
    <main className="mx-auto max-w-6xl space-y-5 px-4 py-6 sm:px-6 lg:py-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-heading-md font-semibold text-ink">
            <Clock className="h-5 w-5 text-primary" aria-hidden="true" />
            任务中心
          </h1>
        </div>
      </div>

      {/* Tab nav */}
      <div className="grid grid-cols-3 gap-1 rounded-lg bg-surface-soft p-1" role="tablist" aria-label="任务类型">
        <button
          type="button"
          role="tab"
          aria-selected={tab === "scan"}
          aria-controls="task-panel-scan"
          onClick={() => handleTabChange("scan")}
          className={tabClass("scan")}
        >
          <FolderSearch className="h-3.5 w-3.5" aria-hidden="true" />
          <span className="hidden sm:inline">照片扫描</span>
          <span className="sm:hidden">扫描</span>
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "ai"}
          aria-controls="task-panel-ai"
          onClick={() => handleTabChange("ai")}
          className={tabClass("ai")}
        >
          <Brain className="h-3.5 w-3.5" aria-hidden="true" />
          <span className="hidden sm:inline">AI 分析</span>
          <span className="sm:hidden">AI</span>
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "face-scan"}
          aria-controls="task-panel-face-scan"
          onClick={() => handleTabChange("face-scan")}
          className={tabClass("face-scan")}
        >
          <ScanFace className="h-3.5 w-3.5" aria-hidden="true" />
          <span className="hidden sm:inline">人脸扫描</span>
          <span className="sm:hidden">人脸</span>
        </button>
      </div>

      {/* Tab content */}
      {tab === "scan" && (
        <section id="task-panel-scan" role="tabpanel" className="space-y-3">
          <ScanPanel
            projectId={currentProjectId}
            status={scanStatus}
            isLoading={scanLoading}
            onStart={() => startScan()}
            isPending={isPending}
            mutationError={scanError?.message ?? null}
            onReindex={(scope) => startReindex(scope)}
            isReindexPending={isReindexPending}
            onCancel={() => cancelScan()}
            isCancelPending={isCancelScanPending}
          />
        </section>
      )}

      {tab === "ai" && (
        <section id="task-panel-ai" role="tabpanel">
          <AISection projectId={currentProjectId} />
        </section>
      )}

      {tab === "face-scan" && (
        <section id="task-panel-face-scan" role="tabpanel">
          <FaceScanSection projectId={currentProjectId} />
        </section>
      )}

      <ProjectTaskHistorySection projectId={currentProjectId} />
    </main>
  );
}
