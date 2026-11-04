import {
  LockOutlined,
  LogoutOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  MoonOutlined,
  SafetyCertificateOutlined,
  SunOutlined,
} from '@ant-design/icons';
import { Avatar, Button, Dropdown, Layout, Menu, Tooltip } from 'antd';
import { useEffect, useMemo, useState } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import StatusTag from '@/components/status/StatusTag';
import SuspenseBoundary from '@/components/SuspenseBoundary';
import Text from '@/components/text';
import { PageHeadingSlotContext } from './PageHeadingSlot';
import { getAccessibleMenuItems, selectedMenuKey, toAntdMenuItems } from '@/constants/menuConfig';
import { ROUTES } from '@/constants/enums/routes';
import { StatusVariant } from '@/constants/enums/status';
import { ThemeMode } from '@/constants/enums/theme';
import { useAuth } from '@/context/AuthContext';
import { NotificationBell } from '@/features/notify/components';
import { useTheme } from '@/theme';

enum UserMenuKey {
  SECURITY = 'security',
  LOGOUT = 'logout',
}

const SIDER_STORAGE_KEY = 'wardx.sider.collapsed';
const SIDER_WIDTH = 200;
/** Collapsed, the sider keeps a rail of icons (labels move to tooltips). */
const SIDER_COLLAPSED_WIDTH = 48;

const readCollapsed = (): boolean => {
  try {
    return localStorage.getItem(SIDER_STORAGE_KEY) === '1';
  } catch {
    return false;
  }
};

export function BaseLayout() {
  const { user, logout, canAccess } = useAuth();
  const { mode, toggle } = useTheme();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const items = useMemo(() => getAccessibleMenuItems(canAccess), [canAccess]);
  const selectedKey = selectedMenuKey(items, pathname);
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const [headingSlot, setHeadingSlot] = useState<HTMLDivElement | null>(null);

  useEffect(() => {
    try {
      localStorage.setItem(SIDER_STORAGE_KEY, collapsed ? '1' : '0');
    } catch {
      // Not persisted; fine.
    }
  }, [collapsed]);

  return (
    <Layout className="!min-h-screen">
      <Layout.Sider
        collapsible
        collapsed={collapsed}
        onCollapse={setCollapsed}
        breakpoint="lg"
        trigger={null}
        width={SIDER_WIDTH}
        collapsedWidth={SIDER_COLLAPSED_WIDTH}
        className="!sticky top-0 h-screen [&>.ant-layout-sider-children]:flex [&>.ant-layout-sider-children]:flex-col"
      >
        <div
          className={`flex h-10 shrink-0 items-center gap-2 border-b border-(--nav-hover-bg) ${collapsed ? 'justify-center' : 'px-4'}`}
        >
          <SafetyCertificateOutlined className="text-lg text-(--nav-accent)!" />
          {collapsed ? null : (
            <Text as="span" variant="h3" className="font-bold! tracking-[0.5px] text-(--nav-foreground)!">
              WardX
            </Text>
          )}
        </div>
        {/* Only the menu scrolls; the logo above and sign-out below stay pinned. */}
        <div className="min-h-0 flex-1 overflow-x-hidden overflow-y-auto">
          <Menu
            className="wardx-nav !border-0 !pt-1"
            theme="dark"
            mode="inline"
            inlineCollapsed={collapsed}
            selectedKeys={[selectedKey]}
            items={toAntdMenuItems(items)}
            onClick={({ key }) => navigate(key)}
          />
        </div>
        <div className="shrink-0 border-t border-(--nav-hover-bg) p-1">
          <Tooltip title={collapsed ? 'Sign out everywhere' : undefined} placement="right">
            <button
              type="button"
              onClick={() => void logout()}
              className={`flex h-8 w-full cursor-pointer items-center gap-2.5 border-0 bg-transparent text-xs text-(--nav-item-color) hover:bg-(--nav-hover-bg) hover:text-(--error-text) ${collapsed ? 'justify-center' : 'px-5'}`}
            >
              <LogoutOutlined className="text-sm" />
              {collapsed ? null : <span>Sign out everywhere</span>}
            </button>
          </Tooltip>
        </div>
      </Layout.Sider>
      <Layout className="min-w-0">
        <Layout.Header className="sticky top-0 z-10 flex items-center gap-2 border-b border-(--border) !leading-none">
          <Button
            type="text"
            size="small"
            aria-label={collapsed ? 'Expand menu' : 'Collapse menu'}
            icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
            onClick={() => setCollapsed((c) => !c)}
          />
          {/* The current page's heading lands here (PageShell portals it in). */}
          <div ref={setHeadingSlot} className="flex min-w-0 flex-1 items-center" />
          <NotificationBell />
          <Tooltip title={mode === ThemeMode.DARK ? 'Light theme' : 'Dark theme'}>
            <Button
              type="text"
              size="small"
              aria-label="Toggle theme"
              icon={mode === ThemeMode.DARK ? <SunOutlined /> : <MoonOutlined />}
              onClick={toggle}
            />
          </Tooltip>
          <Dropdown
            menu={{
              items: [
                { key: UserMenuKey.SECURITY, icon: <LockOutlined />, label: 'Security (MFA)' },
                { key: UserMenuKey.LOGOUT, icon: <LogoutOutlined />, label: 'Sign out everywhere' },
              ],
              onClick: ({ key }) => (key === UserMenuKey.LOGOUT ? void logout() : navigate(ROUTES.SECURITY)),
            }}
          >
            <span className="flex cursor-pointer items-center gap-1.5 text-xs">
              <Avatar size={22}>{user?.username?.slice(0, 1)?.toUpperCase()}</Avatar>
              <span>{user?.full_name || user?.username}</span>
              {user?.role ? <StatusTag label={user.role} variant={StatusVariant.OUTLINE} /> : null}
            </span>
          </Dropdown>
        </Layout.Header>
        <Layout.Content className="min-w-0 p-2">
          <PageHeadingSlotContext.Provider value={headingSlot}>
            <SuspenseBoundary>
              <Outlet />
            </SuspenseBoundary>
          </PageHeadingSlotContext.Provider>
        </Layout.Content>
      </Layout>
    </Layout>
  );
}

export default BaseLayout;
