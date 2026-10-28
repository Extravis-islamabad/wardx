import { Alert, List, Space, Typography } from 'antd';
import { Button } from '@/components';
import { useAcknowledgeAlert, useOpenHighAlerts } from '@/features/dashboard/hooks';
import { fmtTime } from '@/utils/format';
import { notify } from '@/utils/notify';

/** Unacknowledged high-severity alerts (audit.view); admins acknowledge them (audited). */
export function HighAlertsBanner({ canAcknowledge }: { canAcknowledge: boolean }) {
  const alerts = useOpenHighAlerts(true);
  const { mutateAsync: acknowledge, isPending } = useAcknowledgeAlert();
  const rows = alerts.data?.data ?? [];
  if (!rows.length) return null;

  const ack = async (id: string) => {
    try {
      await acknowledge(id);
      notify.success('Alert acknowledged');
    } catch {
      // apiClient's interceptor already toasted the failure.
    }
  };

  return (
    <Alert
      type="error"
      showIcon
      title={`${alerts.data?.total ?? rows.length} unacknowledged high-severity security alert${rows.length === 1 ? '' : 's'}`}
      description={
        <List
          size="small"
          dataSource={rows}
          renderItem={(a) => (
            <List.Item
              actions={
                canAcknowledge
                  ? [
                      <Button key="ack" variant="admin" size="small" loading={isPending} onClick={() => void ack(a.id)}>
                        Acknowledge
                      </Button>,
                    ]
                  : undefined
              }
            >
              <Space orientation="vertical" size={0}>
                <Typography.Text strong>{a.message}</Typography.Text>
                <Typography.Text type="secondary">
                  {a.kind} · {fmtTime(a.created_at)}
                  {typeof a.details?.reason === 'string' ? ` · reason: ${a.details.reason}` : ''}
                </Typography.Text>
              </Space>
            </List.Item>
          )}
        />
      }
    />
  );
}

export default HighAlertsBanner;
