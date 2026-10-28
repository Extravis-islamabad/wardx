import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  safesService,
  type ApprovalPolicy,
  type SafeAppFetch,
  type SafeInput,
  type SafeMemberInput,
} from '@/services/safes-services';
import { inventoryKeys } from '@/features/inventory/hooks/inventoryKeys';
import type { SafePermission } from '@/constants/enums/safes';
import type { PageQuery } from '@/types/api';
import { dashboardKeys } from '@/features/dashboard/hooks/dashboardKeys';
import { safesKeys } from './safesKeys';

export function useSafes(params: PageQuery, options: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: safesKeys.list(params),
    queryFn: () => safesService.list(params),
    enabled: options.enabled ?? true,
  });
}

export function useSafeHealth(enabled: boolean) {
  return useQuery({
    queryKey: safesKeys.health(),
    queryFn: async () => (await safesService.health()).data,
    enabled,
  });
}

/** Membership changes move health, counts and the dashboard's attention list. */
function useInvalidateSafes() {
  const qc = useQueryClient();
  return () => {
    void qc.invalidateQueries({ queryKey: safesKeys.all });
    void qc.invalidateQueries({ queryKey: dashboardKeys.all });
  };
}

export function useSaveSafe() {
  const invalidate = useInvalidateSafes();
  return useMutation({
    mutationFn: ({ id, payload }: { id?: string; payload: SafeInput }) =>
      id ? safesService.update(id, payload) : safesService.create(payload),
    onSuccess: invalidate,
  });
}

export function useSafeMembers(safeId: string | undefined) {
  return useQuery({
    queryKey: safesKeys.members(safeId ?? ''),
    queryFn: async () => (await safesService.members(safeId as string)).data,
    enabled: !!safeId,
  });
}

export function useAddSafeMember(safeId: string) {
  const invalidate = useInvalidateSafes();
  return useMutation({
    mutationFn: (payload: SafeMemberInput) => safesService.addMember(safeId, payload),
    onSuccess: invalidate,
  });
}

export function useUpdateSafeMember(safeId: string) {
  const invalidate = useInvalidateSafes();
  return useMutation({
    mutationFn: ({ memberId, permissions }: { memberId: string; permissions: SafePermission[] }) =>
      safesService.updateMember(safeId, memberId, permissions),
    onSuccess: invalidate,
  });
}

export function useRemoveSafeMember(safeId: string) {
  const invalidate = useInvalidateSafes();
  return useMutation({
    mutationFn: (memberId: string) => safesService.removeMember(safeId, memberId),
    onSuccess: invalidate,
  });
}

export function useSafePolicy(safeId: string | undefined) {
  return useQuery({
    queryKey: safesKeys.policy(safeId ?? ''),
    queryFn: async () => (await safesService.policy(safeId as string)).data,
    enabled: !!safeId,
  });
}

export function useSaveSafePolicy(safeId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: ApprovalPolicy) => safesService.savePolicy(safeId, payload),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: safesKeys.policy(safeId) });
      // Accounts show their safe's approval need.
      void qc.invalidateQueries({ queryKey: inventoryKeys.accountsAll() });
    },
  });
}

export function useSafeAudit(safeId: string | undefined, params: PageQuery) {
  return useQuery({
    queryKey: safesKeys.audit(safeId ?? '', params),
    queryFn: () => safesService.audit(safeId as string, params),
    enabled: !!safeId,
    retry: false,
  });
}

export function useSafeAppFetch(safeId: string) {
  return useQuery({
    queryKey: safesKeys.appFetch(safeId),
    queryFn: async () => (await safesService.appFetch(safeId)).data,
    enabled: !!safeId,
  });
}

export function useSaveSafeAppFetch(safeId: string) {
  const invalidate = useInvalidateSafes();
  return useMutation({
    mutationFn: (payload: SafeAppFetch) => safesService.saveAppFetch(safeId, payload),
    onSuccess: invalidate,
  });
}
