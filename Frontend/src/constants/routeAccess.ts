import { ROUTES } from './enums/routes';
import { MODULES, PERMISSIONS } from './enums/modules';

export type RouteAccessConfig = {
  /** Required module code(s). Not enforced until the backend issues modules. */
  module?: string | string[];
  /** Required permission codename(s) — any one of them passes. */
  permission?: string | string[];
};

/**
 * Single source of truth for route gates: the router, the nav and in-page links all read it.
 * An entry without a permission is open to every signed-in user.
 */
export const ROUTE_ACCESS: Partial<Record<string, RouteAccessConfig>> = {
  [ROUTES.HOME]: { module: MODULES.DASHBOARD },

  [ROUTES.TARGETS]: { module: MODULES.INVENTORY },
  [ROUTES.ACCOUNTS]: { module: MODULES.INVENTORY },
  [ROUTES.SAFES]: { module: MODULES.INVENTORY, permission: PERMISSIONS.INVENTORY_VIEW },
  [ROUTES.ROTATION]: { module: MODULES.INVENTORY, permission: PERMISSIONS.INVENTORY_VIEW },

  [ROUTES.REQUESTS]: { module: MODULES.ACCESS },
  [ROUTES.CHECKOUTS]: { module: MODULES.ACCESS },

  [ROUTES.SESSIONS]: { module: MODULES.SESSIONS },
  [ROUTES.COMMAND_POLICY]: {
    module: MODULES.SESSIONS,
    permission: PERMISSIONS.COMMAND_POLICY_VIEW,
  },

  [ROUTES.AUDIT]: { module: MODULES.AUDIT, permission: PERMISSIONS.AUDIT_VIEW },

  [ROUTES.USERS]: { module: MODULES.IDENTITY, permission: PERMISSIONS.USERS_MANAGE },
  [ROUTES.DIRECTORY]: { module: MODULES.IDENTITY, permission: PERMISSIONS.DIRECTORY_MANAGE },

  // Every signed-in user must reach their own MFA settings, including mid-enrolment.
  [ROUTES.SECURITY]: {},
};

/** The gate for a route; an unlisted route is open to every signed-in user. */
export const routeAccessOf = (route: string): RouteAccessConfig => ROUTE_ACCESS[route] ?? {};
