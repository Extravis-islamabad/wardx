import { Descriptions, Modal } from 'antd';
import { Box, Button, ModalFooter, ModalTitle } from '@/components';
import { usesTlsApi } from '@/constants/enums/inventory';
import {
  useAcceptTargetHostKey,
  useAcceptTargetTlsCert,
  useProbeTargetHostKey,
  useProbeTargetTlsCert,
} from '@/features/inventory/hooks';
import type { Target } from '@/services/inventory-services';
import { fmtTime } from '@/utils/format';
import { IdentityPinSection } from './IdentityPinSection';

interface HostKeyModalProps {
  target: Target | null;
  onClose: () => void;
}

/**
 * Pin (or re-pin) a target's identities, each in two steps: read what the device presents
 * (no credential is sent), then accept it only after comparing the fingerprint with the
 * device. SSH targets pin their host key; MikroTik targets also pin the API-SSL
 * certificate, and rotation is refused until both are pinned.
 */
export function HostKeyModal({ target, onClose }: HostKeyModalProps) {
  const { mutateAsync: probeKey } = useProbeTargetHostKey();
  const { mutateAsync: acceptKey, isPending: acceptingKey } = useAcceptTargetHostKey();
  const { mutateAsync: probeCert } = useProbeTargetTlsCert();
  const { mutateAsync: acceptCert, isPending: acceptingCert } = useAcceptTargetTlsCert();
  const withCert = !!target && usesTlsApi(target.platform) && target.api_tls !== false;

  return (
    <Modal
      open={target !== null}
      title={<ModalTitle>{target ? `Host key: ${target.name}` : 'Host key'}</ModalTitle>}
      onCancel={onClose}
      footer={null}
      width={withCert ? 720 : 560}
      destroyOnHidden
    >
      {target && (
        <Box className="px-2 border-0">
          <IdentityPinSection
            title="SSH host key"
            targetId={target.id}
            probe={probeKey}
            accept={acceptKey}
            accepting={acceptingKey}
            mismatchTitle="The device presented a host key other than the pinned one."
            details={(p) => <Descriptions.Item label="Key type">{p.key_type}</Descriptions.Item>}
            compareHint={
              <>
                Compare it with the fingerprint read on the device itself or over a trusted path (not this network
                path), e.g. <code>ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub</code> on Linux, and check it is
                exactly the one presented above.
              </>
            }
          />
          {withCert && (
            <IdentityPinSection
              title="API-SSL certificate"
              targetId={target.id}
              probe={probeCert}
              accept={acceptCert}
              accepting={acceptingCert}
              mismatchTitle="The device presented an API-SSL certificate other than the pinned one."
              details={(p) => (
                <>
                  <Descriptions.Item label="Subject">{p.subject}</Descriptions.Item>
                  <Descriptions.Item label="Valid until">{p.not_after ? fmtTime(p.not_after) : '—'}</Descriptions.Item>
                </>
              )}
              compareHint={
                <>
                  On the device console, run <code>/certificate print detail where name=&lt;api-ssl certificate&gt;</code>{' '}
                  and check its <code>fingerprint</code> is the one presented above (RouterOS prints it in lower case
                  without colons). Rotation is refused until both identities are pinned.
                </>
              }
            />
          )}
          <ModalFooter>
            <Button variant="admin" size="small" onClick={onClose}>
              Close
            </Button>
          </ModalFooter>
        </Box>
      )}
    </Modal>
  );
}
