import { CopyOutlined, EyeInvisibleOutlined, EyeOutlined } from '@ant-design/icons';
import { Alert, Button as AntdButton, Descriptions, Input, Modal, Space } from 'antd';
import { useEffect, useState } from 'react';
import { Box, Button, ModalFooter, ModalTitle } from '@/components';
import type { NewAppSecret } from '@/services/provider-services';
import { notify } from '@/utils/notify';

const MASK = '•'.repeat(24);

/** A new client secret, shown once: WardX keeps only its hash and can never show it again. */
export function SecretOnceModal({ created, onClose }: { created: NewAppSecret | null; onClose: () => void }) {
  const [visible, setVisible] = useState(false);
  useEffect(() => setVisible(false), [created]);

  const copy = async (value: string, what: string) => {
    await navigator.clipboard.writeText(value);
    notify.success(`${what} copied — clear your clipboard when done`);
  };

  return (
    <Modal
      open={!!created}
      title={<ModalTitle>{`Client secret for ${created?.app.name ?? ''}`}</ModalTitle>}
      onCancel={onClose}
      footer={null}
      maskClosable={false}
      destroyOnHidden
      width={620}
    >
      <Box className="px-2 border-0">
        <Alert
          className="!mb-3"
          type="warning"
          showIcon
          title="Copy the client secret now. It is shown only once; WardX stores only a hash of it."
          description="Put it in the collector's secret store or environment, never in MonetX's database or a ticket."
        />
        {created && (
          <Descriptions column={1} size="small" className="!mb-3">
            <Descriptions.Item label="client_id">
              <Space.Compact block>
                <Input readOnly value={created.client_id} className="font-mono" />
                <AntdButton
                  aria-label="Copy client id"
                  icon={<CopyOutlined />}
                  onClick={() => void copy(created.client_id, 'Client id')}
                />
              </Space.Compact>
            </Descriptions.Item>
            <Descriptions.Item label="client_secret">
              <Space.Compact block>
                <Input readOnly value={visible ? created.client_secret : MASK} className="font-mono" />
                <AntdButton
                  aria-label={visible ? 'Hide secret' : 'Show secret'}
                  icon={visible ? <EyeInvisibleOutlined /> : <EyeOutlined />}
                  onClick={() => setVisible((v) => !v)}
                />
                <AntdButton
                  aria-label="Copy client secret"
                  icon={<CopyOutlined />}
                  onClick={() => void copy(created.client_secret, 'Client secret')}
                />
              </Space.Compact>
            </Descriptions.Item>
          </Descriptions>
        )}
        <ModalFooter>
          <Button variant="primary" size="small" onClick={onClose}>
            I have stored it
          </Button>
        </ModalFooter>
      </Box>
    </Modal>
  );
}

export default SecretOnceModal;
