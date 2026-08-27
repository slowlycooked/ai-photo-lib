import { useEffect, useId, useMemo, useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Loader2,
  AlertCircle,
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
  ChevronDown,
  CheckCircle2,
  Cpu,
  Gauge,
  RefreshCw,
  RotateCcw,
  Server,
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
  type SystemRole,
  type AICapability,
} from "@/api";
import { queryKeys } from "@/api/queryKeys";
import {
  useProjects,
  useCreateProject,
  useUpdateProject,
  useDeleteProject,
} from "@/hooks/useProjects";
import { useProjectContext } from "@/contexts/ProjectContext";
import { useAuth } from "@/contexts/AuthContext";
import { configureFrontendLogger } from "@/lib/logger";
import { SettingsLayout } from "@/components/settings/SettingsLayout";

// ─── Path helpers ────────────────────────────────────────────────────────────

/** Convert legacy container path to host path for display. */
function containerToHost(containerPath: string, hostPrefix: string): string {
  const prefix = hostPrefix.replace(/\/$/, "");
  if (containerPath.startsWith("/photos")) {
    return prefix + containerPath.slice("/photos".length);
  }
  return containerPath;
}

/** Keep the persisted project path aligned with the actual host path. */
export function prepareLibrarySubmitPath(hostPath: string): string {
  return hostPath;
}

/** Keep the identifying end of a long path visible in compact library rows. */
export function compactLibraryPath(path: string): string {
  const segments = path.split("/").filter(Boolean);
  if (segments.length <= 3) {
    return path;
  }
  return `…/${segments.slice(-3).join("/")}`;
}

// ─── Shared UI ────────────────────────────────────────────────────────────────

function SettingRow({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex flex-col gap-1 border-b border-hairline py-3 last:border-0 sm:flex-row sm:items-start sm:justify-between sm:gap-4">
      <span className="shrink-0 text-caption-sm font-medium text-mute sm:w-40 sm:text-body-sm">{label}</span>
      <span className="min-w-0 font-mono text-caption-sm font-medium text-ink [overflow-wrap:anywhere] sm:text-right">{value}</span>
    </div>
  );
}

function SettingsCard({
  title,
  description,
  icon,
  action,
  children,
}: {
  title: string;
  description?: React.ReactNode;
  icon?: React.ReactNode;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="overflow-hidden rounded-2xl border border-hairline bg-canvas shadow-sm">
      <div className="flex items-center justify-between gap-4 border-b border-hairline px-4 py-3.5 sm:px-5">
        <div className="flex min-w-0 items-center gap-3">
          {icon}
          <div className="min-w-0">
            <h2 className="text-body-sm font-semibold text-ink">{title}</h2>
            {description && <div className="mt-0.5 text-caption-sm text-mute">{description}</div>}
          </div>
        </div>
        {action}
      </div>
      <div className="px-4 sm:px-5">{children}</div>
    </div>
  );
}

function RuntimeMetric({
  label,
  value,
  hint,
  icon,
}: {
  label: string;
  value: string | number;
  hint: string;
  icon: React.ReactNode;
}) {
  return (
    <div className="flex min-w-0 items-center gap-3 rounded-xl border border-hairline bg-surface-card p-4">
      <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-canvas text-primary shadow-sm">
        {icon}
      </span>
      <div className="min-w-0">
        <p className="text-caption-sm font-medium text-mute">{label}</p>
        <div className="mt-0.5 flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
          <strong className="text-heading-md font-semibold tabular-nums text-ink">{value}</strong>
          <span className="text-caption-sm text-mute">{hint}</span>
        </div>
      </div>
    </div>
  );
}

export function GeneralRuntimeOverview({
  maxRetries,
  concurrency,
}: {
  maxRetries: number;
  concurrency: number;
}) {
  return (
    <SettingsCard
      title="任务处理"
      description="后台任务的全局运行参数"
      icon={
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
          <Gauge className="h-4 w-4" aria-hidden="true" />
        </span>
      }
      action={
        <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-2.5 py-1 text-caption-sm font-medium text-emerald-700">
          <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
          已载入
        </span>
      }
    >
      <div className="grid gap-3 py-4 sm:grid-cols-2 xl:grid-cols-1 2xl:grid-cols-2">
        <RuntimeMetric
          label="并发任务"
          value={concurrency}
          hint="个同时运行"
          icon={<Cpu className="h-5 w-5" aria-hidden="true" />}
        />
        <RuntimeMetric
          label="失败重试"
          value={maxRetries}
          hint="次自动恢复"
          icon={<RotateCcw className="h-5 w-5" aria-hidden="true" />}
        />
      </div>
    </SettingsCard>
  );
}

