import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";

export function useScanStatus(projectId?: number | null) {
  // If a projectId is given, use project-scoped scan status
  const isProjectMode = projectId !== undefined && projectId !== null;
  return useQuery({
    queryKey: isProjectMode
      ? ["project-scan-status", projectId]
      : ["scan-status"],
    queryFn: isProjectMode
      ? () => api.projects.scanStatus(projectId)
      : api.scan.status,
    refetchInterval: (query) => (query.state.data?.running ? 1500 : false),
    staleTime: 0,
  });
}

export function useStartScan(projectId?: number | null) {
  const qc = useQueryClient();
  const isProjectMode = projectId !== undefined && projectId !== null;
  return useMutation({
    mutationFn: isProjectMode
      ? () => api.projects.startScan(projectId)
      : api.scan.start,
    onSuccess: () => {
      qc.invalidateQueries({
        queryKey: isProjectMode
          ? ["project-scan-status", projectId]
          : ["scan-status"],
      });
    },
    onSettled: () => {
      setTimeout(
        () =>
          qc.invalidateQueries({
            queryKey: ["photos", projectId ?? null],
          }),
        2000
      );
    },
  });
}
