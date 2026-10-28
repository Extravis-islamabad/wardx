import type { PageQuery } from '@/types/api';

/** Credential provider (application identities) query-key factory. Re-exported via src/lib/queryKeys.ts. */
export const providerKeys = {
  all: ['provider'] as const,
  appsAll: () => ['provider', 'apps'] as const,
  apps: (params: PageQuery) => ['provider', 'apps', params] as const,
  fetches: (appId: string, params: PageQuery) => ['provider', 'fetches', appId, params] as const,
};
