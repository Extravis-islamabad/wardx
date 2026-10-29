import { Alert, Checkbox, Input, Modal } from 'antd';
import { useEffect, useState } from 'react';
import { Box, Button, FormField, ModalFooter, ModalTitle } from '@/components';
import { MIN_CONFIRM_REASON } from '@/features/rotation/constants';
import { useAccountRotation, useConfirmRotation, useRequestRotation } from '@/features/rotation/hooks';
import type { RotationOperation } from '@/services/rotation-services';
import { notify } from '@/utils/notify';

export type RotationAction = RotationOperation | 'confirm';

const TITLES: Record<RotationAction, string> = {
  rotate: 'Rotate the password now',
  verify: 'Verify the password on the device',
  reconcile: 'Reconcile through the reconcile account',
  confirm: 'Confirm despite a failed negative check',
};

const HELP: Record<RotationAction, string> = {
  rotate:
    'A new password is stored in the vault first, then set on the device and verified (a login with it, then one login with a wrong password that must be refused). It waits until every holder has released the account.',
  verify: 'A fresh login with the current password, then exactly one login with a wrong password that must be refused.',
  reconcile:
    'The reconcile account sets a new password on the device (the unknown old one is never used), then it is verified. Using the reconcile account is audited and is not a check-out.',
  confirm:
    'The device accepted a wrong password, so a login proves nothing. Confirming accepts that risk: normal access returns, but the account stays on the dashboard until a later clean verify.',
};

interface Props {
  accountId: string;
  action: RotationAction | null;
  onClose: () => void;
}

/** Asks for the reason, then queues a rotate / verify / reconcile, or confirms a risk. */
export function RotationActionModal({ accountId, action, onClose }: Props) {
  const [reason, setReason] = useState('');
  const [dryRun, setDryRun] = useState(false);
  const request = useRequestRotation(accountId);
  const confirm = useConfirmRotation(accountId);
  // DR lag (HA_DR.md §6.1): shown before an on-demand rotation is confirmed.
  const drWarning = useAccountRotation(accountId).data?.dr_lag_warning ?? null;
  const changesDevice = action === 'rotate' || action === 'reconcile';
  useEffect(() => {
    setReason('');
    setDryRun(false);
  }, [action]);
  if (!action) return null;
  const min = action === 'confirm' ? MIN_CONFIRM_REASON : 3;
  const short = reason.trim().length < min;

  const submit = async () => {
    try {
      if (action === 'confirm') {
        await confirm.mutateAsync(reason.trim());
        notify.success('Confirmed: risk accepted');
      } else {
        const job = await request.mutateAsync({ op: action, reason: reason.trim(), dryRun });
        notify.success(`${action.charAt(0).toUpperCase()}${action.slice(1)} queued`);
        if (job.data?.dr_lag_warning) notify.warning(job.data.dr_lag_warning);
      }
      onClose();
    } catch {
      // apiClient's interceptor already toasted the failure.
    }
  };

  return (
    <Modal open title={<ModalTitle>{TITLES[action]}</ModalTitle>} onCancel={onClose} footer={null} destroyOnHidden>
      <Box className="px-2 border-0">
        <Alert className="!mb-3" type={action === 'confirm' ? 'warning' : 'info'} showIcon title={HELP[action]} />
        {changesDevice && drWarning && (
          <Alert className="!mb-3" type="warning" showIcon title="DR replication is behind" description={drWarning} />
        )}
        <FormField
          label={action === 'confirm' ? 'Why is accepting this risk right? (audited)' : 'Reason (audited)'}
          htmlFor="rotation-reason"
          required
          hint={`At least ${min} characters (${reason.trim().length} so far)`}
        >
          <Input.TextArea id="rotation-reason" rows={3} maxLength={1000} value={reason} onChange={(e) => setReason(e.target.value)} />
        </FormField>
        {action === 'rotate' && (
          <Checkbox checked={dryRun} onChange={(e) => setDryRun(e.target.checked)}>
            Dry run: connect and verify only, change nothing
          </Checkbox>
        )}
        <ModalFooter>
          <Button variant="admin" size="small" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant={action === 'confirm' ? 'danger' : 'primary'}
            size="small"
            disabled={short}
            loading={request.isPending || confirm.isPending}
            onClick={submit}
          >
            {action === 'confirm' ? 'Accept the risk' : 'Queue'}
          </Button>
        </ModalFooter>
      </Box>
    </Modal>
  );
}

export default RotationActionModal;
