import { ErrorState, PageShell } from '@/components';
import { PERMISSIONS } from '@/constants/enums/permissions';
import { useAuth } from '@/context/AuthContext';
import { AttentionPanel, HighAlertsBanner, SummaryTiles } from '@/features/dashboard/components';
import { useDashboardSummary } from '@/features/dashboard/hooks';

export default function Dashboard() {
  const { user, canAccess } = useAuth();
  const summary = useDashboardSummary();
  const canSeeAlerts = canAccess({ permission: PERMISSIONS.AUDIT_VIEW });
  const canSeeAttention = canAccess({ permission: [PERMISSIONS.AUDIT_VIEW, PERMISSIONS.SAFES_MANAGE] });
  return (
    <PageShell title={`Welcome, ${user?.full_name || user?.username || ''}`}>
      {canSeeAlerts && (
        <HighAlertsBanner canAcknowledge={canAccess({ permission: PERMISSIONS.ALERTS_ACKNOWLEDGE })} />
      )}
      {canSeeAttention && <AttentionPanel />}
      {summary.isError ? <ErrorState error={summary.error} onRetry={() => void summary.refetch()} /> : null}
      <SummaryTiles data={summary.data} loading={summary.isLoading} />
    </PageShell>
  );
}
