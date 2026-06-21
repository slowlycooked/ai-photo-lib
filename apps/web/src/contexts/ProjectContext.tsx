import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { useQuery } from "@tanstack/react-query";
import { api, type Project } from "@/api";
import { queryKeys } from "@/api/queryKeys";

const STORAGE_KEY = "ai-photo-lib:current-project-id";

function readStoredProjectId() {
  if (typeof localStorage === "undefined" || typeof localStorage.getItem !== "function") {
    return null;
  }

  const stored = localStorage.getItem(STORAGE_KEY);
  return stored ? Number(stored) : null;
}

function writeStoredProjectId(projectId: number) {
  if (typeof localStorage === "undefined" || typeof localStorage.setItem !== "function") {
    return;
  }

  localStorage.setItem(STORAGE_KEY, String(projectId));
}

function clearStoredProjectId() {
  if (typeof localStorage === "undefined" || typeof localStorage.removeItem !== "function") {
    return;
  }

  localStorage.removeItem(STORAGE_KEY);
}

interface ProjectContextValue {
  projects: Project[];
  isLoading: boolean;
  currentProjectId: number | null;
  currentProject: Project | null;
  setCurrentProjectId: (id: number) => void;
}

const ProjectContext = createContext<ProjectContextValue>({
  projects: [],
  isLoading: true,
  currentProjectId: null,
  currentProject: null,
  setCurrentProjectId: () => {},
});

export function ProjectProvider({ children }: { children: ReactNode }) {
  const { data, isLoading } = useQuery({
    queryKey: queryKeys.projects(),
    queryFn: api.projectCore.list,
    refetchInterval: 30_000,
    refetchIntervalInBackground: true,
    staleTime: 60_000,
  });

  const projects = data?.items ?? [];

  const [currentProjectId, setCurrentProjectIdState] = useState<number | null>(() => {
    return readStoredProjectId();
  });

  // Auto-select: restore from localStorage (if valid) or pick the default project
  useEffect(() => {
    if (!projects.length) {
      setCurrentProjectIdState(null);
      clearStoredProjectId();
      return;
    }

    const storedId = currentProjectId;
    const isValid = storedId !== null && projects.some((p) => p.id === storedId);
    if (isValid) return;

    // Fall back to the default project, then the first project
    const defaultProject = projects.find((p) => p.is_default) ?? projects[0];
    if (defaultProject) {
      setCurrentProjectIdState(defaultProject.id);
      writeStoredProjectId(defaultProject.id);
    }
  }, [projects]); // eslint-disable-line react-hooks/exhaustive-deps

  const setCurrentProjectId = useCallback((id: number) => {
    setCurrentProjectIdState(id);
    writeStoredProjectId(id);
  }, []);

  const currentProject =
    projects.find((p) => p.id === currentProjectId) ?? null;

  return (
    <ProjectContext.Provider
      value={{
        projects,
        isLoading,
        currentProjectId,
        currentProject,
        setCurrentProjectId,
      }}
    >
      {children}
    </ProjectContext.Provider>
  );
}

export function useProjectContext() {
  return useContext(ProjectContext);
}
