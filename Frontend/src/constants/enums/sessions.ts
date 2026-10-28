export enum SessionStatus {
  ACTIVE = 'active',
  CLOSED = 'closed',
  TERMINATED = 'terminated',
  FAILED = 'failed',
}

export enum SessionMode {
  SHELL = 'shell',
  EXEC = 'exec',
}

export enum CommandVerdict {
  ALLOWED = 'allowed',
  BLOCKED = 'blocked',
}

/** Response header the recording endpoint sets once the cast matches its stored hash. */
export const RECORDING_VERIFIED_HEADER = 'x-wardx-recording-verified';
