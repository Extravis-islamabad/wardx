import { useQuery } from '@tanstack/react-query';
import { accessKeys } from '@/features/access/hooks/accessKeys';
import { auditKeys } from '@/features/audit/hooks/auditKeys';
import { identityKeys } from '@/features/identity/hooks/identityKeys';
import { inventoryKeys } from '@/features/inventory/hooks/inventoryKeys';
import { providerKeys } from '@/features/provider/hooks/providerKeys';
import { rotationKeys } from '@/features/rotation/hooks/rotationKeys';
import { safesKeys } from '@/features/safes/hooks/safesKeys';
import { sessionsKeys } from '@/features/sessions/hooks/sessionsKeys';
import { statsService } from '@/services/stats-services';

/**
 * Per-page KPI queries. Each key sits under its list's key prefix, so a mutation that
 * invalidates the list (e.g. `inventoryKeys.accountsAll()`) refreshes its KPIs too.
 */
const STATS_POLL_MS = 30_000;

const poll = { refetchInterval: STATS_POLL_MS } as const;

export const useAccountStats = () =>
  useQuery({ queryKey: [...inventoryKeys.accountsAll(), 'stats'], queryFn: statsService.accounts, ...poll });

export const useTargetStats = () =>
  useQuery({ queryKey: [...inventoryKeys.targetsAll(), 'stats'], queryFn: statsService.targets, ...poll });

export const useSafeStats = () =>
  useQuery({ queryKey: [...safesKeys.listAll(), 'stats'], queryFn: statsService.safes, ...poll });

export const useUserStats = () =>
  useQuery({ queryKey: [...identityKeys.usersAll(), 'stats'], queryFn: statsService.users, ...poll });

export const useAppStats = () =>
  useQuery({ queryKey: [...providerKeys.appsAll(), 'stats'], queryFn: statsService.apps, ...poll });

export const useCheckoutStats = () =>
  useQuery({ queryKey: [...accessKeys.checkoutsAll(), 'stats'], queryFn: statsService.checkouts, ...poll });

export const useRequestStats = () =>
  useQuery({ queryKey: [...accessKeys.requestsAll(), 'stats'], queryFn: statsService.requests, ...poll });

export const useSessionStats = () =>
  useQuery({ queryKey: [...sessionsKeys.listAll(), 'stats'], queryFn: statsService.sessions, ...poll });

export const useRotationStats = () =>
  useQuery({ queryKey: [...rotationKeys.jobsAll(), 'stats'], queryFn: statsService.rotationJobs, ...poll });

export const useAuditStats = () =>
  useQuery({ queryKey: [...auditKeys.all, 'stats'], queryFn: statsService.audit, ...poll });
