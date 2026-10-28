import { ExperimentOutlined } from '@ant-design/icons';
import { Alert, Card, Input, Space } from 'antd';
import { useState } from 'react';
import { Button } from '@/components';
import { useTestCommand } from '@/features/sessions/hooks';

/** Dry-runs a typed command against every active rule. */
export function RuleTester() {
  const [command, setCommand] = useState('');
  const test = useTestCommand();
  return (
    <Card
      size="small"
      title={
        <>
          <ExperimentOutlined /> Try a command
        </>
      }
    >
      <Space.Compact block>
        <Input
          aria-label="Command to test"
          className="font-mono"
          placeholder="reload in 5"
          value={command}
          onChange={(e) => setCommand(e.target.value)}
          onPressEnter={() => command && test.mutate(command)}
        />
        <Button onClick={() => test.mutate(command)} disabled={!command} loading={test.isPending}>
          Test
        </Button>
      </Space.Compact>
      {test.data && (
        <Alert
          className="!mt-3"
          showIcon
          type={test.data?.blocked ? 'error' : 'success'}
          title={
            test.data?.blocked
              ? `Blocked: ${test.data?.description ?? 'matches a deny rule'}`
              : 'Allowed by every active rule'
          }
        />
      )}
    </Card>
  );
}

export default RuleTester;
