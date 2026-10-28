import { Space, Tooltip, Typography, type TablePaginationConfig, type TableProps } from 'antd';
import { Button, DataTable, StatusTag } from '@/components';
import { StatusVariant } from '@/constants/enums/status';
import { JOB_STATUS_VARIANT, REASON_LABEL } from '@/features/rotation/constants';
import type { RotationJob } from '@/services/rotation-services';
import { fmtTime, fromNow } from '@/utils/format';
import { RotationSteps } from './RotationSteps';

interface RotationJobsTableProps {
  jobs: RotationJob[] | undefined;
  loading?: boolean;
  pagination?: TablePaginationConfig | false;
  /** Show the account column (the jobs page; not inside an account's tab). */
  showAccount?: boolean;
  onResolve?: (job: RotationJob) => void;
}

/** Rotation jobs, each expandable to its step timeline and redacted transcript. */
export function RotationJobsTable({ jobs, loading, pagination = false, showAccount, onResolve }: RotationJobsTableProps) {
  const columns: TableProps<RotationJob>['columns'] = [
    ...(showAccount
      ? [
          {
            title: 'Account',
            key: 'account',
            render: (_: unknown, j: RotationJob) => (
              <>
                <Typography.Text strong>{j.account_username}</Typography.Text>
                <Typography.Text type="secondary"> @ {j.target_name}</Typography.Text>
              </>
            ),
          },
        ]
      : []),
    {
      title: 'Status',
      key: 'status',
      render: (_, j) => (
        <Space size={4} wrap>
          <StatusTag label={j.status.replace(/_/g, ' ')} variant={JOB_STATUS_VARIANT[j.status] ?? StatusVariant.NEUTRAL} />
          {j.dry_run && <StatusTag label="dry run" variant={StatusVariant.OUTLINE} />}
          {j.verify_result && j.verify_result !== 'verified' && (
            <StatusTag label={`verify ${j.verify_result}`} variant={StatusVariant.DANGER} />
          )}
          {j.release_alerted_at && <StatusTag label="wait overdue" variant={StatusVariant.DANGER} />}
        </Space>
      ),
    },
    { title: 'Trigger', key: 'reason', render: (_, j) => REASON_LABEL[j.reason] ?? j.reason },
    {
      title: 'Versions',
      key: 'versions',
      render: (_, j) => (j.candidate_version ? `v${j.from_version ?? '?'} → v${j.candidate_version}` : '—'),
    },
    { title: 'Attempts', dataIndex: 'attempts', key: 'attempts' },
    {
      title: 'Created',
      key: 'created',
      render: (_, j) => <Tooltip title={fmtTime(j.created_at)}>{fromNow(j.created_at)}</Tooltip>,
    },
    {
      title: 'Detail',
      key: 'detail',
      render: (_, j) => (
        <Typography.Text type="secondary" className="text-xs">
          {j.resolution ? `resolved: ${j.resolution}${j.resolution_note ? ` (${j.resolution_note})` : ''}` : j.detail ?? j.note ?? ''}
        </Typography.Text>
      ),
    },
    ...(onResolve
      ? [
          {
            title: '',
            key: 'actions',
            render: (_: unknown, j: RotationJob) =>
              j.status === 'needs_attention' ? (
                <Button variant="danger" size="small" onClick={() => onResolve(j)}>
                  Resolve
                </Button>
              ) : null,
          },
        ]
      : []),
  ];
  return (
    <DataTable<RotationJob>
      rowKey="id"
      loading={loading}
      dataSource={jobs}
      pagination={pagination}
      columns={columns}
      expandable={{ expandedRowRender: (j) => <RotationSteps jobId={j.id} /> }}
    />
  );
}

export default RotationJobsTable;
