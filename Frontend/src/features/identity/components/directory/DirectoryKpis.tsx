import { KpiBar, KpiTone } from '@/components';
import { SyncStatus } from '@/constants/enums/identity';
import { useDirectoryConfig } from '@/features/identity/hooks';
import { fmtTime } from '@/utils/format';

/** Directory sign-in and sync counters for the Directory page. */
export function DirectoryKpis() {
  const config = useDirectoryConfig();
  const c = config.data;
  const loading = config.isLoading;
  const last = c?.last_sync_summary;
  const syncFailed = c?.last_sync_status && c.last_sync_status !== SyncStatus.OK;
  const disabledLast = last?.disabled?.length ?? 0;

  return (
    <KpiBar
      items={[
        {
          label: 'Directory sign-in',
          value: c?.enabled ? 'On' : 'Off',
          loading,
          tone: c?.enabled ? KpiTone.SUCCESS : KpiTone.DEFAULT,
        },
        {
          label: 'Server',
          value: c?.reachable == null ? 'Unchecked' : c.reachable ? 'Reachable' : 'Unreachable',
          loading,
          tone: c?.reachable === false ? KpiTone.DANGER : c?.reachable ? KpiTone.SUCCESS : KpiTone.DEFAULT,
          hint: c?.reachability_checked_at ? `Checked ${fmtTime(c.reachability_checked_at)}` : undefined,
        },
        { label: 'Group mappings', value: c?.role_mappings?.length ?? 0, loading },
        {
          label: 'Sync every',
          value: c?.enabled && c.sync_interval_minutes ? `${c.sync_interval_minutes} min` : 'Off',
          loading,
        },
        {
          label: 'Last sync',
          value: c?.last_sync_status ?? 'Never',
          loading,
          tone: syncFailed ? KpiTone.WARNING : KpiTone.DEFAULT,
          hint: c?.last_sync_at ? fmtTime(c.last_sync_at) : undefined,
        },
        { label: 'Users checked', value: last?.checked ?? 0, loading, hint: 'In the last sync run' },
        {
          label: 'Disabled by sync',
          value: disabledLast,
          loading,
          tone: disabledLast ? KpiTone.WARNING : KpiTone.DEFAULT,
          hint: 'In the last sync run',
        },
      ]}
    />
  );
}

export default DirectoryKpis;
