import { Spin } from 'antd';
import { lazy, Suspense, type ReactNode } from 'react';
import { createBrowserRouter, Navigate, Outlet } from 'react-router-dom';
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
const UsersPage = lazy(() => import('@/pages/UsersPage'));

const Loading = () => (
  <div className="flex min-h-[50vh] items-center justify-center">
    <Spin size="large" />
  </div>
);

function RequireAuth({ roles, children }: { roles?: RoleT[]; children?: ReactNode }) {
  const { user, loading, hasRole } = useAuth();
  if (loading) return <Loading />;
  if (!user) return <Navigate to="/login" replace />;
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
      {
        path: '/audit',
        element: <RequireAuth roles={[Role.Admin, Role.Auditor]}>{page(<AuditPage />)}</RequireAuth>,
      },
      { path: '/users', element: <RequireAuth roles={[Role.Admin]}>{page(<UsersPage />)}</RequireAuth> },
    ],
  },
  { path: '*', element: <Navigate to="/" replace /> },
]);
