import { useState, useMemo } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  Loader2,
  AlertCircle,
  Settings,
  FolderOpen,
  Plus,
  Pencil,
  Trash2,
  Check,
  X,
  Star,
} from "lucide-react";
import { api, type AppSettings, type Project } from "@/lib/api";
import {
  useProjects,
  useCreateProject,
  useUpdateProject,
  useDeleteProject,
} from "@/hooks/useProjects";
import { useProjectContext } from "@/contexts/ProjectContext";

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

// ─── Page ─────────────────────────────────────────────────────────────────────

export function SettingsPage() {
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
    </main>
  );
}
