import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArchiveRestore,
  BarChart3,
  CheckCircle2,
  ChevronDown,
  Download,
  FolderSearch,
  Image as ImageIcon,
  Loader2,
  Play,
  RefreshCw,
  Save,
  ShieldCheck,
  Square,
  Trash2,
} from "lucide-react";
import { Link, Navigate, useParams } from "react-router-dom";
import {
  api,
  type PhotoQuarantineItem,
  type PhotoQuarantineListResponse,
  type ProjectPhotoQuarantineSettingsUpdate,
} from "@/api";
import { BASE } from "@/api/client";
import { queryKeys } from "@/api/queryKeys";
import { useAuth } from "@/contexts/AuthContext";
import { useProjectContext } from "@/contexts/ProjectContext";
import { canManageProjects } from "@/lib/permissions";

const PENDING_STATUSES = "review,analysis_retry_queued,restore_conflict,restore_failed,queue_failed,move_failed";
const RESTORABLE_STATUSES = new Set(["quarantined", "restore_conflict", "restore_failed"]);
const KEEP_STATUSES = new Set([
  "review",
  "analysis_failed",
  "move_failed",
  "queue_failed",
  "kept",
  "restored",
]);
const DELETE_APPROVAL_STATUSES = new Set([
  "review",
  "move_failed",
  "queue_failed",
  "kept",
  "restored",
]);
const DELETE_REQUEST_STATUSES = new Set([...DELETE_APPROVAL_STATUSES, "delete_queued"]);
const PAGE_SIZE = 24;

const STATUS_OPTIONS = [
  { value: PENDING_STATUSES, label: "待处理" },
  { value: "delete_queued,quarantined", label: "已提交删除" },
  { value: "kept,restored", label: "已保留" },
  { value: "analysis_failed,queue_failed,move_failed,restore_conflict,restore_failed", label: "异常" },
] as const;

const STATUS_LABELS: Record<string, string> = {
  review: "待审核",
  delete_queued: "等待后台删除",
  quarantined: "待人工删除",
  restored: "已放回",
  kept: "已保留",
  deleted_confirmed: "已确认删除",
  analysis_failed: "识别失败",
  analysis_retry_queued: "等待重新识别",
  move_failed: "移动失败",
  queue_failed: "加入删除队列失败",
  restore_conflict: "原位置已有文件",
  restore_failed: "放回失败",
};

const CLASS_LABELS: Record<string, string> = {
  suspected_duplicate: "疑似重复",
  accidental_capture: "误触拍摄",
  severe_blur: "严重模糊",
  obscured_lens: "镜头遮挡",
  blank_image: "空白图片",
  meaningless_test: "无意义测试图",
  meaningless_test_image: "无意义测试图",
  screenshot: "屏幕截图",
  construction_clutter: "工地杂物",
};

const CLASS_FILTER_OPTIONS = [
  { value: "", label: "全部类别" },
  { value: "suspected_duplicate", label: "疑似重复" },
  { value: "accidental_capture", label: "误触拍摄" },
  { value: "severe_blur", label: "严重模糊" },
  { value: "obscured_lens", label: "镜头遮挡" },
  { value: "blank_image", label: "空白图片" },
  { value: "meaningless_test_image", label: "无意义测试图" },
  { value: "screenshot", label: "屏幕截图" },
  { value: "construction_clutter", label: "工地杂物" },
  { value: "valuable", label: "有保留价值" },
  { value: "uncertain", label: "不确定" },
  { value: "other", label: "其他" },
] as const;
function canonicalClassification(value: string) {
  return value === "meaningless_test" ? "meaningless_test_image" : value;
}


const SENSITIVE_CONTENT_LABELS: Record<string, string> = {
  explicit_sexual_content: "露骨色情",
  sexual_content: "色情内容",
  nudity: "裸露",
  suggestive_content: "性暗示",
  graphic_violence: "重度暴力",
  violence: "暴力",
  gore: "血腥",
  self_harm: "自残",
  drug_use: "药物使用",
  disturbing_content: "令人不适",
  other_adult_content: "其他成人内容",
};

function fieldClass() {
  return "mt-1 min-h-11 w-full rounded-md border border-hairline bg-surface-card px-3 py-2 text-body-sm text-ink focus:outline-none focus:ring-2 focus:ring-focus-outer";
}

