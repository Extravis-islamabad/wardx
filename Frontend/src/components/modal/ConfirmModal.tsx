import React, { useState } from 'react';
import { Modal } from 'antd';
import Box from '@/components/box';
import Button from '@/components/button';
import Text from '@/components/text';
import ModalTitle from '@/components/modal-title';
import { ModalFooter } from '@/components/form';

type Props = {
  open: boolean;
  title: string;
  description?: React.ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  /** Red confirm button, for anything that stops or removes something. */
  danger?: boolean;
  /** Resolved before the caller is expected to close — the button spins meanwhile. */
  onConfirm: () => void | Promise<void>;
  onCancel: () => void;
  width?: number;
};

/** The console's confirmation dialog — the same declarative shell every other modal uses. */
const ConfirmModal: React.FC<Props> = ({
  open,
  title,
  description,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  danger,
  onConfirm,
  onCancel,
  width = 440,
}) => {
  const [busy, setBusy] = useState(false);

  const handleConfirm = async () => {
    setBusy(true);
    try {
      await onConfirm?.();
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      centered
      destroyOnHidden
      footer={null}
      onCancel={onCancel}
      open={open}
      title={<ModalTitle>{title}</ModalTitle>}
      width={width}
    >
      <Box className="px-2 border-0">
        {description ? (
          <div className="mb-3 py-2">
            <Text as="div" variant="body_sm">
              {description}
            </Text>
          </div>
        ) : null}
        <ModalFooter>
          <Button variant="admin" size="small" onClick={onCancel}>
            {cancelLabel}
          </Button>
          <Button variant={danger ? 'danger' : 'primary'} size="small" loading={busy} onClick={handleConfirm}>
            {confirmLabel}
          </Button>
        </ModalFooter>
      </Box>
    </Modal>
  );
};

export default ConfirmModal;
