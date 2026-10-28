import { Input, Modal } from 'antd';
import { useEffect, useState } from 'react';
import { Box, Button, FormField, ModalFooter, ModalTitle } from '@/components';
import { MFA_CODE_LENGTH } from '@/features/auth/constants';

interface CodePromptModalProps {
  open: boolean;
  title: string;
  confirmLabel: string;
  danger?: boolean;
  /** Rejects to keep the modal open; the failure was already toasted. */
  onSubmit: (code: string) => Promise<unknown>;
  onClose: () => void;
}

/** Asks for a current authenticator code before an MFA change. */
export function CodePromptModal({ open, title, confirmLabel, danger, onSubmit, onClose }: CodePromptModalProps) {
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) setCode('');
  }, [open]);

  const submit = async () => {
    setBusy(true);
    try {
      await onSubmit(code);
    } catch {
      // apiClient's interceptor already toasted the failure.
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal open={open} title={<ModalTitle>{title}</ModalTitle>} onCancel={onClose} footer={null} destroyOnHidden>
      <Box className="px-2 border-0">
        <FormField label="Authentication code" htmlFor="mfa-prompt-code">
          <Input
            id="mfa-prompt-code"
            autoFocus
            placeholder="Code from your app"
            value={code}
            onChange={(e) => setCode(e.target.value)}
          />
        </FormField>
        <ModalFooter>
          <Button variant="admin" size="small" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant={danger ? 'danger' : 'primary'}
            size="small"
            disabled={code.trim().length < MFA_CODE_LENGTH}
            loading={busy}
            onClick={() => void submit()}
          >
            {confirmLabel}
          </Button>
        </ModalFooter>
      </Box>
    </Modal>
  );
}

export default CodePromptModal;
