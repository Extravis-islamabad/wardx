import {
  ApartmentOutlined,
  AuditOutlined,
  CloudServerOutlined,
  CodeOutlined,
  DashboardOutlined,
  DesktopOutlined,
  InboxOutlined,
  KeyOutlined,
  SafetyCertificateOutlined,
  TeamOutlined,
  UnlockOutlined,
} from '@ant-design/icons';
import type { MenuProps } from 'antd';
import type { ReactNode } from 'react';
import { ROUTES } from './enums/routes';
import { MODULES, PERMISSIONS } from './enums/modules';
import { routeAccessOf, type RouteAccessConfig } from './routeAccess';

type MenuItem = {
  key: string;
  label: string;
  icon?: ReactNode;
  /** Module code required to show this menu item. */
  requiredModule?: string;
  /** Permission codename required to show this menu item. */
  requiredPermission?: string;
};

export const menuItems: MenuItem[] = [
  { key: ROUTES.HOME, label: 'Dashboard', icon: <DashboardOutlined />, requiredModule: MODULES.DASHBOARD },
  { key: ROUTES.ACCOUNTS, label: 'Accounts', icon: <KeyOutlined />, requiredModule: MODULES.INVENTORY },
  {
    key: ROUTES.SAFES,
    label: 'Safes',
    icon: <InboxOutlined />,
    requiredModule: MODULES.INVENTORY,
    requiredPermission: PERMISSIONS.INVENTORY_VIEW,
  },
  { key: ROUTES.CHECKOUTS, label: 'Check-outs', icon: <UnlockOutlined />, requiredModule: MODULES.ACCESS },
  { key: ROUTES.REQUESTS, label: 'Requests', icon: <SafetyCertificateOutlined />, requiredModule: MODULES.ACCESS },
  { key: ROUTES.SESSIONS, label: 'Sessions', icon: <DesktopOutlined />, requiredModule: MODULES.SESSIONS },
  { key: ROUTES.TARGETS, label: 'Targets', icon: <CloudServerOutlined />, requiredModule: MODULES.INVENTORY },
  {
    key: ROUTES.COMMAND_POLICY,
    label: 'Command policy',
    icon: <CodeOutlined />,
    requiredModule: MODULES.SESSIONS,
    requiredPermission: PERMISSIONS.COMMAND_POLICY_VIEW,
  },
  {
    key: ROUTES.AUDIT,
    label: 'Audit',
    icon: <AuditOutlined />,
    requiredModule: MODULES.AUDIT,
    requiredPermission: PERMISSIONS.AUDIT_VIEW,
  },
  {
    key: ROUTES.USERS,
    label: 'Users',
    icon: <TeamOutlined />,
    requiredModule: MODULES.IDENTITY,
    requiredPermission: PERMISSIONS.USERS_MANAGE,
  },
  {
    key: ROUTES.DIRECTORY,
    label: 'Directory',
    icon: <ApartmentOutlined />,
    requiredModule: MODULES.IDENTITY,
    requiredPermission: PERMISSIONS.DIRECTORY_MANAGE,
  },
];

/** `canAccess` from `useAuth()` — passed in because this file can't call hooks. */
type CanAccess = (_check: RouteAccessConfig) => boolean;

/** The item's own access flags, without the route gate. */
const itemAccess = (item: MenuItem): RouteAccessConfig => ({
  module: item.requiredModule,
  permission: item.requiredPermission,
});

/** Filters the static menu by what the user can open: the item's own flags and its route's gate. */
export function getAccessibleMenuItems(canAccess: CanAccess): MenuItem[] {
  return menuItems.filter((item) => canAccess(itemAccess(item)) && canAccess(routeAccessOf(item.key)));
}

/** Drop the frontend-only keys before the items reach antd's `<Menu>`. */
export function toAntdMenuItems(items: MenuItem[]): MenuProps['items'] {
  return items.map(({ key, label, icon }) => ({ key, label, icon }));
}

/** The menu key to highlight for a path: the longest item route the path sits under. */
export const selectedMenuKey = (items: MenuItem[], pathname: string): string =>
  items.filter((item) => item.key !== ROUTES.HOME && pathname.startsWith(item.key))[0]?.key ?? ROUTES.HOME;
