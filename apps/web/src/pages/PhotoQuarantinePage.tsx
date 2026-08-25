import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArchiveRestore,
  BarChart3,
  Download,
  Loader2,
  Play,
  RefreshCw,
  Save,
  ShieldCheck,
  Trash2,
} from "lucide-react";
import { Navigate, useParams } from "react-router-dom";
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

const PENDING_STATUSES = "review,restore_conflict,restore_failed,queue_failed,move_failed,analysis_failed";
const RESTORABLE_STATUSES = new Set(["quarantined", "restore_conflict", "restore_failed"]);
const APPROVAL_STATUSES = new Set([
  "review",
  "analysis_failed",
  "move_failed",
  "queue_failed",
  "kept",
  "restored",
]);
const DELETE_REQUEST_STATUSES = new Set([...APPROVAL_STATUSES, "delete_queued"]);
const PAGE_SIZE = 24;

const STATUS_OPTIONS = [
  { value: PENDING_STATUSES, label: "待处理" },
  { value: "delete_queued,quarantined,deleted_confirmed", label: "已提交删除" },
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
  move_failed: "移动失败",
  queue_failed: "加入删除队列失败",
  restore_conflict: "原位置已有文件",
  restore_failed: "放回失败",
};

const CLASS_LABELS: Record<string, string> = {
  accidental_capture: "误触拍摄",
  severe_blur: "严重模糊",
  obscured_lens: "镜头遮挡",
  blank_image: "空白图片",
  meaningless_test: "无意义测试图",
  screenshot: "屏幕截图",
  construction_clutter: "工地杂物",
};

