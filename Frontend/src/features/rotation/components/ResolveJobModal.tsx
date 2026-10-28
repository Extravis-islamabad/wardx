import { Alert, Input, Modal, Radio, Space } from 'antd';
import { useEffect, useState } from 'react';
import { Box, Button, FormField, ModalFooter, ModalTitle } from '@/components';
import { useResolveRotation } from '@/features/rotation/hooks';
import type { Resolution, RotationJob } from '@/services/rotation-services';
import { notify } from '@/utils/notify';

const OPTIONS: { value: Resolution; label: string }[] = [
  { value: 'keep_current', label: 'The device still uses the current version (v{from})' },
  { value: 'use_candidate', label: 'The device uses the new candidate (v{candidate})' },
  { value: 'set_secret', label: 'I set the password on the device by hand: store it' },
  { value: 'reconcile', label: 'Reconcile through the reconcile account' },
];

/** Resolves a job that needs attention (both versions were kept; nothing is deleted). */
export function ResolveJobModal({ job, onClose }: { job: RotationJob | null; onClose: () => void }) {
  const [action, setAction] = useState<Resolution>('keep_current');
  const [note, setNote] = useState('');
  const [secret, setSecret] = useState('');
  const resolve = useResolveRotation();
  useEffect(() => {
    setAction('keep_current');
    setNote('');
    setSecret('');
  }, [job]);
  if (!job) return null;
  const invalid = note.trim().length < 3 || (action === 'set_secret' && !secret.trim());

  const submit = async () => {
    try {
      await resolve.mutateAsync({ jobId: job.id, action, note: note.trim(), secret: action === 'set_secret' ? secret : undefined });
      notify.success('Resolved');
      onClose();
    } catch {
      // apiClient's interceptor already toasted the failure.
    }
  };

  return (
    <Modal open title={<ModalTitle>Resolve rotation of {job.account_username}</ModalTitle>} onCancel={onClose} footer={null} destroyOnHidden>
      <Box className="px-2 border-0">
        <Alert className="!mb-3" type="warning" showIcon title={job.detail ?? 'This rotation needs attention'} />
        <FormField label="What is on the device now?" htmlFor="resolve-action">
          <Radio.Group id="resolve-action" value={action} onChange={(e) => setAction(e.target.value)}>
            <Space orientation="vertical">
              {OPTIONS.filter((o) => o.value !== 'use_candidate' || job.candidate_version).map((o) => (
                <Radio key={o.value} value={o.value}>
                  {o.label.replace('{from}', String(job.from_version ?? '?')).replace('{candidate}', String(job.candidate_version ?? '?'))}
                </Radio>
              ))}
            </Space>
          </Radio.Group>
        </FormField>
        {action === 'set_secret' && (
          <FormField label="Password now on the device" htmlFor="resolve-secret" required>
            <Input.Password id="resolve-secret" autoComplete="new-password" value={secret} onChange={(e) => setSecret(e.target.value)} />
          </FormField>
        )}
        <FormField label="Note (audited)" htmlFor="resolve-note" required>
          <Input.TextArea id="resolve-note" rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
        </FormField>
        <ModalFooter>
          <Button variant="admin" size="small" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" size="small" disabled={invalid} loading={resolve.isPending} onClick={submit}>
            Resolve
          </Button>
        </ModalFooter>
      </Box>
    </Modal>
  );
}

export default ResolveJobModal;
