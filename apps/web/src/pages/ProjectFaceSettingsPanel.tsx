import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, Loader2, RotateCcw, Save, ScanFace, ShieldCheck } from "lucide-react";
import { api, type ProjectFaceSettingsUpdate } from "@/api";

type FaceSettingsForm = ProjectFaceSettingsUpdate;

function SettingsCard({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="bg-canvas border border-hairline rounded-md">
      <div className="px-5 py-3 border-b border-hairline">
        <h2 className="text-body-sm font-semibold text-ink">{title}</h2>
        {subtitle && <p className="text-caption-sm text-mute mt-1">{subtitle}</p>}
      </div>
      <div className="px-5 py-4 space-y-4">{children}</div>
    </section>
  );
}

function Label({ children }: { children: React.ReactNode }) {
  return <label className="block text-caption-sm text-mute mb-1">{children}</label>;
}

function ToggleRow({
  title,
  description,
  checked,
  onChange,
}: {
  title: string;
  description: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label className="flex items-start justify-between gap-3 py-2 border-b border-hairline last:border-0 cursor-pointer">
      <div>
        <div className="text-body-sm text-ink font-medium">{title}</div>
        <p className="text-caption-sm text-mute mt-0.5">{description}</p>
      </div>
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-1 accent-primary w-4 h-4"
      />
    </label>
  );
}

