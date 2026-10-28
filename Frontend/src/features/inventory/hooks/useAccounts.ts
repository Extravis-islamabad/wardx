import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { accountsService, type AccountInput, type SnmpSecret } from '@/services/inventory-services';
import type { PageQuery } from '@/types/api';
import { dashboardKeys } from '@/features/dashboard/hooks/dashboardKeys';
import { inventoryKeys } from './inventoryKeys';

export function useAccounts(params: PageQuery) {
  return useQuery({
    queryKey: inventoryKeys.accounts(params),
    queryFn: () => accountsService.list(params),
  });
}

export function useCreateAccount() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: AccountInput) => accountsService.create(payload),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: inventoryKeys.accountsAll() });
      void qc.invalidateQueries({ queryKey: dashboardKeys.all });
    },
  });
}

export function useUpdateAccount() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: Partial<AccountInput> }) =>
      accountsService.update(id, payload),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: inventoryKeys.accountsAll() });
      void qc.invalidateQueries({ queryKey: dashboardKeys.all });
    },
  });
}

export function useSetAccountSecret() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, value }: { id: string; value: string | SnmpSecret }) => accountsService.setSecret(id, value),
    onSuccess: () => qc.invalidateQueries({ queryKey: inventoryKeys.accountsAll() }),
  });
}

export function useDeleteAccount() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => accountsService.remove(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: inventoryKeys.accountsAll() }),
  });
}
