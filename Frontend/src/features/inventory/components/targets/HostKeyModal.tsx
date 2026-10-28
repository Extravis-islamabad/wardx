import { Alert, Checkbox, Descriptions, Modal, Spin } from 'antd';
import { useEffect, useState } from 'react';
import { Box, Button, ModalFooter, ModalTitle } from '@/components';
import { useAcceptTargetHostKey, useProbeTargetHostKey } from '@/features/inventory/hooks';
import type { HostKeyProbe, Target } from '@/services/inventory-services';
import { notify } from '@/utils/notify';

interface HostKeyModalProps {
  target: Target | null;
  onClose: () => void;
}

const Fingerprint = ({ value }: { value: string | null | undefined }) =>
  value ? <code className="break-all">{value}</code> : <>—</>;

/**
 * Pin (or re-pin) a target's SSH host key in two steps: read the key the device presents
 * (no credential is sent), then accept it only after comparing the fingerprint with the
 * device. The server pins it only if the device still presents exactly that fingerprint.
 */
export function HostKeyModal({ target, onClose }: HostKeyModalProps) {
  const [probe, setProbe] = useState<HostKeyProbe | null>(null);
  const [compared, setCompared] = useState(false);
  const { mutateAsync: readKey, isPending: reading, isError: readFailed } = useProbeTargetHostKey();
  const { mutateAsync: acceptKey, isPending: accepting } = useAcceptTargetHostKey();

  useEffect(() => {
    setProbe(null);
    setCompared(false);
    if (!target) return;
    readKey(target.id)
      .then((r) => setProbe(r.data))
      .catch(() => {
        // apiClient's interceptor already toasted the failure.
      });
  }, [target, readKey]);

  const accept = async () => {
    if (!target || !probe) return;
    try {
      const r = await acceptKey({ id: target.id, fingerprint: probe.presented_fingerprint });
      notify.success(r.message ?? 'Host key pinned');
      onClose();
    } catch {
      // apiClient's interceptor already toasted the failure (e.g. the key changed meanwhile).
    }
  };

  const alreadyPinned = probe?.matches_pin && !probe?.mismatch_at;

  return (
    <Modal
      open={target !== null}
      title={<ModalTitle>{target ? `Host key: ${target.name}` : 'Host key'}</ModalTitle>}
      onCancel={onClose}
      footer={null}
      destroyOnHidden
    >
      <Box className="px-2 border-0">
        {reading && (
          <div className="flex justify-center py-6">
            <Spin />
          </div>
        )}
        {readFailed && !reading && (
          <Alert type="error" showIcon title="Could not read the device's host key." />
        )}
        {probe && (
          <>
            {probe.mismatch_at && (
              <Alert
                className="!mb-3"
                type="error"
                showIcon
                title="The device presented a key other than the pinned one."
                description="Rotation and verify are blocked for this target until you compare and accept a key."
              />
            )}
            <Descriptions size="small" column={1} bordered>
              <Descriptions.Item label="Presented now">
                <Fingerprint value={probe.presented_fingerprint} /> ({probe.key_type})
              </Descriptions.Item>
              <Descriptions.Item label="Pinned">
                <Fingerprint value={probe.pinned_fingerprint} />
              </Descriptions.Item>
              {probe.mismatch_fingerprint && (
                <Descriptions.Item label="Mismatch seen">
                  <Fingerprint value={probe.mismatch_fingerprint} />
                </Descriptions.Item>
              )}
            </Descriptions>
            {alreadyPinned ? (
              <Alert className="!mt-3" type="success" showIcon title="The device presents the pinned key." />
            ) : (
              <>
                <Alert
                  className="!mt-3"
                  type="warning"
                  showIcon
                  title="Compare before accepting"
                  description={
                    <>
                      On the device console (not over this network path), show its key fingerprint, e.g.{' '}
                      <code>ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub</code> on Linux, and check it is
                      exactly the one presented above.
                    </>
                  }
                />
                <Checkbox className="!mt-3" checked={compared} onChange={(e) => setCompared(e.target.checked)}>
                  I compared this fingerprint with the device and it matches.
                </Checkbox>
              </>
            )}
          </>
        )}
        <ModalFooter>
          <Button variant="admin" size="small" onClick={onClose}>
            {alreadyPinned ? 'Close' : 'Cancel'}
          </Button>
          {probe && !alreadyPinned && (
            <Button
              variant="primary"
              size="small"
              disabled={!compared}
              loading={accepting}
              onClick={() => void accept()}
            >
              {probe.pinned_fingerprint ? 'Accept new key' : 'Accept key'}
            </Button>
          )}
        </ModalFooter>
      </Box>
    </Modal>
  );
}
