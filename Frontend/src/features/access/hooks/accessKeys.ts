import type { PageQuery } from '@/types/api';

/** Access (requests + check-outs) query-key factory. Re-exported via src/lib/queryKeys.ts. */
export const accessKeys = {
  all: ['access'] as const,
  requestsAll: () => ['access', 'requests'] as const,
  requests: (params: PageQuery) => ['access', 'requests', params] as const,
  checkoutsAll: () => ['access', 'checkouts'] as const,
  checkouts: (params: PageQuery) => ['access', 'checkouts', params] as const,
};
