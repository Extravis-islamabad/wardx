import { Spin } from 'antd';
import { lazy, Suspense, type ReactNode } from 'react';
import { createBrowserRouter, Navigate, Outlet, useLocation } from 'react-router-dom';
import { AppLayout } from '@/components/AppLayout';
import { Role } from '@/constants/enums';
import { useAuth } from '@/context/AuthContext';
import type { Role as RoleT } from '@/types/api';

const LoginPage = lazy(() => import('@/pages/LoginPage'));
const DashboardPage = lazy(() => import('@/pages/DashboardPage'));
const AccountsPage = lazy(() => import('@/pages/AccountsPage'));
const CheckoutsPage = lazy(() => import('@/pages/CheckoutsPage'));
const RequestsPage = lazy(() => import('@/pages/RequestsPage'));
const TargetsPage = lazy(() => import('@/pages/TargetsPage'));
const AuditPage = lazy(() => import('@/pages/AuditPage'));
const SessionsPage = lazy(() => import('@/pages/SessionsPage'));
const CommandRulesPage = lazy(() => import('@/pages/CommandRulesPage'));
const UsersPage = lazy(() => import('@/pages/UsersPage'));
const SecurityPage = lazy(() => import('@/pages/SecurityPage'));
const DirectoryPage = lazy(() => import('@/pages/DirectoryPage'));

const Loading = () => (
  <div className="flex min-h-[50vh] items-center justify-center">
    <Spin size="large" />
  </div>
);

function RequireAuth({ roles, children }: { roles?: RoleT[]; children?: ReactNode }) {
  const { user, loading, hasRole, needsMfaEnrolment } = useAuth();
  const { pathname } = useLocation();
  if (loading) return <Loading />;
  if (!user) return <Navigate to="/login" replace />;
  // A role that requires MFA can only reach the Security page until it is on.
  if (needsMfaEnrolment && pathname !== '/security') return <Navigate to="/security" replace />;
  if (roles && !hasRole(...roles)) return <Navigate to="/" replace />;
  return <>{children ?? <Outlet />}</>;
}

const page = (el: ReactNode) => <Suspense fallback={<Loading />}>{el}</Suspense>;

export const router = createBrowserRouter([
  { path: '/login', element: page(<LoginPage />) },
  {
    element: (
      <RequireAuth>
        <AppLayout />
      </RequireAuth>
    ),
    children: [
      { path: '/', element: page(<DashboardPage />) },
      { path: '/accounts', element: page(<AccountsPage />) },
      { path: '/checkouts', element: page(<CheckoutsPage />) },
      { path: '/requests', element: page(<RequestsPage />) },
      { path: '/targets', element: page(<TargetsPage />) },
      { path: '/sessions', element: page(<SessionsPage />) },
      {
        path: '/policy',
        element: <RequireAuth roles={[Role.Admin, Role.Auditor]}>{page(<CommandRulesPage />)}</RequireAuth>,
      },
      {
        path: '/audit',
        element: <RequireAuth roles={[Role.Admin, Role.Auditor]}>{page(<AuditPage />)}</RequireAuth>,
      },
      { path: '/security', element: page(<SecurityPage />) },
      { path: '/users', element: <RequireAuth roles={[Role.Admin]}>{page(<UsersPage />)}</RequireAuth> },
      { path: '/directory', element: <RequireAuth roles={[Role.Admin]}>{page(<DirectoryPage />)}</RequireAuth> },
    ],
  },
  { path: '*', element: <Navigate to="/" replace /> },
]);
