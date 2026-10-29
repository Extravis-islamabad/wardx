/** Dashboard query-key factory. Re-exported via src/lib/queryKeys.ts. */
export const dashboardKeys = {
  all: ['dashboard'] as const,
  summary: () => ['dashboard', 'summary'] as const,
  attention: () => ['dashboard', 'attention'] as const,
  alerts: () => ['dashboard', 'alerts'] as const,
  cluster: () => ['dashboard', 'cluster'] as const,
};
