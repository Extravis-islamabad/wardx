import type { PageQuery } from '@/types/api';

/** Identity (users + directory) query-key factory. Re-exported via src/lib/queryKeys.ts. */
export const identityKeys = {
  all: ['identity'] as const,
  usersAll: () => ['identity', 'users'] as const,
  users: (params: PageQuery) => ['identity', 'users', params] as const,
  directory: () => ['identity', 'directory'] as const,
};
