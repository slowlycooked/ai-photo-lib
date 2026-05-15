import { useQuery } from "@tanstack/react-query";
import { Loader2, AlertCircle, Settings } from "lucide-react";
import { api, type AppSettings } from "@/lib/api";

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
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="bg-canvas border border-hairline rounded-md">
      <div className="px-5 py-3 border-b border-hairline">
        <h2 className="text-body-sm font-semibold text-ink">{title}</h2>
      </div>
      <div className="px-5">{children}</div>
    </div>
  );
}

export function SettingsPage() {
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

      <p className="text-body-sm text-mute">
        当前配置来自环境变量（只读）。如需修改，请编辑 <code className="bg-secondary-bg px-1.5 py-0.5 rounded text-caption-md">.env</code> 文件并重启服务。
      </p>

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
          <SettingsCard title="照片目录">
            <SettingRow label="照片目录路径" value={data.photo_library_path} />
            <SettingRow label="缩略图目录" value={data.thumbnail_path} />
            <SettingRow label="缩略图尺寸" value={`${data.thumbnail_size}px`} />
          </SettingsCard>

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
