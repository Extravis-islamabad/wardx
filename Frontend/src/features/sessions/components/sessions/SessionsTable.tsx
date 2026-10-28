import { Badge, Space, Tooltip, type TablePaginationConfig, type TableProps } from 'antd';
import { Button, DataTable, StatusTag } from '@/components';
import { SessionMode, SessionStatus } from '@/constants/enums/sessions';
import { StatusVariant } from '@/constants/enums/status';
import { tableStateProps } from '@/lib/tableStateProps';
import type { GatewaySession } from '@/services/sessions-services';
import { fmtTime, fromNow } from '@/utils/format';
import { sessionDuration } from '@/features/sessions/constants';
import type { useSessions } from '@/features/sessions/hooks';

interface SessionsTableProps {
  query: ReturnType<typeof useSessions>;
  pagination: TablePaginationConfig;
  canTerminate: boolean;
  onOpen: (session: GatewaySession) => void;
  onTerminate: (session: GatewaySession) => void;
}

export function SessionsTable({ query, pagination, canTerminate, onOpen, onTerminate }: SessionsTableProps) {
  const columns: TableProps<GatewaySession>['columns'] = [
    {
      title: 'Status',
      key: 'status',
      width: 120,
      render: (_, s) =>
        s?.status === SessionStatus.ACTIVE ? <Badge status="processing" text="live" /> : <StatusTag label={s?.status} />,
    },
    { title: 'User', dataIndex: 'username', key: 'username' },
    {
      title: 'Account',
      key: 'account',
      render: (_, s) => (
        <>
          <b>{s?.account_username}</b>@{s?.target_name}
        </>
      ),
    },
    {
      title: 'Mode',
      key: 'mode',
      render: (_, s) =>
        s?.mode === SessionMode.EXEC ? (
          <Tooltip title={s?.exec_command}>
            <StatusTag label={SessionMode.EXEC} variant={StatusVariant.OUTLINE} />
          </Tooltip>
        ) : (
          <StatusTag label={SessionMode.SHELL} variant={StatusVariant.OUTLINE} />
        ),
    },
    {
      title: 'Started',
      dataIndex: 'started_at',
      key: 'started_at',
      render: (v: string) => <span title={fmtTime(v)}>{fromNow(v)}</span>,
    },
    { title: 'Duration', key: 'duration', render: (_, s) => sessionDuration(s) },
    {
      title: 'Commands',
      key: 'commands',
      render: (_, s) => (
        <Space size={4}>
          {s?.commands_count ?? 0}
          {(s?.blocked_count ?? 0) > 0 && <StatusTag label={`${s.blocked_count} blocked`} variant={StatusVariant.DANGER} />}
        </Space>
      ),
    },
    {
      title: '',
      key: 'actions',
      width: 180,
      render: (_, s) => (
        <Space onClick={(e) => e.stopPropagation()}>
          {s?.has_recording && (
            <Button variant="admin" size="small" onClick={() => onOpen(s)}>
              Replay
            </Button>
          )}
          {canTerminate && s?.status === SessionStatus.ACTIVE && (
            <Button variant="danger" size="small" disabled={!!s?.terminate_requested_at} onClick={() => onTerminate(s)}>
              {s?.terminate_requested_at ? 'Killing…' : 'Kill'}
            </Button>
          )}
        </Space>
      ),
    },
  ];

  return (
    <DataTable<GatewaySession>
      rowKey="id"
      {...tableStateProps(query, "Couldn't load sessions")}
      dataSource={query?.data?.data}
      pagination={pagination}
      onRow={(s) => ({ onClick: () => onOpen(s), className: 'cursor-pointer' })}
      columns={columns}
    />
  );
}

export default SessionsTable;
