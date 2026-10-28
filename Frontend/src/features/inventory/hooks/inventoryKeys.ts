import type { PageQuery } from '@/types/api';

/** Inventory (targets + accounts) query-key factory. Re-exported via src/lib/queryKeys.ts. */
export const inventoryKeys = {
  all: ['inventory'] as const,
  targetsAll: () => ['inventory', 'targets'] as const,
  targets: (params: PageQuery) => ['inventory', 'targets', params] as const,
  accountsAll: () => ['inventory', 'accounts'] as const,
  accounts: (params: PageQuery) => ['inventory', 'accounts', params] as const,
};
