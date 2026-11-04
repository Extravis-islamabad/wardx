import { KpiBar, KpiTone } from '@/components';
import { AuthSource } from '@/constants/enums/auth';
import { useAuth } from '@/context/AuthContext';
import { useMfaStatus } from '@/features/auth/hooks';
import { fromNow } from '@/utils/format';

const LOW_RECOVERY_CODES = 3;

/** The signed-in user's own security posture, for the Security page. */
export function SecurityKpis() {
  const { user } = useAuth();
  const mfa = useMfaStatus();
  const s = mfa.data;
  const loading = mfa.isLoading;
  const codes = s?.recovery_codes_left ?? 0;

  return (
    <KpiBar
      items={[
        {
          label: 'Two-step sign-in',
          value: s ? (s.enabled ? 'On' : 'Off') : undefined,
          loading,
          tone: s?.enabled ? KpiTone.SUCCESS : s?.required ? KpiTone.DANGER : KpiTone.WARNING,
        },
        { label: 'Required for role', value: s ? (s.required ? 'Yes' : 'No') : undefined, loading },
        {
          label: 'Recovery codes left',
          value: s?.enabled ? codes : '—',
          loading,
          tone: s?.enabled && codes <= LOW_RECOVERY_CODES ? KpiTone.WARNING : KpiTone.DEFAULT,
        },
        { label: 'Role', value: user?.role },
        { label: 'Signs in with', value: user?.auth_source === AuthSource.LDAP ? 'Directory' : 'Local' },
        {
          label: 'Last sign-in',
          value: fromNow(user?.last_login_at),
        },
      ]}
    />
  );
}

export default SecurityKpis;
