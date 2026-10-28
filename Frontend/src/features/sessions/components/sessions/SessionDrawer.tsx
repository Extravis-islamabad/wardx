import { Descriptions, Drawer, Table, Tabs, Typography, type TableProps } from 'antd';
import { useState } from 'react';
import { StatusTag } from '@/components';
import { SessionStatus } from '@/constants/enums/sessions';
import { StatusVariant } from '@/constants/enums/status';
import { SessionDrawerTab, sessionDuration } from '@/features/sessions/constants';
import { useSessionCommands } from '@/features/sessions/hooks';
import type { GatewaySession, SessionCommand } from '@/services/sessions-services';
import { fmtTime } from '@/utils/format';
import { RecordingPlayer } from './RecordingPlayer';

const DRAWER_SIZE = 960;

const commandColumns: TableProps<SessionCommand>['columns'] = [
  { title: 'At', dataIndex: 'offset_seconds', key: 'offset', width: 80, render: (s: number) => `+${s?.toFixed(1)}s` },
  { title: 'Command', dataIndex: 'command', key: 'command', render: (c: string) => <code>{c}</code> },
  { title: 'Verdict', dataIndex: 'verdict', key: 'verdict', width: 100, render: (v: string) => <StatusTag label={v} /> },
];

export function SessionDrawer({ session, onClose }: { session: GatewaySession | null; onClose: () => void }) {
  const [verified, setVerified] = useState<boolean | null>(null);
  const commands = useSessionCommands(session?.id, session?.status === SessionStatus.ACTIVE);

  return (
    <Drawer
      open={!!session}
      onClose={() => {
        setVerified(null);
        onClose();
      }}
      size={DRAWER_SIZE}
      title={session && `${session.username} → ${session.account_username}@${session.target_name}`}
      destroyOnHidden
    >
      {session && (
        <>
          <Descriptions size="small" column={2} className="!mb-4">
            <Descriptions.Item label="Status">
              <StatusTag label={session.status} /> {session.close_reason}
            </Descriptions.Item>
            <Descriptions.Item label="Mode">
              {session.mode}
              {session.exec_command && <code className="ml-2">{session.exec_command}</code>}
            </Descriptions.Item>
            <Descriptions.Item label="Started">{fmtTime(session.started_at)}</Descriptions.Item>
            <Descriptions.Item label="Duration">{sessionDuration(session)}</Descriptions.Item>
            <Descriptions.Item label="From">
              {session.client_ip ?? '—'} via {session.gateway_node ?? '—'}
            </Descriptions.Item>
            <Descriptions.Item label="Target">{session.target_address}</Descriptions.Item>
            {session.recording_sha256 && (
              <Descriptions.Item label="Recording SHA-256" span={2}>
                <Typography.Text code copyable className="text-xs">
                  {session.recording_sha256}
                </Typography.Text>
                {verified === true && (
                  <span className="ml-2">
                    <StatusTag label="matches" variant={StatusVariant.SUCCESS} />
                  </span>
                )}
                {verified === false && (
                  <span className="ml-2">
                    <StatusTag label="ALTERED" variant={StatusVariant.DANGER} />
                  </span>
                )}
              </Descriptions.Item>
            )}
          </Descriptions>
          <Tabs
            items={[
              {
                key: SessionDrawerTab.REPLAY,
                label: 'Replay',
                children: session.has_recording ? (
                  <RecordingPlayer sessionId={session.id} onVerified={setVerified} />
                ) : (
                  <Typography.Text type="secondary">
                    {session.status === SessionStatus.ACTIVE ? 'Available when the session ends.' : 'No recording.'}
                  </Typography.Text>
                ),
              },
              {
                key: SessionDrawerTab.COMMANDS,
                label: `Commands (${session.commands_count ?? 0})`,
                children: (
                  <Table<SessionCommand>
                    size="small"
                    rowKey="id"
                    loading={commands.isLoading}
                    dataSource={commands.data}
                    pagination={false}
                    columns={commandColumns}
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

export default SessionDrawer;
