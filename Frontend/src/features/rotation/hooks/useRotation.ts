import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { inventoryKeys } from '@/features/inventory/hooks/inventoryKeys';
import {
  rotationService,
  type Resolution,
  type RotationOperation,
  type SafeRotationPolicy,
} from '@/services/rotation-services';
import type { PageQuery } from '@/types/api';
import { rotationKeys } from './rotationKeys';

/** Jobs move on in the background; open views poll while something is in flight. */
const LIVE_MS = 5000;

export function useAccountRotation(accountId: string | undefined) {
  return useQuery({
    queryKey: rotationKeys.account(accountId ?? ''),
    queryFn: async () => (await rotationService.account(accountId as string)).data,
    enabled: !!accountId,
    refetchInterval: (q) => (q.state.data?.open_job ? LIVE_MS : false),
  });
}

export function useRotationJobs(params: PageQuery) {
  return useQuery({
    queryKey: rotationKeys.jobs(params),
    queryFn: () => rotationService.jobs(params),
    refetchInterval: LIVE_MS,
  });
}

export function useRotationJob(jobId: string | undefined) {
  return useQuery({
    queryKey: rotationKeys.job(jobId ?? ''),
    queryFn: async () => (await rotationService.job(jobId as string)).data,
    enabled: !!jobId,
  });
}

export function useRotationAttention(enabled = true) {
  return useQuery({
    queryKey: rotationKeys.attention(),
    queryFn: async () => (await rotationService.attention()).data,
    enabled,
  });
}

function useInvalidateRotation() {
  const qc = useQueryClient();
  return () => {
    void qc.invalidateQueries({ queryKey: rotationKeys.all });
    void qc.invalidateQueries({ queryKey: inventoryKeys.accountsAll() });
  };
}

export function useRequestRotation(accountId: string) {
  const invalidate = useInvalidateRotation();
  return useMutation({
    mutationFn: ({ op, reason, dryRun }: { op: RotationOperation; reason: string; dryRun?: boolean }) =>
      rotationService.request(accountId, op, { reason, dry_run: dryRun }),
    onSuccess: invalidate,
  });
}

export function useConfirmRotation(accountId: string) {
  const invalidate = useInvalidateRotation();
  return useMutation({
    mutationFn: (reason: string) => rotationService.confirm(accountId, reason),
    onSuccess: invalidate,
  });
}

export function useResolveRotation() {
  const invalidate = useInvalidateRotation();
  return useMutation({
    mutationFn: ({ jobId, ...body }: { jobId: string; action: Resolution; note: string; secret?: string }) =>
      rotationService.resolve(jobId, body),
    onSuccess: invalidate,
  });
}

export function useSafeRotationPolicy(safeId: string | undefined) {
  return useQuery({
    queryKey: rotationKeys.safePolicy(safeId ?? ''),
    queryFn: async () => (await rotationService.safePolicy(safeId as string)).data,
    enabled: !!safeId,
  });
}

export function useSaveSafeRotationPolicy(safeId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: SafeRotationPolicy) => rotationService.saveSafePolicy(safeId, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: rotationKeys.all }),
  });
}
