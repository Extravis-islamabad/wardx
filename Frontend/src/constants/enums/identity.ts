export enum SyncStatus {
  OK = 'ok',
  NEEDS_REVIEW = 'needs_review',
  FAILED = 'failed',
}

/** Why a user was disabled, when the system did it. */
export enum DisabledReason {
  DIRECTORY_SYNC = 'directory_sync',
}
