import { SearchOutlined } from '@ant-design/icons';
import { Alert, Card, Descriptions, Input, Space, Typography } from 'antd';
import { useState } from 'react';
import { Button, StatusTag } from '@/components';
import { StatusVariant } from '@/constants/enums/status';
import { useTestDirectoryUser } from '@/features/identity/hooks';
import { errorMessage } from '@/utils/notifyApiError';

/** Looks a login name up with the service account; the service skips the toast, so failures render here. */
export function DirectoryTestUser() {
  const [username, setUsername] = useState('');
  const test = useTestDirectoryUser();
  const r = test.data;
  return (
    <Card size="small" title="Test a user (no password needed)">
      <Space.Compact block>
        <Input
          aria-label="Login name"
          placeholder="Login name, e.g. jdoe"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          onPressEnter={() => username && test.mutate(username)}
        />
        <Button icon={<SearchOutlined />} disabled={!username} loading={test.isPending} onClick={() => test.mutate(username)}>
          Look up
        </Button>
      </Space.Compact>
      {test.error && <Alert className="!mt-3" type="error" showIcon title={errorMessage(test.error)} />}
      {r && (
        <Descriptions className="!mt-3" size="small" column={1}>
          <Descriptions.Item label="DN">
            <Typography.Text code>{r.dn}</Typography.Text>
          </Descriptions.Item>
          <Descriptions.Item label="Name">
            {r.full_name ?? '—'} · {r.email ?? 'no e-mail'}
          </Descriptions.Item>
          <Descriptions.Item label="Groups">
            <Space size={4} wrap>
              {r.groups?.length ? r.groups.map((g) => <StatusTag key={g} label={g} variant={StatusVariant.OUTLINE} />) : '—'}
            </Space>
          </Descriptions.Item>
          <Descriptions.Item label="WardX role">
            {r.role ? (
              <StatusTag label={r.role} variant={StatusVariant.INFO} />
            ) : (
              <StatusTag label="none — sign-in refused" variant={StatusVariant.DANGER} />
            )}
          </Descriptions.Item>
        </Descriptions>
      )}
    </Card>
  );
}

export default DirectoryTestUser;
