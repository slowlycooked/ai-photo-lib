import { useRef, useState } from "react";
import { ChevronDown, FolderOpen, Check, Bot, Lock } from "lucide-react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useProjectContext } from "@/contexts/ProjectContext";

export function ProjectSelector() {
  const { projects, currentProject, setCurrentProjectId, isLoading } =
    useProjectContext();
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const location = useLocation();
  const navigate = useNavigate();

  const switchProject = (projectId: number) => {
    setCurrentProjectId(projectId);
    setOpen(false);

    const projectSettingsMatch = location.pathname.match(
      /^\/projects\/\d+\/settings\/(.+)$/,
    );

    if (projectSettingsMatch) {
      navigate(`/projects/${projectId}/settings/${projectSettingsMatch[1]}`, {
        replace: true,
      });
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center gap-1.5 px-2 py-1 text-mute text-body-sm">
        <FolderOpen className="w-3.5 h-3.5" />
        <span className="hidden sm:block">加载项目…</span>
      </div>
    );
  }

  if (!projects.length) {
    return (
      <div className="flex items-center gap-1.5 px-2 py-1 text-mute text-body-sm" aria-label="无可访问项目">
        <Lock className="w-3.5 h-3.5" />
        <span className="hidden sm:block">无可访问项目</span>
      </div>
    );
  }

  if (!currentProject) {
    return (
      <div className="flex items-center gap-1.5 px-2 py-1 text-mute text-body-sm">
        <FolderOpen className="w-3.5 h-3.5" />
        <span className="hidden sm:block">选择项目…</span>
      </div>
    );
  }

  return (
    <div className="relative">
      <button
        ref={triggerRef}
        onClick={() => setOpen((v) => !v)}
        className={[
          "flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-body-sm transition-colors",
          "border border-hairline bg-surface-card hover:bg-secondary-bg",
          "text-ink",
        ].join(" ")}
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <FolderOpen className="w-3.5 h-3.5 text-primary flex-shrink-0" />
        <span className="hidden sm:block max-w-[120px] truncate font-medium">
          {currentProject.name}
        </span>
        <ChevronDown
          className={`w-3.5 h-3.5 text-mute transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>

      {open && (
        <>
          {/* Backdrop */}
          <div
            className="fixed inset-0 z-40"
            onClick={() => setOpen(false)}
          />
          {/* Dropdown */}
          <div
            className={[
              "absolute left-0 top-full mt-1 z-50 min-w-[220px] max-w-[280px]",
              "bg-canvas border border-hairline rounded-lg shadow-lg py-1",
              "overflow-hidden",
            ].join(" ")}
            role="listbox"
          >
            <div className="px-3 py-1.5 text-caption-sm text-mute font-semibold uppercase tracking-wide">
              项目
            </div>
            {projects.map((project) => (
              <button
                key={project.id}
                role="option"
                aria-selected={project.id === currentProject.id}
                onClick={() => switchProject(project.id)}
                className={[
                  "w-full flex items-center gap-2.5 px-3 py-2 text-left text-body-sm",
                  "hover:bg-secondary-bg transition-colors",
                  project.id === currentProject.id
                    ? "text-ink font-semibold"
                    : "text-ink",
                ].join(" ")}
              >
                <FolderOpen className="w-3.5 h-3.5 text-primary flex-shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="truncate">{project.name}</p>
                  {project.description && (
                    <p className="text-caption-sm text-mute truncate">
                      {project.description}
                    </p>
                  )}
                </div>
                {project.id === currentProject.id && (
                  <Check className="w-3.5 h-3.5 text-primary flex-shrink-0" />
                )}
              </button>
            ))}
            <div className="border-t border-hairline mt-1 pt-1 px-1 pb-1">
              <Link
                to={`/projects/${currentProject.id}/settings/vision-ai`}
                onClick={() => setOpen(false)}
                className="w-full flex items-center gap-2 px-2 py-2 rounded-md text-body-sm text-primary hover:bg-secondary-bg"
              >
                <Bot className="w-3.5 h-3.5" />
                项目设置 / AI 配置
              </Link>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
