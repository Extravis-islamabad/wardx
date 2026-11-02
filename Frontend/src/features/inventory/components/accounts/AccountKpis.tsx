import { KpiBar, KpiTone, toneIf } from '@/components';
import { useAccountStats } from '@/hooks/useStats';

/** Privileged-account counters for the Accounts page (GET /accounts/stats). */
export function AccountKpis() {
  const { data: s, isLoading: loading } = useAccountStats();
  return (
    <KpiBar
      items={[
        { label: 'Accounts', value: s?.total, loading },
        { label: 'In use now', value: s?.in_use, loading, hint: 'Accounts with an active check-out' },
        { label: 'Need approval', value: s?.requires_approval, loading, hint: "Their safe's policy requires approval" },
        { label: 'Exclusive', value: s?.exclusive, loading, hint: 'One holder at a time' },
        {
          label: 'Without a secret',
          value: s?.without_secret,
          loading,
          tone: toneIf(s?.without_secret, KpiTone.WARNING),
        },
        {
          label: 'Out of sync',
          value: s?.out_of_sync,
          loading,
          tone: toneIf(s?.out_of_sync, KpiTone.WARNING),
          hint: 'The vaulted password may not match the device',
        },
        {
          label: 'At risk',
          value: s?.at_risk,
          loading,
          tone: toneIf(s?.at_risk, KpiTone.DANGER),
          hint: 'Flagged by a risk check, e.g. an empty password',
        },
      ]}
    />
  );
}

export default AccountKpis;
