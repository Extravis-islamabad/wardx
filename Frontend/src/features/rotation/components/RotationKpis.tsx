import { KpiBar, KpiTone, toneIf } from '@/components';
import { useRotationStats } from '@/hooks/useStats';

/** Rotation-job counters for the Rotation page (GET /rotation/jobs/stats). */
export function RotationKpis() {
  const { data: s, isLoading: loading } = useRotationStats();
  const n = (...statuses: string[]) =>
    s ? statuses.reduce((sum, st) => sum + (s.by_status[st] ?? 0), 0) : undefined;
  const failed = n('failed');
  const unverified = n('changed_unverified');
  const attention = n('needs_attention');
  return (
    <KpiBar
      items={[
        { label: 'Jobs', value: s?.total, loading },
        { label: 'Queued', value: n('pending', 'waiting_release'), loading, hint: 'Waiting to run, or for a check-in' },
        {
          label: 'In progress',
          value: n('running', 'candidate_stored', 'device_changed', 'persisted'),
          loading,
        },
        { label: 'Succeeded', value: n('succeeded', 'resolved'), loading },
        { label: 'Failed', value: failed, loading, tone: toneIf(failed, KpiTone.WARNING) },
        {
          label: 'Changed, unverified',
          value: unverified,
          loading,
          tone: toneIf(unverified, KpiTone.WARNING),
          hint: 'The device took a new password that WardX could not log in with yet',
        },
        {
          label: 'Needs attention',
          value: attention,
          loading,
          tone: toneIf(attention, KpiTone.DANGER),
          hint: 'An operator has to resolve these',
        },
      ]}
    />
  );
}

export default RotationKpis;
