import { Tooltip } from 'antd';
import { StatusTag } from '@/components';
import { SAFE_HEALTH_TAG, type SafeHealthState } from '@/constants/enums/safes';

/** healthy / break-glass only (warning) / unreachable (critical). */
export function SafeHealthTag({ state }: { state: SafeHealthState | null | undefined }) {
  if (!state) return null;
  const tag = SAFE_HEALTH_TAG[state];
  return (
    <Tooltip title={tag.hint}>
      <StatusTag label={tag.label} variant={tag.variant} />
    </Tooltip>
  );
}

export default SafeHealthTag;
