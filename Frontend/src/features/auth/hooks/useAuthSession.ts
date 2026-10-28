import { useQuery } from '@tanstack/react-query';
import { authService, mfaService } from '@/services/auth-services';
import { authKeys } from './authKeys';

const SESSION_STALE_MS = 60_000;

/** The signed-in user; `retry: false` so an expired session falls straight through to sign-in. */
export function useMe(enabled: boolean) {
  return useQuery({
    queryKey: authKeys.me(),
    queryFn: async () => (await authService.me()).data,
    enabled,
    retry: false,
    staleTime: SESSION_STALE_MS,
  });
}

/** The session's MFA state, read by the auth context to gate on enrolment. */
export function useSessionMfaStatus(enabled: boolean) {
  return useQuery({
    queryKey: authKeys.mfa(),
    queryFn: async () => (await mfaService.status()).data,
    enabled,
    retry: false,
    staleTime: SESSION_STALE_MS,
  });
}
