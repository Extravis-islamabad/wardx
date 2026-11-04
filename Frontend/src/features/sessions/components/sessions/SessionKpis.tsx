import { KpiBar, KpiTone, toneIf } from '@/components';
import { useSessionStats } from '@/hooks/useStats';

/** Gateway-session counters for the Sessions page (GET /sessions/stats). */
export function SessionKpis() {
  const { data: s, isLoading: loading } = useSessionStats();
  return (
    <KpiBar
      items={[
        { label: 'Sessions', value: s?.total, loading },
        { label: 'Live now', value: s?.active, loading, tone: toneIf(s?.active, KpiTone.SUCCESS) },
        { label: 'Mine', value: s?.mine, loading },
        { label: 'Closed', value: s?.closed, loading },
        {
          label: 'Terminated',
          value: s?.terminated,
          loading,
          tone: toneIf(s?.terminated, KpiTone.WARNING),
          hint: 'Killed by an admin or by directory sync',
        },
        {
          label: 'Failed',
          value: s?.failed,
          loading,
          tone: toneIf(s?.failed, KpiTone.DANGER),
          hint: 'Could not reach the target or sign in to it',
        },
      ]}
    />
  );
}

export default SessionKpis;
