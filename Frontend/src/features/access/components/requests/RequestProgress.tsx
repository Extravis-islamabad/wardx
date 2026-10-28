import { CheckCircleFilled, ClockCircleOutlined, CloseCircleFilled, MinusCircleOutlined } from '@ant-design/icons';
import { List, Space, Tooltip, Typography } from 'antd';
import { StatusTag } from '@/components';
import { StatusVariant } from '@/constants/enums/status';
import type { AccessRequest, RequestLevel } from '@/services/access-services';
import { fmtTime } from '@/utils/format';

const ICON: Record<RequestLevel['state'], JSX.Element> = {
  approved: <CheckCircleFilled className="text-(--success)" />,
  denied: <CloseCircleFilled className="text-(--error)" />,
  current: <ClockCircleOutlined className="text-(--warning)" />,
  waiting: <MinusCircleOutlined className="text-(--muted-foreground)" />,
};

const approverLabel = (l: RequestLevel) =>
  l.approver_type === 'safe_approvers' ? 'safe approvers' : l.approver_type === 'user' ? 'named user' : `group ${l.approver_key}`;

/** One chip per level: state, approvals so far of those needed. */
export function RequestLevels({ request }: { request: AccessRequest }) {
  if (!request.levels?.length) return <Typography.Text type="secondary">—</Typography.Text>;
  return (
    <Space size={6} wrap>
      {request.levels.map((l) => (
        <Tooltip key={l.position} title={`Level ${l.position}: ${approverLabel(l)}`}>
          <span className="whitespace-nowrap">
            {ICON[l.state]} L{l.position} {l.approvals}/{l.required_approvals}
          </span>
        </Tooltip>
      ))}
    </Space>
  );
}

/** Decision history and the request's window, shown when a row is expanded. */
export function RequestHistory({ request }: { request: AccessRequest }) {
  return (
    <Space orientation="vertical" className="w-full">
      <Space wrap>
        {request.valid_until && (
          <StatusTag label={`valid until ${fmtTime(request.valid_until)}`} variant={StatusVariant.INFO} />
        )}
        <StatusTag
          label={request.multi_use ? `multi-use (${request.uses} used)` : 'single use'}
          variant={StatusVariant.OUTLINE}
        />
        {request.status === 'pending' && (
          <StatusTag label={`level ${request.current_level} due ${fmtTime(request.expires_at)}`} variant={StatusVariant.WARNING} />
        )}
      </Space>
      <List
        size="small"
        locale={{ emptyText: 'No decisions yet' }}
        dataSource={request.decisions}
        renderItem={(d) => (
          <List.Item>
            <Space>
              {d.approve ? ICON.approved : ICON.denied}
              <Typography.Text strong>{d.approver.full_name || d.approver.username}</Typography.Text>
              <span>
                {d.approve ? 'approved' : 'denied'} level {d.level}
              </span>
              <Typography.Text type="secondary">{fmtTime(d.decided_at)}</Typography.Text>
              {d.note && <Typography.Text italic>“{d.note}”</Typography.Text>}
            </Space>
          </List.Item>
        )}
      />
    </Space>
  );
}
