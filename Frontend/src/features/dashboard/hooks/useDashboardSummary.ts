import { useQuery } from '@tanstack/react-query';
import { dashboardService } from '@/services/dashboard-services';
import { dashboardKeys } from './dashboardKeys';

const SUMMARY_POLL_MS = 30_000;

export function useDashboardSummary() {
  return useQuery({
    queryKey: dashboardKeys.summary(),
    queryFn: async () => (await dashboardService.summary()).data,
    refetchInterval: SUMMARY_POLL_MS,
  });
}
