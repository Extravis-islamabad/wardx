import { CopyOutlined, EyeInvisibleOutlined, EyeOutlined } from '@ant-design/icons';
import { App, Alert, Button, Descriptions, Input, Modal, Space } from 'antd';
import { useEffect, useState } from 'react';
import { errorMessage } from '@/lib/apiClient';
import { fmtTime } from '@/lib/format';
import { checkoutsApi } from '@/services/api';
import type { Checkout, RevealedSecret } from '@/types/api';

const AUTO_HIDE_SECONDS = 30;

/**
 * Fetches the secret only when opened (each reveal is audited), shows it masked,
 * and drops it from state when closed or after AUTO_HIDE_SECONDS.
 */
export function RevealModal({ checkout, onClose }: { checkout: Checkout | null; onClose: () => void }) {
  const { message } = App.useApp();
  const [secret, setSecret] = useState<RevealedSecret | null>(null);
  const [visible, setVisible] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [left, setLeft] = useState(AUTO_HIDE_SECONDS);

  useEffect(() => {
    setSecret(null);
    setVisible(false);
    setError(null);
    setLeft(AUTO_HIDE_SECONDS);
    if (!checkout) return;
    let cancelled = false;
    checkoutsApi
      .reveal(checkout.id)
      .then((r) => !cancelled && setSecret(r.data))
      .catch((e) => !cancelled && setError(errorMessage(e)));
    return () => {
      cancelled = true;
    };
  }, [checkout]);

  useEffect(() => {
    if (!secret) return;
    const t = setInterval(() => setLeft((s) => s - 1), 1000);
    return () => clearInterval(t);
  }, [secret]);

  useEffect(() => {
    if (left <= 0) onClose();
  }, [left, onClose]);

  const copy = async () => {
    if (!secret) return;
    await navigator.clipboard.writeText(secret.value);
    message.success('Copied — clear your clipboard when done');
  };

  return (
    <Modal
      open={!!checkout}
      title="Credential"
      onCancel={onClose}
      footer={<Button onClick={onClose}>Close</Button>}
      destroyOnHidden
    >
      {error && <Alert type="error" showIcon title={error} />}
      {checkout && (
        <Descriptions column={1} size="small" className="!mb-4">
          <Descriptions.Item label="Target">
            {checkout.account.target_name} ({checkout.account.target_address})
          </Descriptions.Item>
          <Descriptions.Item label="Username">{checkout.account.username}</Descriptions.Item>
          <Descriptions.Item label="Check-out ends">{fmtTime(checkout.expires_at)}</Descriptions.Item>
        </Descriptions>
      )}
      {secret && (
        <>
          <Space.Compact block>
            <Input
              readOnly
              value={visible ? secret.value : '•'.repeat(Math.min(secret.value.length, 24))}
              className="font-mono"
            />
            <Button
              icon={visible ? <EyeInvisibleOutlined /> : <EyeOutlined />}
              onClick={() => setVisible((v) => !v)}
            />
            <Button icon={<CopyOutlined />} onClick={() => void copy()} />
          </Space.Compact>
          <Alert
            className="!mt-3"
            type="info"
            showIcon
            title={`This reveal was recorded in the audit trail. Hides in ${left}s.`}
          />
        </>
      )}
    </Modal>
  );
}
