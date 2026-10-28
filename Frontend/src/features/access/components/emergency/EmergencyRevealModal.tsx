import { zodResolver } from '@hookform/resolvers/zod';
import { CopyOutlined, EyeInvisibleOutlined, EyeOutlined } from '@ant-design/icons';
import { Alert, Button as AntdButton, Input, Modal, Select, Space } from 'antd';
import { useEffect, useState } from 'react';
import { Controller, useForm } from 'react-hook-form';
import { Box, Button, FormField, ModalFooter, ModalTitle } from '@/components';
import { REVEAL_AUTO_HIDE_SECONDS } from '@/features/access/constants';
import { useEmergencyAccounts, useEmergencyReveal } from '@/features/access/hooks';
import { emergencyRevealSchema, type EmergencyRevealValues } from '@/features/access/schemas/emergencySchema';
import type { RevealedSecret } from '@/services/access-services';
import type { Account } from '@/services/inventory-services';
import { notify } from '@/utils/notify';

const MASK_MAX_LENGTH = 24;

const PICK_PAGE = { page: 1, page_size: 50 } as const;

interface EmergencyRevealModalProps {
  open: boolean;
  /** Preselected account; without one the holder picks any account, whatever its safe. */
  account: Account | null;
  onClose: () => void;
}

/** Break-glass: an account and a reason first, then the secret (dropped on close or after the timer). */
export function EmergencyRevealModal({ open, account: preselected, onClose }: EmergencyRevealModalProps) {
  const { mutateAsync: reveal, isPending } = useEmergencyReveal();
  const [picked, setPicked] = useState<Account | null>(null);
  const [search, setSearch] = useState('');
  const candidates = useEmergencyAccounts({ ...PICK_PAGE, search: search || undefined }, open && !preselected);
  const account = preselected ?? picked;
  const [secret, setSecret] = useState<RevealedSecret | null>(null);
  const [visible, setVisible] = useState(false);
  const [left, setLeft] = useState(REVEAL_AUTO_HIDE_SECONDS);
  const {
    control,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<EmergencyRevealValues>({ resolver: zodResolver(emergencyRevealSchema), defaultValues: { reason: '' } });

  useEffect(() => {
    setSecret(null);
    setVisible(false);
    setLeft(REVEAL_AUTO_HIDE_SECONDS);
    setPicked(null);
    reset({ reason: '' });
  }, [open, preselected, reset]);

  useEffect(() => {
    if (!secret) return;
    const t = setInterval(() => setLeft((s) => s - 1), 1000);
    return () => clearInterval(t);
  }, [secret]);

  useEffect(() => {
    if (secret && left <= 0) onClose();
  }, [secret, left, onClose]);

  const onSubmit = async ({ reason }: EmergencyRevealValues) => {
    if (!account) {
      notify.error('Choose the account first');
      return;
    }
    try {
      setSecret(await reveal({ accountId: account.id, reason }));
    } catch {
      // apiClient's interceptor already toasted the failure.
    }
  };

  const copy = async () => {
    if (!secret) return;
    await navigator.clipboard.writeText(secret.value);
    notify.success('Copied — clear your clipboard when done');
  };

  return (
    <Modal
      open={open}
      title={
        <ModalTitle>
          {account ? `Break glass: ${account.username}@${account.target?.name}` : 'Break glass'}
        </ModalTitle>
      }
      onCancel={onClose}
      footer={null}
      destroyOnHidden
    >
      <Box className="px-2 border-0">
        {!secret ? (
          <>
            <Alert
              className="!mb-3"
              type="error"
              showIcon
              title="Emergency access bypasses safe membership."
              description="The reveal is recorded as an emergency check-out, audited with your reason, and raises a high-severity alert for the security team."
            />
            {!preselected && (
              <FormField label="Account (any safe)" htmlFor="emergency-account" required>
                <Select
                  id="emergency-account"
                  className="w-full"
                  showSearch
                  filterOption={false}
                  onSearch={setSearch}
                  loading={candidates.isLoading}
                  value={picked?.id}
                  placeholder="Search by account, target or address"
                  onChange={(id) => setPicked(candidates.data?.data?.find((a) => a.id === id) ?? null)}
                  options={candidates.data?.data?.map((a) => ({
                    value: a.id,
                    label: `${a.username}@${a.target?.name} — ${a.safe?.name}`,
                    disabled: !a.has_secret,
                  }))}
                />
              </FormField>
            )}
            <FormField label="Reason" htmlFor="emergency-reason" required error={errors.reason?.message}>
              <Controller
                control={control}
                name="reason"
                render={({ field }) => (
                  <Input.TextArea
                    {...field}
                    id="emergency-reason"
                    rows={3}
                    placeholder="Incident, ticket and why normal access is not possible"
                    status={errors.reason ? 'error' : undefined}
                  />
                )}
              />
            </FormField>
          </>
        ) : (
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
              type="warning"
              showIcon
              title={`Emergency reveal recorded and alerted. Hides in ${left}s.`}
            />
            {secret.notice && (
              <Alert className="!mt-3" type="error" showIcon title="Rotation status" description={secret.notice} />
            )}
          </>
        )}
        <ModalFooter>
          <Button variant="admin" size="small" onClick={onClose}>
            {secret ? 'Close' : 'Cancel'}
          </Button>
          {!secret && (
            <Button variant="danger" size="small" loading={isPending} onClick={handleSubmit(onSubmit)}>
              Reveal
            </Button>
          )}
        </ModalFooter>
      </Box>
    </Modal>
  );
}

export default EmergencyRevealModal;
