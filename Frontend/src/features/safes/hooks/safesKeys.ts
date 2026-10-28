import type { PageQuery } from '@/types/api';

/** Safes query-key factory. Re-exported via src/lib/queryKeys.ts. */
export const safesKeys = {
  all: ['safes'] as const,
  listAll: () => ['safes', 'list'] as const,
  list: (params: PageQuery) => ['safes', 'list', params] as const,
  members: (safeId: string) => ['safes', 'members', safeId] as const,
  health: () => ['safes', 'health'] as const,
};
