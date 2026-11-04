import { KpiBar, KpiTone, toneIf, type KpiItem } from '@/components';
import { useSafeStats } from '@/hooks/useStats';

/** Safe counters for the Safes page (GET /safes/stats). Health only for safes.manage. */
export function SafeKpis() {
  const { data: s, isLoading: loading } = useSafeStats();
  const health: KpiItem[] =
    s && s.break_glass_only !== null
      ? [
          {
            label: 'Break-glass only',
            value: s.break_glass_only,
            tone: toneIf(s.break_glass_only, KpiTone.WARNING),
            hint: 'Only directory groups: if the directory is down, only break-glass reaches it',
          },
          {
            label: 'Unreachable',
            value: s.unreachable,
            tone: toneIf(s.unreachable, KpiTone.DANGER),
            hint: 'A directory outage would lock these safes',
          },
        ]
      : [];
  return (
    <KpiBar
      items={[
        { label: 'Safes', value: s?.total, loading },
        { label: 'Accounts held', value: s?.accounts, loading },
        { label: 'Memberships', value: s?.memberships, loading },
        { label: 'Approval required', value: s?.approval_required, loading, hint: 'Check-outs need an approved request' },
        { label: 'App fetch allowed', value: s?.app_fetch_allowed, loading },
        ...health,
      ]}
    />
  );
}

export default SafeKpis;
