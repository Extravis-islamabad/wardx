import { KpiBar, KpiTone, toneIf } from '@/components';
import { useCommandRules } from '@/features/sessions/hooks';

/** Command-rule counters for the Command policy page. */
export function RuleKpis() {
  const rules = useCommandRules();
  const rows = rules.data ?? [];
  const loading = rules.isLoading;
  const active = rows.filter((r) => r.is_active);
  const inactive = rows.length - active.length;

  return (
    <KpiBar
      items={[
        { label: 'Rules', value: rows.length, loading },
        { label: 'Active', value: active.length, loading, tone: toneIf(active.length, KpiTone.SUCCESS) },
        { label: 'Inactive', value: inactive, loading },
        {
          label: 'Everywhere',
          value: active.filter((r) => !r.account_id && !r.target_id && !r.platform).length,
          loading,
          hint: 'Active rules with no account, target or platform scope',
        },
        { label: 'Per platform', value: active.filter((r) => r.platform).length, loading },
        { label: 'Per target', value: active.filter((r) => r.target_id).length, loading },
        { label: 'Per account', value: active.filter((r) => r.account_id).length, loading },
      ]}
    />
  );
}

export default RuleKpis;
