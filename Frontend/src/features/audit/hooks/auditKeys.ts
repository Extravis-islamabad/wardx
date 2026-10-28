import type { PageQuery } from '@/types/api';

/** Audit query-key factory. Re-exported via src/lib/queryKeys.ts. */
export const auditKeys = {
  all: ['audit'] as const,
  events: (params: PageQuery) => ['audit', 'events', params] as const,
};
