import { authKeys } from '@/features/auth/hooks/authKeys';
import { dashboardKeys } from '@/features/dashboard/hooks/dashboardKeys';
import { inventoryKeys } from '@/features/inventory/hooks/inventoryKeys';
import { accessKeys } from '@/features/access/hooks/accessKeys';
import { sessionsKeys } from '@/features/sessions/hooks/sessionsKeys';
import { auditKeys } from '@/features/audit/hooks/auditKeys';
import { identityKeys } from '@/features/identity/hooks/identityKeys';
import { safesKeys } from '@/features/safes/hooks/safesKeys';

export { authKeys, dashboardKeys, inventoryKeys, accessKeys, sessionsKeys, auditKeys, identityKeys, safesKeys };

/**
 * Namespaced facade for ergonomic call sites:
 *   queryKeys.inventory.targets(params)
 *   queryKeys.auth.mfa()
 */
export const queryKeys = {
  auth: authKeys,
  dashboard: dashboardKeys,
  inventory: inventoryKeys,
  access: accessKeys,
  sessions: sessionsKeys,
  audit: auditKeys,
  identity: identityKeys,
  safes: safesKeys,
};