function fieldClass() {
  return "w-full rounded-md border border-hairline bg-surface-card px-3 py-2 text-body-sm text-ink focus:outline-none focus:ring-2 focus:ring-focus-outer";
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
  const [page, setPage] = useState(0);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
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
    ),
    queryFn: () => api.photoQuarantine.list(
      selectedProjectId!,
      statusFilter,
      PAGE_SIZE,
      page * PAGE_SIZE,
      labelFilter || undefined,
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
  }, [statusFilter, labelFilter, selectedProjectId]);

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
    mutationFn: () => api.photoQuarantine.startRun(selectedProjectId!),
    onSuccess: () => {
      setMessage("分析任务已进入队列，可在任务页查看进度");
      queryClient.invalidateQueries({ queryKey: queryKeys.projectTasks(selectedProjectId) });
      queryClient.invalidateQueries({ queryKey: ["photo-quarantine-latest-task", selectedProjectId] });
    },
    onError: (error: Error) => setMessage(`启动失败：${error.message}`),
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
    mutationFn: ({ action, ids }: { action: "KEEP" | "REQUEST_DELETE" | "RESTORE"; ids: number[] }) =>
      api.photoQuarantine.batch(selectedProjectId!, action, ids),
    onSuccess: (result, variables) => {
      updateCachedItems(
        result.results.flatMap((entry) => entry.item ? [entry.item] : []),
      );
      const verb = variables.action === "RESTORE"
        ? "放回"
        : variables.action === "REQUEST_DELETE"
          ? "批准删除并加入后台清单"
          : "批准保留";
      setMessage(`已${verb} ${result.succeeded} 张${result.failed ? `，${result.failed} 张失败，请逐项检查` : ""}`);
      setSelectedIds(new Set());
      refreshItems();
    },
    onError: (error: Error) => setMessage(`批量操作失败：${error.message}`),
  });

  const items = itemsQuery.data?.items ?? [];
  const batchSelectableItems = useMemo(
    () => items.filter(
      (item) => DELETE_REQUEST_STATUSES.has(item.status) || RESTORABLE_STATUSES.has(item.status),
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
  const approvalSelected = useMemo(
    () => items.filter((item) => selectedIds.has(item.id) && APPROVAL_STATUSES.has(item.status)),
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
  const latestTask = taskQuery.data?.items[0];
  const taskProgress = latestTask?.progress_payload ?? latestTask?.result_payload;
  const calibration = calibrationQuery.data;

  if (selectedProjectId == null) {
    return <main className="max-w-6xl mx-auto px-6 py-8 text-mute">请先选择一个项目。</main>;
  }
  if (projects.length > 0 && !projectExists) return <Navigate to="/photos" replace />;

  return (
    <main className="max-w-7xl mx-auto px-4 sm:px-6 py-6 space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-ink flex items-center gap-2">
            <Trash2 className="w-5 h-5" /> 待删除图片审核
          </h1>
          <p className="mt-1 text-body-sm text-mute">
            页面只写入删除清单，不会移动或删除原片；原片由 NAS 后台脚本统一处理。提交后如需反悔，请在脚本执行前停用该清单，或在执行后从 NAS 回收目录恢复。
          </p>
        </div>
        {canManage && (
          <button
            type="button"
            onClick={() => runMutation.mutate()}
            disabled={runMutation.isPending}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-md bg-primary text-white text-btn-sm font-bold disabled:opacity-50"
          >
            {runMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
            立即分析
          </button>
        )}
      </div>

      {message && <div className="rounded-md border border-hairline bg-canvas px-4 py-3 text-body-sm text-ink">{message}</div>}
      {latestTask && (
        <div className="rounded-md border border-hairline bg-canvas px-4 py-3 text-body-sm text-mute">
          最近分析任务：{latestTask.status}
          {typeof taskProgress?.analyzed === "number" ? ` · 已分析 ${taskProgress.analyzed} 张` : ""}
          {typeof taskProgress?.review === "number" ? ` · 待审核 ${taskProgress.review} 张` : ""}
          {latestTask.error_message ? ` · ${latestTask.error_message}` : ""}
        </div>
      )}

      <section className="rounded-lg border border-hairline bg-canvas p-5 space-y-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="font-bold text-ink flex items-center gap-2">
              <BarChart3 className="w-4 h-4 text-primary" /> 校准报告
            </h2>
            <p className="mt-1 text-caption-sm text-mute">
              人工选择“保留”会自动记为 KEEP；“提交删除”会自动记为 TRASH；放回旧隔离照片也会记为 KEEP。
            </p>
          </div>
          <a
            href={`${BASE}/projects/${selectedProjectId}/photo-quarantine/calibration.csv`}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-md border border-hairline text-btn-sm font-bold hover:bg-surface-card"
          >
            <Download className="w-4 h-4" /> 导出 CSV
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
      </section>

      <section className="rounded-lg border border-hairline bg-canvas p-5 space-y-4">
        <div className="flex items-center gap-2">
          <ShieldCheck className="w-4 h-4 text-primary" />
          <h2 className="font-bold text-ink">夜间跑批设置</h2>
        </div>
        {settingsQuery.isLoading || !form ? (
          <div className="flex items-center gap-2 text-mute"><Loader2 className="w-4 h-4 animate-spin" />加载中…</div>
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
            <div className="flex flex-wrap items-center gap-5 text-body-sm">
              <label className="flex items-center gap-2"><input type="checkbox" disabled={!canManage} checked={form.enabled} onChange={(event) => setForm({ ...form, enabled: event.target.checked })} />启用每日跑批</label>
              <label className="flex items-center gap-2"><input type="checkbox" disabled={!canManage} checked={form.dry_run} onChange={(event) => setForm({ ...form, dry_run: event.target.checked })} />校准模式（只识别、不移动）</label>
              {canManage && <button type="button" onClick={() => saveMutation.mutate()} disabled={saveMutation.isPending} className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-hairline text-btn-sm font-bold hover:bg-surface-card disabled:opacity-50"><Save className="w-4 h-4" />保存设置</button>}
            </div>
            <p className="text-caption-sm text-mute">默认 01:00–06:00。到结束时间后会完成当前图片再暂停，剩余图片次日继续。系统不会按保留天数自动删除文件。</p>
          </div>
        )}
      </section>

      <section className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)} className="rounded-md border border-hairline bg-canvas px-3 py-2 text-body-sm">
              {STATUS_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
            <select value={labelFilter} onChange={(event) => setLabelFilter(event.target.value as typeof labelFilter)} className="rounded-md border border-hairline bg-canvas px-3 py-2 text-body-sm" aria-label="人工标签筛选">
              <option value="">全部标签</option><option value="UNLABELED">未标注</option><option value="KEEP">应保留</option><option value="TRASH">垃圾</option>
            </select>
            <span className="text-caption-sm text-mute">共 {itemsQuery.data?.total ?? 0} 项</span>
            <button type="button" onClick={() => itemsQuery.refetch()} className="text-mute hover:text-ink" aria-label="刷新"><RefreshCw className="w-4 h-4" /></button>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {canManage && batchSelectableItems.length > 0 && <button type="button" onClick={toggleSelectCurrentPage} aria-pressed={allOnPageSelected} className="px-3 py-2 rounded-md border border-hairline text-btn-sm font-bold hover:bg-surface-card">{allOnPageSelected ? "取消全选" : `全选当前页（${batchSelectableItems.length}）`}</button>}
            {canManage && selectedOnPageCount > 0 && <span className="px-1 text-caption-sm text-mute">已选 {selectedOnPageCount} 张</span>}
            {canManage && approvalSelected.length > 0 && <button type="button" onClick={() => batchMutation.mutate({ action: "KEEP", ids: approvalSelected.map((item) => item.id) })} disabled={batchMutation.isPending} className="px-3 py-2 rounded-md border border-hairline text-btn-sm font-bold hover:bg-surface-card disabled:opacity-50">批量保留（{approvalSelected.length}）</button>}
            {canManage && deleteRequestSelected.length > 0 && <button type="button" onClick={() => { if (window.confirm(`${retryingQueuedOnly ? "将重新写入" : "将批准删除并写入"} ${deleteRequestSelected.length} 张照片的 NAS 后台删除清单。应用不会直接移动或删除原片，但当前不能从页面撤销已写入的请求。继续？`)) batchMutation.mutate({ action: "REQUEST_DELETE", ids: deleteRequestSelected.map((item) => item.id) }); }} disabled={batchMutation.isPending} className="px-3 py-2 rounded-md bg-primary text-white text-btn-sm font-bold disabled:opacity-50">{retryingQueuedOnly ? "批量重写删除清单" : "批量提交删除"}（{deleteRequestSelected.length}）</button>}
            {canManage && restorableSelected.length > 0 && <button type="button" onClick={() => batchMutation.mutate({ action: "RESTORE", ids: restorableSelected.map((item) => item.id) })} disabled={batchMutation.isPending} className="inline-flex items-center gap-1.5 px-3 py-2 rounded-md border border-hairline text-btn-sm font-bold hover:bg-surface-card disabled:opacity-50"><ArchiveRestore className="w-4 h-4" />批量放回（{restorableSelected.length}）</button>}
          </div>
        </div>

        {itemsQuery.isLoading ? (
          <div className="flex items-center gap-2 py-12 justify-center text-mute"><Loader2 className="w-5 h-5 animate-spin" />加载审核项…</div>
        ) : items.length === 0 ? (
          <div className="rounded-lg border border-hairline bg-canvas py-14 text-center text-mute">当前筛选条件下没有图片。</div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
            {items.map((item) => (
              <article key={item.id} className={`overflow-hidden rounded-lg border bg-canvas ${item.status === "delete_queued" ? "border-danger/50" : "border-hairline"}`}>
                <div className="relative aspect-video bg-surface-card">
                  <img src={`${BASE}/projects/${selectedProjectId}/photo-quarantine/items/${item.id}/thumbnail`} alt="待删除候选图片" className={`h-full w-full object-contain transition ${item.status === "delete_queued" ? "grayscale opacity-45" : ""}`} loading="lazy" />
                  {item.status === "delete_queued" && <div className="absolute inset-0 flex flex-col items-center justify-center bg-black/45 text-white" aria-label="已提交删除，等待后台处理"><Trash2 className="mb-2 h-7 w-7" /><span className="text-body-sm font-bold">已提交删除</span><span className="mt-1 text-caption-sm">等待 NAS 后台处理</span></div>}
                  {canManage && (DELETE_REQUEST_STATUSES.has(item.status) || RESTORABLE_STATUSES.has(item.status)) && <input type="checkbox" className="absolute top-3 left-3 w-4 h-4" aria-label="选择审核项" checked={selectedIds.has(item.id)} onChange={(event) => setSelectedIds((current) => { const next = new Set(current); event.target.checked ? next.add(item.id) : next.delete(item.id); return next; })} />}
                  <span className="absolute top-2 right-2 rounded-full bg-black/70 px-2 py-1 text-[11px] text-white">{STATUS_LABELS[item.status] ?? item.status}</span>
                </div>
                <div className="p-4 space-y-3">
                  <div>
                    <div className="font-bold text-ink">{CLASS_LABELS[item.classification] ?? item.classification}</div>
                    <div className="text-caption-sm text-mute">置信度 {(item.confidence * 100).toFixed(1)}% · {item.model_name}</div>
                  </div>
                  <p className="text-body-sm text-ink">{item.reason}</p>
                  {item.preservation_flags.length > 0 && <p className="text-caption-sm text-danger">保留信号：{item.preservation_flags.join("、")}</p>}
                  {item.human_label && <p className="text-caption-sm font-bold text-primary">人工标签：{item.human_label === "KEEP" ? "应保留" : "垃圾"}{item.human_labeled_by ? ` · ${item.human_labeled_by}` : ""}</p>}
                  {item.last_error && <p className="text-caption-sm text-danger break-all">{item.last_error}</p>}
                  <p className="text-[11px] text-mute break-all" title={item.original_path}>{item.original_path}</p>
                  {canManage && (
                    <div className="flex flex-wrap gap-2">
                      {APPROVAL_STATUSES.has(item.status) && <button type="button" onClick={() => { if (window.confirm("将批准删除此照片，并写入 NAS 后台删除清单。应用不会直接移动或删除原片，但当前不能从页面撤销已写入的请求。继续？")) itemMutation.mutate({ item, action: "requestDelete" }); }} disabled={itemMutation.isPending} className="px-3 py-1.5 rounded-md bg-primary text-white text-btn-sm font-bold disabled:opacity-50">{item.status === "queue_failed" ? "重试提交删除" : "提交删除"}</button>}
                      {item.status === "delete_queued" && <button type="button" onClick={() => { if (window.confirm("将重新写入此照片的 NAS 后台删除清单。继续？")) itemMutation.mutate({ item, action: "requestDelete" }); }} disabled={itemMutation.isPending} className="px-3 py-1.5 rounded-md bg-primary text-white text-btn-sm font-bold disabled:opacity-50">重写删除清单</button>}
                      {APPROVAL_STATUSES.has(item.status) && <button type="button" onClick={() => itemMutation.mutate({ item, action: "keep" })} disabled={itemMutation.isPending} className="px-3 py-1.5 rounded-md border border-hairline text-btn-sm font-bold hover:bg-surface-card disabled:opacity-50">保留</button>}
                      {RESTORABLE_STATUSES.has(item.status) && <button type="button" onClick={() => itemMutation.mutate({ item, action: "restore" })} disabled={itemMutation.isPending} className="inline-flex items-center gap-1 px-3 py-1.5 rounded-md border border-hairline text-btn-sm font-bold hover:bg-surface-card disabled:opacity-50"><ArchiveRestore className="w-3.5 h-3.5" />放回原处</button>}
                      {(item.status === "delete_queued" || item.status === "quarantined") && <button type="button" onClick={() => { if (window.confirm("仅当 NAS 后台脚本已处理该文件时才确认。继续？")) itemMutation.mutate({ item, action: "confirm" }); }} disabled={itemMutation.isPending} className="px-3 py-1.5 rounded-md border border-hairline text-btn-sm text-mute hover:text-ink disabled:opacity-50">确认后台已处理</button>}
                    </div>
                  )}
                </div>
              </article>
            ))}
          </div>
        )}
        {(itemsQuery.data?.total ?? 0) > PAGE_SIZE && (
          <div className="flex items-center justify-center gap-3">
            <button type="button" onClick={() => setPage((value) => Math.max(0, value - 1))} disabled={page === 0} className="px-3 py-1.5 rounded-md border border-hairline text-btn-sm disabled:opacity-40">上一页</button>
            <span className="text-caption-sm text-mute">第 {page + 1} / {Math.ceil((itemsQuery.data?.total ?? 0) / PAGE_SIZE)} 页</span>
            <button type="button" onClick={() => setPage((value) => value + 1)} disabled={(page + 1) * PAGE_SIZE >= (itemsQuery.data?.total ?? 0)} className="px-3 py-1.5 rounded-md border border-hairline text-btn-sm disabled:opacity-40">下一页</button>
          </div>
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

function formatPercent(value: number | null): string {
  return value == null ? "暂无" : `${(value * 100).toFixed(1)}%`;
}
