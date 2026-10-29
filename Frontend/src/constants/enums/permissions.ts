/**
 * Permission codenames the console gates on. They are the backend's codenames
 * (Backend/src/core/permissions.py): `/auth/me` returns the signed-in user's effective
 * list (role bundle plus direct grants such as break-glass), and `canAccess` checks it.
 */
export enum PERMISSIONS {
  INVENTORY_VIEW = 'inventory.view',
  TARGETS_MANAGE = 'inventory.manage',
  ACCOUNTS_MANAGE = 'inventory.manage',
  SAFES_MANAGE = 'safes.manage',
  REQUESTS_DECIDE = 'access.approve',
  CHECKOUTS_VIEW_ALL = 'access.view_all',
  CHECKOUTS_REVOKE = 'access.revoke',
  /** Break-glass: a direct per-user grant only; no role holds it. */
  ACCESS_EMERGENCY = 'access.emergency',
  SESSIONS_VIEW_ALL = 'sessions.view_all',
  SESSIONS_TERMINATE = 'sessions.terminate',
  /** Read command rules and use the rule tester: admin and auditor only. */
  COMMAND_POLICY_VIEW = 'commands.view',
  COMMAND_POLICY_MANAGE = 'policy.manage',
  AUDIT_VIEW = 'audit.view',
  ALERTS_ACKNOWLEDGE = 'alerts.acknowledge',
  USERS_MANAGE = 'users.manage',
  DIRECTORY_MANAGE = 'directory.manage',
  /** Application identities for the credential provider (admin). */
  APPS_MANAGE = 'apps.manage',
  /** Cluster health: scheduler leader, replication, DR lag, gateway nodes (admin). */
  CLUSTER_VIEW = 'cluster.view',
}
