import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { checkoutsService, type CheckoutCreatePayload } from '@/services/access-services';
import type { PageQuery } from '@/types/api';
import { dashboardKeys } from '@/features/dashboard/hooks/dashboardKeys';
import { inventoryKeys } from '@/features/inventory/hooks/inventoryKeys';
import { accessKeys } from './accessKeys';

const CHECKOUTS_POLL_MS = 30_000;

export function useCheckouts(params: PageQuery) {
  return useQuery({
    queryKey: accessKeys.checkouts(params),
    queryFn: () => checkoutsService.list(params),
    refetchInterval: CHECKOUTS_POLL_MS,
  });
}

/** Direct check-out, or redeeming an approved request when `request_id` is set. */
export function useCreateCheckout() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: CheckoutCreatePayload) => (await checkoutsService.create(payload)).data,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: accessKeys.all });
      void qc.invalidateQueries({ queryKey: inventoryKeys.accountsAll() });
      void qc.invalidateQueries({ queryKey: dashboardKeys.all });
    },
  });
}

/** Check a credential back in; on someone else's check-out this is an admin revoke. */
export function useCheckin() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => checkoutsService.checkin(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: accessKeys.checkoutsAll() });
      void qc.invalidateQueries({ queryKey: inventoryKeys.accountsAll() });
      void qc.invalidateQueries({ queryKey: dashboardKeys.all });
    },
  });
}

/** Each reveal is audited server-side, so it is a mutation, never a cached query. */
export function useRevealCheckout() {
  return useMutation({
    mutationFn: async (id: string) => (await checkoutsService.reveal(id)).data,
  });
}
