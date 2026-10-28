import { CopyOutlined, EyeInvisibleOutlined, EyeOutlined } from '@ant-design/icons';
import { Alert, Button as AntdButton, Descriptions, Input, Modal, Space } from 'antd';
import { useEffect, useState } from 'react';
import { Box, Button, ModalFooter, ModalTitle } from '@/components';
import { REVEAL_AUTO_HIDE_SECONDS } from '@/features/access/constants';
import { useRevealCheckout } from '@/features/access/hooks';
import type { Checkout, RevealedSecret } from '@/services/access-services';
import { fmtTime } from '@/utils/format';
import { notify } from '@/utils/notify';
import { errorMessage } from '@/utils/notifyApiError';

const MASK_MAX_LENGTH = 24;

/** Fetches the secret only when opened (each reveal is audited) and drops it on close or after the timer. */
export function RevealModal({ checkout, onClose }: { checkout: Checkout | null; onClose: () => void }) {
  const { mutateAsync: reveal } = useRevealCheckout();
  const [secret, setSecret] = useState<RevealedSecret | null>(null);
  const [visible, setVisible] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [left, setLeft] = useState(REVEAL_AUTO_HIDE_SECONDS);

  useEffect(() => {
    setSecret(null);
    setVisible(false);
    setError(null);
    setLeft(REVEAL_AUTO_HIDE_SECONDS);
    if (!checkout) return;
    let cancelled = false;
    reveal(checkout.id)
      .then((s) => !cancelled && setSecret(s))
      .catch((e: unknown) => !cancelled && setError(errorMessage(e)));
    return () => {
      cancelled = true;
    };
  }, [checkout, reveal]);

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
    notify.success('Copied — clear your clipboard when done');
  };

  return (
    <Modal open={!!checkout} title={<ModalTitle>Credential</ModalTitle>} onCancel={onClose} footer={null} destroyOnHidden>
      <Box className="px-2 border-0">
        {error && <Alert type="error" showIcon title={error} />}
        {checkout && (
          <Descriptions column={1} size="small" className="!mb-4">
            <Descriptions.Item label="Target">
              {checkout.account?.target_name} ({checkout.account?.target_address})
            </Descriptions.Item>
            <Descriptions.Item label="Username">{checkout.account?.username}</Descriptions.Item>
            <Descriptions.Item label="Check-out ends">{fmtTime(checkout.expires_at)}</Descriptions.Item>
          </Descriptions>
        )}
        {secret && (
          <>
            <Space.Compact block>
              <Input
                readOnly
                value={visible ? secret.value : '•'.repeat(Math.min(secret.value?.length ?? 0, MASK_MAX_LENGTH))}
                className="font-mono"
              />
              <AntdButton
                aria-label={visible ? 'Hide secret' : 'Show secret'}
                icon={visible ? <EyeInvisibleOutlined /> : <EyeOutlined />}
                onClick={() => setVisible((v) => !v)}
              />
              <AntdButton aria-label="Copy secret" icon={<CopyOutlined />} onClick={() => void copy()} />
            </Space.Compact>
            <Alert
              className="!mt-3"
              type="info"
              showIcon
              title={`This reveal was recorded in the audit trail. Hides in ${left}s.`}
            />
          </>
        )}
        <ModalFooter>
          <Button variant="admin" size="small" onClick={onClose}>
            Close
          </Button>
        </ModalFooter>
      </Box>
    </Modal>
  );
}

export default RevealModal;
