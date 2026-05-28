import { useEffect, useMemo, useState } from "react";
import { Link, NavLink, Navigate, useLocation } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Loader2,
  AlertCircle,
  Settings,
  Save,
  FolderOpen,
  Plus,
  Pencil,
  Trash2,
  Check,
  X,
  Star,
  AlertTriangle,
  Activity,
  CheckCircle2,
} from "lucide-react";
import {
  api,
  type DebugMatrix,
  type DebugMode,
  type DebugPresetMode,
  type DebugSettingsResponse,
  type DebugSettingsUpdate,
  type LogLevel,
  type Project,
} from "@/api";
import { queryKeys } from "@/api/queryKeys";
import {
  useProjects,
  useCreateProject,
  useUpdateProject,
  useDeleteProject,
} from "@/hooks/useProjects";
import { useProjectContext } from "@/contexts/ProjectContext";
import { configureFrontendLogger } from "@/lib/logger";

// ─── Path helpers ────────────────────────────────────────────────────────────

/** Convert legacy container path to host path for display. */
function containerToHost(containerPath: string, hostPrefix: string): string {
  const prefix = hostPrefix.replace(/\/$/, "");
  if (containerPath.startsWith("/photos")) {
    return prefix + containerPath.slice("/photos".length);
  }
  return containerPath;
}

/** Convert host path back to the legacy stored path shape when needed. */
function hostToContainer(hostPath: string, hostPrefix: string): string {
  const prefix = hostPrefix.replace(/\/$/, "");
  const normalized = hostPath.replace(/\/$/, "");
  if (normalized.startsWith(prefix)) {
    return "/photos" + normalized.slice(prefix.length);
  }
  // Already a container path or unknown prefix — pass through
  return hostPath;
}

// ─── Shared UI ────────────────────────────────────────────────────────────────

function SettingRow({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex items-start justify-between gap-4 py-3 border-b border-hairline last:border-0">
      <span className="text-body-sm text-mute flex-shrink-0 w-40">{label}</span>
      <span className="text-body-sm text-ink font-medium text-right break-all">{value}</span>
    </div>
  );
}

function SettingsCard({
  title,
  action,
  children,
}: {
  title: string;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="bg-canvas border border-hairline rounded-md">
      <div className="px-5 py-3 border-b border-hairline flex items-center justify-between">
        <h2 className="text-body-sm font-semibold text-ink">{title}</h2>
        {action}
      </div>
      <div className="px-5">{children}</div>
    </div>
  );
}

function ProjectReadinessCard({ projectId }: { projectId: number }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["project-readiness", projectId],
    queryFn: () => api.projects.readiness(projectId),
    staleTime: 30_000,
  });

  return (
    <SettingsCard title="项目运行就绪检查">
      <div className="py-3 space-y-3">
        {isLoading && (
          <div className="flex items-center gap-2 text-body-sm text-mute">
            <Loader2 className="w-4 h-4 animate-spin" />
            正在检查项目配置…
          </div>
        )}
        {isError && (
          <div className="flex items-center gap-2 text-body-sm text-danger">
            <AlertCircle className="w-4 h-4" />
            无法获取项目就绪状态，请检查 API 服务。
          </div>
        )}
        {data && (
          <>
            <div className="flex items-center justify-between gap-3 pb-2 border-b border-hairline">
              <span className="text-body-sm text-mute">当前项目整体状态</span>
              <span
                className={`inline-flex items-center gap-1 text-body-sm font-semibold ${
                  data.ready ? "text-green-600" : "text-amber-600"
                }`}
              >
                {data.ready ? <CheckCircle2 className="w-4 h-4" /> : <AlertTriangle className="w-4 h-4" />}
                {data.ready ? "READY" : "NOT READY"}
              </span>
            </div>
            {data.checks.map((check) => (
              <div key={check.name} className="flex items-start justify-between gap-3 py-2 border-b border-hairline last:border-0">
                <div>
                  <p className="text-body-sm text-ink font-medium">{check.name}</p>
                  <p className="text-caption-sm text-mute mt-0.5">{check.message}</p>
                  {!check.ready && (
                    <div className="mt-2">
                      <Link
                        to={resolveReadinessFixPath(projectId, check.name)}
                        className="text-caption-sm text-primary hover:underline"
                      >
                        去修复
                      </Link>
                    </div>
                  )}
                </div>
                <span
                  className={`text-caption-sm font-semibold px-2 py-0.5 rounded ${
                    check.ready
                      ? "bg-green-50 text-green-700"
                      : "bg-amber-50 text-amber-700"
                  }`}
                >
                  {check.ready ? "READY" : "NOT READY"}
                </span>
              </div>
            ))}
          </>
        )}
      </div>
    </SettingsCard>
  );
}

