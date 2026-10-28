import { StatusVariant } from '@/constants/enums/status';

/** Rotation job states and account sync states (Backend/docs/phase1/ROTATION.md). */
export const JOB_STATUS_VARIANT: Record<string, StatusVariant> = {
  pending: StatusVariant.WARNING,
  waiting_release: StatusVariant.WARNING,
  running: StatusVariant.INFO,
  candidate_stored: StatusVariant.INFO,
  device_changed: StatusVariant.INFO,
  persisted: StatusVariant.INFO,
  succeeded: StatusVariant.SUCCESS,
  changed_unverified: StatusVariant.DANGER,
  failed: StatusVariant.WARNING,
  needs_attention: StatusVariant.DANGER,
  resolved: StatusVariant.NEUTRAL,
  cancelled: StatusVariant.NEUTRAL,
};

export const SYNC_VARIANT: Record<string, StatusVariant> = {
  unknown: StatusVariant.OUTLINE,
  in_sync: StatusVariant.SUCCESS,
  out_of_sync: StatusVariant.DANGER,
  unreachable: StatusVariant.WARNING,
  unverified: StatusVariant.WARNING,
  verify_untrustworthy: StatusVariant.DANGER,
  confirmed_untrustworthy: StatusVariant.WARNING,
};

export const SYNC_LABEL: Record<string, string> = {
  unknown: 'not verified yet',
  in_sync: 'in sync',
  out_of_sync: 'out of sync',
  unreachable: 'unreachable',
  unverified: 'changed, unverified',
  verify_untrustworthy: 'verify untrustworthy',
  confirmed_untrustworthy: 'risk accepted',
};

export const REASON_LABEL: Record<string, string> = {
  manual: 'on demand',
  schedule: 'scheduled',
  after_use: 'after use',
  checkin: 'after check-in',
  reconcile: 'reconcile',
  verify: 'verify',
  compromise: 'compromise',
};

export const JOB_STATUS_OPTIONS = Object.keys(JOB_STATUS_VARIANT).map((s) => ({ value: s, label: s.replace('_', ' ') }));

/** Confirming an untrustworthy verify accepts a known risk: same rule as break-glass. */
export const MIN_CONFIRM_REASON = 20;
export const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
