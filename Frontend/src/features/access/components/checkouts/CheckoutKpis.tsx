import { KpiBar, KpiTone, toneIf } from '@/components';
import { useCheckoutStats } from '@/hooks/useStats';

/** Check-out counters for the Check-outs page (GET /checkouts/stats). */
export function CheckoutKpis() {
  const { data: s, isLoading: loading } = useCheckoutStats();
  return (
    <KpiBar
      items={[
        { label: 'Check-outs', value: s?.total, loading },
        { label: 'Active now', value: s?.active, loading, tone: toneIf(s?.active, KpiTone.SUCCESS) },
        { label: 'Mine, active', value: s?.mine_active, loading },
        { label: 'Returned', value: s?.returned, loading },
        {
          label: 'Expired',
          value: s?.expired,
          loading,
          hint: 'Not checked in before the time ran out; the sweeper closed them',
        },
        { label: 'Revoked', value: s?.revoked, loading, tone: toneIf(s?.revoked, KpiTone.WARNING) },
      ]}
    />
  );
}

export default CheckoutKpis;
