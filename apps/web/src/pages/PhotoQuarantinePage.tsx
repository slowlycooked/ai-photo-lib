import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArchiveRestore, Loader2, Play, RefreshCw, Save, ShieldCheck, Trash2 } from "lucide-react";
import { Navigate, useParams } from "react-router-dom";
import {
  api,
  type PhotoQuarantineItem,
  type ProjectPhotoQuarantineSettingsUpdate,
} from "@/api";
import { BASE } from "@/api/client";
import { queryKeys } from "@/api/queryKeys";
import { useAuth } from "@/contexts/AuthContext";
import { useProjectContext } from "@/contexts/ProjectContext";
import { canManageProjects } from "@/lib/permissions";

const REVIEW_STATUSES = "review,quarantined,restore_conflict,restore_failed,move_failed,analysis_failed";
const RESTORABLE_STATUSES = new Set(["quarantined", "restore_conflict", "restore_failed"]);

const STATUS_OPTIONS = [
  { value: REVIEW_STATUSES, label: "待处理" },
  { value: "review", label: "待审核" },
  { value: "quarantined", label: "已移入待删除区" },
  { value: "restored", label: "已放回" },
  { value: "kept", label: "已保留" },
  { value: "deleted_confirmed", label: "已确认删除" },
  { value: "analysis_failed,move_failed,restore_conflict,restore_failed", label: "异常" },
] as const;

