/** Which code-confirmed MFA action the Security page is asking for. */
export enum MfaPromptMode {
  DISABLE = 'disable',
  REGENERATE = 'regenerate',
}

export const MFA_CODE_LENGTH = 6;

/** Long enough for a recovery code as well as a 6-digit TOTP. */
export const MFA_CODE_MAX_LENGTH = 20;

export const RECOVERY_CODES_COPIED = 'Copied';
