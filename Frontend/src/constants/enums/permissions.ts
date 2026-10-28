import { Role } from './auth';

/** Permission codenames the console gates on. Today they resolve from the user's role via ROLE_PERMISSIONS. */
export enum PERMISSIONS {
  TARGETS_MANAGE = 'inventory.targets.manage',
  ACCOUNTS_MANAGE = 'inventory.accounts.manage',
  REQUESTS_DECIDE = 'access.requests.decide',
  CHECKOUTS_VIEW_ALL = 'access.checkouts.view_all',
  CHECKOUTS_REVOKE = 'access.checkouts.revoke',
  SESSIONS_VIEW_ALL = 'sessions.view_all',
  SESSIONS_TERMINATE = 'sessions.terminate',
  COMMAND_POLICY_VIEW = 'sessions.command_policy.view',
  COMMAND_POLICY_MANAGE = 'sessions.command_policy.manage',
  AUDIT_VIEW = 'audit.view',
  USERS_MANAGE = 'identity.users.manage',
  DIRECTORY_MANAGE = 'identity.directory.manage',
}

// Swap for a server-issued permission list once the backend sends one; call sites keep using codenames.
export const ROLE_PERMISSIONS: Record<Role, PERMISSIONS[]> = {
  [Role.ADMIN]: Object.values(PERMISSIONS),
  [Role.APPROVER]: [PERMISSIONS.REQUESTS_DECIDE],
  [Role.AUDITOR]: [
    PERMISSIONS.CHECKOUTS_VIEW_ALL,
    PERMISSIONS.SESSIONS_VIEW_ALL,
    PERMISSIONS.COMMAND_POLICY_VIEW,
    PERMISSIONS.AUDIT_VIEW,
  ],
  [Role.USER]: [],
};
