import { useEffect } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Settings2 } from "lucide-react";
import { useProjectContext } from "@/contexts/ProjectContext";
import { ProjectAISettingsPanel } from "./ProjectAISettingsPanel";

export function ProjectAISettingsPage() {
  const { projectId } = useParams();
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

  // When entering from /projects/:projectId/settings/ai and no
  // project is selected yet, hydrate the project context once from route id.
  useEffect(() => {
    if (normalizedCurrentProjectId !== null) return;
    if (normalizedRouteProjectId === null) return;
    setCurrentProjectId(normalizedRouteProjectId);
  }, [normalizedCurrentProjectId, normalizedRouteProjectId, setCurrentProjectId]);

  const selectedProjectId =
    normalizedCurrentProjectId ?? normalizedRouteProjectId;

  if (selectedProjectId == null) {
    return (
      <main className="max-w-5xl mx-auto px-4 sm:px-6 py-6">
        <div className="bg-canvas border border-hairline rounded-md px-5 py-4 text-body-sm text-mute">
          请先选择一个项目，再进入 AI 配置页。
        </div>
      </main>
    );
  }

  return (
    <main className="max-w-5xl mx-auto px-4 sm:px-6 py-6 space-y-6">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-heading-md font-semibold text-ink flex items-center gap-2">
            <Settings2 className="w-5 h-5" />
            项目 AI 配置
          </h1>
          <p className="text-caption-sm text-mute mt-1">
            项目：{currentProject?.id === selectedProjectId ? currentProject.name : `#${selectedProjectId}`}
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => navigate("/tasks?tab=ai-settings")}
            className="px-3 py-1.5 text-btn-sm rounded-md border border-hairline hover:bg-surface-card"
          >
            返回任务中心
          </button>
          <Link
            to="/settings"
            className="px-3 py-1.5 text-btn-sm rounded-md border border-hairline hover:bg-surface-card"
          >
            系统设置
          </Link>
        </div>
      </div>

      <ProjectAISettingsPanel projectId={selectedProjectId} />
    </main>
  );
}

