import { KeyOutlined, LockOutlined, SafetyCertificateOutlined, UserOutlined } from '@ant-design/icons';
import { zodResolver } from '@hookform/resolvers/zod';
import { Alert, Button, Card, Form, Input, Typography } from 'antd';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { Navigate } from 'react-router-dom';
import { z } from 'zod';
import { FormField } from '@/components/FormField';
import { useAuth } from '@/context/AuthContext';
import { errorMessage } from '@/lib/apiClient';

const schema = z.object({
  username: z.string().min(1, 'Enter your username'),
  password: z.string().min(1, 'Enter your password'),
});
type Values = z.infer<typeof schema>;

function CodeStep() {
  const { verifyCode, cancelCode } = useAuth();
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await verifyCode(code);
    } catch (e) {
      setError(errorMessage(e));
      setCode('');
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <Typography.Paragraph type="secondary" className="text-center">
        Enter the 6-digit code from your authenticator app, or a recovery code.
      </Typography.Paragraph>
      {error && <Alert className="!mb-4" type="error" showIcon title={error} />}
      <Form layout="vertical" onFinish={() => void submit()}>
        <Form.Item label="Authentication code" htmlFor="mfa-code">
          <Input
            id="mfa-code"
            prefix={<KeyOutlined />}
            autoFocus
            autoComplete="one-time-code"
            inputMode="numeric"
            maxLength={20}
            value={code}
            onChange={(e) => setCode(e.target.value)}
          />
        </Form.Item>
        <Button type="primary" htmlType="submit" block loading={busy} disabled={code.trim().length < 6}>
          Verify
        </Button>
        <Button type="link" block className="!mt-2" onClick={cancelCode}>
          Use a different account
        </Button>
      </Form>
    </>
  );
}

export default function LoginPage() {
  const { user, login, awaitingCode } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const { control, handleSubmit, formState } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { username: '', password: '' },
  });

  if (user) return <Navigate to="/" replace />;

  const onSubmit = handleSubmit(async (v) => {
    setError(null);
    try {
      await login(v.username, v.password);
    } catch (e) {
      setError(errorMessage(e));
    }
  });

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <Card className="w-full max-w-sm">
        <div className="mb-6 flex flex-col items-center gap-2">
          <SafetyCertificateOutlined className="text-4xl text-[#5b6cff]" />
          <Typography.Title level={3} className="!m-0">
            WardX
          </Typography.Title>
          <Typography.Text type="secondary">Privileged access management</Typography.Text>
        </div>
        {awaitingCode ? (
          <CodeStep />
        ) : (
        <>
        {error && <Alert className="!mb-4" type="error" showIcon title={error} />}
        <Form layout="vertical" onSubmitCapture={onSubmit} requiredMark={false}>
          <FormField
            control={control}
            name="username"
            label="Username"
            render={(f) => (
              <Input
                prefix={<UserOutlined />}
                autoComplete="username"
                autoFocus
                value={f.value as string}
                onChange={(e) => f.onChange(e.target.value)}
                onBlur={f.onBlur}
              />
            )}
          />
          <FormField
            control={control}
            name="password"
            label="Password"
            render={(f) => (
              <Input.Password
                prefix={<LockOutlined />}
                autoComplete="current-password"
                value={f.value as string}
                onChange={(e) => f.onChange(e.target.value)}
                onBlur={f.onBlur}
              />
            )}
          />
          <Button type="primary" htmlType="submit" block loading={formState.isSubmitting}>
            Sign in
          </Button>
        </Form>
        </>
        )}
      </Card>
    </div>
  );
}
