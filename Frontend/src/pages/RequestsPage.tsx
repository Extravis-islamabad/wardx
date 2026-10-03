import { CheckOutlined, CloseOutlined, StopOutlined, UnlockOutlined } from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App, Button, Input, Modal, Segmented, Space, Table, Tag, Typography } from 'antd';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Role, STATUS_COLORS } from '@/constants/enums';
import { useAuth } from '@/context/AuthContext';
import { usePaging } from '@/hooks/usePaging';
import { errorMessage } from '@/lib/apiClient';
import { fmtTime, fromNow } from '@/lib/format';
import { queryKeys } from '@/lib/queryKeys';
import { checkoutsApi, requestsApi } from '@/services/api';
import type { AccessRequest } from '@/types/api';

type Scope = 'queue' | 'mine' | 'all';

export default function RequestsPage() {
  const { user, hasRole } = useAuth();
  const canDecide = hasRole(Role.Admin, Role.Approver);
  const { message } = App.useApp();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [scope, setScope] = useState<Scope>(canDecide ? 'queue' : 'mine');
  const [deciding, setDeciding] = useState<{ req: AccessRequest; approve: boolean } | null>(null);
  const [note, setNote] = useState('');
  const { page, page_size, setPage, pagination } = usePaging();
  const q = {
    page,
    page_size,
    mine: scope === 'mine',
    status: scope === 'queue' ? 'pending' : undefined,
  };
  const { data, isLoading } = useQuery({
    queryKey: queryKeys.requests.list(q),
    queryFn: () => requestsApi.list(q),
    refetchInterval: 20_000,
  });

  const refresh = () => {
    void qc.invalidateQueries({ queryKey: queryKeys.requests.all });
    void qc.invalidateQueries({ queryKey: queryKeys.dashboard });
  };
  const decide = useMutation({
    mutationFn: () => requestsApi.decide(deciding!.req.id, deciding!.approve, note || undefined),
    onSuccess: () => {
      message.success(deciding?.approve ? 'Approved' : 'Denied');
      setDeciding(null);
      setNote('');
      refresh();
    },
    onError: (e) => message.error(errorMessage(e)),
  });
  const cancel = useMutation({
    mutationFn: (id: string) => requestsApi.cancel(id),
    onSuccess: refresh,
    onError: (e) => message.error(errorMessage(e)),
  });
  const use = useMutation({
    mutationFn: (r: AccessRequest) => checkoutsApi.create({ account_id: r.account.id, request_id: r.id }),
    onSuccess: () => {
      message.success('Checked out — reveal it from Check-outs');
      refresh();
      void qc.invalidateQueries({ queryKey: queryKeys.checkouts.all });
      navigate('/checkouts');
    },
    onError: (e) => message.error(errorMessage(e)),
  });

  const scopes = [
    ...(canDecide ? [{ value: 'queue', label: 'Awaiting decision' }] : []),
    { value: 'mine', label: 'My requests' },
    ...(canDecide ? [{ value: 'all', label: 'All' }] : []),
  ];

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <Typography.Title level={3} className="!m-0">Access requests</Typography.Title>
        <Segmented options={scopes} value={scope} onChange={(v) => { setScope(v as Scope); setPage(1); }} />
      </div>
      <Table<AccessRequest>
        rowKey="id"
        loading={isLoading}
        dataSource={data?.data}
        pagination={pagination(data?.total)}
        columns={[
          { title: 'Account', render: (_, r) => <><b>{r.account.username}</b>@{r.account.target_name}</> },
          { title: 'Requester', render: (_, r) => r.requester.full_name || r.requester.username },
          {
            title: 'Reason',
            render: (_, r) => (
              <>
                {r.reason} {r.ticket_ref && <Tag>{r.ticket_ref}</Tag>}
              </>
            ),
          },
          { title: 'Duration', render: (_, r) => `${r.duration_minutes} min` },
          { title: 'Requested', dataIndex: 'created_at', render: (v: string) => <span title={fmtTime(v)}>{fromNow(v)}</span> },
          {
            title: 'Status',
            render: (_, r) => (
              <Space direction="vertical" size={0}>
                <Tag color={STATUS_COLORS[r.status]}>{r.status}</Tag>
                {r.decided_by && (
                  <Typography.Text type="secondary" className="text-xs">
                    by {r.decided_by.username}{r.decision_note ? `: ${r.decision_note}` : ''}
                  </Typography.Text>
                )}
              </Space>
            ),
          },
          {
            title: '',
            width: 220,
            render: (_, r) => {
              const mine = r.requester.id === user?.id;
              return (
                <Space>
                  {r.status === 'pending' && canDecide && !mine && (
                    <>
                      <Button size="small" type="primary" icon={<CheckOutlined />} onClick={() => setDeciding({ req: r, approve: true })}>
                        Approve
                      </Button>
                      <Button size="small" danger icon={<CloseOutlined />} onClick={() => setDeciding({ req: r, approve: false })}>
                        Deny
                      </Button>
                    </>
                  )}
                  {r.status === 'approved' && mine && (
                    <Button size="small" type="primary" icon={<UnlockOutlined />} loading={use.isPending} onClick={() => use.mutate(r)}>
                      Check out
                    </Button>
                  )}
                  {(r.status === 'pending' || r.status === 'approved') && mine && (
                    <Button size="small" icon={<StopOutlined />} onClick={() => cancel.mutate(r.id)}>
                      Cancel
                    </Button>
                  )}
                </Space>
              );
            },
          },
        ]}
      />
      <Modal
        open={!!deciding}
        title={deciding?.approve ? 'Approve request' : 'Deny request'}
        okText={deciding?.approve ? 'Approve' : 'Deny'}
        okButtonProps={{ danger: !deciding?.approve }}
        confirmLoading={decide.isPending}
        onOk={() => decide.mutate()}
        onCancel={() => { setDeciding(null); setNote(''); }}
      >
        {deciding && (
          <Typography.Paragraph>
            <b>{deciding.req.requester.username}</b> wants <b>{deciding.req.account.username}@{deciding.req.account.target_name}</b>{' '}
            for {deciding.req.duration_minutes} minutes: “{deciding.req.reason}”.
          </Typography.Paragraph>
        )}
        <Input.TextArea rows={2} placeholder="Note (optional)" value={note} onChange={(e) => setNote(e.target.value)} />
      </Modal>
    </>
  );
}
