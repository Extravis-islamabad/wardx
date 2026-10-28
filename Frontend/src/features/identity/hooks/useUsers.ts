import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { usersService, type UserCreatePayload, type UserUpdatePayload } from '@/services/identity-services';
import type { PageQuery } from '@/types/api';
import { identityKeys } from './identityKeys';

export function useUsers(params: PageQuery, options: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: identityKeys.users(params),
    queryFn: () => usersService.list(params),
    enabled: options.enabled ?? true,
  });
}

export function useCreateUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: UserCreatePayload) => usersService.create(payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: identityKeys.usersAll() }),
  });
}

export function useUpdateUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: UserUpdatePayload }) => usersService.update(id, payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: identityKeys.usersAll() }),
  });
}

/** For a lost phone: their sessions end and they re-enrol at next sign-in (break-glass is revoked). */
export function useResetUserMfa() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => usersService.resetMfa(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: identityKeys.usersAll() }),
  });
}

export function useSetEmergencyAccess() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, grant }: { id: string; grant: boolean }) =>
      grant ? usersService.grantEmergency(id) : usersService.revokeEmergency(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: identityKeys.usersAll() }),
  });
}