export function TechnicalPaths({ hostPath, containerPath }: { hostPath: string; containerPath: string }) {
  return (
    <details className="group overflow-hidden rounded-2xl border border-hairline bg-canvas shadow-sm">
      <summary className="flex min-h-16 cursor-pointer list-none items-center justify-between gap-4 px-4 py-3.5 transition-colors hover:bg-surface-card focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary/40 sm:px-5 [&::-webkit-details-marker]:hidden">
        <div className="flex min-w-0 items-center gap-3">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-secondary-bg text-mute">
            <Server className="h-4 w-4" aria-hidden="true" />
          </span>
          <div className="min-w-0">
            <h2 className="text-body-sm font-semibold text-ink">技术路径</h2>
            <p className="mt-0.5 text-caption-sm text-mute">Host 与 Container 映射 · 2 项</p>
          </div>
        </div>
        <ChevronDown className="h-4 w-4 shrink-0 text-mute transition-transform group-open:rotate-180 motion-reduce:transition-none" aria-hidden="true" />
      </summary>
      <div className="border-t border-hairline px-4 sm:px-5">
        <SettingRow label="Host Path" value={hostPath} />
        <SettingRow label="Container Path" value={containerPath} />
      </div>
    </details>
  );
}

function ProjectReadinessCard({ projectId }: { projectId: number }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["project-readiness", projectId],
    queryFn: () => api.projectCore.readiness(projectId),
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

export function LibraryForm({
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
  const formId = useId();
  const nameInputId = `${formId}-name`;
  const pathInputId = `${formId}-path`;
  const defaultInputId = `${formId}-default`;

  function set(k: keyof LibraryFormValues, v: string | boolean) {
    setValues((prev) => ({ ...prev, [k]: v }));
  }

  function handleSubmit() {
    onSubmit({
      ...values,
      photo_library_path: prepareLibrarySubmitPath(values.photo_library_path),
    });
  }

  const hostExample = hostPrefix.replace(/\/$/, "") + "/my-library";

  return (
    <form
      className="space-y-3 py-4"
      aria-busy={isSubmitting}
      onSubmit={(event) => {
        event.preventDefault();
        handleSubmit();
      }}
    >
      <div className="grid gap-3 sm:grid-cols-[minmax(0,0.8fr)_minmax(0,1.8fr)]">
        <div className="min-w-0">
          <label htmlFor={nameInputId} className="mb-1.5 block text-caption-sm font-medium text-mute">
            名称
          </label>
          <input
            id={nameInputId}
            type="text"
            value={values.name}
            onChange={(e) => set("name", e.target.value)}
            placeholder="我的图片库"
            className="h-10 w-full rounded-xl border border-hairline bg-surface-card px-3 text-body-sm text-ink placeholder:text-mute focus:outline-none focus:ring-2 focus:ring-primary/40"
          />
        </div>
        <div className="min-w-0">
          <label htmlFor={pathInputId} className="mb-1.5 block text-caption-sm font-medium text-mute">
            图片库路径
          </label>
          <input
            id={pathInputId}
            type="text"
            value={values.photo_library_path}
            onChange={(e) => set("photo_library_path", e.target.value)}
            placeholder={hostExample}
            className="h-10 w-full rounded-xl border border-hairline bg-surface-card px-3 font-mono text-body-sm text-ink placeholder:text-mute focus:outline-none focus:ring-2 focus:ring-primary/40"
          />
        </div>
      </div>
      <label
        htmlFor={defaultInputId}
        className="flex min-h-10 cursor-pointer select-none items-center gap-2 rounded-xl px-1 text-body-sm text-ink focus-within:ring-2 focus-within:ring-primary/40"
      >
        <input
          id={defaultInputId}
          type="checkbox"
          checked={values.is_default}
          onChange={(e) => set("is_default", e.target.checked)}
          className="h-4 w-4 accent-primary"
        />
        <span>设为默认图片库</span>
      </label>
      <div className="flex flex-wrap gap-2 pt-1">
        <button
          type="submit"
          disabled={isSubmitting || !values.name.trim() || !values.photo_library_path.trim()}
          className="inline-flex h-10 cursor-pointer items-center gap-1.5 rounded-xl bg-primary px-4 text-body-sm font-medium text-white transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isSubmitting ? (
            <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />
          ) : (
            <Check className="h-4 w-4" aria-hidden="true" />
          )}
          {submitLabel}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="inline-flex h-10 cursor-pointer items-center gap-1.5 rounded-xl border border-hairline px-4 text-body-sm text-ink transition-colors hover:bg-secondary-bg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 focus-visible:ring-offset-2"
        >
          <X className="h-4 w-4" aria-hidden="true" />
          取消
        </button>
      </div>
      {error && (
        <p className="flex items-center gap-1.5 text-caption-sm text-danger" role="alert">
          <AlertCircle className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          {error.message}
        </p>
      )}
    </form>
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
  const fullPath = containerToHost(project.photo_library_path, hostPrefix);

  return (
    <div className="group flex flex-wrap items-center gap-3 border-b border-hairline py-4 last:border-0">
      <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
        <FolderOpen className="h-5 w-5" aria-hidden="true" />
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="truncate text-body-sm font-semibold text-ink">{project.name}</span>
          {project.is_default && (
            <span className="rounded-full bg-primary/10 px-2 py-0.5 text-caption-sm font-medium text-primary">
              默认
            </span>
          )}
        </div>
        <p
          className="mt-1 truncate font-mono text-caption-sm text-mute"
          title={fullPath}
        >
          {compactLibraryPath(fullPath)}
        </p>
      </div>
      <div className="ml-auto flex shrink-0 items-center gap-1.5">
        {!project.is_default && (
          <button
            type="button"
            onClick={onSetDefault}
            title="设为默认"
            aria-label={`将 ${project.name} 设为默认图片库`}
            className="inline-flex h-9 w-9 cursor-pointer items-center justify-center rounded-lg text-mute transition-colors hover:bg-primary/10 hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
          >
            <Star className="h-4 w-4" aria-hidden="true" />
          </button>
        )}
        <button
          type="button"
          onClick={onEdit}
          title="编辑"
          aria-label={`编辑图片库 ${project.name}`}
          className="inline-flex h-9 w-9 cursor-pointer items-center justify-center rounded-lg text-mute transition-colors hover:bg-secondary-bg hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
        >
          <Pencil className="h-4 w-4" aria-hidden="true" />
        </button>
        {!project.is_default && (
          <button
            type="button"
            onClick={onDelete}
            title="删除"
            aria-label={`删除图片库 ${project.name}`}
            className="inline-flex h-9 w-9 cursor-pointer items-center justify-center rounded-lg text-mute transition-colors hover:bg-danger/10 hover:text-danger focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-danger/40"
          >
            <Trash2 className="h-4 w-4" aria-hidden="true" />
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
      title="图片库"
      description={isLoading ? "正在读取…" : `${projects.length} 个图片库${projects.some((project) => project.is_default) ? " · 已设默认" : ""}`}
      icon={
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
          <FolderOpen className="h-4 w-4" aria-hidden="true" />
        </span>
      }
      action={
        !showAddForm && (
          <button
            type="button"
            onClick={() => { setShowAddForm(true); setEditingId(null); }}
            className="inline-flex h-9 cursor-pointer items-center gap-1.5 rounded-xl border border-hairline px-3 text-body-sm font-medium text-ink transition-colors hover:bg-secondary-bg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 focus-visible:ring-offset-2"
          >
            <Plus className="h-4 w-4" aria-hidden="true" />
            <span className="hidden sm:inline">添加图片库</span>
            <span className="sm:hidden">添加</span>
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
            className="flex flex-col gap-3 border-b border-hairline py-4 last:border-0 sm:flex-row sm:items-center sm:justify-between"
            role="group"
            aria-label={`确认删除图片库 ${project.name}`}
          >
            <div className="flex min-w-0 items-start gap-3">
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-danger/10 text-danger">
                <Trash2 className="h-4 w-4" aria-hidden="true" />
              </span>
              <div className="min-w-0">
                <p className="text-body-sm font-semibold text-ink">删除“{project.name}”？</p>
                <p className="mt-0.5 text-caption-sm text-mute">此操作不可恢复。</p>
              </div>
            </div>
            <div className="flex shrink-0 gap-2 self-end sm:self-auto">
              <button
                type="button"
                disabled={deleteProject.isPending}
                onClick={() => handleDelete(project.id)}
                className="inline-flex h-9 cursor-pointer items-center gap-1.5 rounded-xl bg-danger px-3 text-body-sm font-medium text-white transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-danger/40 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {deleteProject.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />
                ) : (
                  <Trash2 className="h-4 w-4" aria-hidden="true" />
                )}
                删除
              </button>
              <button
                type="button"
                onClick={() => setDeleteConfirmId(null)}
                className="h-9 cursor-pointer rounded-xl border border-hairline px-3 text-body-sm text-ink transition-colors hover:bg-secondary-bg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 focus-visible:ring-offset-2"
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

function UsersManagementCard() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const auth = useAuth();
  const { data: projectsData } = useProjects();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["admin-users"],
    queryFn: api.admin.listUsers,
    staleTime: 30_000,
  });
  const [selectedAccessUserId, setSelectedAccessUserId] = useState<number | null>(null);
  const [form, setForm] = useState({
    username: "",
    password: "",
    display_name: "",
    role: "viewer" as SystemRole,
  });

  const createMutation = useMutation({
    mutationFn: () =>
      api.admin.createUser({
        username: form.username.trim(),
        password: form.password,
        display_name: form.display_name.trim() || null,
        role: form.role,
        status: "active",
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-users"] });
      setForm({ username: "", password: "", display_name: "", role: "viewer" });
    },
  });
  const updateMutation = useMutation({
    mutationFn: ({ userId, role, status }: { userId: number; role?: SystemRole; status?: string }) =>
      api.admin.updateUser(userId, { role, status }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin-users"] }),
  });
  const deleteMutation = useMutation({
    mutationFn: (userId: number) => api.admin.deleteUser(userId),
    onSuccess: async (_data, userId) => {
      await queryClient.invalidateQueries({ queryKey: ["admin-users"] });
      if (selectedAccessUserId === userId) {
        setSelectedAccessUserId(null);
      }
      if (auth.session?.user_id === userId) {
        await auth.logout();
        navigate("/login", { replace: true });
      }
    },
  });

  const { data: selectedAccessData, isLoading: accessLoading, isError: accessError } = useQuery({
    queryKey: ["user-project-access", selectedAccessUserId],
    queryFn: () => api.admin.listUserProjectAccess(selectedAccessUserId!),
    enabled: selectedAccessUserId != null,
    staleTime: 30_000,
  });

  const projectAccessMutation = useMutation({
    mutationFn: ({ projectId, projectRole }: { projectId: number; projectRole: "viewer" | "manager" }) =>
      api.admin.upsertUserProjectAccess(selectedAccessUserId!, projectId, { project_role: projectRole }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["user-project-access", selectedAccessUserId] });
      queryClient.invalidateQueries({ queryKey: ["admin-users"] });
    },
  });

  const projectAccessDeleteMutation = useMutation({
    mutationFn: (projectId: number) => api.admin.deleteUserProjectAccess(selectedAccessUserId!, projectId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["user-project-access", selectedAccessUserId] });
      queryClient.invalidateQueries({ queryKey: ["admin-users"] });
    },
  });

  const selectedAccessUser = data?.items.find((user) => user.id === selectedAccessUserId) ?? null;
  const selectedAccessMap = useMemo(
    () => new Map((selectedAccessData?.items ?? []).map((item) => [item.project_id, item])),
    [selectedAccessData],
  );

  return (
    <SettingsCard title="用户管理">
      <div className="py-4 space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-[1fr_1fr_1fr_160px_auto] gap-2">
          <input
            value={form.username}
            onChange={(e) => setForm((x) => ({ ...x, username: e.target.value }))}
            placeholder="用户名"
            className="px-3 py-2 text-body-sm bg-surface-card border border-hairline rounded-md"
          />
          <input
            value={form.display_name}
            onChange={(e) => setForm((x) => ({ ...x, display_name: e.target.value }))}
            placeholder="显示名"
            className="px-3 py-2 text-body-sm bg-surface-card border border-hairline rounded-md"
          />
          <input
            type="password"
            value={form.password}
            onChange={(e) => setForm((x) => ({ ...x, password: e.target.value }))}
            placeholder="初始密码"
            className="px-3 py-2 text-body-sm bg-surface-card border border-hairline rounded-md"
          />
          <select
            value={form.role}
            onChange={(e) => setForm((x) => ({ ...x, role: e.target.value as SystemRole }))}
            className="px-3 py-2 text-body-sm bg-surface-card border border-hairline rounded-md"
          >
            <option value="viewer">viewer</option>
            <option value="project_manager">project_manager</option>
            <option value="admin">admin</option>
          </select>
          <button
            onClick={() => createMutation.mutate()}
            disabled={createMutation.isPending || !form.username.trim() || form.password.length < 6}
            className="inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-md bg-primary text-white text-btn-sm font-bold disabled:opacity-50"
          >
            {createMutation.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />}
            新建
          </button>
        </div>

        {createMutation.isError && (
          <p className="text-caption-sm text-red-500">创建失败：{(createMutation.error as Error).message}</p>
        )}
        {deleteMutation.isError && (
          <p className="text-caption-sm text-red-500">删除失败：{(deleteMutation.error as Error).message}</p>
        )}

        {isLoading && <div className="py-6 text-body-sm text-mute">加载用户中…</div>}
        {isError && <div className="py-6 text-body-sm text-red-500">无法加载用户列表</div>}
        {data && (
          <div className="overflow-x-auto rounded-md border border-hairline">
            <table className="min-w-full text-body-sm">
              <thead className="bg-secondary-bg text-mute">
                <tr>
                  <th className="px-3 py-2 text-left">用户</th>
                  <th className="px-3 py-2 text-left">角色</th>
                  <th className="px-3 py-2 text-left">状态</th>
                  <th className="px-3 py-2 text-left">操作</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((user) => (
                  <tr key={user.id} className="border-t border-hairline">
                    <td className="px-3 py-2">
                      <div className="font-medium text-ink">{user.username}</div>
                      <div className="text-caption-sm text-mute">{user.display_name || "-"}</div>
                    </td>
                    <td className="px-3 py-2">
                      <select
                        value={user.role}
                        onChange={(e) =>
                          updateMutation.mutate({ userId: user.id, role: e.target.value as SystemRole })
                        }
                        className="px-2 py-1 rounded-md border border-hairline bg-surface-card"
                      >
                        <option value="viewer">viewer</option>
                        <option value="project_manager">project_manager</option>
                        <option value="admin">admin</option>
                      </select>
                    </td>
                    <td className="px-3 py-2 text-mute">{user.status}</td>
                    <td className="px-3 py-2">
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() =>
                            updateMutation.mutate({
                              userId: user.id,
                              status: user.status === "active" ? "disabled" : "active",
                            })
                          }
                          className="px-2.5 py-1 rounded-md border border-hairline hover:bg-secondary-bg"
                        >
                          {user.status === "active" ? "禁用" : "启用"}
                        </button>
                        <button
                          onClick={() => {
                            if (!window.confirm(`确定删除用户“${user.username}”吗？此操作不可恢复。`)) {
                              return;
                            }
                            deleteMutation.mutate(user.id);
                          }}
                          disabled={deleteMutation.isPending}
                          className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md border border-red-200 text-red-600 hover:bg-red-50 disabled:opacity-50"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                          删除
                        </button>
                        <button
                          onClick={() => setSelectedAccessUserId(user.id)}
                          className="px-2.5 py-1 rounded-md border border-hairline hover:bg-secondary-bg"
                        >
                          项目权限
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <SettingsCard title="项目权限配置">
          <div className="py-4 space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-[1fr_auto] gap-2 items-end">
              <div>
                <label className="block text-caption-sm text-mute mb-1">选择用户</label>
                <select
                  value={selectedAccessUserId ?? ""}
                  onChange={(e) => setSelectedAccessUserId(e.target.value ? Number(e.target.value) : null)}
                  className="w-full px-3 py-2 text-body-sm bg-surface-card border border-hairline rounded-md"
                >
                  <option value="">请选择一个用户</option>
                  {(data?.items ?? []).map((user) => (
                    <option key={user.id} value={user.id}>
                      {user.username} ({user.role})
                    </option>
                  ))}
                </select>
              </div>
              <div className="text-caption-sm text-mute">查看=可见项目，管理=可见并可配置该项目成员</div>
            </div>

            {!selectedAccessUser && <div className="text-body-sm text-mute">选择一个用户后，可以为他配置可查看的项目。</div>}

            {selectedAccessUser && accessLoading && <div className="text-body-sm text-mute">加载项目权限中…</div>}
            {selectedAccessUser && accessError && <div className="text-body-sm text-red-500">无法加载项目权限</div>}

            {selectedAccessUser && projectsData && (
              <div className="overflow-hidden rounded-md border border-hairline">
                {projectsData.items.map((project) => {
                  const access = selectedAccessMap.get(project.id);
                  return (
                    <div key={project.id} className="flex flex-col gap-3 border-b border-hairline px-3 py-3 last:border-0 md:flex-row md:items-center md:justify-between">
                      <div>
                        <div className="text-body-sm font-medium text-ink">{project.name}</div>
                        <div className="text-caption-sm text-mute">{project.description || "未填写描述"}</div>
                      </div>
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-caption-sm text-mute rounded border border-hairline px-2 py-1">
                          {access ? `当前：${access.project_role}` : "未授权"}
                        </span>
                        <button
                          onClick={() => projectAccessMutation.mutate({ projectId: project.id, projectRole: "viewer" })}
                          disabled={projectAccessMutation.isPending}
                          className="px-2.5 py-1 rounded-md border border-hairline hover:bg-secondary-bg disabled:opacity-50"
                        >
                          查看
                        </button>
                        <button
                          onClick={() => projectAccessMutation.mutate({ projectId: project.id, projectRole: "manager" })}
                          disabled={projectAccessMutation.isPending}
                          className="px-2.5 py-1 rounded-md border border-hairline hover:bg-secondary-bg disabled:opacity-50"
                        >
                          管理
                        </button>
                        <button
                          onClick={() => projectAccessDeleteMutation.mutate(project.id)}
                          disabled={projectAccessDeleteMutation.isPending || !access}
                          className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md border border-red-200 text-red-600 hover:bg-red-50 disabled:opacity-50"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                          移除
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </SettingsCard>
      </div>
    </SettingsCard>
  );
}

function ProjectMembersCard({ projectId }: { projectId: number | null }) {
  const queryClient = useQueryClient();
  const { data: usersData } = useQuery({
    queryKey: ["admin-users"],
    queryFn: api.admin.listUsers,
    staleTime: 30_000,
  });
  const { data, isLoading, isError } = useQuery({
    queryKey: ["project-members", projectId],
    queryFn: () => api.admin.listProjectMembers(projectId!),
    enabled: projectId != null,
    staleTime: 30_000,
  });
  const [selectedUserId, setSelectedUserId] = useState<number | "">("");
  const [projectRole, setProjectRole] = useState<"manager" | "viewer">("viewer");

  const upsertMutation = useMutation({
    mutationFn: () => api.admin.upsertProjectMember(projectId!, Number(selectedUserId), projectRole),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["project-members", projectId] });
      setSelectedUserId("");
      setProjectRole("viewer");
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (userId: number) => api.admin.deleteProjectMember(projectId!, userId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["project-members", projectId] }),
  });

  if (projectId == null) {
    return (
      <SettingsCard title="项目授权">
        <div className="py-4 text-body-sm text-mute">请选择一个项目后配置成员授权。</div>
      </SettingsCard>
    );
  }

  return (
    <SettingsCard title="项目授权">
      <div className="py-4 space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-[1fr_180px_auto] gap-2">
          <select
            value={selectedUserId}
            onChange={(e) => setSelectedUserId(e.target.value ? Number(e.target.value) : "")}
            className="px-3 py-2 text-body-sm bg-surface-card border border-hairline rounded-md"
          >
            <option value="">选择用户</option>
            {(usersData?.items ?? []).map((user) => (
              <option key={user.id} value={user.id}>
                {user.username} ({user.role})
              </option>
            ))}
          </select>
          <select
            value={projectRole}
            onChange={(e) => setProjectRole(e.target.value as "manager" | "viewer")}
            className="px-3 py-2 text-body-sm bg-surface-card border border-hairline rounded-md"
          >
            <option value="viewer">viewer</option>
            <option value="manager">manager</option>
          </select>
          <button
            onClick={() => upsertMutation.mutate()}
            disabled={upsertMutation.isPending || selectedUserId === ""}
            className="inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-md bg-primary text-white text-btn-sm font-bold disabled:opacity-50"
          >
            {upsertMutation.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />}
            授权
          </button>
        </div>

        {isLoading && <div className="py-4 text-body-sm text-mute">加载项目成员中…</div>}
        {isError && <div className="py-4 text-body-sm text-red-500">无法加载项目成员</div>}
        {data && (
          <div className="rounded-md border border-hairline overflow-hidden">
            {data.items.map((member) => (
              <div key={member.id} className="flex items-center justify-between gap-3 px-3 py-2 border-b border-hairline last:border-0">
                <div>
                  <div className="text-body-sm font-medium text-ink">{member.username}</div>
                  <div className="text-caption-sm text-mute">{member.display_name || "-"} · {member.project_role}</div>
                </div>
                <button
                  onClick={() => deleteMutation.mutate(member.user_id)}
                  className="px-2.5 py-1 rounded-md border border-hairline text-mute hover:text-red-500 hover:bg-secondary-bg"
                >
                  移除
                </button>
              </div>
            ))}
            {data.items.length === 0 && (
              <div className="px-3 py-6 text-center text-body-sm text-mute">当前项目尚未授权给任何数据库用户。</div>
            )}
          </div>
        )}
      </div>
    </SettingsCard>
  );
}

function AIServiceProfilesCard() {
  const queryClient = useQueryClient();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["ai-service-profiles"],
    queryFn: api.admin.listAIProfiles,
    staleTime: 30_000,
  });
  const [form, setForm] = useState({
    name: "",
    capability: "vision" as AICapability,
    provider: "openai-compatible",
    endpoint_url: "",
    api_key: "",
    model_name: "",
    timeout_seconds: 60,
    is_default: false,
  });

  const createMutation = useMutation({
    mutationFn: () =>
      api.admin.createAIProfile({
        ...form,
        api_key: form.api_key || null,
        timeout_seconds: Number(form.timeout_seconds),
      }),
    onSuccess: (next) => {
      queryClient.setQueryData(["ai-service-profiles"], next);
      setForm({
        name: "",
        capability: "vision",
        provider: "openai-compatible",
        endpoint_url: "",
        api_key: "",
        model_name: "",
        timeout_seconds: 60,
        is_default: false,
      });
    },
  });
  const profileUpdateMutation = useMutation({
    mutationFn: ({ id, body }: { id: number; body: Parameters<typeof api.admin.updateAIProfile>[1] }) =>
      api.admin.updateAIProfile(id, body),
    onSuccess: (next) => queryClient.setQueryData(["ai-service-profiles"], next),
  });
  const importEnvMutation = useMutation({
    mutationFn: api.admin.importAIProfilesFromEnv,
    onSuccess: (next) => queryClient.setQueryData(["ai-service-profiles"], next),
  });

  return (
    <SettingsCard title="系统 AI 服务">
      <div className="py-4 space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
          <input
            value={form.name}
            onChange={(e) => setForm((x) => ({ ...x, name: e.target.value }))}
            placeholder="服务名称"
            className="px-3 py-2 text-body-sm bg-surface-card border border-hairline rounded-md"
          />
          <select
            value={form.capability}
            onChange={(e) => setForm((x) => ({ ...x, capability: e.target.value as AICapability }))}
            className="px-3 py-2 text-body-sm bg-surface-card border border-hairline rounded-md"
          >
            <option value="vision">vision</option>
            <option value="embedding">embedding</option>
            <option value="query_planner">query_planner</option>
          </select>
          <input
            value={form.provider}
            onChange={(e) => setForm((x) => ({ ...x, provider: e.target.value }))}
            placeholder="provider"
            className="px-3 py-2 text-body-sm bg-surface-card border border-hairline rounded-md"
          />
          <input
            value={form.endpoint_url}
            onChange={(e) => setForm((x) => ({ ...x, endpoint_url: e.target.value }))}
            placeholder="endpoint_url"
            className="md:col-span-2 px-3 py-2 text-body-sm bg-surface-card border border-hairline rounded-md font-mono"
          />
          <input
            value={form.model_name}
            onChange={(e) => setForm((x) => ({ ...x, model_name: e.target.value }))}
            placeholder="model_name"
            className="px-3 py-2 text-body-sm bg-surface-card border border-hairline rounded-md"
          />
          <input
            type="password"
            value={form.api_key}
            onChange={(e) => setForm((x) => ({ ...x, api_key: e.target.value }))}
            placeholder="api_key"
            className="px-3 py-2 text-body-sm bg-surface-card border border-hairline rounded-md"
          />
          <input
            type="number"
            value={form.timeout_seconds}
            onChange={(e) => setForm((x) => ({ ...x, timeout_seconds: Number(e.target.value) }))}
            className="px-3 py-2 text-body-sm bg-surface-card border border-hairline rounded-md"
          />
          <label className="flex items-center gap-2 px-3 py-2 text-body-sm">
            <input
              type="checkbox"
              checked={form.is_default}
              onChange={(e) => setForm((x) => ({ ...x, is_default: e.target.checked }))}
            />
            默认服务
          </label>
        </div>
        <button
          onClick={() => createMutation.mutate()}
          disabled={createMutation.isPending || !form.name.trim() || !form.endpoint_url.trim() || !form.model_name.trim()}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-primary text-white text-btn-sm font-bold disabled:opacity-50"
        >
          {createMutation.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />}
          添加 AI 服务
        </button>
        <button
          onClick={() => importEnvMutation.mutate()}
          disabled={importEnvMutation.isPending}
          className="ml-2 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-hairline text-btn-sm text-ink hover:bg-secondary-bg disabled:opacity-50"
        >
          {importEnvMutation.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
          从环境配置导入
        </button>

        {isLoading && <div className="py-6 text-body-sm text-mute">加载 AI 服务中…</div>}
        {isError && <div className="py-6 text-body-sm text-red-500">无法加载 AI 服务列表</div>}
        {data && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
            {data.items.map((profile) => (
              <div key={profile.id} className="rounded-md border border-hairline p-3 bg-surface-card">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-body-sm font-semibold text-ink">{profile.name}</div>
                    <div className="text-caption-sm text-mute">{profile.capability} · {profile.provider}</div>
                  </div>
                  <div className="flex gap-1">
                    {profile.is_default && <span className="text-caption-sm px-2 py-0.5 rounded bg-primary/10 text-primary">默认</span>}
                    <span className="text-caption-sm px-2 py-0.5 rounded bg-secondary-bg text-mute">
                      {profile.enabled ? "enabled" : "disabled"}
                    </span>
                  </div>
                </div>
                <div className="mt-3 space-y-1 text-caption-sm text-mute">
                  <div className="break-all font-mono">{profile.endpoint_url || "endpoint hidden"}</div>
                  <div>model: {profile.model_name}</div>
                  <div>api key: {profile.has_api_key ? "已配置" : "未配置"}</div>
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  <button
                    onClick={() => profileUpdateMutation.mutate({ id: profile.id, body: { enabled: !profile.enabled } })}
                    className="px-2.5 py-1 rounded-md border border-hairline text-caption-sm hover:bg-secondary-bg"
                  >
                    {profile.enabled ? "停用" : "启用"}
                  </button>
                  {!profile.is_default && (
                    <button
                      onClick={() => profileUpdateMutation.mutate({ id: profile.id, body: { is_default: true } })}
                      className="px-2.5 py-1 rounded-md border border-hairline text-caption-sm hover:bg-secondary-bg"
                    >
                      设为默认
                    </button>
                  )}
                  <button
                    onClick={() =>
                      profileUpdateMutation.mutate({
                        id: profile.id,
                        body: { visible_to_projects: !profile.visible_to_projects },
                      })
                    }
                    className="px-2.5 py-1 rounded-md border border-hairline text-caption-sm hover:bg-secondary-bg"
                  >
                    {profile.visible_to_projects ? "隐藏给项目" : "开放给项目"}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
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
  const knownSections = new Set(["general", "ai-services", "users", "monitoring", "debug"]);
  const legacyProjectSectionMap: Record<string, string> = {
    ai: "vision-ai",
    "vision-ai": "vision-ai",
    "embedding-ai": "embedding-ai",
    "planner-ai": "planner-ai",
    advanced: "advanced",
  };

  if (section === "") {
    return <Navigate to="/settings/general" replace />;
  }

  if (activeSection in legacyProjectSectionMap) {
    if (currentProjectId == null) {
      return <Navigate to="/settings/general" replace />;
    }
    return (
      <Navigate
        to={`/projects/${currentProjectId}/settings/${legacyProjectSectionMap[activeSection]}`}
        replace
      />
    );
  }

  if (!knownSections.has(activeSection)) {
    return <Navigate to="/settings/general" replace />;
  }

  const sectionDescriptions: Record<string, string> = {
    general: "图片库与后台任务的全局配置",
    "ai-services": "管理系统级 AI 服务与项目可见范围",
    users: "管理系统用户、角色与项目成员",
    monitoring: "查看服务健康状态与项目就绪情况",
    debug: "调整日志级别并诊断运行问题",
  };

  return (
    <SettingsLayout
      title="系统设置"
      subtitle={sectionDescriptions[activeSection]}
      currentProjectId={currentProjectId}
    >
      {activeSection === "general" && (
        <div
          className="grid min-w-0 items-start gap-5 xl:grid-cols-[minmax(0,1.35fr)_minmax(320px,0.65fr)]"
        >
          <div className="min-w-0">
            <LibraryManagementCard />
          </div>

          <div className="min-w-0 space-y-5 xl:sticky xl:top-20">
            {isLoading && (
              <div
                className="space-y-3 rounded-2xl border border-hairline bg-canvas p-5 shadow-sm"
                aria-label="正在加载运行参数"
              >
                <div className="h-20 animate-pulse rounded-xl bg-secondary-bg motion-reduce:animate-none" />
                <div className="h-20 animate-pulse rounded-xl bg-secondary-bg motion-reduce:animate-none" />
              </div>
            )}

            {isError && (
              <div
                className="flex items-start gap-3 rounded-2xl border border-danger/20 bg-danger/5 p-4 text-danger"
                role="alert"
              >
                <AlertCircle className="mt-0.5 h-5 w-5 shrink-0" aria-hidden="true" />
                <div>
                  <p className="text-body-sm font-semibold">运行参数加载失败</p>
                  <p className="mt-0.5 text-caption-sm">请检查 API 服务后刷新页面。</p>
                </div>
              </div>
            )}

            {data && (
              <GeneralRuntimeOverview
                maxRetries={data.ai_max_retries}
                concurrency={data.ai_worker_concurrency}
              />
            )}

            {data && (
              <TechnicalPaths
                hostPath={data.host_photo_library_path}
                containerPath={data.photo_library_path}
              />
            )}
          </div>
        </div>
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

      {activeSection === "ai-services" && <AIServiceProfilesCard />}

      {activeSection === "users" && (
        <>
          <UsersManagementCard />
          <ProjectMembersCard projectId={currentProjectId} />
        </>
      )}

      {activeSection === "debug" && <DebugLogSettingsCard />}
    </SettingsLayout>
  );
}