export function PhotoQuarantinePage() {
  const { projectId } = useParams();
  const auth = useAuth();
  const queryClient = useQueryClient();
  const { projects, currentProjectId, setCurrentProjectId } = useProjectContext();
  const routeProjectId = projectId ? Number(projectId) : NaN;
  const selectedProjectId = Number.isFinite(routeProjectId) ? routeProjectId : currentProjectId;
  const projectExists = selectedProjectId != null && projects.some((project) => project.id === selectedProjectId);
  const canManage = canManageProjects(auth.session);
  const [statusFilter, setStatusFilter] = useState<string>(PENDING_STATUSES);
  const [labelFilter, setLabelFilter] = useState<"" | "KEEP" | "TRASH" | "UNLABELED">("");
  const [classificationFilter, setClassificationFilter] = useState("");
  const [page, setPage] = useState(0);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [retryFailedOnStart, setRetryFailedOnStart] = useState(false);
  const [form, setForm] = useState<ProjectPhotoQuarantineSettingsUpdate | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (selectedProjectId != null && selectedProjectId !== currentProjectId) {
      setCurrentProjectId(selectedProjectId);
    }
  }, [currentProjectId, selectedProjectId, setCurrentProjectId]);

  const settingsQuery = useQuery({
    queryKey: queryKeys.photoQuarantineSettings(selectedProjectId),
    queryFn: () => api.photoQuarantine.getSettings(selectedProjectId!),
    enabled: projectExists,
  });
  const itemsQuery = useQuery({
    queryKey: queryKeys.photoQuarantineItems(
      selectedProjectId,
      statusFilter,
      page * PAGE_SIZE,
      labelFilter,
      classificationFilter,
    ),
    queryFn: () => api.photoQuarantine.list(
      selectedProjectId!,
      statusFilter,
      PAGE_SIZE,
      page * PAGE_SIZE,
      labelFilter || undefined,
      classificationFilter || undefined,
    ),
    enabled: projectExists,
    refetchInterval: 30_000,
  });
  const calibrationQuery = useQuery({
    queryKey: queryKeys.photoQuarantineCalibration(selectedProjectId),
    queryFn: () => api.photoQuarantine.getCalibration(selectedProjectId!),
    enabled: projectExists,
  });
  const taskQuery = useQuery({
    queryKey: ["photo-quarantine-latest-task", selectedProjectId],
    queryFn: () => api.projectTasks.list(selectedProjectId!, {
      task_type: "photo_quarantine_analysis",
      limit: 1,
    }),
    enabled: projectExists,
    refetchInterval: (query) => {
      const task = query.state.data?.items[0];
      return task && (task.status === "queued" || task.status === "running") ? 3_000 : 15_000;
    },
  });
  const latestTask = taskQuery.data?.items[0];
  const analysisActive = latestTask?.status === "queued" || latestTask?.status === "running";
  const cancelRequested = latestTask?.progress_payload?.cancel_requested === true;
  const retryFailedTask = latestTask?.request_params?.trigger === "manual_retry_failed";
  const retryQueueQuery = useQuery({
    queryKey: ["photo-quarantine-retry-progress", selectedProjectId, latestTask?.id],
    queryFn: () => api.photoQuarantine.list(
      selectedProjectId!,
      "analysis_retry_queued",
      1,
      0,
    ),
    enabled: projectExists && analysisActive && retryFailedTask,
    refetchInterval: 3_000,
  });

  useEffect(() => {
    const value = settingsQuery.data;
    if (!value) return;
    setForm({
      enabled: value.enabled,
      dry_run: value.dry_run,
      start_hour: value.start_hour,
      end_hour: value.end_hour,
      timezone: value.timezone,
      model_name: value.model_name,
      retention_days: value.retention_days,
    });
  }, [settingsQuery.data]);

  useEffect(() => {
    setPage(0);
    setSelectedIds(new Set());
  }, [statusFilter, labelFilter, classificationFilter, selectedProjectId]);

  useEffect(() => {
    setSelectedIds(new Set());
  }, [page]);

  const refreshItems = () => {
    queryClient.invalidateQueries({ queryKey: ["photo-quarantine-items", selectedProjectId] });
    queryClient.invalidateQueries({ queryKey: queryKeys.photosBase(selectedProjectId) });
    queryClient.invalidateQueries({
      queryKey: queryKeys.photoQuarantineCalibration(selectedProjectId),
    });
  };

  const updateCachedItems = (updatedItems: PhotoQuarantineItem[]) => {
    if (updatedItems.length === 0) return;
    const updatedById = new Map(updatedItems.map((item) => [item.id, item]));
    const visibleStatuses = new Set(
      statusFilter.split(",").map((status) => status.trim()).filter(Boolean),
    );
    const matchesActiveFilter = (item: PhotoQuarantineItem) => {
      if (!visibleStatuses.has(item.status)) return false;
      if (
        classificationFilter
        && canonicalClassification(item.classification) !== classificationFilter
      ) return false;
      if (labelFilter === "UNLABELED") return item.human_label == null;
      if (labelFilter) return item.human_label === labelFilter;
      return true;
    };
    queryClient.setQueryData<PhotoQuarantineListResponse>(
      queryKeys.photoQuarantineItems(
        selectedProjectId,
        statusFilter,
        page * PAGE_SIZE,
        labelFilter,
        classificationFilter,
      ),
      (current) => current
        ? (() => {
          const nextItems = current.items
            .map((item) => updatedById.get(item.id) ?? item)
            .filter(matchesActiveFilter);
          return {
            ...current,
            total: Math.max(0, current.total - (current.items.length - nextItems.length)),
            items: nextItems,
          };
        })()
        : current,
    );
  };

  const saveMutation = useMutation({
    mutationFn: () => api.photoQuarantine.updateSettings(selectedProjectId!, form!),
    onSuccess: (data) => {
      queryClient.setQueryData(queryKeys.photoQuarantineSettings(selectedProjectId), data);
      setMessage("设置已保存");
    },
    onError: (error: Error) => setMessage(`保存失败：${error.message}`),
  });
  const runMutation = useMutation({
    mutationFn: (retryFailed: boolean) => api.photoQuarantine.startRun(selectedProjectId!, retryFailed),
    onSuccess: (task, retryFailed) => {
      setMessage(retryFailed
        ? "历史识别失败项已优先重新提交，分析任务已进入队列"
        : "分析任务已进入队列，可在任务页查看进度");
      queryClient.setQueryData(
        ["photo-quarantine-latest-task", selectedProjectId],
        { total: 1, items: [task] },
      );
      queryClient.invalidateQueries({ queryKey: queryKeys.projectTasks(selectedProjectId) });
      queryClient.invalidateQueries({ queryKey: ["photo-quarantine-latest-task", selectedProjectId] });
    },
    onError: (error: Error) => setMessage(`启动失败：${error.message}`),
  });
  const stopMutation = useMutation({
    mutationFn: () => api.projectTasks.cancel(selectedProjectId!, latestTask!.id),
    onSuccess: (task) => {
      setMessage(task.status === "cancelled" ? "分析任务已停止" : "正在停止分析，将在当前图片处理完成后退出");
      queryClient.setQueryData(
        ["photo-quarantine-latest-task", selectedProjectId],
        { total: 1, items: [task] },
      );
      queryClient.invalidateQueries({ queryKey: queryKeys.projectTasks(selectedProjectId) });
    },
    onError: (error: Error) => setMessage(`停止失败：${error.message}`),
  });
  const itemMutation = useMutation({
    mutationFn: ({ item, action }: { item: PhotoQuarantineItem; action: "requestDelete" | "restore" | "confirm" | "keep" }) => {
      if (action === "requestDelete") return api.photoQuarantine.requestDelete(selectedProjectId!, item.id);
      if (action === "restore") return api.photoQuarantine.restore(selectedProjectId!, item.id);
      if (action === "keep") return api.photoQuarantine.keep(selectedProjectId!, item.id);
      return api.photoQuarantine.confirmDeleted(selectedProjectId!, item.id);
    },
    onSuccess: (updatedItem, variables) => {
      updateCachedItems([updatedItem]);
      const successMessage = variables.action === "restore"
        ? "照片已安全放回原位置，并记为应保留"
        : variables.action === "requestDelete"
          ? "已批准删除：垃圾标签已记录，删除请求已写入后台清单"
          : variables.action === "keep"
            ? "已批准保留，并记为应保留"
            : "已确认后台处理完成";
      setMessage(successMessage);
      refreshItems();
    },
    onError: (error: Error) => setMessage(`操作失败：${error.message}`),
  });
  const batchMutation = useMutation({
    mutationFn: ({ action, ids }: { action: "KEEP" | "REQUEST_DELETE" | "RESTORE" | "RETRY_ANALYSIS"; ids: number[] }) =>
      api.photoQuarantine.batch(selectedProjectId!, action, ids),
    onSuccess: (result, variables) => {
      updateCachedItems(
        result.results.flatMap((entry) => entry.item ? [entry.item] : []),
      );
      const verb = variables.action === "RESTORE"
        ? "放回"
        : variables.action === "RETRY_ANALYSIS"
          ? "重新提交识别"
        : variables.action === "REQUEST_DELETE"
          ? "批准删除并加入后台清单"
          : "批准保留";
      const failedEntries = result.results.filter((entry) => !entry.succeeded);
      const failedIds = new Set(failedEntries.map((entry) => entry.item_id));
      const fileNamesById = new Map(items.map((item) => [item.id, item.original_path.split("/").pop() ?? item.original_path]));
      const failureDetails = failedEntries
        .map((entry) => `${fileNamesById.get(entry.item_id) ?? `#${entry.item_id}`}（${entry.message ?? entry.error_code ?? "未知原因"}）`)
        .join("；");
      setMessage(
        `已${verb} ${result.succeeded} 张${result.failed ? `，${result.failed} 张失败：${failureDetails}` : ""}`,
      );
      setSelectedIds(failedIds);
      if (variables.action === "RETRY_ANALYSIS") {
        queryClient.invalidateQueries({ queryKey: ["photo-quarantine-latest-task", selectedProjectId] });
        queryClient.invalidateQueries({ queryKey: queryKeys.projectTasks(selectedProjectId) });
      }
      refreshItems();
    },
    onError: (error: Error) => setMessage(`批量操作失败：${error.message}`),
  });
  const reconcileMutation = useMutation({
    mutationFn: () => api.photoQuarantine.reconcile(selectedProjectId!),
    onSuccess: (result) => {
      if (result.confirmed > 0) {
        setMessage(`已自动核验并清理 ${result.confirmed} 张后台已删除的图片记录`);
        refreshItems();
      } else if (result.failed > 0) {
        setMessage(`有 ${result.failed} 张图片暂时无法核验，已保留原状态`);
      }
    },
    onError: (error: Error) => setMessage(`自动核验失败：${error.message}`),
  });
  const reconcileItems = reconcileMutation.mutate;

  useEffect(() => {
    if (projectExists) reconcileItems();
  }, [projectExists, selectedProjectId, reconcileItems]);

  const items = itemsQuery.data?.items ?? [];
  const classificationCounts = itemsQuery.data?.classification_counts;
  const classificationTotal = classificationCounts
    ? Object.values(classificationCounts).reduce((total, count) => total + count, 0)
    : null;
  const topClassificationCounts = useMemo(
    () => Object.entries(classificationCounts ?? {})
      .filter(([, count]) => count > 0)
      .sort(([, left], [, right]) => right - left)
      .slice(0, 4),
    [classificationCounts],
  );
  const maxClassificationCount = topClassificationCounts[0]?.[1] ?? 1;
  const batchSelectableItems = useMemo(
    () => items.filter(
      (item) => KEEP_STATUSES.has(item.status)
        || DELETE_REQUEST_STATUSES.has(item.status)
        || RESTORABLE_STATUSES.has(item.status),
    ),
    [items],
  );
  const selectedOnPageCount = batchSelectableItems.filter(
    (item) => selectedIds.has(item.id),
  ).length;
  const allOnPageSelected = batchSelectableItems.length > 0
    && selectedOnPageCount === batchSelectableItems.length;
  const toggleSelectCurrentPage = () => {
    setSelectedIds(
      allOnPageSelected
        ? new Set()
        : new Set(batchSelectableItems.map((item) => item.id)),
    );
  };
  const restorableSelected = useMemo(
    () => items.filter((item) => selectedIds.has(item.id) && RESTORABLE_STATUSES.has(item.status)),
    [items, selectedIds],
  );
  const keepSelected = useMemo(
    () => items.filter((item) => selectedIds.has(item.id) && KEEP_STATUSES.has(item.status)),
    [items, selectedIds],
  );
  const retryAnalysisSelected = useMemo(
    () => items.filter((item) => selectedIds.has(item.id) && item.status === "analysis_failed"),
    [items, selectedIds],
  );
  const deleteRequestSelected = useMemo(
    () => items.filter(
      (item) => selectedIds.has(item.id) && DELETE_REQUEST_STATUSES.has(item.status),
    ),
    [items, selectedIds],
  );
  const retryingQueuedOnly = deleteRequestSelected.length > 0
    && deleteRequestSelected.every((item) => item.status === "delete_queued");
  const taskProgress = latestTask?.progress_payload ?? latestTask?.result_payload;
  const analyzedCount = typeof taskProgress?.analyzed === "number" ? taskProgress.analyzed : 0;
  const errorCount = typeof taskProgress?.errors === "number" ? taskProgress.errors : 0;
  const processedCount = analyzedCount + errorCount;
  const reviewCount = typeof taskProgress?.review === "number" ? taskProgress.review : 0;
  const retryRemaining = retryQueueQuery.data?.total;
  const scanTotal = retryFailedTask && typeof retryRemaining === "number"
    ? retryRemaining + processedCount
    : null;
  const scanPercent = scanTotal != null && scanTotal > 0
    ? Math.min(100, Math.round((processedCount / scanTotal) * 100))
    : null;
  const scanControlOnRight = analysisActive || runMutation.isPending;
  const scanControlPending = runMutation.isPending || stopMutation.isPending || cancelRequested;
  const calibration = calibrationQuery.data;

  if (selectedProjectId == null) {
    return <main className="max-w-6xl mx-auto px-6 py-8 text-mute">请先选择一个项目。</main>;
  }
  if (projects.length > 0 && !projectExists) return <Navigate to="/photos" replace />;

  return (
    <main className="max-w-7xl mx-auto px-4 sm:px-6 py-6 space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex min-w-0 items-start gap-3">
          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-danger/10 text-danger">
            <Trash2 className="h-5 w-5" aria-hidden="true" />
          </span>
          <div className="min-w-0">
            <h1 className="text-heading-lg font-semibold text-ink">待删除图片审核</h1>
            <p className="mt-1 max-w-3xl text-body-sm text-mute">集中复核 AI 标记的低质量及敏感照片。</p>
            <p className="mt-2 flex max-w-3xl items-start gap-2 rounded-md bg-warning/10 px-3 py-2 text-caption-sm text-secondary">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning" aria-hidden="true" />
              <span>所有候选均需人工确认；页面只写入删除清单，不会移动或删除原片，由 NAS 后台统一处理。</span>
            </p>
          </div>
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2" data-scan-position={scanControlOnRight ? "right" : "left"}>
          <label className="inline-flex min-h-11 items-center gap-2 rounded-md border border-hairline bg-canvas px-3 text-btn-sm font-medium text-secondary">
            <input
              type="checkbox"
              checked={retryFailedOnStart}
              onChange={(event) => setRetryFailedOnStart(event.target.checked)}
              disabled={!canManage || scanControlOnRight}
              className="h-4 w-4 rounded border-hairline text-primary focus:ring-focus-outer disabled:opacity-40"
            />
            重新扫描失败项
          </label>
          <button
            type="button"
            onClick={() => analysisActive
              ? stopMutation.mutate()
              : runMutation.mutate(retryFailedOnStart)}
            disabled={!canManage || scanControlPending}
            title={!canManage
              ? "需要项目管理员权限"
              : analysisActive
                ? "取消待删除图片扫描"
                : "启动待删除图片扫描"}
            className={`inline-flex min-h-11 min-w-32 items-center justify-center gap-2 rounded-md px-4 text-btn-sm font-semibold text-white transition-colors disabled:cursor-not-allowed disabled:opacity-60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-outer ${analysisActive ? "bg-danger hover:bg-danger/90" : "bg-primary hover:bg-primary/90"}`}
          >
            {scanControlPending
              ? <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />
              : analysisActive
                ? <Square className="h-4 w-4" aria-hidden="true" />
                : <Play className="h-4 w-4" aria-hidden="true" />}
            {runMutation.isPending
              ? "正在启动"
              : stopMutation.isPending || cancelRequested
                ? "正在取消"
                : analysisActive
                  ? "取消扫描"
                  : "启动扫描"}
          </button>
        </div>
      </header>

      {message && <div role="status" aria-live="polite" className="rounded-md border border-hairline bg-canvas px-4 py-3 text-body-sm text-ink">{message}</div>}
      {latestTask && (
        <section className="space-y-4 rounded-lg border border-hairline bg-canvas p-4 sm:p-5" aria-labelledby="analysis-progress-title">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <span className={`grid h-9 w-9 place-items-center rounded-md ${analysisActive ? "bg-primary/10 text-primary" : "bg-success/10 text-success"}`}>
                {analysisActive ? <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden="true" /> : <CheckCircle2 className="h-4 w-4" aria-hidden="true" />}
              </span>
              <div>
                <h2 id="analysis-progress-title" className="text-body-sm font-semibold text-ink">最近分析任务</h2>
                <p className="text-caption-sm text-mute">{analysisActive ? "正在分析候选照片" : "最近一次任务已停止"}</p>
                <span className="sr-only">最近分析任务：{latestTask.status}</span>
              </div>
            </div>
            {analysisActive && scanPercent != null && <strong className="tabular-nums text-heading-md text-ink">{scanPercent}%</strong>}
          </div>
          {latestTask.error_message && <p className="rounded-md bg-danger/5 px-3 py-2 text-caption-sm text-danger">{latestTask.error_message}</p>}
          {analysisActive && (
            <>
              <div className="text-body-sm text-secondary">
                {cancelRequested
                  ? "正在取消，将在当前图片处理完成后停止"
                  : latestTask.status === "queued"
                    ? "等待 Worker 接收任务"
                    : processedCount === 0
                      ? "模型正在分析第一张照片，单张识别可能需要一些时间"
                      : scanTotal != null
                        ? `已处理 ${processedCount} / ${scanTotal} 张`
                        : `已处理 ${processedCount} 张，扫描仍在进行`}
              </div>
              <div
                role="progressbar"
                aria-label="扫描进度"
                aria-valuemin={scanTotal != null ? 0 : undefined}
                aria-valuemax={scanTotal != null ? scanTotal : undefined}
                aria-valuenow={scanTotal != null ? processedCount : undefined}
                className="h-2 overflow-hidden rounded-full bg-surface-soft ring-1 ring-inset ring-hairline"
              >
                {scanPercent == null ? (
                  <div className="h-full w-2/5 animate-pulse rounded-full bg-primary motion-reduce:animate-none" />
                ) : scanPercent === 0 ? (
                  <div className="h-full w-8 animate-pulse rounded-full bg-primary motion-reduce:animate-none" />
                ) : (
                  <div
                    className="h-full rounded-full bg-primary transition-[width] duration-500 motion-reduce:transition-none"
                    style={{ width: `${scanPercent}%` }}
                  />
                )}
              </div>
            </>
          )}
          <div className="grid grid-cols-3 gap-2">
            <MiniMetric label="已分析" value={analyzedCount} />
            <MiniMetric label="待审核" value={reviewCount} />
            <MiniMetric label="识别失败" value={errorCount} danger={errorCount > 0} />
          </div>
          <p className="sr-only">成功分析 {analyzedCount} 张 · 待审核 {reviewCount} 张 · 识别失败 {errorCount} 张</p>
        </section>
      )}

      <details className="group rounded-lg border border-hairline bg-canvas">
        <summary className="flex min-h-14 cursor-pointer list-none items-center justify-between gap-3 rounded-lg px-4 py-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-outer sm:px-5 [&::-webkit-details-marker]:hidden">
          <span className="flex min-w-0 items-center gap-3">
            <span className="grid h-9 w-9 shrink-0 place-items-center rounded-md bg-primary/5 text-primary"><BarChart3 className="h-4 w-4" aria-hidden="true" /></span>
            <span className="min-w-0">
              <span className="block text-body-sm font-semibold text-ink">校准报告</span>
              <span className="block truncate text-caption-sm text-mute">{calibration ? `已标注 ${calibration.labeled_total}/${calibration.target_sample_size} · 误删风险 ${calibration.false_positive}` : "人工标注质量与自动移动门槛"}</span>
            </span>
          </span>
          <ChevronDown className="h-4 w-4 shrink-0 text-mute transition-transform duration-200 group-open:rotate-180 motion-reduce:transition-none" aria-hidden="true" />
        </summary>
        <div className="space-y-4 border-t border-hairline p-4 sm:p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <p className="max-w-3xl text-caption-sm text-mute">“保留”记为 KEEP，“提交删除”记为 TRASH；放回旧隔离照片也会记为 KEEP。</p>
          <a
            href={`${BASE}/projects/${selectedProjectId}/photo-quarantine/calibration.csv`}
            className="inline-flex min-h-11 items-center gap-1.5 rounded-md border border-hairline px-3 text-btn-sm font-medium text-secondary transition-colors hover:bg-surface-soft hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-outer"
          >
            <Download className="h-4 w-4" aria-hidden="true" /> 导出 CSV
          </a>
          </div>
        {calibrationQuery.isLoading ? (
          <div className="text-body-sm text-mute">正在统计人工标签…</div>
        ) : calibrationQuery.isError || !calibration ? (
          <div className="text-body-sm text-danger">校准报告加载失败。</div>
        ) : (
          <>
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
              <MetricCard label="已标注" value={`${calibration.labeled_total} / ${calibration.target_sample_size}`} />
              <MetricCard label="误删风险项" value={String(calibration.false_positive)} danger={calibration.false_positive > 0} />
              <MetricCard label="垃圾判定精确率" value={formatPercent(calibration.precision)} />
              <MetricCard label="垃圾召回率" value={formatPercent(calibration.recall)} />
            </div>
            <div className={`rounded-md border px-4 py-3 text-body-sm ${calibration.ready_for_auto_move ? "border-success/40 bg-success/5 text-ink" : "border-hairline bg-surface-card text-mute"}`}>
              {calibration.ready_for_auto_move
                ? "校准门槛已满足。仍需人工确认后才能关闭校准模式。"
                : `尚未达到自动移动门槛：至少 ${calibration.target_sample_size} 张，KEEP/TRASH 各不少于 ${calibration.minimum_per_label} 张，并且误删风险项必须为 0。`}
            </div>
            {calibration.categories.length > 0 && (
              <div className="overflow-x-auto">
                <table className="w-full text-body-sm">
                  <thead className="text-left text-mute"><tr><th className="py-2">类别</th><th>样本</th><th>应保留</th><th>垃圾</th><th>误删风险</th><th>漏删</th></tr></thead>
                  <tbody>
                    {calibration.categories.map((category) => (
                      <tr key={category.classification} className="border-t border-hairline">
                        <td className="py-2 pr-3 text-ink">{CLASS_LABELS[category.classification] ?? category.classification}</td>
                        <td>{category.labeled_total}</td><td>{category.human_keep}</td><td>{category.human_trash}</td>
                        <td className={category.false_positive > 0 ? "text-danger font-bold" : ""}>{category.false_positive}</td>
                        <td>{category.false_negative}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
        </div>
      </details>

      <details className="group rounded-lg border border-hairline bg-canvas">
        <summary className="flex min-h-14 cursor-pointer list-none items-center justify-between gap-3 rounded-lg px-4 py-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-outer sm:px-5 [&::-webkit-details-marker]:hidden">
          <span className="flex min-w-0 items-center gap-3">
            <span className="grid h-9 w-9 shrink-0 place-items-center rounded-md bg-primary/5 text-primary"><ShieldCheck className="h-4 w-4" aria-hidden="true" /></span>
            <span className="min-w-0">
              <span className="block text-body-sm font-semibold text-ink">夜间跑批设置</span>
              <span className="block truncate text-caption-sm text-mute">{form ? `${String(form.start_hour).padStart(2, "0")}:00–${String(form.end_hour).padStart(2, "0")}:00 · ${form.enabled ? "已启用" : "未启用"}` : "运行时间、模型与保留策略"}</span>
            </span>
          </span>
          <ChevronDown className="h-4 w-4 shrink-0 text-mute transition-transform duration-200 group-open:rotate-180 motion-reduce:transition-none" aria-hidden="true" />
        </summary>
        <div className="border-t border-hairline p-4 sm:p-5">
          {settingsQuery.isLoading || !form ? (
            <div className="flex items-center gap-2 text-mute"><Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />加载中…</div>
          ) : (
          <div className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
              <label className="text-caption-sm text-mute">开始小时
                <input className={fieldClass()} type="number" min={0} max={23} disabled={!canManage} value={form.start_hour} onChange={(event) => setForm({ ...form, start_hour: Number(event.target.value) })} />
              </label>
              <label className="text-caption-sm text-mute">结束小时
                <input className={fieldClass()} type="number" min={0} max={23} disabled={!canManage} value={form.end_hour} onChange={(event) => setForm({ ...form, end_hour: Number(event.target.value) })} />
              </label>
              <label className="text-caption-sm text-mute">时区
                <input className={fieldClass()} disabled={!canManage} value={form.timezone} onChange={(event) => setForm({ ...form, timezone: event.target.value })} />
              </label>
              <label className="text-caption-sm text-mute">模型
                <input className={fieldClass()} disabled={!canManage} value={form.model_name} onChange={(event) => setForm({ ...form, model_name: event.target.value })} />
              </label>
              <label className="text-caption-sm text-mute">人工删除前建议保留天数
                <input className={fieldClass()} type="number" min={1} max={3650} disabled={!canManage} value={form.retention_days} onChange={(event) => setForm({ ...form, retention_days: Number(event.target.value) })} />
              </label>
            </div>
            <div className="flex flex-wrap items-center gap-3 text-body-sm sm:gap-5">
              <label className="flex min-h-11 items-center gap-2"><input type="checkbox" disabled={!canManage} checked={form.enabled} onChange={(event) => setForm({ ...form, enabled: event.target.checked })} />启用每日跑批</label>
              <label className="flex min-h-11 items-center gap-2"><input type="checkbox" disabled={!canManage} checked={form.dry_run} onChange={(event) => setForm({ ...form, dry_run: event.target.checked })} />校准模式（只识别、不移动）</label>
              {canManage && <button type="button" onClick={() => saveMutation.mutate()} disabled={saveMutation.isPending} className="inline-flex min-h-11 items-center gap-1.5 rounded-md border border-hairline px-3 text-btn-sm font-medium text-secondary hover:bg-surface-soft hover:text-ink disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-outer"><Save className="h-4 w-4" aria-hidden="true" />保存设置</button>}
            </div>
            <p className="text-caption-sm text-mute">默认 01:00–06:00。到结束时间后会完成当前图片再暂停，剩余图片次日继续。系统不会按保留天数自动删除文件。</p>
          </div>
          )}
        </div>
      </details>

      <section className="space-y-4" aria-labelledby="review-queue-title">
        <div className="rounded-lg border border-hairline bg-canvas p-4 sm:p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="flex items-start gap-3">
              <span className="grid h-9 w-9 shrink-0 place-items-center rounded-md bg-primary/5 text-primary"><ImageIcon className="h-4 w-4" aria-hidden="true" /></span>
              <div>
                <h2 id="review-queue-title" className="text-heading-md font-semibold text-ink">审核队列</h2>
                <p className="mt-0.5 text-caption-sm text-mute">当前筛选 <span>共 {itemsQuery.data?.total ?? 0} 项</span></p>
              </div>
            </div>
            <button type="button" onClick={() => reconcileItems()} disabled={reconcileMutation.isPending} className="inline-flex min-h-11 items-center gap-1.5 rounded-md border border-hairline px-3 text-btn-sm font-medium text-secondary hover:bg-surface-soft hover:text-ink disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-outer" aria-label="刷新"><RefreshCw className={`h-4 w-4 ${reconcileMutation.isPending ? "animate-spin motion-reduce:animate-none" : ""}`} aria-hidden="true" />刷新</button>
          </div>

          {topClassificationCounts.length > 0 && (
            <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-4" role="img" aria-label={`候选类别分布：${topClassificationCounts.map(([classification, count]) => `${CLASS_LABELS[classification] ?? classification} ${count}`).join("，")}`}>
              {topClassificationCounts.map(([classification, count]) => (
                <div key={classification} className="rounded-md bg-surface-soft px-3 py-2.5">
                  <div className="flex items-center justify-between gap-2 text-caption-sm"><span className="truncate text-secondary">{CLASS_LABELS[classification] ?? classification}</span><strong className="tabular-nums text-ink">{count.toLocaleString()}</strong></div>
                  <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-secondary-bg"><div className="h-full rounded-full bg-primary" style={{ width: `${Math.max(4, (count / maxClassificationCount) * 100)}%` }} /></div>
                </div>
              ))}
            </div>
          )}

          <div className="mt-4 grid gap-3 sm:grid-cols-3">
            <label className="text-caption-sm font-medium text-secondary">处理状态
              <select value={statusFilter} onChange={(event) => { setStatusFilter(event.target.value); setClassificationFilter(""); }} className="mt-1 min-h-11 w-full rounded-md border border-hairline bg-canvas px-3 text-body-sm text-ink focus:outline-none focus:ring-2 focus:ring-focus-outer">
                {STATUS_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
              </select>
            </label>
            <label className="text-caption-sm font-medium text-secondary">人工标签
              <select value={labelFilter} onChange={(event) => { setLabelFilter(event.target.value as typeof labelFilter); setClassificationFilter(""); }} className="mt-1 min-h-11 w-full rounded-md border border-hairline bg-canvas px-3 text-body-sm text-ink focus:outline-none focus:ring-2 focus:ring-focus-outer" aria-label="人工标签筛选">
                <option value="">全部标签</option><option value="UNLABELED">未标注</option><option value="KEEP">应保留</option><option value="TRASH">垃圾</option>
              </select>
            </label>
            <label className="text-caption-sm font-medium text-secondary">识别类别
              <select value={classificationFilter} onChange={(event) => setClassificationFilter(event.target.value)} className="mt-1 min-h-11 w-full rounded-md border border-hairline bg-canvas px-3 text-body-sm text-ink focus:outline-none focus:ring-2 focus:ring-focus-outer" aria-label="类别筛选">
                {CLASS_FILTER_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}{classificationCounts ? `（${option.value ? classificationCounts[option.value] ?? 0 : classificationTotal}）` : ""}</option>)}
              </select>
            </label>
          </div>

          {canManage && batchSelectableItems.length > 0 && (
            <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-hairline pt-4">
              <button type="button" onClick={toggleSelectCurrentPage} aria-pressed={allOnPageSelected} className="min-h-11 rounded-md border border-hairline px-3 text-btn-sm font-medium text-secondary hover:bg-surface-soft hover:text-ink">{allOnPageSelected ? "取消全选" : `全选当前页（${batchSelectableItems.length}）`}</button>
              {selectedOnPageCount > 0 && <span className="px-1 text-caption-sm font-medium text-ink">已选 {selectedOnPageCount} 张</span>}
              {keepSelected.length > 0 && <button type="button" onClick={() => batchMutation.mutate({ action: "KEEP", ids: keepSelected.map((item) => item.id) })} disabled={batchMutation.isPending} className="min-h-11 rounded-md border border-hairline px-3 text-btn-sm font-medium hover:bg-surface-soft disabled:opacity-50">批量保留（{keepSelected.length}）</button>}
              {retryAnalysisSelected.length > 0 && <button type="button" onClick={() => batchMutation.mutate({ action: "RETRY_ANALYSIS", ids: retryAnalysisSelected.map((item) => item.id) })} disabled={batchMutation.isPending} className="min-h-11 rounded-md border border-primary px-3 text-btn-sm font-medium text-primary hover:bg-primary/5 disabled:opacity-50">批量重新识别（{retryAnalysisSelected.length}）</button>}
              {deleteRequestSelected.length > 0 && <button type="button" onClick={() => { if (window.confirm(`${retryingQueuedOnly ? "将重新写入" : "将批准删除并写入"} ${deleteRequestSelected.length} 张照片的 NAS 后台删除清单。应用不会直接移动或删除原片，但当前不能从页面撤销已写入的请求。继续？`)) batchMutation.mutate({ action: "REQUEST_DELETE", ids: deleteRequestSelected.map((item) => item.id) }); }} disabled={batchMutation.isPending} className="min-h-11 rounded-md bg-danger px-3 text-btn-sm font-semibold text-white hover:bg-danger/90 disabled:opacity-50">{retryingQueuedOnly ? "批量重写删除清单" : "批量提交删除"}（{deleteRequestSelected.length}）</button>}
              {restorableSelected.length > 0 && <button type="button" onClick={() => batchMutation.mutate({ action: "RESTORE", ids: restorableSelected.map((item) => item.id) })} disabled={batchMutation.isPending} className="inline-flex min-h-11 items-center gap-1.5 rounded-md border border-hairline px-3 text-btn-sm font-medium hover:bg-surface-soft disabled:opacity-50"><ArchiveRestore className="h-4 w-4" aria-hidden="true" />批量放回（{restorableSelected.length}）</button>}
            </div>
          )}
        </div>

        {itemsQuery.isLoading ? (
          <div className="flex items-center gap-2 py-12 justify-center text-mute"><Loader2 className="w-5 h-5 animate-spin" />加载审核项…</div>
        ) : items.length === 0 ? (
          <div className="rounded-lg border border-hairline bg-canvas py-14 text-center text-mute">当前筛选条件下没有图片。</div>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {items.map((item) => (
              <article key={item.id} className={`overflow-hidden rounded-lg border bg-canvas transition-shadow hover:shadow-sm ${selectedIds.has(item.id) ? "border-primary ring-2 ring-primary/15" : item.status === "delete_queued" ? "border-danger/50" : "border-hairline"}`}>
                <div className="relative aspect-[4/3] bg-surface-soft">
                  <img src={`${BASE}/projects/${selectedProjectId}/photo-quarantine/items/${item.id}/thumbnail`} alt="待删除候选图片" className={`h-full w-full object-contain transition ${item.status === "delete_queued" ? "grayscale opacity-45" : ""}`} loading="lazy" />
                  {item.status === "delete_queued" && <div className="absolute inset-0 flex flex-col items-center justify-center bg-black/45 text-white" aria-label="已提交删除，等待后台处理"><Trash2 className="mb-2 h-7 w-7" aria-hidden="true" /><span className="text-body-sm font-semibold">已提交删除</span><span className="mt-1 text-caption-sm">等待 NAS 后台处理</span></div>}
                  {canManage && (KEEP_STATUSES.has(item.status) || DELETE_REQUEST_STATUSES.has(item.status) || RESTORABLE_STATUSES.has(item.status)) && <label className="absolute left-2 top-2 grid h-11 w-11 cursor-pointer place-items-center rounded-md bg-black/55"><span className="sr-only">选择审核项</span><input type="checkbox" className="h-5 w-5 rounded border-white text-primary focus:ring-focus-outer" aria-label="选择审核项" checked={selectedIds.has(item.id)} onChange={(event) => setSelectedIds((current) => { const next = new Set(current); event.target.checked ? next.add(item.id) : next.delete(item.id); return next; })} /></label>}
                  <span className="absolute right-2 top-2 rounded-full bg-black/70 px-2.5 py-1 text-[11px] font-medium text-white">{STATUS_LABELS[item.status] ?? item.status}</span>
                </div>
                <div className="space-y-3 p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="font-semibold text-ink">{CLASS_LABELS[item.classification] ?? item.classification}</div>
                    <span className="shrink-0 rounded-full bg-surface-soft px-2 py-1 text-caption-sm tabular-nums text-secondary">{(item.confidence * 100).toFixed(0)}%</span>
                  </div>
                  <p className="line-clamp-3 text-body-sm text-secondary">{item.reason}</p>
                  {item.content_rating && item.content_rating !== "SAFE" && (
                    <p className="flex items-start gap-2 rounded-md border border-danger/30 bg-danger/5 px-3 py-2 text-caption-sm font-medium text-danger">
                      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
                      <span>{item.content_rating === "ADULT" ? "18+ 内容" : "敏感内容"}：{(item.sensitive_content_flags ?? [])
                        .map((flag) => SENSITIVE_CONTENT_LABELS[flag] ?? flag)
                        .join("、") || "需人工复核"}</span>
                    </p>
                  )}
                  {item.preservation_flags.length > 0 && <p className="rounded-md bg-warning/10 px-3 py-2 text-caption-sm text-secondary">保留信号：{item.preservation_flags.join("、")}</p>}
                  <details className="group rounded-md border border-hairline bg-surface-soft px-3 py-2 text-caption-sm">
                    <summary className="flex min-h-7 cursor-pointer list-none items-center justify-between text-secondary [&::-webkit-details-marker]:hidden">文件信息<ChevronDown className="h-3.5 w-3.5 transition-transform group-open:rotate-180" aria-hidden="true" /></summary>
                    <div className="mt-2 space-y-1 border-t border-hairline pt-2 text-mute">
                      <p>模型：{item.model_name}</p>
                      {item.human_label && <p className="font-medium text-primary">人工标签：{item.human_label === "KEEP" ? "应保留" : "垃圾"}{item.human_labeled_by ? ` · ${item.human_labeled_by}` : ""}</p>}
                      {item.last_error && <p className="break-all text-danger">{item.last_error}</p>}
                      <p className="break-all" title={item.original_path}>{item.original_path}</p>
                    </div>
                  </details>
                  <Link
                    to={`/photos?photo_id=${item.photo_id}`}
                    aria-label={`查看照片 ${item.photo_id} 的原文件夹`}
                    className="inline-flex min-h-11 items-center gap-1.5 text-caption-sm font-semibold text-primary hover:text-primary-pressed"
                  >
                    <FolderSearch className="h-3.5 w-3.5" aria-hidden="true" />查看原文件夹
                  </Link>
                  {canManage && (
                    <div className="flex flex-wrap gap-2">
                      {DELETE_APPROVAL_STATUSES.has(item.status) && <button type="button" onClick={() => { if (window.confirm("将批准删除此照片，并写入 NAS 后台删除清单。应用不会直接移动或删除原片，但当前不能从页面撤销已写入的请求。继续？")) itemMutation.mutate({ item, action: "requestDelete" }); }} disabled={itemMutation.isPending} className="min-h-11 rounded-md bg-danger px-3 text-btn-sm font-semibold text-white hover:bg-danger/90 disabled:opacity-50">{item.status === "queue_failed" ? "重试提交删除" : "提交删除"}</button>}
                      {item.status === "analysis_failed" && <button type="button" onClick={() => batchMutation.mutate({ action: "RETRY_ANALYSIS", ids: [item.id] })} disabled={batchMutation.isPending} className="min-h-11 rounded-md border border-primary px-3 text-btn-sm font-medium text-primary hover:bg-primary/5 disabled:opacity-50">重新识别</button>}
                      {item.status === "delete_queued" && <button type="button" onClick={() => { if (window.confirm("将重新写入此照片的 NAS 后台删除清单。继续？")) itemMutation.mutate({ item, action: "requestDelete" }); }} disabled={itemMutation.isPending} className="min-h-11 rounded-md bg-danger px-3 text-btn-sm font-semibold text-white hover:bg-danger/90 disabled:opacity-50">重写删除清单</button>}
                      {KEEP_STATUSES.has(item.status) && <button type="button" onClick={() => itemMutation.mutate({ item, action: "keep" })} disabled={itemMutation.isPending} className="min-h-11 rounded-md border border-hairline px-3 text-btn-sm font-medium hover:bg-surface-soft disabled:opacity-50">保留</button>}
                      {RESTORABLE_STATUSES.has(item.status) && <button type="button" onClick={() => itemMutation.mutate({ item, action: "restore" })} disabled={itemMutation.isPending} className="inline-flex min-h-11 items-center gap-1 rounded-md border border-hairline px-3 text-btn-sm font-medium hover:bg-surface-soft disabled:opacity-50"><ArchiveRestore className="h-3.5 w-3.5" aria-hidden="true" />放回原处</button>}
                      {(item.status === "delete_queued" || item.status === "quarantined") && <button type="button" onClick={() => { if (window.confirm("仅当 NAS 后台脚本已处理该文件时才确认。继续？")) itemMutation.mutate({ item, action: "confirm" }); }} disabled={itemMutation.isPending} className="min-h-11 rounded-md border border-hairline px-3 text-btn-sm text-mute hover:text-ink disabled:opacity-50">确认后台已处理</button>}
                    </div>
                  )}
                </div>
              </article>
            ))}
          </div>
        )}
        {(itemsQuery.data?.total ?? 0) > PAGE_SIZE && (
          <nav className="flex items-center justify-center gap-3" aria-label="审核队列分页">
            <button type="button" onClick={() => setPage((value) => Math.max(0, value - 1))} disabled={page === 0} className="min-h-11 rounded-md border border-hairline px-3 text-btn-sm disabled:opacity-40">上一页</button>
            <span className="text-caption-sm text-mute">第 {page + 1} / {Math.ceil((itemsQuery.data?.total ?? 0) / PAGE_SIZE)} 页</span>
            <button type="button" onClick={() => setPage((value) => value + 1)} disabled={(page + 1) * PAGE_SIZE >= (itemsQuery.data?.total ?? 0)} className="min-h-11 rounded-md border border-hairline px-3 text-btn-sm disabled:opacity-40">下一页</button>
          </nav>
        )}
      </section>
    </main>
  );
}

function MetricCard({ label, value, danger = false }: { label: string; value: string; danger?: boolean }) {
  return (
    <div className="rounded-md border border-hairline bg-surface-card p-3">
      <div className="text-caption-sm text-mute">{label}</div>
      <div className={`mt-1 text-lg font-bold ${danger ? "text-danger" : "text-ink"}`}>{value}</div>
    </div>
  );
}

function MiniMetric({ label, value, danger = false }: { label: string; value: number; danger?: boolean }) {
  return (
    <div className="rounded-md bg-surface-soft px-3 py-2.5 text-center">
      <div className={`text-heading-md font-semibold tabular-nums ${danger ? "text-danger" : "text-ink"}`}>{value.toLocaleString()}</div>
      <div className="mt-0.5 text-caption-sm text-mute">{label}</div>
    </div>
  );
}

function formatPercent(value: number | null): string {
  return value == null ? "暂无" : `${(value * 100).toFixed(1)}%`;
}
