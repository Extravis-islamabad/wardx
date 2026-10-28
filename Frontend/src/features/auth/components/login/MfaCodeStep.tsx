import { KeyOutlined } from '@ant-design/icons';
import { Alert, Input } from 'antd';
import { useState, type FormEvent } from 'react';
import { Button, FormField, Text } from '@/components';
import { useAuth } from '@/context/AuthContext';
import { MFA_CODE_LENGTH, MFA_CODE_MAX_LENGTH } from '@/features/auth/constants';
import { errorMessage } from '@/utils/notifyApiError';

/** Second sign-in step: a TOTP or recovery code for the pending MFA token. */
export function MfaCodeStep() {
  const { verifyCode, cancelCode } = useAuth();
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await verifyCode(code);
    } catch (err) {
      setError(errorMessage(err));
      setCode('');
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <Text variant="caption" className="mb-4 text-center">
        Enter the 6-digit code from your authenticator app, or a recovery code.
      </Text>
      {error && <Alert className="!mb-4" type="error" showIcon title={error} />}
      <form onSubmit={(e) => void submit(e)}>
        <FormField label="Authentication code" htmlFor="mfa-code" className="mb-6">
          <Input
            id="mfa-code"
            prefix={<KeyOutlined />}
            autoFocus
            autoComplete="one-time-code"
            inputMode="numeric"
            maxLength={MFA_CODE_MAX_LENGTH}
            value={code}
            onChange={(e) => setCode(e.target.value)}
          />
        </FormField>
        <Button variant="primary" type="submit" block loading={busy} disabled={code.trim().length < MFA_CODE_LENGTH}>
          Verify
        </Button>
        <Button variant="ghost" block className="!mt-2" onClick={cancelCode}>
          Use a different account
        </Button>
      </form>
    </>
  );
}

export default MfaCodeStep;
