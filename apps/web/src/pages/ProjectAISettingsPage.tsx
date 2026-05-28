import { type ComponentType, useEffect } from "react";
import { Link, NavLink, Navigate, useLocation, useNavigate, useParams } from "react-router-dom";
import { Bot, BrainCircuit, Settings2, Sparkles, Wrench } from "lucide-react";
import { useProjectContext } from "@/contexts/ProjectContext";
import { EmbeddingSettingsSection } from "@/components/project-ai-settings/EmbeddingSettingsSection";
import { SettingsCard } from "@/components/project-ai-settings/SettingsPrimitives";
import ProjectQueryPlannerSettingsPanel from "./ProjectQueryPlannerSettingsPanel";
import ProjectSearchSettingsPanel from "./ProjectSearchSettingsPanel";
import { ProjectVisionAISettingsPanel } from "./ProjectVisionAISettingsPanel";

export function ProjectAISettingsPage() {
  const { projectId } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
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

  const navItems: Array<{
    key: "vision-ai" | "embedding-ai" | "planner-ai" | "advanced";
    label: string;
    icon: ComponentType<{ className?: string }>;
  }> = [
    { key: "vision-ai", label: "视觉 AI", icon: Bot },
    { key: "embedding-ai", label: "Embedding AI", icon: BrainCircuit },
    { key: "planner-ai", label: "Planner AI", icon: Sparkles },
    { key: "advanced", label: "高级搜索参数", icon: Wrench },
  ];

  return (
    <main className="max-w-7xl mx-auto px-4 sm:px-6 py-6 space-y-6">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-heading-md font-semibold text-ink flex items-center gap-2">
            <Settings2 className="w-5 h-5" />
            项目设置中心
          </h1>
          <p className="text-caption-sm text-mute mt-1">
            项目：{currentProject?.id === selectedProjectId ? currentProject.name : `#${selectedProjectId}`}
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => navigate("/tasks")}
            className="px-3 py-1.5 text-btn-sm rounded-md border border-hairline hover:bg-surface-card"
          >
            返回任务中心
          </button>
          <Link
            to="/settings/general"
            className="px-3 py-1.5 text-btn-sm rounded-md border border-hairline hover:bg-surface-card"
          >
            系统设置
          </Link>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[220px_minmax(0,1fr)] gap-6">
        <aside className="bg-canvas border border-hairline rounded-md p-2 h-fit">
          <p className="px-2 py-1 text-caption-sm text-mute">AI 能力</p>
          <nav className="space-y-1 mt-1">
            {navItems.map((item) => {
              const Icon = item.icon;
              return (
                <NavLink
                  key={item.key}
                  to={`/projects/${selectedProjectId}/settings/${item.key}`}
                  className={({ isActive }) =>
                    [
                      "flex items-center gap-2 px-2.5 py-2 rounded-md text-body-sm border transition-colors",
                      isActive
                        ? "border-primary text-primary bg-primary/10"
                        : "border-transparent text-ink hover:bg-surface-card",
                    ].join(" ")
                  }
                >
                  <Icon className="w-4 h-4" />
                  {item.label}
                </NavLink>
              );
            })}
          </nav>
        </aside>

        <section className="space-y-6">
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
        </section>
      </div>
    </main>
  );
}