export function ProjectFaceSettingsPanel({ projectId }: { projectId: number }) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<FaceSettingsForm>({});
  const [message, setMessage] = useState<string | null>(null);

  const { data, isLoading, error } = useQuery({
    queryKey: ["project-face-settings", projectId],
    queryFn: () => api.projectSettings.getFace(projectId),
    staleTime: 30_000,
  });

  useEffect(() => {
    if (!data) return;
    setForm({
      face_recognition_enabled: data.face_recognition_enabled,
      face_provider: data.face_provider,
      face_detector_model: data.face_detector_model,
      face_embedding_model: data.face_embedding_model,
      face_runtime: data.face_runtime,
      store_face_crops: data.store_face_crops,
      face_crop_storage: data.face_crop_storage,
      auto_accept_threshold: data.auto_accept_threshold,
      review_threshold: data.review_threshold,
      cluster_threshold: data.cluster_threshold,
      min_face_size: data.min_face_size,
      min_detection_confidence: data.min_detection_confidence,
      min_quality_for_prototype: data.min_quality_for_prototype,
      max_positive_samples_per_person: data.max_positive_samples_per_person,
      allow_auto_assignment: data.allow_auto_assignment,
      require_human_confirmation_for_new_person: data.require_human_confirmation_for_new_person,
      enable_negative_constraints: data.enable_negative_constraints,
      enable_person_cannot_links: data.enable_person_cannot_links,
    });
  }, [data]);

  const saveMutation = useMutation({
    mutationFn: (body: ProjectFaceSettingsUpdate) =>
      api.projectSettings.updateFace(projectId, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["project-face-settings", projectId] });
      setMessage("人脸识别配置已保存");
    },
    onError: (err) => {
      setMessage((err as Error).message);
    },
  });

  const resetMutation = useMutation({
    mutationFn: () => api.projectSettings.resetFace(projectId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["project-face-settings", projectId] });
      setMessage("已恢复默认配置");
    },
    onError: (err) => {
      setMessage((err as Error).message);
    },
  });

  function setField<K extends keyof FaceSettingsForm>(key: K, value: FaceSettingsForm[K]) {
    setForm((prev: FaceSettingsForm) => ({ ...prev, [key]: value }));
  }

  if (isLoading) {
    return (
      <SettingsCard title="人脸识别配置">
        <div className="flex items-center gap-2 text-body-sm text-mute">
          <Loader2 className="w-4 h-4 animate-spin" />
          正在加载配置...
        </div>
      </SettingsCard>
    );
  }

  if (error || !data) {
    return (
      <SettingsCard title="人脸识别配置">
        <div className="flex items-center gap-2 text-body-sm text-danger">
          <AlertCircle className="w-4 h-4" />
          {(error as Error | undefined)?.message ?? "加载失败"}
        </div>
      </SettingsCard>
    );
  }

  return (
    <SettingsCard
      title="人脸识别配置"
      subtitle="本地 People Recognition 的启停、阈值和隐私开关。真实身份识别不在此功能范围内。"
    >
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <div className="rounded-md bg-surface-soft border border-hairline p-3">
          <div className="flex items-center gap-2 text-body-sm font-medium text-ink">
            <ScanFace className="w-4 h-4 text-primary" />
            当前 Provider
          </div>
          <p className="text-caption-sm text-mute mt-1">
            {data.face_provider} / {data.face_detector_model} / {data.face_embedding_model}
          </p>
        </div>
        <div className="rounded-md bg-surface-soft border border-hairline p-3">
          <div className="flex items-center gap-2 text-body-sm font-medium text-ink">
            <ShieldCheck className="w-4 h-4 text-primary" />
            运行方式
          </div>
          <p className="text-caption-sm text-mute mt-1">
            {data.face_runtime} · crop {data.store_face_crops ? "已开启" : "未保存"}
          </p>
        </div>
        <div className="rounded-md bg-surface-soft border border-hairline p-3">
          <div className="text-body-sm font-medium text-ink">服务要求</div>
          <p className="text-caption-sm text-mute mt-1">
            服务器需要可用的 `cv2`，并配置 `FACE_DETECTOR_MODEL_PATH` 与 `FACE_EMBEDDING_MODEL_PATH`。
          </p>
        </div>
      </div>

      <div className="space-y-1">
        <ToggleRow
          title="启用项目级人脸识别"
          description="开启后才能执行单张照片人脸扫描，以及后续人物聚类与匹配。"
          checked={Boolean(form.face_recognition_enabled)}
          onChange={(value) => setField("face_recognition_enabled", value)}
        />
        <ToggleRow
          title="允许自动归类已命名人物"
          description="高于自动阈值的结果可直接归到已命名人物；关闭后只进入待确认。"
          checked={Boolean(form.allow_auto_assignment)}
          onChange={(value) => setField("allow_auto_assignment", value)}
        />
        <ToggleRow
          title="新人物必须人工确认"
          description="未知人物不会直接成为正式人物，而是先进入人工确认流程。"
          checked={Boolean(form.require_human_confirmation_for_new_person)}
          onChange={(value) => setField("require_human_confirmation_for_new_person", value)}
        />
        <ToggleRow
          title="保存人脸裁剪图"
          description="开启后会把每张检测到的人脸 crop 落到本地，便于复核与调试。"
          checked={Boolean(form.store_face_crops)}
          onChange={(value) => setField("store_face_crops", value)}
        />
        <ToggleRow
          title="启用负样本约束"
          description="人工标记“这不是某人”后，后续自动匹配会显式绕开。"
          checked={Boolean(form.enable_negative_constraints)}
          onChange={(value) => setField("enable_negative_constraints", value)}
        />
        <ToggleRow
          title="启用人物不可合并约束"
          description="人工拆分或拒绝合并后，后续聚类不能再把这两个人重新合到一起。"
          checked={Boolean(form.enable_person_cannot_links)}
          onChange={(value) => setField("enable_person_cannot_links", value)}
        />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
        <div>
          <Label>自动接受阈值</Label>
          <input
            type="number"
            step="0.01"
            min="0"
            max="1"
            className="input-base w-full"
            value={form.auto_accept_threshold ?? ""}
            onChange={(e) => setField("auto_accept_threshold", Number(e.target.value))}
          />
        </div>
        <div>
          <Label>待确认阈值</Label>
          <input
            type="number"
            step="0.01"
            min="0"
            max="1"
            className="input-base w-full"
            value={form.review_threshold ?? ""}
            onChange={(e) => setField("review_threshold", Number(e.target.value))}
          />
        </div>
        <div>
          <Label>聚类阈值</Label>
          <input
            type="number"
            step="0.01"
            min="0"
            max="1"
            className="input-base w-full"
            value={form.cluster_threshold ?? ""}
            onChange={(e) => setField("cluster_threshold", Number(e.target.value))}
          />
        </div>
        <div>
          <Label>最小检测置信度</Label>
          <input
            type="number"
            step="0.01"
            min="0"
            max="1"
            className="input-base w-full"
            value={form.min_detection_confidence ?? ""}
            onChange={(e) => setField("min_detection_confidence", Number(e.target.value))}
          />
        </div>
        <div>
          <Label>最小人脸尺寸</Label>
          <input
            type="number"
            min="1"
            className="input-base w-full"
            value={form.min_face_size ?? ""}
            onChange={(e) => setField("min_face_size", Number(e.target.value))}
          />
        </div>
        <div>
          <Label>原型最小质量</Label>
          <input
            type="number"
            step="0.01"
            min="0"
            max="1"
            className="input-base w-full"
            value={form.min_quality_for_prototype ?? ""}
            onChange={(e) => setField("min_quality_for_prototype", Number(e.target.value))}
          />
        </div>
        <div>
          <Label>每人最大正样本数</Label>
          <input
            type="number"
            min="1"
            className="input-base w-full"
            value={form.max_positive_samples_per_person ?? ""}
            onChange={(e) => setField("max_positive_samples_per_person", Number(e.target.value))}
          />
        </div>
        <div>
          <Label>Crop 存储策略</Label>
          <input
            type="text"
            className="input-base w-full"
            value={form.face_crop_storage ?? ""}
            onChange={(e) => setField("face_crop_storage", e.target.value)}
          />
        </div>
      </div>

      <div className="flex gap-2 flex-wrap">
        <button
          onClick={() => saveMutation.mutate(form)}
          disabled={saveMutation.isPending}
          className="btn-primary flex items-center gap-1.5 text-sm"
        >
          {saveMutation.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
          保存人脸配置
        </button>
        <button
          onClick={() => resetMutation.mutate()}
          disabled={resetMutation.isPending}
          className="btn-secondary flex items-center gap-1.5 text-sm"
        >
          {resetMutation.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RotateCcw className="w-3.5 h-3.5" />}
          恢复默认
        </button>
      </div>

      {message && (
        <div className={`rounded-md px-3 py-2 text-sm ${message.includes("失败") || message.includes("error") ? "bg-red-50 text-red-700" : "bg-green-50 text-green-700"}`}>
          {message}
        </div>
      )}
    </SettingsCard>
  );
}