function resolveReadinessFixPath(projectId: number, checkName: string): string {
  if (checkName === "scan_runtime") {
    return "/tasks?tab=scan";
  }
  if (checkName === "ai_runtime" || checkName === "embedding_runtime") {
    return `/projects/${projectId}/settings/vision-ai`;
  }
  return "/settings/general";
}

// ─── Library form (shared by add & edit) ─────────────────────────────────────

interface LibraryFormValues {
  name: string;
  photo_library_path: string;
  is_default: boolean;
}

function LibraryForm({
  initial,
  hostPrefix,
  submitLabel,
  isSubmitting,
  error,
  onSubmit,
  onCancel,
}: {
  initial: LibraryFormValues;
  hostPrefix: string;
  submitLabel: string;
  isSubmitting: boolean;
  error?: Error | null;
  onSubmit: (v: LibraryFormValues) => void;
  onCancel: () => void;
}) {
  // Keep compatibility with older records that still store `/photos/...`.
  const initialDisplay = useMemo(
    () => ({ ...initial, photo_library_path: containerToHost(initial.photo_library_path, hostPrefix) }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [initial.photo_library_path, hostPrefix]
  );
  const [values, setValues] = useState<LibraryFormValues>(initialDisplay);

  function set(k: keyof LibraryFormValues, v: string | boolean) {
    setValues((prev) => ({ ...prev, [k]: v }));
  }

  function handleSubmit() {
    onSubmit({
      ...values,
      photo_library_path: hostToContainer(values.photo_library_path, hostPrefix),
    });
  }

  const hostExample = hostPrefix.replace(/\/$/, "") + "/my-library";

  return (
    <div className="py-3 space-y-2.5">
      <div className="flex gap-2">
        <div className="flex-1">
          <label className="block text-caption-sm text-mute mb-1">名称</label>
          <input
            type="text"
            value={values.name}
            onChange={(e) => set("name", e.target.value)}
            placeholder="我的图片库"
            className="w-full px-3 py-1.5 text-body-sm bg-surface-card border border-hairline rounded-md focus:outline-none focus:ring-1 focus:ring-primary text-ink placeholder:text-mute"
          />
        </div>
        <div className="flex-[2]">
          <label className="block text-caption-sm text-mute mb-1">路径（系统实际路径）</label>
          <input
            type="text"
            value={values.photo_library_path}
            onChange={(e) => set("photo_library_path", e.target.value)}
            placeholder={hostExample}
            className="w-full px-3 py-1.5 text-body-sm bg-surface-card border border-hairline rounded-md focus:outline-none focus:ring-1 focus:ring-primary text-ink placeholder:text-mute font-mono"
          />
        </div>
      </div>
      <label className="flex items-center gap-2 cursor-pointer select-none">
        <input
          type="checkbox"
          checked={values.is_default}
          onChange={(e) => set("is_default", e.target.checked)}
          className="accent-primary w-3.5 h-3.5"
        />
        <span className="text-body-sm text-ink">设为默认图片库</span>
      </label>
      <div className="flex gap-2 pt-1">
        <button
          disabled={isSubmitting || !values.name.trim() || !values.photo_library_path.trim()}
          onClick={handleSubmit}
          className="flex items-center gap-1.5 px-3 py-1.5 text-body-sm font-medium rounded-md bg-primary text-white disabled:opacity-50 hover:opacity-90 transition-opacity"
        >
          {isSubmitting ? (
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
          ) : (
            <Check className="w-3.5 h-3.5" />
          )}
          {submitLabel}
        </button>
        <button
          onClick={onCancel}
          className="flex items-center gap-1.5 px-3 py-1.5 text-body-sm rounded-md border border-hairline text-ink hover:bg-secondary-bg transition-colors"
        >
          <X className="w-3.5 h-3.5" />
          取消
        </button>
      </div>
      {error && (
        <p className="flex items-center gap-1.5 text-caption-sm text-red-500">
          <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" />
          {error.message}
        </p>
      )}
    </div>
  );
}

// ─── Single library row ───────────────────────────────────────────────────────

function LibraryRow({
  project,
  hostPrefix,
  onEdit,
  onDelete,
  onSetDefault,
}: {
  project: Project;
  hostPrefix: string;
  onEdit: () => void;
  onDelete: () => void;
  onSetDefault: () => void;
}) {
  return (
    <div className="flex items-center gap-3 py-3 border-b border-hairline last:border-0">
      <FolderOpen className="w-4 h-4 text-primary flex-shrink-0" />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-body-sm font-medium text-ink truncate">{project.name}</span>
          {project.is_default && (
            <span className="text-caption-sm px-1.5 py-0.5 bg-primary/10 text-primary rounded font-medium">
              默认
            </span>
          )}
        </div>
        <p className="text-caption-sm text-mute font-mono truncate mt-0.5">
          {containerToHost(project.photo_library_path, hostPrefix)}
        </p>
      </div>
      <div className="flex items-center gap-1 flex-shrink-0">
        {!project.is_default && (
          <button
            onClick={onSetDefault}
            title="设为默认"
            className="p-1.5 rounded hover:bg-secondary-bg text-mute hover:text-primary transition-colors"
          >
            <Star className="w-3.5 h-3.5" />
          </button>
        )}
        <button
          onClick={onEdit}
          title="编辑"
          className="p-1.5 rounded hover:bg-secondary-bg text-mute hover:text-ink transition-colors"
        >
          <Pencil className="w-3.5 h-3.5" />
        </button>
        {!project.is_default && (
          <button
            onClick={onDelete}
            title="删除"
            className="p-1.5 rounded hover:bg-secondary-bg text-mute hover:text-red-500 transition-colors"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        )}
      </div>
    </div>
  );
}

// ─── Library management card ──────────────────────────────────────────────────

function LibraryManagementCard() {
  const { data: projectsData, isLoading, isError } = useProjects();
  const { data: settingsData } = useQuery({
    queryKey: queryKeys.settings(),
    queryFn: api.settings.get,
    staleTime: 60_000,
  });
  const hostPrefix = settingsData?.host_photo_library_path ?? "";

  const createProject = useCreateProject();
  const updateProject = useUpdateProject();
  const deleteProject = useDeleteProject();

  const [showAddForm, setShowAddForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [deleteConfirmId, setDeleteConfirmId] = useState<number | null>(null);

  const projects = projectsData?.items ?? [];

  function handleCreate(v: LibraryFormValues) {
    createProject.mutate(
      { name: v.name, photo_library_path: v.photo_library_path, is_default: v.is_default },
      { onSuccess: () => setShowAddForm(false) }
    );
  }

  function handleUpdate(id: number, v: LibraryFormValues) {
    updateProject.mutate(
      { id, body: { name: v.name, photo_library_path: v.photo_library_path, is_default: v.is_default } },
      { onSuccess: () => setEditingId(null) }
    );
  }

  function handleSetDefault(id: number) {
    updateProject.mutate({ id, body: { is_default: true } });
  }

  function handleDelete(id: number) {
    deleteProject.mutate(id, { onSuccess: () => setDeleteConfirmId(null) });
  }

  return (
    <SettingsCard
      title="图片库管理"
      action={
        !showAddForm && (
          <button
            onClick={() => { setShowAddForm(true); setEditingId(null); }}
            className="flex items-center gap-1.5 px-2.5 py-1 text-body-sm rounded-md border border-hairline text-ink hover:bg-secondary-bg transition-colors"
          >
            <Plus className="w-3.5 h-3.5" />
            添加图片库
          </button>
        )
      }
    >
      {isLoading && (
        <div className="flex items-center gap-2 text-mute py-6 justify-center">
          <Loader2 className="w-4 h-4 animate-spin" />
          <span className="text-body-sm">加载中…</span>
        </div>
      )}
      {isError && (
        <div className="flex items-center gap-2 text-mute py-6 justify-center">
          <AlertCircle className="w-4 h-4" />
          <span className="text-body-sm">无法加载图片库列表</span>
        </div>
      )}

      {projects.map((project) =>
        editingId === project.id ? (
          <div key={project.id} className="border-b border-hairline last:border-0">
            <LibraryForm
              initial={{
                name: project.name,
                photo_library_path: project.photo_library_path,
                is_default: project.is_default,
              }}
              hostPrefix={hostPrefix}
              submitLabel="保存"
              isSubmitting={updateProject.isPending}
              error={updateProject.error}
              onSubmit={(v) => handleUpdate(project.id, v)}
              onCancel={() => setEditingId(null)}
            />
          </div>
        ) : deleteConfirmId === project.id ? (
          <div
            key={project.id}
            className="flex items-center justify-between gap-3 py-3 border-b border-hairline last:border-0"
          >
            <span className="text-body-sm text-ink">
              确认删除图片库 <span className="font-medium">"{project.name}"</span>？此操作不可恢复。
            </span>
            <div className="flex gap-2 flex-shrink-0">
              <button
                disabled={deleteProject.isPending}
                onClick={() => handleDelete(project.id)}
                className="flex items-center gap-1 px-3 py-1.5 text-body-sm font-medium rounded-md bg-red-500 text-white disabled:opacity-50 hover:opacity-90 transition-opacity"
              >
                {deleteProject.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}
                删除
              </button>
              <button
                onClick={() => setDeleteConfirmId(null)}
                className="px-3 py-1.5 text-body-sm rounded-md border border-hairline text-ink hover:bg-secondary-bg transition-colors"
              >
                取消
              </button>
            </div>
          </div>
        ) : (
          <LibraryRow
            key={project.id}
            project={project}
            hostPrefix={hostPrefix}
            onEdit={() => { setEditingId(project.id); setShowAddForm(false); setDeleteConfirmId(null); }}
            onDelete={() => { setDeleteConfirmId(project.id); setEditingId(null); }}
            onSetDefault={() => handleSetDefault(project.id)}
          />
        )
      )}

      {showAddForm && (
        <div className="border-t border-hairline">
          <LibraryForm
            initial={{ name: "", photo_library_path: "", is_default: false }}
            hostPrefix={hostPrefix}
            submitLabel="添加"
            isSubmitting={createProject.isPending}
            error={createProject.error}
            onSubmit={handleCreate}
            onCancel={() => setShowAddForm(false)}
          />
        </div>
      )}

      {!isLoading && !isError && projects.length === 0 && !showAddForm && (
        <p className="text-body-sm text-mute py-6 text-center">
          暂无图片库，点击「添加图片库」开始使用
        </p>
      )}
    </SettingsCard>
  );
}

const MODE_OPTIONS: Array<{ value: DebugMode; label: string }> = [
  { value: "OFF", label: "OFF" },
  { value: "BASIC", label: "BASIC" },
  { value: "DEBUG", label: "DEBUG" },
  { value: "TRACE", label: "TRACE" },
  { value: "CUSTOM", label: "CUSTOM" },
];

const LOG_LEVEL_OPTIONS: LogLevel[] = ["OFF", "ERROR", "WARNING", "INFO", "DEBUG", "TRACE"];

const MATRIX_FIELD_LABELS: Array<{ key: keyof DebugMatrix; label: string }> = [
  { key: "frontendLogLevel", label: "Frontend" },
  { key: "backendLogLevel", label: "Backend" },
  { key: "aiLogLevel", label: "AI" },
  { key: "searchLogLevel", label: "Search" },
  { key: "sqlLogLevel", label: "SQL" },
  { key: "taskLogLevel", label: "Task" },
];

const FALLBACK_PRESETS: Record<DebugPresetMode, DebugMatrix> = {
  OFF: {
    frontendLogLevel: "OFF",
    backendLogLevel: "OFF",
    aiLogLevel: "OFF",
    searchLogLevel: "OFF",
    sqlLogLevel: "OFF",
    taskLogLevel: "OFF",
  },
  BASIC: {
    frontendLogLevel: "INFO",
    backendLogLevel: "INFO",
    aiLogLevel: "INFO",
    searchLogLevel: "INFO",
    sqlLogLevel: "WARNING",
    taskLogLevel: "INFO",
  },
  DEBUG: {
    frontendLogLevel: "DEBUG",
    backendLogLevel: "DEBUG",
    aiLogLevel: "DEBUG",
    searchLogLevel: "DEBUG",
    sqlLogLevel: "DEBUG",
    taskLogLevel: "DEBUG",
  },
  TRACE: {
    frontendLogLevel: "TRACE",
    backendLogLevel: "TRACE",
    aiLogLevel: "TRACE",
    searchLogLevel: "TRACE",
    sqlLogLevel: "TRACE",
    taskLogLevel: "TRACE",
  },
};

const FALLBACK_DEBUG_SETTINGS: DebugSettingsResponse = {
  debugMode: "BASIC",
  debugMatrix: FALLBACK_PRESETS.BASIC,
  presets: FALLBACK_PRESETS,
  updatedAt: null,
};

function cloneMatrix(matrix: DebugMatrix): DebugMatrix {
  return { ...matrix };
}

export function DebugLogSettingsCard() {
  const queryClient = useQueryClient();
  const {
    data,
    isLoading,
    error,
  } = useQuery({
    queryKey: queryKeys.settingsDebug(),
    queryFn: api.settings.getDebug,
    staleTime: 15_000,
    retry: 0,
  });

  const [form, setForm] = useState<DebugSettingsUpdate>({
    debugMode: FALLBACK_DEBUG_SETTINGS.debugMode,
    debugMatrix: cloneMatrix(FALLBACK_DEBUG_SETTINGS.debugMatrix),
  });
  const [successMessage, setSuccessMessage] = useState<string>("");

  useEffect(() => {
    if (!data) return;
    setForm({
      debugMode: data.debugMode,
      debugMatrix: cloneMatrix(data.debugMatrix),
    });
  }, [data]);

  const presets = data?.presets ?? FALLBACK_DEBUG_SETTINGS.presets;
  const loadErrorMessage = error instanceof Error ? error.message : "";

  const saveMutation = useMutation({
    mutationFn: (payload: DebugSettingsUpdate) => api.settings.updateDebug(payload),
    onSuccess: (saved) => {
      queryClient.setQueryData(queryKeys.settingsDebug(), saved);
      configureFrontendLogger(saved.debugMatrix);
      setForm({
        debugMode: saved.debugMode,
        debugMatrix: cloneMatrix(saved.debugMatrix),
      });
      setSuccessMessage("已保存并应用到运行时");
      setTimeout(() => setSuccessMessage(""), 1800);
    },
  });

  function applyMode(nextMode: DebugMode) {
    if (nextMode === "CUSTOM") {
      setForm((prev) => ({ ...prev, debugMode: "CUSTOM" }));
      return;
    }
    setForm({
      debugMode: nextMode,
      debugMatrix: cloneMatrix(presets[nextMode]),
    });
  }

  function updateMatrix(field: keyof DebugMatrix, value: LogLevel) {
    setForm((prev) => ({
      debugMode: "CUSTOM",
      debugMatrix: {
        ...prev.debugMatrix,
        [field]: value,
      },
    }));
  }

  if (isLoading && !data) {
    return (
      <SettingsCard title="Debug 与日志">
        <div className="flex items-center gap-2 text-mute py-6 justify-center">
          <Loader2 className="w-4 h-4 animate-spin" />
          <span className="text-body-sm">加载 Debug 配置中…</span>
        </div>
      </SettingsCard>
    );
  }

  return (
    <SettingsCard
      title="Debug 与日志"
      action={
        <button
          onClick={() => saveMutation.mutate(form)}
          disabled={saveMutation.isPending}
          className="flex items-center gap-1.5 px-2.5 py-1 text-body-sm rounded-md border border-hairline text-ink hover:bg-secondary-bg disabled:opacity-50 transition-colors"
        >
          {saveMutation.isPending ? (
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
          ) : (
            <Save className="w-3.5 h-3.5" />
          )}
          保存配置
        </button>
      }
    >
      <div className="py-4 space-y-4">
        {loadErrorMessage && (
          <div className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-amber-700">
            <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0" />
            <p className="text-caption-sm">加载失败：{loadErrorMessage}。页面已回退到 BASIC 预设，避免白屏。</p>
          </div>
        )}

        <div className="space-y-2">
          <p className="text-caption-sm text-mute">Debug Mode</p>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
            {MODE_OPTIONS.map((option) => (
              <button
                key={option.value}
                type="button"
                onClick={() => applyMode(option.value)}
                className={`rounded-md border px-3 py-2 text-body-sm transition-colors ${
                  form.debugMode === option.value
                    ? "border-primary bg-primary/10 text-primary"
                    : "border-hairline text-ink hover:bg-secondary-bg"
                }`}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>

        <div className="overflow-x-auto rounded-md border border-hairline">
          <table className="min-w-full border-collapse">
            <thead className="bg-secondary-bg">
              <tr>
                <th className="px-3 py-2 text-left text-caption-sm font-medium text-mute">Logger</th>
                <th className="px-3 py-2 text-left text-caption-sm font-medium text-mute">Level</th>
              </tr>
            </thead>
            <tbody>
              {MATRIX_FIELD_LABELS.map((field) => (
                <tr key={field.key} className="border-t border-hairline">
                  <td className="px-3 py-2 text-body-sm text-ink">{field.label}</td>
                  <td className="px-3 py-2">
                    <select
                      value={form.debugMatrix[field.key]}
                      onChange={(e) => updateMatrix(field.key, e.target.value as LogLevel)}
                      className="w-full rounded-md border border-hairline bg-surface-card px-3 py-1.5 text-body-sm text-ink"
                    >
                      {LOG_LEVEL_OPTIONS.map((option) => (
                        <option key={option} value={option}>{option}</option>
                      ))}
                    </select>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {form.debugMode === "TRACE" && (
          <p className="text-caption-sm text-amber-600 bg-amber-50 border border-amber-200 rounded-md px-3 py-2">
            <span className="inline-flex items-center gap-1.5">
              <AlertTriangle className="h-4 w-4" />
              TRACE 模式可能产生大量日志，并可能包含 AI 输入输出内容。
            </span>
          </p>
        )}

        <div className="flex items-center justify-between gap-3 text-caption-sm text-mute">
          <span>当前模式：{form.debugMode}</span>
          <span>上次应用：{data?.updatedAt ? new Date(data.updatedAt).toLocaleString() : "未保存"}</span>
        </div>

        {successMessage && (
          <p className="text-caption-sm text-green-600">{successMessage}</p>
        )}
        {saveMutation.isError && (
          <p className="text-caption-sm text-red-500">
            保存失败：{(saveMutation.error as Error)?.message ?? "未知错误"}
          </p>
        )}
      </div>
    </SettingsCard>
  );
}

export function SystemHealthCard() {
  const { data, isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: ["system-health"],
    queryFn: api.settings.health,
    staleTime: 15_000,
    retry: 0,
  });

  const statusClass = {
    ok: "text-green-700",
    warn: "text-amber-600",
    fail: "text-red-600",
  } as const;

  return (
    <SettingsCard
      title="运行状态"
      action={
        <button
          type="button"
          onClick={() => refetch()}
          disabled={isFetching}
          className="flex items-center gap-1.5 px-2.5 py-1 text-body-sm rounded-md border border-hairline text-ink hover:bg-secondary-bg disabled:opacity-50 transition-colors"
        >
          {isFetching ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Activity className="w-3.5 h-3.5" />}
          检查
        </button>
      }
    >
      {isLoading && (
        <div className="flex items-center gap-2 text-mute py-6 justify-center">
          <Loader2 className="w-4 h-4 animate-spin" />
          <span className="text-body-sm">检查中…</span>
        </div>
      )}
      {isError && (
        <div className="flex items-center gap-2 text-red-600 py-6 justify-center">
          <AlertCircle className="w-4 h-4" />
          <span className="text-body-sm">{error instanceof Error ? error.message : "健康检查失败"}</span>
        </div>
      )}
      {data && (
        <div className="py-3 space-y-2">
          <div className="flex items-center justify-between gap-3 border-b border-hairline pb-3">
            <span className="text-body-sm text-mute">整体状态</span>
            <span className={`text-body-sm font-semibold ${statusClass[data.status]}`}>
              {data.status.toUpperCase()} · v{data.version}
            </span>
          </div>
          {data.checks.map((check) => (
            <div key={check.name} className="flex items-start justify-between gap-4 py-2 border-b border-hairline last:border-0">
              <span className="text-body-sm text-ink">{check.name}</span>
              <span className={`text-caption-sm text-right break-all ${statusClass[check.status]}`}>
                {check.status.toUpperCase()}
                {check.message ? ` · ${check.message}` : ""}
              </span>
            </div>
          ))}
        </div>
      )}
    </SettingsCard>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export function SettingsPage() {
  const location = useLocation();
  const { currentProjectId } = useProjectContext();
  const { data, isLoading, isError } = useQuery({
    queryKey: queryKeys.settings(),
    queryFn: api.settings.get,
    staleTime: 60_000,
  });

  const section = location.pathname.split("/")[2] ?? "";
  const activeSection = section === "" ? "general" : section;
  const knownSections = new Set(["general", "monitoring", "debug"]);

  if (section === "") {
    return <Navigate to="/settings/general" replace />;
  }

  if (!knownSections.has(activeSection)) {
    return <Navigate to="/settings/general" replace />;
  }

  const currentProjectSettingsBase =
    currentProjectId != null ? `/projects/${currentProjectId}/settings` : null;

  const globalNavItems = [
    { key: "general", label: "常规配置", to: "/settings/general" },
    { key: "monitoring", label: "系统监控", to: "/settings/monitoring" },
    { key: "debug", label: "Debug / 日志", to: "/settings/debug" },
  ] as const;

  const projectNavItems = [
    { key: "vision-ai", label: "视觉 AI", suffix: "vision-ai" },
    { key: "embedding-ai", label: "Embedding AI", suffix: "embedding-ai" },
    { key: "planner-ai", label: "Planner AI", suffix: "planner-ai" },
    { key: "advanced", label: "高级搜索参数", suffix: "advanced" },
  ] as const;

  return (
    <main className="max-w-7xl mx-auto px-4 sm:px-6 py-6 space-y-6">
      <div className="flex items-center gap-2">
        <Settings className="w-5 h-5 text-ink" />
        <h1 className="text-heading-md font-semibold text-ink">系统设置</h1>
      </div>

      <div className="rounded-md border border-hairline bg-canvas px-4 py-3 flex flex-wrap items-center gap-3 text-body-sm">
        <span className="text-mute">当前项目</span>
        <span className="font-medium text-ink">{currentProjectId != null ? `#${currentProjectId}` : "未选择"}</span>
        {currentProjectId != null && (
          <Link
            to={`/projects/${currentProjectId}/settings/vision-ai`}
            className="ml-auto px-3 py-1.5 rounded-md border border-hairline hover:bg-surface-card"
          >
            打开项目设置
          </Link>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[220px_minmax(0,1fr)] gap-6">
        <aside className="bg-canvas border border-hairline rounded-md p-2 h-fit space-y-3">
          <div>
            <p className="px-2 py-1 text-caption-sm text-mute">基础</p>
            <nav className="space-y-1 mt-1">
              {globalNavItems.map((item) => (
                <NavLink
                  key={item.key}
                  to={item.to}
                  className={({ isActive }) =>
                    [
                      "flex items-center gap-2 px-2.5 py-2 rounded-md text-body-sm border transition-colors",
                      isActive
                        ? "border-primary text-primary bg-primary/10"
                        : "border-transparent text-ink hover:bg-surface-card",
                    ].join(" ")
                  }
                >
                  {item.label}
                </NavLink>
              ))}
            </nav>
          </div>

          <div>
            <p className="px-2 py-1 text-caption-sm text-mute">AI 能力（项目级）</p>
            <nav className="space-y-1 mt-1">
              {projectNavItems.map((item) => {
                const target =
                  currentProjectSettingsBase != null
                    ? `${currentProjectSettingsBase}/${item.suffix}`
                    : null;
                if (!target) {
                  return (
                    <span
                      key={item.key}
                      className="flex items-center gap-2 px-2.5 py-2 rounded-md text-body-sm text-mute border border-transparent"
                    >
                      {item.label}
                    </span>
                  );
                }
                return (
                  <NavLink
                    key={item.key}
                    to={target}
                    className="flex items-center gap-2 px-2.5 py-2 rounded-md text-body-sm border border-transparent text-ink hover:bg-surface-card"
                  >
                    {item.label}
                  </NavLink>
                );
              })}
            </nav>
          </div>
        </aside>

        <section className="space-y-6">
          {activeSection === "general" && (
            <>
              <LibraryManagementCard />

              {currentProjectId != null ? (
                <SettingsCard title="当前项目状态摘要">
                  <div className="py-3 flex items-center justify-between gap-3">
                    <p className="text-body-sm text-mute">
                      项目级 AI、Embedding、Planner 配置已迁移到独立设置分区。
                    </p>
                    <Link
                      to={`/projects/${currentProjectId}/settings/vision-ai`}
                      className="px-3 py-1.5 text-body-sm rounded-md border border-hairline text-ink hover:bg-secondary-bg transition-colors"
                    >
                      打开项目设置
                    </Link>
                  </div>
                </SettingsCard>
              ) : (
                <SettingsCard title="当前项目状态摘要">
                  <div className="py-3 text-body-sm text-mute">
                    请先选择项目后查看项目级配置与就绪状态。
                  </div>
                </SettingsCard>
              )}

              {isLoading && (
                <div className="flex items-center gap-2 text-mute py-12 justify-center">
                  <Loader2 className="w-5 h-5 animate-spin" />
                  <span className="text-body-sm">加载中…</span>
                </div>
              )}

              {isError && (
                <div className="flex items-center gap-2 text-mute py-12 justify-center">
                  <AlertCircle className="w-5 h-5" />
                  <span className="text-body-sm">无法加载设置，请检查 API 服务</span>
                </div>
              )}

              {data && (
                <div className="space-y-4">
                  <SettingsCard title="路径映射与系统配置">
                    <SettingRow label="Host Path" value={data.host_photo_library_path} />
                    <SettingRow label="Container Path" value={data.photo_library_path} />
                  </SettingsCard>

                  <SettingsCard title="Worker 配置">
                    <SettingRow label="最大重试次数" value={data.ai_max_retries} />
                  </SettingsCard>
                </div>
              )}
            </>
          )}

          {activeSection === "monitoring" && (
            <>
              <SystemHealthCard />
              {currentProjectId != null && <ProjectReadinessCard projectId={currentProjectId} />}
              <SettingsCard title="日志入口">
                <div className="py-3 flex items-center justify-between gap-3">
                  <p className="text-body-sm text-mute">需要查看详细日志级别和实时 debug 配置，请进入 Debug 页。</p>
                  <Link
                    to="/settings/debug"
                    className="px-3 py-1.5 text-body-sm rounded-md border border-hairline text-ink hover:bg-secondary-bg transition-colors"
                  >
                    打开 Debug / 日志
                  </Link>
                </div>
              </SettingsCard>
            </>
          )}

          {activeSection === "debug" && <DebugLogSettingsCard />}
        </section>
      </div>
    </main>
  );
}
