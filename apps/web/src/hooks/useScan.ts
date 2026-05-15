import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";

export function useScanStatus() {
  return useQuery({
    queryKey: ["scan-status"],
    queryFn: api.scan.status,
    refetchInterval: (query) => (query.state.data?.running ? 1500 : false),
    staleTime: 0,
  });
}

export function useStartScan() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.scan.start,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["scan-status"] });
    },
    onSettled: () => {
      // Refetch photos after scan completes
      setTimeout(() => qc.invalidateQueries({ queryKey: ["photos"] }), 2000);
    },
  });
}
