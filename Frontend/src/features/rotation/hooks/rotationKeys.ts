import type { PageQuery } from '@/types/api';

/** Rotation query-key factory. */
export const rotationKeys = {
  all: ['rotation'] as const,
  account: (accountId: string) => ['rotation', 'account', accountId] as const,
  jobsAll: () => ['rotation', 'jobs'] as const,
  jobs: (params: PageQuery) => ['rotation', 'jobs', params] as const,
  job: (jobId: string) => ['rotation', 'job', jobId] as const,
  attention: () => ['rotation', 'attention'] as const,
  safePolicy: (safeId: string) => ['rotation', 'safe-policy', safeId] as const,
};
