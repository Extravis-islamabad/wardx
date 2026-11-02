import { KpiBar, KpiTone, toneIf } from '@/components';
import { useAppStats } from '@/hooks/useStats';

/** Application-identity counters for the Application identities page (GET /apps/stats). */
export function AppKpis() {
  const { data: s, isLoading: loading } = useAppStats();
  return (
    <KpiBar
      items={[
        { label: 'Applications', value: s?.total, loading },
        { label: 'Enabled', value: s?.enabled, loading },
        { label: 'Disabled', value: s?.disabled, loading },
        { label: 'Active secrets', value: s?.active_secrets, loading },
        {
          label: 'Secrets expiring',
          value: s?.secrets_expiring,
          loading,
          tone: toneIf(s?.secrets_expiring, KpiTone.WARNING),
          hint: 'Active secrets that expire within 30 days',
        },
        {
          label: 'Enabled, unusable',
          value: s?.enabled_unusable,
          loading,
          tone: toneIf(s?.enabled_unusable, KpiTone.DANGER),
          hint: 'Enabled, but missing an IP allowlist or an active secret: their fetches fail',
        },
      ]}
    />
  );
}

export default AppKpis;
