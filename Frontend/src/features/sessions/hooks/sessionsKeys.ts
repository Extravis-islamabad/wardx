import type { PageQuery } from '@/types/api';

/** Sessions (gateway sessions + command policy) query-key factory. Re-exported via src/lib/queryKeys.ts. */
export const sessionsKeys = {
  all: ['sessions'] as const,
  listAll: () => ['sessions', 'list'] as const,
  list: (params: PageQuery) => ['sessions', 'list', params] as const,
  commands: (sessionId: string) => ['sessions', 'commands', sessionId] as const,
  recording: (sessionId: string) => ['sessions', 'recording', sessionId] as const,
  gateway: () => ['sessions', 'gateway-info'] as const,
  commandRules: () => ['sessions', 'command-rules'] as const,
};
