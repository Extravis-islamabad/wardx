import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  requestsService,
  type RequestCreatePayload,
  type RequestDecisionPayload,
} from '@/services/access-services';
import type { PageQuery } from '@/types/api';
import { dashboardKeys } from '@/features/dashboard/hooks/dashboardKeys';
import { inventoryKeys } from '@/features/inventory/hooks/inventoryKeys';
import { accessKeys } from './accessKeys';

const REQUESTS_POLL_MS = 20_000;

export function useRequests(params: PageQuery) {
  return useQuery({
    queryKey: accessKeys.requests(params),
    queryFn: () => requestsService.list(params),
    refetchInterval: REQUESTS_POLL_MS,
  });
}

export function useCreateRequest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: RequestCreatePayload) => requestsService.create(payload),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: accessKeys.all });
      void qc.invalidateQueries({ queryKey: inventoryKeys.accountsAll() });
      void qc.invalidateQueries({ queryKey: dashboardKeys.all });
    },
  });
}

export function useDecideRequest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: RequestDecisionPayload }) =>
      requestsService.decide(id, payload),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: accessKeys.requestsAll() });
      void qc.invalidateQueries({ queryKey: dashboardKeys.all });
    },
  });
}

export function useCancelRequest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => requestsService.cancel(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: accessKeys.requestsAll() });
      void qc.invalidateQueries({ queryKey: dashboardKeys.all });
    },
  });
}
