import type { PageQuery } from '@/types/api';

/** Notification query-key factory. Re-exported via src/lib/queryKeys.ts. */
export const notifyKeys = {
  all: ['notify'] as const,
  unread: () => ['notify', 'unread'] as const,
  list: (params: PageQuery) => ['notify', 'list', params] as const,
};
