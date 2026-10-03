import { PlayCircleOutlined, PoweroffOutlined, SafetyCertificateOutlined, WarningOutlined } from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  App,
  Badge,
  Button,
  Descriptions,
  Drawer,
  Input,
  Popconfirm,
  Segmented,
  Space,
  Table,
  Tabs,
  Tag,
  Tooltip,
  Typography,
} from 'antd';
import { useState } from 'react';
import { RecordingPlayer } from '@/components/RecordingPlayer';
import { Role, STATUS_COLORS } from '@/constants/enums';
import { useAuth } from '@/context/AuthContext';
import { usePaging } from '@/hooks/usePaging';
import { errorMessage } from '@/lib/apiClient';
import { fmtTime, fromNow } from '@/lib/format';
import { queryKeys } from '@/lib/queryKeys';
import { sessionsApi } from '@/services/api';
import type { GatewaySession, SessionCommand } from '@/types/api';

const duration = (s: GatewaySession) => {
  const end = s.ended_at ? new Date(s.ended_at) : new Date();
  const secs = Math.max(0, Math.round((end.getTime() - new Date(s.started_at).getTime()) / 1000));
  const m = Math.floor(secs / 60);
  return m ? `${m}m ${secs % 60}s` : `${secs}s`;
};

function SessionDrawer({ session, onClose }: { session: GatewaySession | null; onClose: () => void }) {
  const [verified, setVerified] = useState<boolean | null>(null);
  const commands = useQuery({
    queryKey: queryKeys.sessionCommands(session?.id ?? ''),
    queryFn: async () => (await sessionsApi.commands(session!.id)).data,
    enabled: !!session,
    refetchInterval: session?.status === 'active' ? 3000 : false,
  });

  return (
    <Drawer
      open={!!session}
      onClose={() => { setVerified(null); onClose(); }}
      size={960}
      title={session && `${session.username} → ${session.account_username}@${session.target_name}`}
      destroyOnHidden
    >
      {session && (
        <>
          <Descriptions size="small" column={2} className="!mb-4">
            <Descriptions.Item label="Status"><Tag color={STATUS_COLORS[session.status]}>{session.status}</Tag> {session.close_reason}</Descriptions.Item>
            <Descriptions.Item label="Mode">{session.mode}{session.exec_command && <code className="ml-2">{session.exec_command}</code>}</Descriptions.Item>
            <Descriptions.Item label="Started">{fmtTime(session.started_at)}</Descriptions.Item>
            <Descriptions.Item label="Duration">{duration(session)}</Descriptions.Item>
            <Descriptions.Item label="From">{session.client_ip ?? '—'} via {session.gateway_node ?? '—'}</Descriptions.Item>
            <Descriptions.Item label="Target">{session.target_address}</Descriptions.Item>
            {session.recording_sha256 && (
              <Descriptions.Item label="Recording SHA-256" span={2}>
                <Typography.Text code copyable className="text-xs">{session.recording_sha256}</Typography.Text>
                {verified === true && <Tag icon={<SafetyCertificateOutlined />} color="green" className="!ml-2">matches</Tag>}
                {verified === false && <Tag icon={<WarningOutlined />} color="red" className="!ml-2">ALTERED</Tag>}
              </Descriptions.Item>
            )}
          </Descriptions>
          <Tabs
            items={[
              {
                key: 'replay',
                label: 'Replay',
                children: session.has_recording ? (
                  <RecordingPlayer sessionId={session.id} onVerified={setVerified} />
                ) : (
                  <Typography.Text type="secondary">
                    {session.status === 'active' ? 'Available when the session ends.' : 'No recording.'}
                  </Typography.Text>
                ),
              },
              {
                key: 'commands',
                label: `Commands (${session.commands_count})`,
                children: (
                  <Table<SessionCommand>
                    size="small"
                    rowKey="id"
                    loading={commands.isLoading}
                    dataSource={commands.data}
                    pagination={false}
                    columns={[
                      { title: 'At', dataIndex: 'offset_seconds', width: 80, render: (s: number) => `+${s.toFixed(1)}s` },
                      { title: 'Command', dataIndex: 'command', render: (c: string) => <code>{c}</code> },
                      { title: 'Verdict', dataIndex: 'verdict', width: 100, render: (v: string) => <Tag color={STATUS_COLORS[v]}>{v}</Tag> },
                    ]}
                  />
                ),
              },
            ]}
          />
        </>
      )}
    </Drawer>
  );
}

