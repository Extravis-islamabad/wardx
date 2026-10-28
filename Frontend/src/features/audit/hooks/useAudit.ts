import { useMutation, useQuery } from '@tanstack/react-query';
import { auditService } from '@/services/audit-services';
import type { PageQuery } from '@/types/api';
import { auditKeys } from './auditKeys';

export function useAuditEvents(params: PageQuery) {
  return useQuery({
    queryKey: auditKeys.events(params),
    queryFn: () => auditService.list(params),
  });
}

/** Re-walks the hash chain server-side. */
export function useVerifyAuditChain() {
  return useMutation({
    mutationFn: async () => (await auditService.verify()).data,
  });
}
