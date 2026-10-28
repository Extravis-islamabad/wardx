/** Auth query-key factory. Re-exported via src/lib/queryKeys.ts. */
export const authKeys = {
  all: ['auth'] as const,
  me: () => ['auth', 'me'] as const,
  mfa: () => ['auth', 'mfa'] as const,
};
