export enum StatusVariant {
  SUCCESS = 'success',
  DANGER = 'danger',
  WARNING = 'warning',
  /** Neutral grey chip for a finished or inert state. */
  NEUTRAL = 'neutral',
  /** Solid blue chip for an informational state. */
  INFO = 'info',
  /** Solid accent chip for a state an operator set. */
  PRIMARY = 'primary',
  /** Outlined chip for plain labels (tags, protocol, policy flags). */
  OUTLINE = 'outline',
}

/** Status words the API returns across requests, check-outs, sessions, commands and audit outcomes. */
export const STATUS_VARIANT: Record<string, StatusVariant> = {
  pending: StatusVariant.WARNING,
  approved: StatusVariant.SUCCESS,
  denied: StatusVariant.DANGER,
  cancelled: StatusVariant.NEUTRAL,
  expired: StatusVariant.NEUTRAL,
  used: StatusVariant.INFO,
  active: StatusVariant.SUCCESS,
  returned: StatusVariant.NEUTRAL,
  revoked: StatusVariant.DANGER,
  success: StatusVariant.SUCCESS,
  closed: StatusVariant.NEUTRAL,
  terminated: StatusVariant.DANGER,
  failed: StatusVariant.WARNING,
  allowed: StatusVariant.SUCCESS,
  blocked: StatusVariant.DANGER,
  failure: StatusVariant.DANGER,
};

export const statusVariantOf = (status: string | null | undefined): StatusVariant =>
  (status ? STATUS_VARIANT[status] : undefined) ?? StatusVariant.NEUTRAL;
