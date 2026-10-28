import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { appsService, type AppInput } from '@/services/provider-services';
import type { PageQuery } from '@/types/api';
import { providerKeys } from './providerKeys';

export function useApps(params: PageQuery, options: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: providerKeys.apps(params),
    queryFn: () => appsService.list(params),
    enabled: options.enabled ?? true,
  });
}

function useInvalidateApps() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: providerKeys.all });
}

/** Resolves with the new app and its client secret, which is shown once. */
export function useCreateApp() {
  const invalidate = useInvalidateApps();
  return useMutation({
    mutationFn: async (payload: AppInput) => (await appsService.create(payload)).data,
    onSuccess: invalidate,
  });
}

export function useUpdateApp() {
  const invalidate = useInvalidateApps();
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: Partial<AppInput> }) => appsService.update(id, payload),
    onSuccess: invalidate,
  });
}

export function useAddAppSecret() {
  const invalidate = useInvalidateApps();
  return useMutation({
    mutationFn: async ({ id, expiresAt }: { id: string; expiresAt: string | null }) =>
      (await appsService.addSecret(id, expiresAt)).data,
    onSuccess: invalidate,
  });
}

export function useRevokeAppSecret() {
  const invalidate = useInvalidateApps();
  return useMutation({
    mutationFn: ({ id, secretId }: { id: string; secretId: string }) => appsService.revokeSecret(id, secretId),
    onSuccess: invalidate,
  });
}

export function useAppFetches(appId: string | undefined, params: PageQuery) {
  return useQuery({
    queryKey: providerKeys.fetches(appId ?? '', params),
    queryFn: () => appsService.fetches(appId as string, params),
    enabled: !!appId,
  });
}
