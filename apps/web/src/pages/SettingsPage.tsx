import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Loader2,
  AlertCircle,
  Settings,
  Bug,
  Save,
  FolderOpen,
  Plus,
  Pencil,
  Trash2,
  Check,
  X,
  Star,
} from "lucide-react";
import { api, type DebugSettings, type Project } from "@/lib/api";
import {
  useProjects,
  useCreateProject,
  useUpdateProject,
  useDeleteProject,
} from "@/hooks/useProjects";
import { useProjectContext } from "@/contexts/ProjectContext";
import { configureFrontendLogger } from "@/lib/logger";

// ─── Path helpers ────────────────────────────────────────────────────────────

/** Convert container-internal path to real host path for display. */
function containerToHost(containerPath: string, hostPrefix: string): string {
  const prefix = hostPrefix.replace(/\/$/, "");
  if (containerPath.startsWith("/photos")) {
    return prefix + containerPath.slice("/photos".length);
  }
  return containerPath;
}

/** Convert host path entered by user back to container-internal path. */
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
  // Display values use host paths; convert back to container path on submit
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
    queryKey: ["settings"],
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

const DEBUG_MODE_OPTIONS = ["off", "basic", "debug", "trace"] as const;
const LOG_LEVEL_OPTIONS = ["ERROR", "WARNING", "INFO", "DEBUG"] as const;

