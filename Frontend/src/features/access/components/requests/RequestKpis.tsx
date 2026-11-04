import { KpiBar, KpiTone, toneIf } from '@/components';
import { useRequestStats } from '@/hooks/useStats';

/** Access-request counters for the Requests page (GET /requests/stats). */
export function RequestKpis() {
  const { data: s, isLoading: loading } = useRequestStats();
  return (
    <KpiBar
      items={[
        { label: 'Requests', value: s?.total, loading },
        {
          label: 'Awaiting me',
          value: s?.awaiting_me,
          loading,
          tone: toneIf(s?.awaiting_me, KpiTone.WARNING),
          hint: 'Requests whose current approval level you can decide',
        },
        { label: 'Pending', value: s?.pending, loading },
        { label: 'Approved, unused', value: s?.approved, loading, tone: toneIf(s?.approved, KpiTone.SUCCESS) },
        { label: 'Used', value: s?.used, loading },
        { label: 'Denied', value: s?.denied, loading },
        { label: 'Expired', value: s?.expired, loading },
      ]}
    />
  );
}

export default RequestKpis;
