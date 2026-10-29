import { useQuery } from '@tanstack/react-query';
import { clusterService } from '@/services/dashboard-services';
import { dashboardKeys } from './dashboardKeys';

const CLUSTER_POLL_MS = 15_000;

/** Scheduler leader, replication, DR lag and gateway nodes (cluster.view). */
export function useCluster(enabled: boolean) {
  return useQuery({
    queryKey: dashboardKeys.cluster(),
    queryFn: async () => (await clusterService.health()).data,
    refetchInterval: CLUSTER_POLL_MS,
    enabled,
  });
}
