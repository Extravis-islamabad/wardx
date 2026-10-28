import { Alert } from 'antd';
import { AuditTable } from '@/features/audit/components';
import { useSafeAudit } from '@/features/safes/hooks';
import { usePagination } from '@/hooks';
import { apiErrorStatus } from '@/utils/notifyApiError';

/** Audit events for the safe, its accounts and their requests and check-outs (view_audit). */
export function SafeAuditTab({ safeId }: { safeId: string }) {
  const { page, page_size, paginationFor } = usePagination();
  const events = useSafeAudit(safeId, { page, page_size });
  if (apiErrorStatus(events.error) === 403) {
    return <Alert type="info" showIcon title="You need 'view_audit' on this safe to read its audit trail." />;
  }
  return <AuditTable query={events} pagination={paginationFor(events.data?.total)} />;
}

export default SafeAuditTab;
