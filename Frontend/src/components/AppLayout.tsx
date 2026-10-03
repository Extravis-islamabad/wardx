import {
  AuditOutlined,
  CloudServerOutlined,
  DashboardOutlined,
  KeyOutlined,
  LogoutOutlined,
  MoonOutlined,
  SafetyCertificateOutlined,
  SunOutlined,
  TeamOutlined,
  UnlockOutlined,
} from '@ant-design/icons';
import { Avatar, Button, Dropdown, Layout, Menu, Tag, Typography } from 'antd';
import type { ReactNode } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { Role } from '@/constants/enums';
import { useAuth } from '@/context/AuthContext';
import { useThemeMode } from '@/context/ThemeContext';
import type { Role as RoleT } from '@/types/api';

interface NavItem {
  key: string;
  label: string;
  icon: ReactNode;
  roles?: RoleT[];
}

export const NAV: NavItem[] = [
  { key: '/', label: 'Dashboard', icon: <DashboardOutlined /> },
  { key: '/accounts', label: 'Accounts', icon: <KeyOutlined /> },
  { key: '/checkouts', label: 'Check-outs', icon: <UnlockOutlined /> },
  { key: '/requests', label: 'Requests', icon: <SafetyCertificateOutlined /> },
  { key: '/targets', label: 'Targets', icon: <CloudServerOutlined /> },
  { key: '/audit', label: 'Audit', icon: <AuditOutlined />, roles: [Role.Admin, Role.Auditor] },
  { key: '/users', label: 'Users', icon: <TeamOutlined />, roles: [Role.Admin] },
];

export function AppLayout() {
  const { user, logout, hasRole } = useAuth();
  const { mode, toggle } = useThemeMode();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const items = NAV.filter((n) => !n.roles || hasRole(...n.roles));
  const selected = items.filter((n) => n.key !== '/' && pathname.startsWith(n.key))[0]?.key ?? '/';

  return (
    <Layout className="!min-h-screen">
      <Layout.Sider breakpoint="lg" collapsedWidth={0} width={220}>
        <div className="flex items-center gap-2 px-5 py-5">
          <SafetyCertificateOutlined className="text-2xl text-[#5b6cff]" />
          <Typography.Title level={4} className="!m-0 !text-white">
            WardX
          </Typography.Title>
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[selected]}
          items={items.map(({ key, label, icon }) => ({ key, label, icon }))}
          onClick={({ key }) => navigate(key)}
        />
      </Layout.Sider>
      <Layout>
        <Layout.Header className="flex items-center justify-end gap-3 !px-6">
          <Button
            type="text"
            aria-label="Toggle theme"
            icon={mode === 'dark' ? <SunOutlined /> : <MoonOutlined />}
            onClick={toggle}
          />
          <Dropdown
            menu={{
              items: [{ key: 'logout', icon: <LogoutOutlined />, label: 'Sign out everywhere' }],
              onClick: () => void logout(),
            }}
          >
            <span className="flex cursor-pointer items-center gap-2">
              <Avatar size="small">{user?.username.slice(0, 1).toUpperCase()}</Avatar>
              <span>{user?.full_name || user?.username}</span>
              <Tag>{user?.role}</Tag>
            </span>
          </Dropdown>
        </Layout.Header>
        <Layout.Content className="p-6">
          <Outlet />
        </Layout.Content>
      </Layout>
    </Layout>
  );
}
