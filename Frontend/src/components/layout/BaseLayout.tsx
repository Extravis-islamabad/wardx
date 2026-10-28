import { LockOutlined, LogoutOutlined, MoonOutlined, SafetyCertificateOutlined, SunOutlined } from '@ant-design/icons';
import { Avatar, Button, Dropdown, Layout, Menu } from 'antd';
import { useMemo } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import StatusTag from '@/components/status/StatusTag';
import SuspenseBoundary from '@/components/SuspenseBoundary';
import Text from '@/components/text';
import { getAccessibleMenuItems, selectedMenuKey, toAntdMenuItems } from '@/constants/menuConfig';
import { ROUTES } from '@/constants/enums/routes';
import { StatusVariant } from '@/constants/enums/status';
import { ThemeMode } from '@/constants/enums/theme';
import { useAuth } from '@/context/AuthContext';
import { useTheme } from '@/theme';

enum UserMenuKey {
  SECURITY = 'security',
  LOGOUT = 'logout',
}

export function BaseLayout() {
  const { user, logout, canAccess } = useAuth();
  const { mode, toggle } = useTheme();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const items = useMemo(() => getAccessibleMenuItems(canAccess), [canAccess]);

  return (
    <Layout className="!min-h-screen">
      <Layout.Sider breakpoint="lg" collapsedWidth={0} width={220}>
        <div className="flex items-center gap-2 px-5 py-5">
          <SafetyCertificateOutlined className="text-2xl text-(--primary)" />
          <Text as="span" variant="h1" className="text-(--nav-foreground)!">
            WardX
          </Text>
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[selectedMenuKey(items, pathname)]}
          items={toAntdMenuItems(items)}
          onClick={({ key }) => navigate(key)}
        />
      </Layout.Sider>
      <Layout>
        <Layout.Header className="flex items-center justify-end gap-3 !px-6">
          <Button
            type="text"
            aria-label="Toggle theme"
            icon={mode === ThemeMode.DARK ? <SunOutlined /> : <MoonOutlined />}
            onClick={toggle}
          />
          <Dropdown
            menu={{
              items: [
                { key: UserMenuKey.SECURITY, icon: <LockOutlined />, label: 'Security (MFA)' },
                { key: UserMenuKey.LOGOUT, icon: <LogoutOutlined />, label: 'Sign out everywhere' },
              ],
              onClick: ({ key }) => (key === UserMenuKey.LOGOUT ? void logout() : navigate(ROUTES.SECURITY)),
            }}
          >
            <span className="flex cursor-pointer items-center gap-2">
              <Avatar size="small">{user?.username?.slice(0, 1)?.toUpperCase()}</Avatar>
              <span>{user?.full_name || user?.username}</span>
              {user?.role ? <StatusTag label={user.role} variant={StatusVariant.OUTLINE} /> : null}
            </span>
          </Dropdown>
        </Layout.Header>
        <Layout.Content className="p-6">
          <SuspenseBoundary>
            <Outlet />
          </SuspenseBoundary>
        </Layout.Content>
      </Layout>
    </Layout>
  );
}

export default BaseLayout;
