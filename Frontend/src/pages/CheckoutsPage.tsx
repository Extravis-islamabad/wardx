import { EyeOutlined, RollbackOutlined } from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App, Button, Popconfirm, Segmented, Space, Table, Tag, Typography } from 'antd';
import { useState } from 'react';
import { RevealModal } from '@/components/RevealModal';
import { Role, STATUS_COLORS } from '@/constants/enums';
import { useAuth } from '@/context/AuthContext';
import { usePaging } from '@/hooks/usePaging';
import { errorMessage } from '@/lib/apiClient';
import { fmtTime, fromNow, isFuture } from '@/lib/format';
import { queryKeys } from '@/lib/queryKeys';
import { checkoutsApi } from '@/services/api';
import type { Checkout } from '@/types/api';

type Scope = 'mine-active' | 'mine' | 'all-active' | 'all';

export default function CheckoutsPage() {
  const { user, hasRole } = useAuth();
  const canSeeAll = hasRole(Role.Admin, Role.Auditor);
  const { message } = App.useApp();
  const qc = useQueryClient();
  const [scope, setScope] = useState<Scope>('mine-active');
  const [revealing, setRevealing] = useState<Checkout | null>(null);
  const { page, page_size, setPage, pagination } = usePaging();
  const q = {
    page,
    page_size,
    mine: scope.startsWith('mine'),
    status: scope.endsWith('active') ? 'active' : undefined,
  };
  const { data, isLoading } = useQuery({
    queryKey: queryKeys.checkouts.list(q),
    queryFn: () => checkoutsApi.list(q),
    refetchInterval: 30_000,
  });

  const checkin = useMutation({
    mutationFn: (id: string) => checkoutsApi.checkin(id),
    onSuccess: () => {
      message.success('Checked in');
      void qc.invalidateQueries({ queryKey: queryKeys.checkouts.all });
      void qc.invalidateQueries({ queryKey: queryKeys.accounts.all });
      void qc.invalidateQueries({ queryKey: queryKeys.dashboard });
    },
    onError: (e) => message.error(errorMessage(e)),
  });

  const scopes = [
    { value: 'mine-active', label: 'My active' },
    { value: 'mine', label: 'My history' },
    ...(canSeeAll ? [{ value: 'all-active', label: 'All active' }, { value: 'all', label: 'All' }] : []),
  ];

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <Typography.Title level={3} className="!m-0">Check-outs</Typography.Title>
        <Segmented options={scopes} value={scope} onChange={(v) => { setScope(v as Scope); setPage(1); }} />
      </div>
      <Table<Checkout>
        rowKey="id"
        loading={isLoading}
        dataSource={data?.data}
        pagination={pagination(data?.total)}
        columns={[
          { title: 'Account', render: (_, c) => <><b>{c.account.username}</b>@{c.account.target_name}</> },
          { title: 'Holder', render: (_, c) => c.user.full_name || c.user.username },
          { title: 'Reason', dataIndex: 'reason', ellipsis: true },
          { title: 'Since', dataIndex: 'checked_out_at', render: fmtTime },
          {
            title: 'Ends',
            dataIndex: 'expires_at',
            render: (v: string, c) => (c.status === 'active' ? <span title={fmtTime(v)}>{fromNow(v)}</span> : fmtTime(c.checked_in_at)),
          },
          { title: 'Status', dataIndex: 'status', render: (s: string) => <Tag color={STATUS_COLORS[s]}>{s}</Tag> },
          {
            title: '',
            width: 200,
            render: (_, c) => {
              if (c.status !== 'active') return null;
              const mine = c.user.id === user?.id;
              return (
                <Space>
                  {mine && isFuture(c.expires_at) && (
                    <Button size="small" type="primary" icon={<EyeOutlined />} onClick={() => setRevealing(c)}>
                      Reveal
                    </Button>
                  )}
                  {(mine || hasRole(Role.Admin)) && (
                    <Popconfirm
                      title={mine ? 'Check this credential back in?' : 'Revoke this check-out?'}
                      onConfirm={() => checkin.mutate(c.id)}
                    >
                      <Button size="small" danger={!mine} icon={<RollbackOutlined />}>
                        {mine ? 'Check in' : 'Revoke'}
                      </Button>
                    </Popconfirm>
                  )}
                </Space>
              );
            },
          },
        ]}
      />
      <RevealModal checkout={revealing} onClose={() => setRevealing(null)} />
    </>
  );
}
