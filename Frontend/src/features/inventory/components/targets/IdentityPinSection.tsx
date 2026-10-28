import { Alert, Checkbox, Descriptions, Spin, Typography } from 'antd';
import { useEffect, useState, type ReactNode } from 'react';
import { Button } from '@/components';
import type { Target } from '@/services/inventory-services';
import type { ApiResponse } from '@/types/api';
import { notify } from '@/utils/notify';

/** What every identity probe returns: the presented fingerprint next to the pin. */
export interface IdentityProbe {
  presented_fingerprint: string;
  pinned_fingerprint: string | null;
  matches_pin: boolean;
  mismatch_at: string | null;
  mismatch_fingerprint: string | null;
}

interface IdentityPinSectionProps<P extends IdentityProbe> {
  title: string;
  targetId: string;
  /** Reads what the device presents now; sends no credential and pins nothing. */
  probe: (id: string) => Promise<ApiResponse<P>>;
  accept: (args: { id: string; fingerprint: string }) => Promise<ApiResponse<Target>>;
  accepting: boolean;
  /** Extra rows about the presented identity (key type, certificate subject and expiry). */
  details?: (probe: P) => ReactNode;
  /** How to read the fingerprint on the device, to compare. */
  compareHint: ReactNode;
  mismatchTitle: string;
}

const Fingerprint = ({ value }: { value: string | null | undefined }) =>
  value ? <code className="break-all">{value}</code> : <>—</>;

/**
 * One pinned identity of a target (SSH host key or API-SSL certificate): read what the
 * device presents, compare it on the device, and accept it only after ticking that it
 * matches. The server pins it only if the device still presents exactly that fingerprint.
 */
export function IdentityPinSection<P extends IdentityProbe>({
  title,
  targetId,
  probe: readIdentity,
  accept,
  accepting,
  details,
  compareHint,
  mismatchTitle,
}: IdentityPinSectionProps<P>) {
  const [probe, setProbe] = useState<P | null>(null);
  const [reading, setReading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [compared, setCompared] = useState(false);

  useEffect(() => {
    let live = true;
    setProbe(null);
    setCompared(false);
    setFailed(false);
    setReading(true);
    readIdentity(targetId)
      .then((r) => live && setProbe(r.data))
      .catch(() => live && setFailed(true)) // apiClient's interceptor already toasted it
      .finally(() => live && setReading(false));
    return () => {
      live = false;
    };
  }, [targetId, readIdentity]);

  const onAccept = async () => {
    if (!probe) return;
    try {
      const r = await accept({ id: targetId, fingerprint: probe.presented_fingerprint });
      notify.success(r.message ?? `${title} pinned`);
      // Shown as pinned; the dialog stays open for the other identity.
      setProbe({
        ...probe,
        pinned_fingerprint: probe.presented_fingerprint,
        matches_pin: true,
        mismatch_at: null,
        mismatch_fingerprint: null,
      });
    } catch {
      // Toasted by the interceptor (e.g. the device changed it meanwhile).
    }
  };

  const alreadyPinned = probe?.matches_pin && !probe?.mismatch_at;

  return (
    <div className="mb-4">
      <Typography.Title level={5}>{title}</Typography.Title>
      {reading && (
        <div className="flex justify-center py-4">
          <Spin />
        </div>
      )}
      {failed && !reading && (
        <Alert type="error" showIcon title={`Could not read the device's ${title.toLowerCase()}.`} />
      )}
      {probe && (
        <>
          {probe.mismatch_at && (
            <Alert
              className="!mb-3"
              type="error"
              showIcon
              title={mismatchTitle}
              description="Rotation and verify are blocked for this target until you compare and accept one."
            />
          )}
          <Descriptions size="small" column={1} bordered>
            <Descriptions.Item label="Presented now">
              <Fingerprint value={probe.presented_fingerprint} />
            </Descriptions.Item>
            {details?.(probe)}
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
            <Alert className="!mt-3" type="success" showIcon title="The device presents the pinned one." />
          ) : (
            <>
              <Alert className="!mt-3" type="warning" showIcon title="Compare before accepting" description={compareHint} />
              <div className="mt-3 flex items-center justify-between gap-3">
                <Checkbox checked={compared} onChange={(e) => setCompared(e.target.checked)}>
                  I compared this fingerprint with the device and it matches.
                </Checkbox>
                <Button variant="primary" size="small" disabled={!compared} loading={accepting} onClick={() => void onAccept()}>
                  {probe.pinned_fingerprint ? 'Accept new' : 'Accept'}
                </Button>
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}

export default IdentityPinSection;
