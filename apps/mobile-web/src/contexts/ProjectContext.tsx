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

const STORAGE_KEY = "ai-photo-lib:mobile:current-project-id";

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
    queryKey: ["mobile-projects"],
    queryFn: api.projects.list,
    staleTime: 60_000,
  });

  const projects = data?.items ?? [];

  const [currentProjectId, setCurrentProjectIdState] = useState<number | null>(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored ? Number(stored) : null;
  });

  useEffect(() => {
    if (!projects.length) {
      setCurrentProjectIdState(null);
      localStorage.removeItem(STORAGE_KEY);
      return;
    }

    const storedId = currentProjectId;
    const isValid = storedId !== null && projects.some((p) => p.id === storedId);
    if (isValid) return;

    const defaultProject = projects.find((p) => p.is_default) ?? projects[0];
    if (defaultProject) {
      setCurrentProjectIdState(defaultProject.id);
      localStorage.setItem(STORAGE_KEY, String(defaultProject.id));
    }
  }, [projects, currentProjectId]);

  const setCurrentProjectId = useCallback((id: number) => {
    setCurrentProjectIdState(id);
    localStorage.setItem(STORAGE_KEY, String(id));
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
