import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { gatewayService, sessionsService } from '@/services/sessions-services';
import type { PageQuery } from '@/types/api';
import { sessionsKeys } from './sessionsKeys';

const SESSIONS_POLL_MS = 5_000;
const LIVE_COMMANDS_POLL_MS = 3_000;

export function useSessions(params: PageQuery) {
  return useQuery({
    queryKey: sessionsKeys.list(params),
    queryFn: () => sessionsService.list(params),
    refetchInterval: SESSIONS_POLL_MS,
  });
}

/** Commands typed in a session; polled while the session is still live. */
export function useSessionCommands(sessionId: string | undefined, live: boolean) {
  return useQuery({
    queryKey: sessionsKeys.commands(sessionId ?? ''),
    queryFn: async () => (await sessionsService.commands(sessionId as string)).data,
    enabled: Boolean(sessionId),
    refetchInterval: live ? LIVE_COMMANDS_POLL_MS : false,
  });
}

/** The cast is fetched with the user's token, never by URL; a recording never changes. */
export function useSessionRecording(sessionId: string) {
  return useQuery({
    queryKey: sessionsKeys.recording(sessionId),
    queryFn: () => sessionsService.recording(sessionId),
    staleTime: Infinity,
    retry: false,
  });
}

export function useGatewayInfo() {
  return useQuery({
    queryKey: sessionsKeys.gateway(),
    queryFn: async () => (await gatewayService.info()).data,
  });
}

export function useTerminateSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => sessionsService.terminate(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: sessionsKeys.listAll() }),
  });
}
