import { CopyOutlined } from '@ant-design/icons';
import { Modal } from 'antd';
import { Box, Button, ModalFooter, ModalTitle, Text } from '@/components';
import { RECOVERY_CODES_COPIED } from '@/features/auth/constants';
import { notify } from '@/utils/notify';

/** Shown once after enrolling or regenerating; it can only be dismissed by confirming. */
export function RecoveryCodesModal({ codes, onDone }: { codes: string[] | null; onDone: () => void }) {
  return (
    <Modal
      open={!!codes}
      closable={false}
      mask={{ closable: false }}
      title={<ModalTitle>Save your recovery codes</ModalTitle>}
      footer={null}
    >
      <Box className="px-2 border-0">
        <Text className="mb-3">Each code signs you in once if you lose your phone. They are shown only now.</Text>
        <div className="grid grid-cols-2 gap-2 rounded-lg bg-(--code-surface) p-4 font-mono text-base">
          {codes?.map((c) => (
            <span key={c}>{c}</span>
          ))}
        </div>
        <ModalFooter
          start={
            <Button
              variant="admin"
              size="small"
              icon={<CopyOutlined />}
              onClick={() => {
                void navigator.clipboard.writeText(codes?.join('\n') ?? '');
                notify.success(RECOVERY_CODES_COPIED);
              }}
            >
              Copy all
            </Button>
          }
        >
          <Button variant="primary" size="small" onClick={onDone}>
            I have saved them
          </Button>
        </ModalFooter>
      </Box>
    </Modal>
  );
}

export default RecoveryCodesModal;
