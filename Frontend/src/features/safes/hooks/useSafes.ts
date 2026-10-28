import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { safesService, type SafeInput, type SafeMemberInput } from '@/services/safes-services';
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
