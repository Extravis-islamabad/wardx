import { Space, type TablePaginationConfig, type TableProps } from 'antd';
import { Button, DataTable, StatusTag } from '@/components';
import { CheckoutStatus } from '@/constants/enums/access';
import { tableStateProps } from '@/lib/tableStateProps';
import type { Checkout } from '@/services/access-services';
import { fmtTime, fromNow, isFuture } from '@/utils/format';
import type { useCheckouts } from '@/features/access/hooks';

interface CheckoutsTableProps {
  query: ReturnType<typeof useCheckouts>;
  pagination: TablePaginationConfig;
  currentUserId?: string;
  canRevoke: boolean;
  onReveal: (checkout: Checkout) => void;
  onCheckin: (checkout: Checkout) => void;
}

export function CheckoutsTable({ query, pagination, currentUserId, canRevoke, onReveal, onCheckin }: CheckoutsTableProps) {
  const columns: TableProps<Checkout>['columns'] = [
    {
      title: 'Account',
      key: 'account',
      render: (_, c) => (
        <>
          <b>{c?.account?.username}</b>@{c?.account?.target_name}
        </>
      ),
    },
    { title: 'Holder', key: 'holder', render: (_, c) => c?.user?.full_name || c?.user?.username },
    { title: 'Reason', dataIndex: 'reason', key: 'reason', ellipsis: true },
    { title: 'Since', dataIndex: 'checked_out_at', key: 'checked_out_at', render: fmtTime },
    {
      title: 'Ends',
      dataIndex: 'expires_at',
      key: 'expires_at',
      render: (v: string, c) =>
        c?.status === CheckoutStatus.ACTIVE ? <span title={fmtTime(v)}>{fromNow(v)}</span> : fmtTime(c?.checked_in_at),
    },
    { title: 'Status', dataIndex: 'status', key: 'status', render: (s: string) => <StatusTag label={s} /> },
    {
      title: '',
      key: 'actions',
      width: 200,
      render: (_, c) => {
        if (c?.status !== CheckoutStatus.ACTIVE) return null;
        const mine = c?.user?.id === currentUserId;
        return (
          <Space>
            {mine && isFuture(c?.expires_at) && (
              <Button variant="primary" size="small" onClick={() => onReveal(c)}>
                Reveal
              </Button>
            )}
            {(mine || canRevoke) && (
              <Button variant={mine ? 'admin' : 'danger'} size="small" onClick={() => onCheckin(c)}>
                {mine ? 'Check in' : 'Revoke'}
              </Button>
            )}
          </Space>
        );
      },
    },
  ];

  return (
    <DataTable<Checkout>
      rowKey="id"
      {...tableStateProps(query, "Couldn't load check-outs")}
      dataSource={query?.data?.data}
      pagination={pagination}
      columns={columns}
    />
  );
}

export default CheckoutsTable;
