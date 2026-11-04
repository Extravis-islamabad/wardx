import { KpiBar, KpiTone, toneIf } from '@/components';
import { ROUTES } from '@/constants/enums/routes';
import type { DashboardSummary } from '@/services/dashboard-services';

/** The dashboard KPI strip: one dense row of counters, each a link to its list. */
export function SummaryTiles({ data, loading }: { data?: DashboardSummary; loading: boolean }) {
  return (
    <KpiBar
      items={[
        { label: 'My check-outs', value: data?.my_active_checkouts, loading, to: ROUTES.CHECKOUTS },
        { label: 'My open requests', value: data?.my_open_requests, loading, to: ROUTES.REQUESTS },
        {
          label: 'Pending approvals',
          value: data?.pending_requests,
          loading,
          to: ROUTES.REQUESTS,
          tone: toneIf(data?.pending_requests, KpiTone.WARNING),
        },
        { label: 'Active check-outs', value: data?.active_checkouts, loading, to: ROUTES.CHECKOUTS },
        { label: 'Targets', value: data?.targets, loading, to: ROUTES.TARGETS },
        { label: 'Privileged accounts', value: data?.accounts, loading, to: ROUTES.ACCOUNTS },
        {
          label: 'Accounts without a secret',
          value: data?.accounts_without_secret,
          loading,
          to: ROUTES.ACCOUNTS,
          tone: toneIf(data?.accounts_without_secret, KpiTone.WARNING),
        },
      ]}
    />
  );
}

export default SummaryTiles;