function DebugLogSettingsCard() {
  const queryClient = useQueryClient();
  const {
    data,
    isLoading,
    isError,
    error,
  } = useQuery({
    queryKey: ["settings", "debug"],
    queryFn: api.settings.getDebug,
    staleTime: 15_000,
  });

  const [form, setForm] = useState<DebugSettings | null>(null);
  const [successMessage, setSuccessMessage] = useState<string>("");

  useEffect(() => {
    if (!data) return;
    setForm(data);
  }, [data]);

  const saveMutation = useMutation({
    mutationFn: (payload: DebugSettings) => api.settings.updateDebug(payload),
    onSuccess: (saved) => {
      queryClient.setQueryData(["settings", "debug"], saved);
      configureFrontendLogger(saved);
      setSuccessMessage("Debug 与日志配置已保存");
      setTimeout(() => setSuccessMessage(""), 1800);
    },
  });

  function update<K extends keyof DebugSettings>(key: K, value: DebugSettings[K]) {
    setForm((prev) => (prev ? { ...prev, [key]: value } : prev));
  }

  if (isLoading || !form) {
    return (
      <SettingsCard title="Debug 与日志">
        <div className="flex items-center gap-2 text-mute py-6 justify-center">
          <Loader2 className="w-4 h-4 animate-spin" />
          <span className="text-body-sm">加载 Debug 配置中…</span>
        </div>
      </SettingsCard>
    );
  }

  if (isError) {
    return (
      <SettingsCard title="Debug 与日志">
        <div className="py-6 flex items-center gap-2 text-red-500">
          <AlertCircle className="w-4 h-4" />
          <span className="text-body-sm">加载失败：{(error as Error)?.message ?? "未知错误"}</span>
        </div>
      </SettingsCard>
    );
  }

  const minLen = 200;
  const maxLen = 10000;

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
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <label className="text-caption-sm text-mute">
            Debug 模式
            <select
              value={form.debug_mode}
              onChange={(e) => update("debug_mode", e.target.value as DebugSettings["debug_mode"])}
              className="mt-1 w-full px-3 py-1.5 text-body-sm bg-surface-card border border-hairline rounded-md text-ink"
            >
              {DEBUG_MODE_OPTIONS.map((opt) => (
                <option key={opt} value={opt}>{opt}</option>
              ))}
            </select>
          </label>
          <label className="text-caption-sm text-mute">
            前端日志等级
            <select
              value={form.frontend_log_level}
              onChange={(e) => update("frontend_log_level", e.target.value as DebugSettings["frontend_log_level"])}
              className="mt-1 w-full px-3 py-1.5 text-body-sm bg-surface-card border border-hairline rounded-md text-ink"
            >
              {LOG_LEVEL_OPTIONS.map((opt) => (
                <option key={opt} value={opt}>{opt}</option>
              ))}
            </select>
          </label>
          {([
            "backend_log_level",
            "ai_log_level",
            "search_log_level",
            "db_log_level",
            "task_log_level",
          ] as const).map((field) => (
            <label key={field} className="text-caption-sm text-mute">
              {field}
              <select
                value={form[field]}
                onChange={(e) => update(field, e.target.value as DebugSettings[typeof field])}
                className="mt-1 w-full px-3 py-1.5 text-body-sm bg-surface-card border border-hairline rounded-md text-ink"
              >
                {LOG_LEVEL_OPTIONS.map((opt) => (
                  <option key={opt} value={opt}>{opt}</option>
                ))}
              </select>
            </label>
          ))}
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {([
            "log_request_body",
            "log_ai_prompt",
            "log_ai_response",
            "log_sql",
            "log_stacktrace",
          ] as const).map((flag) => (
            <label key={flag} className="flex items-center gap-2 text-body-sm text-ink">
              <input
                type="checkbox"
                checked={form[flag]}
                onChange={(e) => update(flag, e.target.checked as DebugSettings[typeof flag])}
                className="accent-primary w-3.5 h-3.5"
              />
              {flag}
            </label>
          ))}
        </div>

        <label className="block text-caption-sm text-mute">
          max_log_text_length ({minLen} - {maxLen})
          <input
            type="number"
            min={minLen}
            max={maxLen}
            value={form.max_log_text_length}
            onChange={(e) => update("max_log_text_length", Number(e.target.value || minLen))}
            className="mt-1 w-full sm:w-56 px-3 py-1.5 text-body-sm bg-surface-card border border-hairline rounded-md text-ink"
          />
        </label>

        {form.debug_mode === "trace" && (
          <p className="text-caption-sm text-amber-600 bg-amber-50 border border-amber-200 rounded-md px-3 py-2">
            风险提示：trace 模式会增加日志量，仅建议临时排查时开启。
          </p>
        )}

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

// ─── Page ─────────────────────────────────────────────────────────────────────

export function SettingsPage() {
  const [activeTab, setActiveTab] = useState<"general" | "debug">("general");
  const { currentProjectId } = useProjectContext();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["settings"],
    queryFn: api.settings.get,
    staleTime: 60_000,
  });

  return (
    <main className="max-w-2xl mx-auto px-4 sm:px-6 py-6 space-y-6">
      <div className="flex items-center gap-2">
        <Settings className="w-5 h-5 text-ink" />
        <h1 className="text-heading-md font-semibold text-ink">系统设置</h1>
      </div>

      <div className="flex items-center gap-2 border-b border-hairline pb-2">
        <button
          type="button"
          onClick={() => setActiveTab("general")}
          className={`px-3 py-1.5 rounded-md text-body-sm border transition-colors ${
            activeTab === "general"
              ? "border-primary text-primary bg-primary/10"
              : "border-hairline text-ink hover:bg-secondary-bg"
          }`}
        >
          <span className="inline-flex items-center gap-1.5">
            <Settings className="w-3.5 h-3.5" />
            常规设置
          </span>
        </button>
        <button
          type="button"
          onClick={() => setActiveTab("debug")}
          className={`px-3 py-1.5 rounded-md text-body-sm border transition-colors ${
            activeTab === "debug"
              ? "border-primary text-primary bg-primary/10"
              : "border-hairline text-ink hover:bg-secondary-bg"
          }`}
        >
          <span className="inline-flex items-center gap-1.5">
            <Bug className="w-3.5 h-3.5" />
            Debug 与日志
          </span>
        </button>
      </div>

      {activeTab === "debug" && <DebugLogSettingsCard />}

      {activeTab === "general" && (
        <>
          <LibraryManagementCard />

          {currentProjectId != null && (
            <SettingsCard title="项目 AI 设置">
              <div className="py-3 flex items-center justify-between gap-3">
                <p className="text-body-sm text-mute">进入当前项目的模型配置、Prompt 版本与测试区。</p>
                <Link
                  to={`/project/${currentProjectId}/settings/ai`}
                  className="px-3 py-1.5 text-body-sm rounded-md border border-hairline text-ink hover:bg-secondary-bg transition-colors"
                >
                  打开项目 AI 配置
                </Link>
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
              <SettingsCard title="AI 模型 (llama-server)">
                <SettingRow label="API Base URL" value={data.openai_base_url} />
                <SettingRow label="文本模型" value={data.openai_model} />
                <SettingRow label="视觉模型" value={data.openai_vision_model} />
              </SettingsCard>

              <SettingsCard title="Worker 配置">
                <SettingRow label="并发数" value={data.ai_worker_concurrency} />
                <SettingRow label="最大重试次数" value={data.ai_max_retries} />
              </SettingsCard>
            </div>
          )}
        </>
      )}
    </main>
  );
}
