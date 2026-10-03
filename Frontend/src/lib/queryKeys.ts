import type { PageQuery } from '@/types/api';

export const queryKeys = {
  me: ['auth', 'me'] as const,
  dashboard: ['dashboard'] as const,
  targets: { all: ['targets'] as const, list: (q: PageQuery) => ['targets', 'list', q] as const },
  accounts: { all: ['accounts'] as const, list: (q: PageQuery) => ['accounts', 'list', q] as const },
  requests: { all: ['requests'] as const, list: (q: PageQuery) => ['requests', 'list', q] as const },
  checkouts: { all: ['checkouts'] as const, list: (q: PageQuery) => ['checkouts', 'list', q] as const },
  audit: { all: ['audit'] as const, list: (q: PageQuery) => ['audit', 'list', q] as const },
  users: { all: ['users'] as const, list: (q: PageQuery) => ['users', 'list', q] as const },
};
