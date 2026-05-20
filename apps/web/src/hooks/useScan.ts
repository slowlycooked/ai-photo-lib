import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";

export function useScanStatus(projectId: number | null) {
  return useQuery({
    queryKey: ["project-scan-status", projectId],
    queryFn: () => api.projects.scanStatus(projectId!),
    enabled: projectId !== null,
    refetchInterval: (query) => (query.state.data?.running ? 1500 : false),
    staleTime: 0,
  });
}

export function useStartScan(projectId: number | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => {
      if (projectId === null) return Promise.reject(new Error("No project selected"));
      return api.projects.startScan(projectId);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["project-scan-status", projectId] });
    },
    onSettled: () => {
      setTimeout(
        () => qc.invalidateQueries({ queryKey: ["photos", projectId] }),
        2000
      );
    },
  });
}
