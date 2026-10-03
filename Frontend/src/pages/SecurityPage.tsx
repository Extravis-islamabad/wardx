import { CheckCircleOutlined, CopyOutlined, SafetyCertificateOutlined } from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, App, Button, Card, Input, Modal, QRCode, Space, Steps, Tag, Typography } from 'antd';
import { useState } from 'react';
import { useAuth } from '@/context/AuthContext';
import { errorMessage } from '@/lib/apiClient';
import { queryKeys } from '@/lib/queryKeys';
import { authApi } from '@/services/api';

function RecoveryCodes({ codes, onDone }: { codes: string[]; onDone: () => void }) {
  const { message } = App.useApp();
  return (
    <Modal
      open
      closable={false}
      mask={{ closable: false }}
      title="Save your recovery codes"
      footer={<Button type="primary" onClick={onDone}>I have saved them</Button>}
    >
      <Typography.Paragraph>
        Each code signs you in once if you lose your phone. They are shown only now.
      </Typography.Paragraph>
      <div className="grid grid-cols-2 gap-2 rounded-lg bg-black/20 p-4 font-mono text-base">
        {codes.map((c) => (
          <span key={c}>{c}</span>
        ))}
      </div>
      <Button
        className="!mt-3"
        icon={<CopyOutlined />}
        onClick={() => {
          void navigator.clipboard.writeText(codes.join('\n'));
          message.success('Copied');
        }}
      >
        Copy all
      </Button>
    </Modal>
  );
}

function Enrol({ onEnabled }: { onEnabled: (codes: string[]) => void }) {
  const { message } = App.useApp();
  const { adoptTokens } = useAuth();
  const [setup, setSetup] = useState<{ secret: string; otpauth_uri: string } | null>(null);
  const [code, setCode] = useState('');
  const start = useMutation({
    mutationFn: async () => (await authApi.mfaSetup()).data,
    onSuccess: setSetup,
    onError: (e) => message.error(errorMessage(e)),
  });
  const enable = useMutation({
    mutationFn: async () => (await authApi.mfaEnable(code)).data,
    onSuccess: (data) => {
      if (data.tokens) adoptTokens(data.tokens.access_token, data.tokens.refresh_token);
      onEnabled(data.recovery_codes);
    },
    onError: (e) => {
      message.error(errorMessage(e));
      setCode('');
    },
  });

  if (!setup) {
    return (
      <Button type="primary" icon={<SafetyCertificateOutlined />} loading={start.isPending} onClick={() => start.mutate()}>
        Set up authenticator app
      </Button>
    );
  }
  return (
    <Steps
      orientation="vertical"
      current={1}
      items={[
        {
          title: 'Scan with Google Authenticator, Microsoft Authenticator, 1Password…',
          content: (
            <Space align="start" size="large" wrap className="!my-3">
              <QRCode value={setup.otpauth_uri} size={176} bgColor="#ffffff" color="#000000" />
              <div>
                <Typography.Text type="secondary">Can't scan? Enter this key:</Typography.Text>
                <Typography.Paragraph code copyable className="!mt-1 font-mono">
                  {setup.secret.match(/.{1,4}/g)?.join(' ')}
                </Typography.Paragraph>
              </div>
            </Space>
          ),
        },
        {
          title: 'Enter the 6-digit code it shows',
          content: (
            <Space.Compact className="!my-3">
              <Input
                aria-label="Code from app"
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={6}
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
                onPressEnter={() => code.length === 6 && enable.mutate()}
              />
              <Button type="primary" disabled={code.length !== 6} loading={enable.isPending} onClick={() => enable.mutate()}>
                Turn on
              </Button>
            </Space.Compact>
          ),
        },
      ]}
    />
  );
}

function CodePrompt({
  title,
  okText,
  danger,
  onSubmit,
  onClose,
}: {
  title: string;
  okText: string;
  danger?: boolean;
  onSubmit: (code: string) => Promise<unknown>;
  onClose: () => void;
}) {
  const { message } = App.useApp();
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  return (
    <Modal
      open
      title={title}
      okText={okText}
      okButtonProps={{ danger, disabled: code.trim().length < 6 }}
      confirmLoading={busy}
      onCancel={onClose}
      onOk={async () => {
        setBusy(true);
        try {
          await onSubmit(code);
        } catch (e) {
          message.error(errorMessage(e));
        } finally {
          setBusy(false);
        }
      }}
    >
      <Input
        aria-label="Authentication code"
        autoFocus
        placeholder="Code from your app"
        value={code}
        onChange={(e) => setCode(e.target.value)}
      />
    </Modal>
  );
}

export default function SecurityPage() {
  const { message } = App.useApp();
  const qc = useQueryClient();
  const { user, needsMfaEnrolment } = useAuth();
  const [codes, setCodes] = useState<string[] | null>(null);
  const [prompt, setPrompt] = useState<'disable' | 'regenerate' | null>(null);
  const status = useQuery({ queryKey: queryKeys.mfa, queryFn: async () => (await authApi.mfaStatus()).data });
  const refresh = () => void qc.invalidateQueries({ queryKey: queryKeys.mfa });

  return (
    <>
      <Typography.Title level={3}>Security</Typography.Title>
      {needsMfaEnrolment && (
        <Alert
          className="!mb-4"
          type="warning"
          showIcon
          title={`Your role (${user?.role}) requires multi-factor authentication. Set it up to continue using WardX.`}
        />
      )}
      <Card
        loading={status.isLoading}
        title={
          <Space>
            Two-step sign-in
            {status.data?.enabled ? (
              <Tag icon={<CheckCircleOutlined />} color="green">on</Tag>
            ) : (
              <Tag color="orange">off</Tag>
            )}
          </Space>
        }
        className="max-w-3xl"
      >
        {status.data?.enabled ? (
          <>
            <Typography.Paragraph>
              Signing in to the console and the SSH gateway asks for a code from your authenticator app.
              You have <b>{status.data.recovery_codes_left}</b> unused recovery codes.
            </Typography.Paragraph>
            <Space wrap>
              <Button onClick={() => setPrompt('regenerate')}>New recovery codes</Button>
              {!status.data.required && (
                <Button danger onClick={() => setPrompt('disable')}>Turn off</Button>
              )}
            </Space>
          </>
        ) : (
          <>
            <Typography.Paragraph>
              Add a second step to sign-in: after your password, enter a code from an authenticator
              app on your phone. This also applies when connecting through the SSH gateway.
            </Typography.Paragraph>
            <Enrol onEnabled={(c) => { setCodes(c); refresh(); }} />
          </>
        )}
      </Card>
      {codes && <RecoveryCodes codes={codes} onDone={() => setCodes(null)} />}
      {prompt === 'disable' && (
        <CodePrompt
          title="Turn off two-step sign-in"
          okText="Turn off"
          danger
          onClose={() => setPrompt(null)}
          onSubmit={async (c) => {
            await authApi.mfaDisable(c);
            message.success('Two-step sign-in is off');
            setPrompt(null);
            refresh();
          }}
        />
      )}
      {prompt === 'regenerate' && (
        <CodePrompt
          title="Replace recovery codes"
          okText="Generate"
          onClose={() => setPrompt(null)}
          onSubmit={async (c) => {
            const r = await authApi.mfaRecoveryCodes(c);
            setPrompt(null);
            setCodes(r.data.recovery_codes);
            refresh();
          }}
        />
      )}
    </>
  );
}
