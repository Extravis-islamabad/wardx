import { Alert, Card, List, Space, Typography } from 'antd';
import { useNavigate } from 'react-router-dom';
import { StatusTag } from '@/components';
import { ROUTES } from '@/constants/enums/routes';
import { StatusVariant } from '@/constants/enums/status';
import { useAttention } from '@/features/dashboard/hooks';
import { SafeHealthTag } from '@/features/safes/components';
import type { SafeHealth } from '@/services/safes-services';
import { fmtTime } from '@/utils/format';

const safeNames = (safes: SafeHealth[]) => safes.map((s) => s.name).join(', ');

/** Directory outage, break-glass coverage and safes needing attention (audit.view or safes.manage). */
export function AttentionPanel() {
  const navigate = useNavigate();
  const attention = useAttention(true);
  const data = attention.data;
  if (!data) return null;
  const { directory, break_glass: coverage, safes_needing_attention: safes } = data;

  return (
    <Space orientation="vertical" size={12} className="w-full">
      {directory.unreachable && (
        <Alert
          type="error"
          showIcon
          title="The directory is unreachable: directory-group access is suspended (fail closed)."
          description={
            <>
              <div>
                Last contact failed {fmtTime(directory.checked_at)}
                {directory.error ? `: ${directory.error}` : ''}.
              </div>
              {directory.affected_safes.length ? (
                <div>
                  Safes nobody can reach until it is back ({directory.affected_safes.length}):{' '}
                  <Typography.Text strong>{safeNames(directory.affected_safes)}</Typography.Text>. Only break-glass
                  reaches them.
                </div>
              ) : (
                <div>Every safe still has a local user or role member.</div>
              )}
            </>
          }
        />
      )}
      {coverage.warning && (
        <Alert
          type="warning"
          showIcon
          title={`Break-glass coverage: ${coverage.eligible_holders} of at least ${coverage.minimum} eligible holders`}
          description={coverage.message}
        />
      )}
      {safes.length > 0 && (
        <Card size="small" title={`Safes needing attention (${safes.length})`}>
          <List
            size="small"
            dataSource={safes}
            renderItem={(s) => (
              <List.Item className="cursor-pointer" onClick={() => navigate(ROUTES.SAFES)}>
                <Space>
                  <SafeHealthTag state={s.state} />
                  <Typography.Text strong>{s.name}</Typography.Text>
                  <StatusTag label={`${s.group_members} group member${s.group_members === 1 ? '' : 's'}`} variant={StatusVariant.OUTLINE} />
                  <Typography.Text type="secondary">
                    Add a direct user member so a directory outage cannot lock it.
                  </Typography.Text>
                </Space>
              </List.Item>
            )}
          />
        </Card>
      )}
    </Space>
  );
}

export default AttentionPanel;
