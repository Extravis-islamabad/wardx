/** Which slice of check-outs the page lists. */
export enum CheckoutScope {
  MINE_ACTIVE = 'mine-active',
  MINE = 'mine',
  ALL_ACTIVE = 'all-active',
  ALL = 'all',
}

/** Which slice of access requests the page lists. */
export enum RequestScope {
  QUEUE = 'queue',
  MINE = 'mine',
  ALL = 'all',
}

/** Seconds a revealed secret stays on screen before the modal drops it. */
export const REVEAL_AUTO_HIDE_SECONDS = 30;

/** Default check-out length, capped by the account's own maximum. */
export const DEFAULT_ACCESS_MINUTES = 60;
