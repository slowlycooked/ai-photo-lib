import type { Project } from "@/api";

export function ProjectSwitcherSheet({
  open,
  projects,
  currentProjectId,
  onClose,
  onSelect,
}: {
  open: boolean;
  projects: Project[];
  currentProjectId: number | null;
  onClose: () => void;
  onSelect: (projectId: number) => void;
}) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50">
      <button
        aria-label="关闭项目切换"
        className="absolute inset-0 bg-black/40"
        onClick={onClose}
      />
      <div className="absolute inset-x-0 bottom-0 rounded-t-3xl bg-mobileCard p-4 shadow-sheet">
        <div className="mx-auto mb-3 h-1.5 w-10 rounded-full bg-mobileHairline" />
        <h2 className="mb-3 text-base font-semibold text-mobileInk">切换项目</h2>
        <div className="max-h-[50vh] space-y-2 overflow-auto pb-3">
          {projects.map((project) => {
            const active = currentProjectId === project.id;
            return (
              <button
                key={project.id}
                type="button"
                onClick={() => {
                  onSelect(project.id);
                  onClose();
                }}
                className={`w-full rounded-xl border px-3 py-3 text-left ${
                  active
                    ? "border-mobileAccent bg-emerald-50 text-mobileAccent"
                    : "border-mobileHairline text-mobileInk"
                }`}
              >
                <div className="truncate text-sm font-semibold">{project.name}</div>
                {project.description && (
                  <div className="mt-1 truncate text-xs text-mobileMute">{project.description}</div>
                )}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
