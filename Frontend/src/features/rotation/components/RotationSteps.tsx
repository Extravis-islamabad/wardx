import { Collapse, Empty, Spin, Timeline, Typography } from 'antd';
import { StatusTag } from '@/components';
import { StatusVariant } from '@/constants/enums/status';
import { useRotationJob } from '@/features/rotation/hooks';
import type { RotationStep } from '@/services/rotation-services';
import { fmtTime } from '@/utils/format';

const OUTCOME_VARIANT: Record<string, StatusVariant> = {
  ok: StatusVariant.SUCCESS,
  auth_failed: StatusVariant.WARNING,
  rejected_by_device: StatusVariant.DANGER,
  unreachable: StatusVariant.WARNING,
  host_key_mismatch: StatusVariant.DANGER,
  ambiguous: StatusVariant.WARNING,
  channel_unavailable: StatusVariant.DANGER,
  refused: StatusVariant.DANGER,
};

const color = (s: RotationStep) => {
  if (s.step === 'verify_negative') return s.outcome === 'auth_failed' ? 'green' : 'red';
  return s.outcome === 'ok' ? 'green' : s.outcome === 'unreachable' ? 'gray' : 'red';
};

/** A job's step timeline with each step's redacted device transcript. */
export function RotationSteps({ jobId }: { jobId: string }) {
  const job = useRotationJob(jobId);
  if (job.isLoading) return <Spin size="small" />;
  const steps = job.data?.steps ?? [];
  if (!steps.length) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No device steps yet" />;
  return (
    <Timeline
      items={steps.map((s, i) => ({
        key: `${s.step}-${i}`,
        color: color(s),
        children: (
          <>
            <Typography.Text strong>{s.step.replace(/_/g, ' ')}</Typography.Text>{' '}
            <StatusTag
              label={s.step === 'verify_negative' ? (s.outcome === 'auth_failed' ? 'wrong password refused' : s.outcome) : s.outcome}
              variant={OUTCOME_VARIANT[s.outcome] ?? StatusVariant.OUTLINE}
            />
            {s.secret_version ? <Typography.Text type="secondary"> v{s.secret_version}</Typography.Text> : null}
            {s.channel ? <Typography.Text type="secondary"> · via {s.channel}</Typography.Text> : null}
            <Typography.Text type="secondary"> · {fmtTime(s.finished_at)}</Typography.Text>
            {s.detail && <div className="text-xs">{s.detail}</div>}
            {s.transcript && (
              <Collapse
                size="small"
                ghost
                items={[
                  {
                    key: 't',
                    label: 'Transcript (secrets shown as ****)',
                    children: <pre className="max-h-64 overflow-auto whitespace-pre-wrap text-xs">{s.transcript}</pre>,
                  },
                ]}
              />
            )}
          </>
        ),
      }))}
    />
  );
}

export default RotationSteps;
