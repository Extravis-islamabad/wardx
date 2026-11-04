import { KpiBar, KpiTone, toneIf } from '@/components';
import { useTargetStats } from '@/hooks/useStats';

/** Target counters for the Targets page (GET /targets/stats). */
export function TargetKpis() {
  const { data: s, isLoading: loading } = useTargetStats();
  return (
    <KpiBar
      items={[
        { label: 'Targets', value: s?.total, loading },
        { label: 'Active', value: s?.active, loading },
        { label: 'Inactive', value: s?.inactive, loading },
        { label: 'Platforms', value: s?.platforms, loading },
        {
          label: 'Host key not pinned',
          value: s?.host_key_unpinned,
          loading,
          tone: toneIf(s?.host_key_unpinned, KpiTone.WARNING),
          hint: 'SSH targets never connected to: the first connection pins the key',
        },
        {
          label: 'Key or cert changed',
          value: s?.key_changed,
          loading,
          tone: toneIf(s?.key_changed, KpiTone.DANGER),
          hint: 'The device presented a different key than the pinned one — credentials are withheld',
        },
      ]}
    />
  );
}

export default TargetKpis;
