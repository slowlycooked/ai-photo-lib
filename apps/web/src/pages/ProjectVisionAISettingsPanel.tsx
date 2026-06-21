import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, Loader2 } from "lucide-react";

import { api } from "@/api";
import { Label, SettingsCard } from "@/components/project-ai-settings/SettingsPrimitives";
import { ProjectFaceSettingsPanel } from "./ProjectFaceSettingsPanel";

export function ProjectVisionAISettingsPanel({ projectId }: { projectId: number }) {
  const { data: settingsData, isLoading: settingsLoading } = useQuery({
    queryKey: ["project-ai-settings", projectId],
    queryFn: () => api.projectSettings.getAi(projectId),
    staleTime: 30_000,
  });

  const { data: readinessData, isLoading: readinessLoading } = useQuery({
    queryKey: ["project-readiness", projectId],
    queryFn: () => api.projectCore.readiness(projectId),
    staleTime: 15_000,
  });

  const { data: aiProfiles } = useQuery({
    queryKey: ["ai-service-profiles"],
    queryFn: api.admin.listAIProfiles,
    staleTime: 30_000,
  });
  const profileName = settingsData?.ai_service_profile_id
    ? (aiProfiles?.items ?? []).find((item) => item.id === settingsData.ai_service_profile_id)?.name ?? "(未找到 profile)"
    : "全局 .env"
  const aiRuntime = readinessData?.checks.find((check) => check.name === "ai_runtime")

  return (
    <div className="space-y-6">
      <SettingsCard title="视觉 AI 服务状态（只读）">
        {readinessLoading ? (
          <div className="flex items-center gap-2 text-mute">
            <Loader2 className="w-4 h-4 animate-spin" />
            加载中…
          </div>
        ) : (
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-body-sm">
              {aiRuntime?.ready ? (
                <CheckCircle2 className="w-4 h-4 text-green-600" />
              ) : (
                <AlertTriangle className="w-4 h-4 text-amber-600" />
              )}
              <span className="font-medium text-ink">{aiRuntime?.ready ? "运行正常" : "需要检查"}</span>
            </div>
            <p className="text-caption-sm text-mute">{aiRuntime?.message ?? "未获取到 ai_runtime 状态"}</p>
            <p className="text-caption-sm text-mute">
              当前系统使用全局 AI 基建能力（.env）作为默认运行参数，不要求逐项目手动初始化模型服务配置。
            </p>
          </div>
        )}
      </SettingsCard>

      <SettingsCard title="视觉 AI 运行参数（只读）">
        {settingsLoading ? (
          <div className="flex items-center gap-2 text-mute">
            <Loader2 className="w-4 h-4 animate-spin" />
            加载中…
          </div>
        ) : !settingsData ? (
          <div className="text-body-sm text-mute">未获取到视觉 AI 运行参数。</div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <Label>系统 AI 服务来源</Label>
              <div className="w-full px-3 py-2 text-body-sm bg-surface-card border border-hairline rounded-md">{profileName}</div>
            </div>
            <div>
              <Label>provider</Label>
              <div className="w-full px-3 py-2 text-body-sm bg-surface-card border border-hairline rounded-md">{settingsData.provider}</div>
            </div>
            <div className="md:col-span-2">
              <Label>模型服务地址</Label>
              <div className="w-full px-3 py-2 text-body-sm bg-surface-card border border-hairline rounded-md break-all">{settingsData.endpoint_url}</div>
            </div>
            <div>
              <Label>模型名称</Label>
              <div className="w-full px-3 py-2 text-body-sm bg-surface-card border border-hairline rounded-md">{settingsData.model_name}</div>
            </div>
            <div>
              <Label>temperature</Label>
              <div className="w-full px-3 py-2 text-body-sm bg-surface-card border border-hairline rounded-md">{settingsData.temperature}</div>
            </div>
            <div>
              <Label>top_p</Label>
              <div className="w-full px-3 py-2 text-body-sm bg-surface-card border border-hairline rounded-md">{settingsData.top_p}</div>
            </div>
            <div>
              <Label>max_tokens</Label>
              <div className="w-full px-3 py-2 text-body-sm bg-surface-card border border-hairline rounded-md">{settingsData.max_tokens}</div>
            </div>
            <div>
              <Label>失败重试次数</Label>
              <div className="w-full px-3 py-2 text-body-sm bg-surface-card border border-hairline rounded-md">{settingsData.retry_count}</div>
            </div>
            <div>
              <Label>输出语言</Label>
              <div className="w-full px-3 py-2 text-body-sm bg-surface-card border border-hairline rounded-md">{settingsData.output_language}</div>
            </div>
            <div>
              <Label>JSON 解析策略</Label>
              <div className="w-full px-3 py-2 text-body-sm bg-surface-card border border-hairline rounded-md">{settingsData.json_parse_strategy}</div>
            </div>
          </div>
        )}
      </SettingsCard>

      <ProjectFaceSettingsPanel projectId={projectId} />
    </div>
  );
}
