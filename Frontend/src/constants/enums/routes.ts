/** Every route the console can navigate to. Paths are part of the product contract; keep them stable. */
export enum ROUTES {
  HOME = '/',
  LOGIN = '/login',

  // Inventory
  TARGETS = '/targets',
  ACCOUNTS = '/accounts',
  SAFES = '/safes',
  ROTATION = '/rotation',

  // Access
  REQUESTS = '/requests',
  CHECKOUTS = '/checkouts',

  // Sessions
  SESSIONS = '/sessions',
  COMMAND_POLICY = '/policy',

  // Audit
  AUDIT = '/audit',

  // Identity
  USERS = '/users',
  DIRECTORY = '/directory',

  // Own account
  SECURITY = '/security',
}
