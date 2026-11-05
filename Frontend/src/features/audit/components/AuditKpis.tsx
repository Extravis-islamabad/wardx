import { KpiBar, KpiTone, toneIf } from '@/components';
import { useAuditStats } from '@/hooks/useStats';

/** Audit-trail counters for the Audit page (GET /audit/stats). */
export function AuditKpis() {
  const { data: s, isLoading: loading } = useAuditStats();
  return (
    <KpiBar
      items={[
        { label: 'Events', value: s?.total, loading },
        { label: 'Last 24 h', value: s?.last_24h, loading },
        { label: 'Last 7 days', value: s?.last_7d, loading },
        { label: 'Sign-ins, 24 h', value: s?.logins_24h, loading, hint: 'Successful sign-ins' },
        { label: 'Reveals, 24 h', value: s?.reveals_24h, loading, hint: 'Credentials shown in the console' },
        {
          label: 'Break-glass, 7 d',
          value: s?.emergency_reveals_7d,
          loading,
          tone: toneIf(s?.emergency_reveals_7d, KpiTone.DANGER),
          hint: 'Emergency reveals that bypassed approval',
        },
        {
          label: 'Blocked cmds, 7 d',
          value: s?.blocked_commands_7d,
          loading,
          tone: toneIf(s?.blocked_commands_7d, KpiTone.WARNING),
          hint: 'Commands erased by a command-policy rule',
        },
      ]}
    />
  );
}

export default AuditKpis;