export default function SessionsPage() {
  const { hasRole } = useAuth();
  const canSeeAll = hasRole(Role.Admin, Role.Auditor);
  const isAdmin = hasRole(Role.Admin);
  const { message } = App.useApp();
  const qc = useQueryClient();
  const [scope, setScope] = useState<'active' | 'all' | 'mine'>(canSeeAll ? 'all' : 'mine');
  const [search, setSearch] = useState('');
  const [open, setOpen] = useState<GatewaySession | null>(null);
  const { page, page_size, setPage, pagination } = usePaging();
  const q = {
    page,
    page_size,
    status: scope === 'active' ? 'active' : undefined,
    mine: scope === 'mine',
    search: search || undefined,
  };
  const { data, isLoading } = useQuery({
    queryKey: queryKeys.sessions.list(q),
    queryFn: () => sessionsApi.list(q),
    refetchInterval: 5000,
  });
  const gateway = useQuery({ queryKey: queryKeys.gateway, queryFn: async () => (await sessionsApi.gatewayInfo()).data });

  const kill = useMutation({
    mutationFn: (id: string) => sessionsApi.terminate(id),
    onSuccess: (r) => {
      message.success(r.message ?? 'Termination requested');
      void qc.invalidateQueries({ queryKey: queryKeys.sessions.all });
    },
    onError: (e) => message.error(errorMessage(e)),
  });

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <Typography.Title level={3} className="!m-0">Sessions</Typography.Title>
          {gateway.data && (
            <Typography.Text type="secondary">
              Connect: <Typography.Text code copyable>{`ssh -p ${gateway.data.port} ${gateway.data.login_format}@${gateway.data.host}`}</Typography.Text>
            </Typography.Text>
          )}
        </div>
        <Space wrap>
          <Input.Search allowClear placeholder="Target or account" onSearch={(v) => { setSearch(v); setPage(1); }} />
          <Segmented
            value={scope}
            onChange={(v) => { setScope(v as typeof scope); setPage(1); }}
            options={[
              ...(canSeeAll ? [{ value: 'all', label: 'All' }, { value: 'active', label: 'Live' }] : []),
              { value: 'mine', label: 'Mine' },
            ]}
          />
        </Space>
      </div>
      <Table<GatewaySession>
        rowKey="id"
        loading={isLoading}
        dataSource={data?.data}
        pagination={pagination(data?.total)}
        onRow={(s) => ({ onClick: () => setOpen(s), className: 'cursor-pointer' })}
        columns={[
          {
            title: 'Status',
            width: 120,
            render: (_, s) =>
              s.status === 'active' ? <Badge status="processing" text="live" /> : <Tag color={STATUS_COLORS[s.status]}>{s.status}</Tag>,
          },
          { title: 'User', dataIndex: 'username' },
          { title: 'Account', render: (_, s) => <><b>{s.account_username}</b>@{s.target_name}</> },
          { title: 'Mode', render: (_, s) => (s.mode === 'exec' ? <Tooltip title={s.exec_command}><Tag>exec</Tag></Tooltip> : <Tag>shell</Tag>) },
          { title: 'Started', dataIndex: 'started_at', render: (v: string) => <span title={fmtTime(v)}>{fromNow(v)}</span> },
          { title: 'Duration', render: (_, s) => duration(s) },
          {
            title: 'Commands',
            render: (_, s) => (
              <Space size={4}>
                {s.commands_count}
                {s.blocked_count > 0 && <Tag color="red">{s.blocked_count} blocked</Tag>}
              </Space>
            ),
          },
          {
            title: '',
            width: 180,
            render: (_, s) => (
              <Space onClick={(e) => e.stopPropagation()}>
                {s.has_recording && <Button size="small" icon={<PlayCircleOutlined />} onClick={() => setOpen(s)}>Replay</Button>}
                {isAdmin && s.status === 'active' && (
                  <Popconfirm title="Disconnect this session now?" onConfirm={() => kill.mutate(s.id)}>
                    <Button size="small" danger icon={<PoweroffOutlined />} disabled={!!s.terminate_requested_at}>
                      {s.terminate_requested_at ? 'Killing…' : 'Kill'}
                    </Button>
                  </Popconfirm>
                )}
              </Space>
            ),
          },
        ]}
      />
      <SessionDrawer session={open} onClose={() => setOpen(null)} />
    </>
  );
}
