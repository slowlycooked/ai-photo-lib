import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { Navigate, useLocation, useParams } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { api, type EffectiveSettingValue } from "@/api";
import { useProjectContext } from "@/contexts/ProjectContext";
import { EmbeddingSettingsSection } from "@/components/project-ai-settings/EmbeddingSettingsSection";
import { SettingsCard } from "@/components/project-ai-settings/SettingsPrimitives";
import { SettingsLayout } from "@/components/settings/SettingsLayout";
import ProjectQueryPlannerSettingsPanel from "./ProjectQueryPlannerSettingsPanel";
import ProjectSearchSettingsPanel from "./ProjectSearchSettingsPanel";
import { ProjectVisionAISettingsPanel } from "./ProjectVisionAISettingsPanel";

const AI_EFFECTIVE_FIELDS = [
  { key: "profile_name", label: "Profile" },
  { key: "provider", label: "Provider" },
  { key: "endpoint_url", label: "Endpoint" },
  { key: "model_name", label: "Model" },
] as const;

function sourceLabel(source: string) {
  const labels: Record<string, string> = {
    ai_service_profiles: "系统 AI 服务",
    project_ai_settings: "项目视觉配置",
    project_embedding_settings: "项目 Embedding 配置",
    project_query_planner_settings: "项目 Planner 配置",
    global_config: "全局环境配置",
  };
  return labels[source] ?? source;
}

function effectiveValue(setting: EffectiveSettingValue | undefined) {
  if (!setting || setting.value == null || setting.value === "") return "-";
  return String(setting.value);
}

function ProjectEffectiveAIConfigCard({ projectId }: { projectId: number }) {
  const { data, isLoading } = useQuery({
    queryKey: ["project-effective-settings", projectId],
    queryFn: () => api.projectSettings.effective(projectId),
    staleTime: 15_000,
  });
  const groups = [
    { key: "vision", label: "Vision" },
    { key: "embedding", label: "Embedding" },
    { key: "query_planner", label: "Planner" },
  ] as const;

  return (
    <SettingsCard title="当前生效 AI 配置">
      {isLoading ? (
        <div className="flex items-center gap-2 text-mute">
          <Loader2 className="w-4 h-4 animate-spin" />
          加载中…
        </div>
      ) : (
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-3">
          {groups.map((group) => {
            const config = data?.ai?.[group.key] ?? {};
            return (
              <div key={group.key} className="rounded-md border border-hairline bg-surface-card p-3">
                <div className="text-body-sm font-semibold text-ink mb-2">{group.label}</div>
                <div className="space-y-2">
                  {AI_EFFECTIVE_FIELDS.map((field) => {
                    const setting = config[field.key];
                    return (
                      <div key={field.key}>
                        <div className="text-caption-sm text-mute">{field.label}</div>
                        <div className="text-body-sm text-ink break-all">{effectiveValue(setting)}</div>
                        {setting?.source && (
                          <div className="mt-0.5 text-[11px] text-mute">{sourceLabel(setting.source)}</div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </SettingsCard>
  );
}

export function ProjectAISettingsPage() {
  const { projectId } = useParams();
  const location = useLocation();
  const { currentProjectId, currentProject, setCurrentProjectId } = useProjectContext();

  const routeProjectId = projectId ? Number(projectId) : NaN;
  const normalizedRouteProjectId = Number.isFinite(routeProjectId)
    ? routeProjectId
    : null;
  const normalizedCurrentProjectId =
    currentProjectId !== null && Number.isFinite(currentProjectId)
      ? currentProjectId
      : null;

  // Keep project context aligned with route id when route is explicit.
  useEffect(() => {
    if (normalizedRouteProjectId === null) return;
    if (normalizedCurrentProjectId === normalizedRouteProjectId) return;
    setCurrentProjectId(normalizedRouteProjectId);
  }, [normalizedCurrentProjectId, normalizedRouteProjectId, setCurrentProjectId]);

  const selectedProjectId =
    normalizedRouteProjectId ?? normalizedCurrentProjectId;

  const section = location.pathname.split("/")[4] ?? "";
  const activeSection = section === "ai" || section === "" ? "vision-ai" : section;
  const knownSections = new Set(["vision-ai", "embedding-ai", "planner-ai", "advanced"]);

  if (selectedProjectId == null) {
    return (
      <main className="max-w-5xl mx-auto px-4 sm:px-6 py-6">
        <div className="bg-canvas border border-hairline rounded-md px-5 py-4 text-body-sm text-mute">
          请先选择一个项目，再进入 AI 配置页。
        </div>
      </main>
    );
  }

  if (section === "ai" || section === "") {
    return <Navigate to={`/projects/${selectedProjectId}/settings/vision-ai`} replace />;
  }

  if (!knownSections.has(activeSection)) {
    return <Navigate to={`/projects/${selectedProjectId}/settings/vision-ai`} replace />;
  }

  return (
    <SettingsLayout
      title="项目设置"
      subtitle={`项目：${currentProject?.id === selectedProjectId ? currentProject.name : `#${selectedProjectId}`}`}
      currentProjectId={selectedProjectId}
      showProjectSettingsLink={false}
    >
      <ProjectEffectiveAIConfigCard projectId={selectedProjectId} />

      {activeSection === "vision-ai" && <ProjectVisionAISettingsPanel projectId={selectedProjectId} />}

      {activeSection === "embedding-ai" && <EmbeddingSettingsSection projectId={selectedProjectId} />}

      {activeSection === "planner-ai" && (
        <SettingsCard title="Planner AI 配置与测试">
          <ProjectQueryPlannerSettingsPanel projectId={selectedProjectId} />
        </SettingsCard>
      )}

      {activeSection === "advanced" && (
        <SettingsCard title="高级搜索参数">
          <ProjectSearchSettingsPanel projectId={selectedProjectId} />
        </SettingsCard>
      )}
    </SettingsLayout>
  );
}
