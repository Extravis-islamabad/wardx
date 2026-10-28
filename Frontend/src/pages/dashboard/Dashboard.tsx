import { ErrorState, PageShell } from '@/components';
import { useAuth } from '@/context/AuthContext';
import { SummaryTiles } from '@/features/dashboard/components';
import { useDashboardSummary } from '@/features/dashboard/hooks';

export default function Dashboard() {
  const { user } = useAuth();
  const summary = useDashboardSummary();
  return (
    <PageShell title={`Welcome, ${user?.full_name || user?.username || ''}`}>
      {summary.isError ? <ErrorState error={summary.error} onRetry={() => void summary.refetch()} /> : null}
      <SummaryTiles data={summary.data} loading={summary.isLoading} />
    </PageShell>
  );
}
