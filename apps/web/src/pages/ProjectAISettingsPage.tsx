import { useEffect } from "react";
import { Navigate, useLocation, useParams } from "react-router-dom";
import { useProjectContext } from "@/contexts/ProjectContext";
import { EmbeddingSettingsSection } from "@/components/project-ai-settings/EmbeddingSettingsSection";
import { SettingsCard } from "@/components/project-ai-settings/SettingsPrimitives";
import { SettingsLayout } from "@/components/settings/SettingsLayout";
import ProjectQueryPlannerSettingsPanel from "./ProjectQueryPlannerSettingsPanel";
import ProjectSearchSettingsPanel from "./ProjectSearchSettingsPanel";
import { ProjectVisionAISettingsPanel } from "./ProjectVisionAISettingsPanel";

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
      title="系统设置"
      subtitle={`项目：${currentProject?.id === selectedProjectId ? currentProject.name : `#${selectedProjectId}`}`}
      currentProjectId={selectedProjectId}
      showProjectSettingsLink={false}
    >
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
