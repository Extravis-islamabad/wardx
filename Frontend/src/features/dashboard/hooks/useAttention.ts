import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { dashboardService } from '@/services/dashboard-services';
import { alertsService } from '@/services/security-services';
import { dashboardKeys } from './dashboardKeys';

const ATTENTION_POLL_MS = 30_000;
const OPEN_HIGH_ALERTS = { page: 1, page_size: 20, severity: 'high', acknowledged: false } as const;

/** Directory outage, break-glass coverage and safes needing attention. */
export function useAttention(enabled: boolean) {
  return useQuery({
    queryKey: dashboardKeys.attention(),
    queryFn: async () => (await dashboardService.attention()).data,
    refetchInterval: ATTENTION_POLL_MS,
    enabled,
  });
}

/** Unacknowledged high-severity alerts (audit.view). */
export function useOpenHighAlerts(enabled: boolean) {
  return useQuery({
    queryKey: dashboardKeys.alerts(),
    queryFn: () => alertsService.list(OPEN_HIGH_ALERTS),
    refetchInterval: ATTENTION_POLL_MS,
    enabled,
  });
}

export function useAcknowledgeAlert() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => alertsService.acknowledge(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: dashboardKeys.alerts() }),
  });
}
