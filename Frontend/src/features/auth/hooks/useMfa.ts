import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { mfaService } from '@/services/auth-services';
import { authKeys } from './authKeys';

export function useMfaStatus() {
  return useQuery({
    queryKey: authKeys.mfa(),
    queryFn: async () => (await mfaService.status()).data,
  });
}

export function useStartMfaSetup() {
  return useMutation({
    mutationFn: async () => (await mfaService.setup()).data,
  });
}

export function useEnableMfa() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (code: string) => (await mfaService.enable(code)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: authKeys.mfa() }),
  });
}

export function useDisableMfa() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (code: string) => mfaService.disable(code),
    onSuccess: () => qc.invalidateQueries({ queryKey: authKeys.mfa() }),
  });
}

export function useRegenerateRecoveryCodes() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (code: string) => (await mfaService.regenerateRecoveryCodes(code)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: authKeys.mfa() }),
  });
}
