import { KpiBar, KpiTone, toneIf } from '@/components';
import { useUserStats } from '@/hooks/useStats';

/** User counters for the Users page (GET /users/stats). */
export function UserKpis() {
  const { data: s, isLoading: loading } = useUserStats();
  return (
    <KpiBar
      items={[
        { label: 'Users', value: s?.total, loading },
        { label: 'Active', value: s?.active, loading },
        { label: 'Disabled', value: s?.disabled, loading },
        { label: 'Admins', value: s?.admins, loading, hint: 'Active administrators' },
        { label: 'Approvers', value: s?.approvers, loading, hint: 'Active approvers' },
        { label: 'Directory users', value: s?.directory, loading, hint: 'Sign in with LDAP / Active Directory' },
        { label: 'MFA on', value: s?.mfa_enabled, loading },
        {
          label: 'Admins without MFA',
          value: s?.admins_without_mfa,
          loading,
          tone: toneIf(s?.admins_without_mfa, KpiTone.DANGER),
          hint: 'Active administrators who sign in with a password alone',
        },
        {
          label: 'Locked out',
          value: s?.locked,
          loading,
          tone: toneIf(s?.locked, KpiTone.WARNING),
          hint: 'Too many failed sign-ins',
        },
      ]}
    />
  );
}

export default UserKpis;
