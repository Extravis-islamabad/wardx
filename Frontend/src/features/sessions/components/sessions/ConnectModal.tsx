import { Modal, Typography } from 'antd';
import { Box, Button, ModalFooter, ModalTitle, Text } from '@/components';
import { useAuth } from '@/context/AuthContext';
import { useGatewayInfo } from '@/features/sessions/hooks';
import type { Account } from '@/services/inventory-services';

/** How to reach an account through the SSH gateway with the vaulted credential. */
export function ConnectModal({ account, onClose }: { account: Account | null; onClose: () => void }) {
  const { user } = useAuth();
  const info = useGatewayInfo();
  const command =
    info.data && account
      ? `ssh -p ${info.data.port} ${user?.username}%${account.username}%${account.target?.name}@${info.data.host}`
      : '';

  return (
    <Modal
      open={!!account}
      title={<ModalTitle>{`Connect to ${account?.username}@${account?.target?.name}`}</ModalTitle>}
      onCancel={onClose}
      footer={null}
      destroyOnHidden
    >
      <Box className="px-2 border-0">
        <Text className="mb-3">Run this in your terminal and sign in with your WardX password:</Text>
        <Typography.Paragraph code copyable className="!text-base">
          {command}
        </Typography.Paragraph>
        <Text variant="caption">
          The gateway logs you in with the vaulted credential; you never see it. The session is recorded and command
          policy applies.{' '}
          {account?.requires_approval
            ? 'This account needs an approved request first.'
            : 'The account is checked out for the session and checked back in when you disconnect.'}
        </Text>
        <ModalFooter>
          <Button variant="admin" size="small" onClick={onClose}>
            Close
          </Button>
        </ModalFooter>
      </Box>
    </Modal>
  );
}

export default ConnectModal;
