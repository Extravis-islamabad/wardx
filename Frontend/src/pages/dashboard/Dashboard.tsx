import { ErrorState, PageShell } from '@/components';
import { PERMISSIONS } from '@/constants/enums/permissions';
import { useAuth } from '@/context/AuthContext';
import { AttentionPanel, ClusterPanel, HighAlertsBanner, SummaryTiles } from '@/features/dashboard/components';
import { useDashboardSummary } from '@/features/dashboard/hooks';
import { RotationAttentionPanel } from '@/features/rotation/components';

export default function Dashboard() {
  const { user, canAccess } = useAuth();
  const summary = useDashboardSummary();
  const canSeeAlerts = canAccess({ permission: PERMISSIONS.AUDIT_VIEW });
  const canSeeAttention = canAccess({ permission: [PERMISSIONS.AUDIT_VIEW, PERMISSIONS.SAFES_MANAGE] });
  return (
    <PageShell title="Dashboard" description={`Signed in as ${user?.full_name || user?.username || ''}`}>
      {summary.isError ? <ErrorState error={summary.error} onRetry={() => void summary.refetch()} /> : null}
      <SummaryTiles data={summary.data} loading={summary.isLoading} />
      {canSeeAlerts && (
        <HighAlertsBanner canAcknowledge={canAccess({ permission: PERMISSIONS.ALERTS_ACKNOWLEDGE })} />
      )}
      {/* Panels side by side on wide screens; each hides itself when there is nothing to show. */}
      <div className="grid grid-cols-1 items-start gap-2 xl:grid-cols-2">
        {canSeeAttention && <AttentionPanel />}
        {canAccess({ permission: PERMISSIONS.INVENTORY_VIEW }) && <RotationAttentionPanel />}
        {canAccess({ permission: PERMISSIONS.CLUSTER_VIEW }) && <ClusterPanel />}
      </div>
    </PageShell>
  );
}