const STATUS_LABELS: Record<string, string> = {
  review: "待审核",
  quarantined: "待人工删除",
  restored: "已放回",
  kept: "已保留",
  deleted_confirmed: "已确认删除",
  analysis_failed: "识别失败",
  move_failed: "移动失败",
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
  const [statusFilter, setStatusFilter] = useState<string>(REVIEW_STATUSES);
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
    queryKey: queryKeys.photoQuarantineItems(selectedProjectId, statusFilter),
    queryFn: () => api.photoQuarantine.list(selectedProjectId!, statusFilter),
    enabled: projectExists,
    refetchInterval: 30_000,
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

  useEffect(() => setSelectedIds(new Set()), [statusFilter, selectedProjectId]);

  const refreshItems = () => {
    queryClient.invalidateQueries({ queryKey: ["photo-quarantine-items", selectedProjectId] });
    queryClient.invalidateQueries({ queryKey: queryKeys.photosBase(selectedProjectId) });
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
    },
    onError: (error: Error) => setMessage(`启动失败：${error.message}`),
  });
  const itemMutation = useMutation({
    mutationFn: ({ item, action }: { item: PhotoQuarantineItem; action: "move" | "restore" | "confirm" | "keep" }) => {
      if (action === "move") return api.photoQuarantine.move(selectedProjectId!, item.id);
      if (action === "restore") return api.photoQuarantine.restore(selectedProjectId!, item.id);
      if (action === "keep") return api.photoQuarantine.keep(selectedProjectId!, item.id);
      return api.photoQuarantine.confirmDeleted(selectedProjectId!, item.id);
    },
    onSuccess: (_, variables) => {
      setMessage(variables.action === "restore" ? "照片已安全放回原位置" : "操作已完成");
      refreshItems();
    },
    onError: (error: Error) => setMessage(`操作失败：${error.message}`),
  });
  const bulkRestoreMutation = useMutation({
    mutationFn: async (ids: number[]) => {
      const results = await Promise.allSettled(
        ids.map((id) => api.photoQuarantine.restore(selectedProjectId!, id)),
      );
      return {
        restored: results.filter((result) => result.status === "fulfilled").length,
        failed: results.filter((result) => result.status === "rejected").length,
      };
    },
    onSuccess: ({ restored, failed }) => {
      setMessage(`已放回 ${restored} 张${failed ? `，${failed} 张失败，请逐项检查` : ""}`);
      setSelectedIds(new Set());
      refreshItems();
    },
  });

  const items = itemsQuery.data?.items ?? [];
  const restorableSelected = useMemo(
    () => items.filter((item) => selectedIds.has(item.id) && RESTORABLE_STATUSES.has(item.status)),
    [items, selectedIds],
  );

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
            系统只移动文件，不会永久删除；放回时绝不覆盖原位置已有文件。
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
              <label className="text-caption-sm text-mute">保留天数
                <input className={fieldClass()} type="number" min={1} max={3650} disabled={!canManage} value={form.retention_days} onChange={(event) => setForm({ ...form, retention_days: Number(event.target.value) })} />
              </label>
            </div>
            <div className="flex flex-wrap items-center gap-5 text-body-sm">
              <label className="flex items-center gap-2"><input type="checkbox" disabled={!canManage} checked={form.enabled} onChange={(event) => setForm({ ...form, enabled: event.target.checked })} />启用每日跑批</label>
              <label className="flex items-center gap-2"><input type="checkbox" disabled={!canManage} checked={form.dry_run} onChange={(event) => setForm({ ...form, dry_run: event.target.checked })} />校准模式（只识别、不移动）</label>
              {canManage && <button type="button" onClick={() => saveMutation.mutate()} disabled={saveMutation.isPending} className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-hairline text-btn-sm font-bold hover:bg-surface-card disabled:opacity-50"><Save className="w-4 h-4" />保存设置</button>}
            </div>
            <p className="text-caption-sm text-mute">默认 01:00–06:00。到结束时间后会完成当前图片再暂停，剩余图片次日继续。</p>
          </div>
        )}
      </section>

      <section className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)} className="rounded-md border border-hairline bg-canvas px-3 py-2 text-body-sm">
              {STATUS_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
            <span className="text-caption-sm text-mute">共 {itemsQuery.data?.total ?? 0} 项</span>
            <button type="button" onClick={() => itemsQuery.refetch()} className="text-mute hover:text-ink" aria-label="刷新"><RefreshCw className="w-4 h-4" /></button>
          </div>
          {canManage && restorableSelected.length > 0 && (
            <button type="button" onClick={() => bulkRestoreMutation.mutate(restorableSelected.map((item) => item.id))} disabled={bulkRestoreMutation.isPending} className="inline-flex items-center gap-1.5 px-3 py-2 rounded-md border border-hairline text-btn-sm font-bold hover:bg-surface-card disabled:opacity-50">
              <ArchiveRestore className="w-4 h-4" />批量放回（{restorableSelected.length}）
            </button>
          )}
        </div>

        {itemsQuery.isLoading ? (
          <div className="flex items-center gap-2 py-12 justify-center text-mute"><Loader2 className="w-5 h-5 animate-spin" />加载审核项…</div>
        ) : items.length === 0 ? (
          <div className="rounded-lg border border-hairline bg-canvas py-14 text-center text-mute">当前筛选条件下没有图片。</div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
            {items.map((item) => (
              <article key={item.id} className="overflow-hidden rounded-lg border border-hairline bg-canvas">
                <div className="relative aspect-video bg-surface-card">
                  <img src={`${BASE}/projects/${selectedProjectId}/photo-quarantine/items/${item.id}/thumbnail`} alt="待删除候选图片" className="h-full w-full object-contain" loading="lazy" />
                  {canManage && RESTORABLE_STATUSES.has(item.status) && <input type="checkbox" className="absolute top-3 left-3 w-4 h-4" aria-label="选择放回" checked={selectedIds.has(item.id)} onChange={(event) => setSelectedIds((current) => { const next = new Set(current); event.target.checked ? next.add(item.id) : next.delete(item.id); return next; })} />}
                  <span className="absolute top-2 right-2 rounded-full bg-black/70 px-2 py-1 text-[11px] text-white">{STATUS_LABELS[item.status] ?? item.status}</span>
                </div>
                <div className="p-4 space-y-3">
                  <div>
                    <div className="font-bold text-ink">{CLASS_LABELS[item.classification] ?? item.classification}</div>
                    <div className="text-caption-sm text-mute">置信度 {(item.confidence * 100).toFixed(1)}% · {item.model_name}</div>
                  </div>
                  <p className="text-body-sm text-ink">{item.reason}</p>
                  {item.preservation_flags.length > 0 && <p className="text-caption-sm text-danger">保留信号：{item.preservation_flags.join("、")}</p>}
                  {item.last_error && <p className="text-caption-sm text-danger break-all">{item.last_error}</p>}
                  <p className="text-[11px] text-mute break-all" title={item.original_path}>{item.original_path}</p>
                  {canManage && (
                    <div className="flex flex-wrap gap-2">
                      {item.status === "review" && item.decision === "QUARANTINE" && <button type="button" onClick={() => itemMutation.mutate({ item, action: "move" })} disabled={itemMutation.isPending} className="px-3 py-1.5 rounded-md bg-primary text-white text-btn-sm font-bold disabled:opacity-50">移至待删除区</button>}
                      {item.status === "review" && <button type="button" onClick={() => itemMutation.mutate({ item, action: "keep" })} disabled={itemMutation.isPending} className="px-3 py-1.5 rounded-md border border-hairline text-btn-sm font-bold hover:bg-surface-card disabled:opacity-50">保留此图</button>}
                      {RESTORABLE_STATUSES.has(item.status) && <button type="button" onClick={() => itemMutation.mutate({ item, action: "restore" })} disabled={itemMutation.isPending} className="inline-flex items-center gap-1 px-3 py-1.5 rounded-md border border-hairline text-btn-sm font-bold hover:bg-surface-card disabled:opacity-50"><ArchiveRestore className="w-3.5 h-3.5" />放回原处</button>}
                      {item.status === "quarantined" && <button type="button" onClick={() => { if (window.confirm("仅当你已在文件系统中人工删除该文件时才确认。继续？")) itemMutation.mutate({ item, action: "confirm" }); }} disabled={itemMutation.isPending} className="px-3 py-1.5 rounded-md border border-hairline text-btn-sm text-mute hover:text-ink disabled:opacity-50">确认已人工删除</button>}
                    </div>
                  )}
                </div>
              </article>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
