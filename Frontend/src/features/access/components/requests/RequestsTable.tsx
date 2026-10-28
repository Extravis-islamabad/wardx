import { Space, Typography, type TablePaginationConfig, type TableProps } from 'antd';
import { Button, DataTable, StatusTag } from '@/components';
import { RequestStatus } from '@/constants/enums/access';
import { StatusVariant } from '@/constants/enums/status';
import { tableStateProps } from '@/lib/tableStateProps';
import type { AccessRequest } from '@/services/access-services';
import { fmtTime, fromNow } from '@/utils/format';
import type { useRequests } from '@/features/access/hooks';

interface RequestsTableProps {
  query: ReturnType<typeof useRequests>;
  pagination: TablePaginationConfig;
  currentUserId?: string;
  canDecide: boolean;
  checkingOutId: string | null;
  onDecide: (request: AccessRequest, approve: boolean) => void;
  onCheckout: (request: AccessRequest) => void;
  onCancel: (request: AccessRequest) => void;
}

export function RequestsTable({
  query,
  pagination,
  currentUserId,
  canDecide,
  checkingOutId,
  onDecide,
  onCheckout,
  onCancel,
}: RequestsTableProps) {
  const columns: TableProps<AccessRequest>['columns'] = [
    {
      title: 'Account',
      key: 'account',
      render: (_, r) => (
        <>
          <b>{r?.account?.username}</b>@{r?.account?.target_name}
        </>
      ),
    },
    { title: 'Requester', key: 'requester', render: (_, r) => r?.requester?.full_name || r?.requester?.username },
    {
      title: 'Reason',
      key: 'reason',
      render: (_, r) => (
        <Space size={4} wrap>
          {r?.reason}
          {r?.ticket_ref && <StatusTag label={r.ticket_ref} variant={StatusVariant.OUTLINE} />}
        </Space>
      ),
    },
    { title: 'Duration', key: 'duration', render: (_, r) => `${r?.duration_minutes} min` },
    {
      title: 'Requested',
      dataIndex: 'created_at',
      key: 'created_at',
      render: (v: string) => <span title={fmtTime(v)}>{fromNow(v)}</span>,
    },
    {
      title: 'Status',
      key: 'status',
      render: (_, r) => (
        <Space orientation="vertical" size={0}>
          <StatusTag label={r?.status} />
          {r?.decided_by && (
            <Typography.Text type="secondary" className="text-xs">
              by {r.decided_by.username}
              {r?.decision_note ? `: ${r.decision_note}` : ''}
            </Typography.Text>
          )}
        </Space>
      ),
    },
    {
      title: '',
      key: 'actions',
      width: 220,
      render: (_, r) => {
        const mine = r?.requester?.id === currentUserId;
        return (
          <Space>
            {r?.status === RequestStatus.PENDING && canDecide && !mine && (
              <>
                <Button variant="primary" size="small" onClick={() => onDecide(r, true)}>
                  Approve
                </Button>
                <Button variant="danger" size="small" onClick={() => onDecide(r, false)}>
                  Deny
                </Button>
              </>
            )}
            {r?.status === RequestStatus.APPROVED && mine && (
              <Button variant="primary" size="small" loading={checkingOutId === r.id} onClick={() => onCheckout(r)}>
                Check out
              </Button>
            )}
            {(r?.status === RequestStatus.PENDING || r?.status === RequestStatus.APPROVED) && mine && (
              <Button variant="admin" size="small" onClick={() => onCancel(r)}>
                Cancel
              </Button>
            )}
          </Space>
        );
      },
    },
  ];

  return (
    <DataTable<AccessRequest>
      rowKey="id"
      {...tableStateProps(query, "Couldn't load access requests")}
      dataSource={query?.data?.data}
      pagination={pagination}
      columns={columns}
    />
  );
}

export default RequestsTable;
