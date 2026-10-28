import { Card, List, Space, Typography } from 'antd';
import { useNavigate } from 'react-router-dom';
import { StatusTag } from '@/components';
import { ROUTES } from '@/constants/enums/routes';
import { StatusVariant } from '@/constants/enums/status';
import { useRotationAttention } from '@/features/rotation/hooks';
import { fmtTime } from '@/utils/format';

interface Row {
  key: string;
  tag: string;
  variant: StatusVariant;
  title: string;
  detail?: string;
}

/** Rotation problems in the caller's safes: needs attention, out of sync, untrustworthy
 * or risk-accepted verifies, empty passwords and waits for release past their limit. */
export function RotationAttentionPanel() {
  const navigate = useNavigate();
  const attention = useRotationAttention();
  const a = attention.data;
  if (!a) return null;
  const rows: Row[] = [
    ...a.needs_attention.map((j) => ({
      key: `na-${j.id}`,
      tag: 'needs attention',
      variant: StatusVariant.DANGER,
      title: `${j.account_username} @ ${j.target_name}`,
      detail: j.detail ?? undefined,
    })),
    ...a.verify_untrustworthy.map((x) => ({
      key: `vu-${x.id}`,
      tag: 'verify untrustworthy',
      variant: StatusVariant.DANGER,
      title: x.username,
      detail: 'Accepted a wrong password: normal access blocked until confirmed or reconciled',
    })),
    ...a.empty_password.map((x) => ({
      key: `ep-${x.id}`,
      tag: 'empty password',
      variant: StatusVariant.DANGER,
      title: x.username,
      detail: 'High risk: the stored password is empty',
    })),
    ...a.out_of_sync.map((x) => ({
      key: `os-${x.id}`,
      tag: 'out of sync',
      variant: StatusVariant.WARNING,
      title: x.username,
      detail: 'The device rejected the vaulted password',
    })),
    ...a.release_overdue.map((j) => ({
      key: `ro-${j.id}`,
      tag: 'wait overdue',
      variant: StatusVariant.WARNING,
      title: `${j.account_username} @ ${j.target_name}`,
      detail: `Waiting for holders since ${fmtTime(j.waiting_since)}`,
    })),
    ...a.confirmed_untrustworthy.map((x) => ({
      key: `cu-${x.id}`,
      tag: 'confirmed despite failed negative check',
      variant: StatusVariant.WARNING,
      title: x.username,
      detail: `By ${x.risk_accepted_by_name ?? x.risk_accepted_by ?? '?'} ${fmtTime(x.risk_accepted_at)}: ${x.risk_accepted_reason ?? ''}`,
    })),
  ];
  if (!rows.length) return null;
  return (
    <Card size="small" title={`Password rotation needs attention (${rows.length})`}>
      <List
        size="small"
        dataSource={rows}
        renderItem={(r) => (
          <List.Item className="cursor-pointer" onClick={() => navigate(ROUTES.ROTATION)}>
            <Space wrap>
              <StatusTag label={r.tag} variant={r.variant} />
              <Typography.Text strong>{r.title}</Typography.Text>
              {r.detail && <Typography.Text type="secondary">{r.detail}</Typography.Text>}
            </Space>
          </List.Item>
        )}
      />
    </Card>
  );
}

export default RotationAttentionPanel;
