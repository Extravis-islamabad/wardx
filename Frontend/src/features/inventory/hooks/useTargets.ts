import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { targetsService, type TargetPayload } from '@/services/inventory-services';
import type { PageQuery } from '@/types/api';
import { dashboardKeys } from '@/features/dashboard/hooks/dashboardKeys';
import { inventoryKeys } from './inventoryKeys';

export function useTargets(params: PageQuery, options: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: inventoryKeys.targets(params),
    queryFn: () => targetsService.list(params),
    enabled: options.enabled ?? true,
  });
}

export function useSaveTarget() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id?: string; payload: TargetPayload }) =>
      id ? targetsService.update(id, payload) : targetsService.create(payload),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: inventoryKeys.targetsAll() });
      void qc.invalidateQueries({ queryKey: dashboardKeys.all });
    },
  });
}

export function useDeleteTarget() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => targetsService.remove(id),
    // A target's accounts go with it.
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: inventoryKeys.targetsAll() });
      void qc.invalidateQueries({ queryKey: inventoryKeys.accountsAll() });
    },
  });
}

export function useResetTargetHostKey() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => targetsService.resetHostKey(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: inventoryKeys.targetsAll() }),
  });
}

export function useLearnTargetHostKey() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => targetsService.learnHostKey(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: inventoryKeys.targetsAll() }),
  });
}
