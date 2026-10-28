import { PERMISSIONS } from './permissions';

// Re-exported so `enums/modules` imports can reach both, as in MonetX.
export { PERMISSIONS };

/** Top-level console areas. The backend does not license modules yet, so these group routes and menu entries. */
export enum MODULES {
  DASHBOARD = 'dashboard',
  INVENTORY = 'inventory',
  ACCESS = 'access',
  SESSIONS = 'sessions',
  AUDIT = 'audit',
  IDENTITY = 'identity',
}
