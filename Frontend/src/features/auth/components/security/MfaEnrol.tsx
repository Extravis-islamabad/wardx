import { SafetyCertificateOutlined } from '@ant-design/icons';
import { Input, QRCode, Space, Steps, Typography } from 'antd';
import { useState } from 'react';
import { Button } from '@/components';
import { useAuth } from '@/context/AuthContext';
import { MFA_CODE_LENGTH } from '@/features/auth/constants';
import { useEnableMfa, useStartMfaSetup } from '@/features/auth/hooks';
import type { MfaSetup } from '@/services/auth-services';
import { cssVar } from '@/theme';

const QR_SIZE = 176;

// Black on white in every theme: authenticator apps read a dark-on-light code most reliably.

/** Scan-then-confirm TOTP enrolment; hands the one-time recovery codes back. */
export function MfaEnrol({ onEnabled }: { onEnabled: (codes: string[]) => void }) {
  const { adoptTokens } = useAuth();
  const { mutateAsync: startSetup, isPending: starting } = useStartMfaSetup();
  const { mutateAsync: enableMfa, isPending: enabling } = useEnableMfa();
  const [setup, setSetup] = useState<MfaSetup | null>(null);
  const [code, setCode] = useState('');

  const start = async () => {
    try {
      setSetup(await startSetup());
    } catch {
      // apiClient's interceptor already toasted the failure.
    }
  };

  const enable = async () => {
    try {
      const result = await enableMfa(code);
      // Enabling rotates the session; the old tokens no longer carry the MFA claim.
      if (result?.tokens) adoptTokens(result.tokens.access_token, result.tokens.refresh_token);
      onEnabled(result?.recovery_codes ?? []);
    } catch {
      setCode('');
    }
  };

  if (!setup) {
    return (
      <Button variant="primary" icon={<SafetyCertificateOutlined />} loading={starting} onClick={() => void start()}>
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
              <QRCode
                value={setup.otpauth_uri}
                size={QR_SIZE}
                bgColor={cssVar('--qr-background')}
                color={cssVar('--qr-foreground')}
              />
              <div>
                <Typography.Text type="secondary">Can't scan? Enter this key:</Typography.Text>
                <Typography.Paragraph code copyable className="!mt-1 font-mono">
                  {setup.secret?.match(/.{1,4}/g)?.join(' ')}
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
                maxLength={MFA_CODE_LENGTH}
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
                onPressEnter={() => code.length === MFA_CODE_LENGTH && void enable()}
              />
              <Button
                variant="primary"
                disabled={code.length !== MFA_CODE_LENGTH}
                loading={enabling}
                onClick={() => void enable()}
              >
                Turn on
              </Button>
            </Space.Compact>
          ),
        },
      ]}
    />
  );
}

export default MfaEnrol;
