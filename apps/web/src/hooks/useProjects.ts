import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type ProjectCreate, type ProjectUpdate } from "@/api";
import { queryKeys } from "@/api/queryKeys";

export function useProjects() {
  return useQuery({
    queryKey: queryKeys.projects(),
    queryFn: api.projectCore.list,
    staleTime: 60_000,
  });
}

export function useProjectScanStatus(projectId: number | null) {
  return useQuery({
    queryKey: queryKeys.projectScanStatus(projectId),
    queryFn: () => api.projectScans.status(projectId!),
    enabled: projectId !== null,
    refetchInterval: (query) => (query.state.data?.running ? 1500 : false),
    staleTime: 0,
  });
}

export function useStartProjectScan(projectId: number | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.projectScans.start(projectId!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.projectScanStatus(projectId) });
    },
    onSettled: () => {
      setTimeout(
        () => qc.invalidateQueries({ queryKey: queryKeys.photosBase(projectId) }),
        2000
      );
    },
  });
}

export function useProjectAIStatus(projectId: number | null) {
  return useQuery({
    queryKey: queryKeys.aiStatus(projectId),
    queryFn: () => api.projectAiJobs.status(projectId!),
    enabled: projectId !== null,
    refetchInterval: (query) => {
      const d = query.state.data;
      return d && (d.queued > 0 || d.running > 0) ? 3000 : 15000;
    },
  });
}

export function useCreateProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ProjectCreate) => api.projectCore.create(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.projects() }),
  });
}

export function useUpdateProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: ProjectUpdate }) =>
      api.projectCore.update(id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.projects() }),
  });
}

export function useDeleteProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.projectCore.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.projects() }),
  });
}
