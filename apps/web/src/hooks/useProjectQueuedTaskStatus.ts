import { useQuery, type QueryFunctionContext } from "@tanstack/react-query";

interface QueueLikeStatus {
  queued: number;
  running: number;
}

export function useProjectQueuedTaskStatus<T extends QueueLikeStatus>(
  queryKey: readonly unknown[],
  queryFn: (context: QueryFunctionContext) => Promise<T>,
  enabled: boolean
) {
  return useQuery({
    queryKey,
    queryFn,
    enabled,
    staleTime: 3_000,
    refetchInterval: (query) => {
      const data = query.state.data as QueueLikeStatus | undefined;
      return data && (data.queued > 0 || data.running > 0) ? 3000 : 15000;
    },
  });
}
