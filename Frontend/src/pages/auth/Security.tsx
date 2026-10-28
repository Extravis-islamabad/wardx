import { Alert, Card, Space, Typography } from 'antd';
import { useState } from 'react';
import { Button, PageShell, StatusTag } from '@/components';
import { StatusVariant } from '@/constants/enums/status';
import { useAuth } from '@/context/AuthContext';
import { CodePromptModal, MfaEnrol, RecoveryCodesModal } from '@/features/auth/components';
import { MfaPromptMode } from '@/features/auth/constants';
import { useDisableMfa, useMfaStatus, useRegenerateRecoveryCodes } from '@/features/auth/hooks';
import { notify } from '@/utils/notify';

export default function Security() {
  const { user, needsMfaEnrolment } = useAuth();
  const [codes, setCodes] = useState<string[] | null>(null);
  const [prompt, setPrompt] = useState<MfaPromptMode | null>(null);
  const status = useMfaStatus();
  const { mutateAsync: disableMfa } = useDisableMfa();
  const { mutateAsync: regenerateCodes } = useRegenerateRecoveryCodes();
  const enabled = !!status.data?.enabled;

  return (
    <PageShell title="Security">
      {needsMfaEnrolment && (
        <Alert
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
            <StatusTag label={enabled ? 'on' : 'off'} variant={enabled ? StatusVariant.SUCCESS : StatusVariant.WARNING} />
          </Space>
        }
        className="max-w-3xl"
      >
        {enabled ? (
          <>
            <Typography.Paragraph>
              Signing in to the console and the SSH gateway asks for a code from your authenticator app. You have{' '}
              <b>{status.data?.recovery_codes_left ?? 0}</b> unused recovery codes.
            </Typography.Paragraph>
            <Space wrap>
              <Button variant="admin" onClick={() => setPrompt(MfaPromptMode.REGENERATE)}>
                New recovery codes
              </Button>
              {!status.data?.required && (
                <Button variant="danger" onClick={() => setPrompt(MfaPromptMode.DISABLE)}>
                  Turn off
                </Button>
              )}
            </Space>
          </>
        ) : (
          <>
            <Typography.Paragraph>
              Add a second step to sign-in: after your password, enter a code from an authenticator app on your phone.
              This also applies when connecting through the SSH gateway.
            </Typography.Paragraph>
            <MfaEnrol onEnabled={setCodes} />
          </>
        )}
      </Card>
      <RecoveryCodesModal codes={codes} onDone={() => setCodes(null)} />
      <CodePromptModal
        open={prompt === MfaPromptMode.DISABLE}
        title="Turn off two-step sign-in"
        confirmLabel="Turn off"
        danger
        onClose={() => setPrompt(null)}
        onSubmit={async (c) => {
          await disableMfa(c);
          notify.success('Two-step sign-in is off');
          setPrompt(null);
        }}
      />
      <CodePromptModal
        open={prompt === MfaPromptMode.REGENERATE}
        title="Replace recovery codes"
        confirmLabel="Generate"
        onClose={() => setPrompt(null)}
        onSubmit={async (c) => {
          const r = await regenerateCodes(c);
          setPrompt(null);
          setCodes(r?.recovery_codes ?? []);
        }}
      />
    </PageShell>
  );
}
