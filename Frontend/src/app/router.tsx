import { lazy, type ReactElement } from 'react';
import { createBrowserRouter, Navigate } from 'react-router-dom';
import { ROUTES } from '@/constants/enums/routes';
import { routeAccessOf } from '@/constants/routeAccess';
import { BaseLayout } from '@/components/layout/BaseLayout';
import ProtectedRoute from '@/components/ProtectedRoute';
import SuspenseBoundary from '@/components/SuspenseBoundary';

// Login sits outside the layout's Suspense, so it carries its own boundary.
const Login = lazy(() => import('@/pages/Login'));

const Dashboard = lazy(() => import('@/pages/dashboard/Dashboard'));

// Inventory
const Targets = lazy(() => import('@/pages/inventory/Targets'));
const Accounts = lazy(() => import('@/pages/inventory/Accounts'));
const Safes = lazy(() => import('@/pages/safes/Safes'));
const RotationJobs = lazy(() => import('@/pages/rotation/RotationJobs'));

// Access
const Requests = lazy(() => import('@/pages/access/Requests'));
const Checkouts = lazy(() => import('@/pages/access/Checkouts'));

// Sessions
const Sessions = lazy(() => import('@/pages/sessions/Sessions'));
const CommandPolicy = lazy(() => import('@/pages/sessions/CommandPolicy'));

// Audit
const AuditTrail = lazy(() => import('@/pages/audit/AuditTrail'));

// Identity
const Users = lazy(() => import('@/pages/identity/Users'));
const Directory = lazy(() => import('@/pages/identity/Directory'));

// Own account
const Security = lazy(() => import('@/pages/auth/Security'));

/** Gates a page on its route's entry in ROUTE_ACCESS — the same gate the nav reads. */
function guard(path: ROUTES, element: ReactElement) {
  return <ProtectedRoute {...routeAccessOf(path)}>{element}</ProtectedRoute>;
}

const routes = createBrowserRouter([
  {
    path: ROUTES.LOGIN,
    element: (
      <SuspenseBoundary>
        <Login />
      </SuspenseBoundary>
    ),
  },
  {
    element: (
      <ProtectedRoute>
        <BaseLayout />
      </ProtectedRoute>
    ),
    children: [
      { path: ROUTES.HOME, element: guard(ROUTES.HOME, <Dashboard />) },
      { path: ROUTES.ACCOUNTS, element: guard(ROUTES.ACCOUNTS, <Accounts />) },
      { path: ROUTES.SAFES, element: guard(ROUTES.SAFES, <Safes />) },
      { path: ROUTES.ROTATION, element: guard(ROUTES.ROTATION, <RotationJobs />) },
      { path: ROUTES.CHECKOUTS, element: guard(ROUTES.CHECKOUTS, <Checkouts />) },
      { path: ROUTES.REQUESTS, element: guard(ROUTES.REQUESTS, <Requests />) },
      { path: ROUTES.TARGETS, element: guard(ROUTES.TARGETS, <Targets />) },
      { path: ROUTES.SESSIONS, element: guard(ROUTES.SESSIONS, <Sessions />) },
      { path: ROUTES.COMMAND_POLICY, element: guard(ROUTES.COMMAND_POLICY, <CommandPolicy />) },
      { path: ROUTES.AUDIT, element: guard(ROUTES.AUDIT, <AuditTrail />) },
      { path: ROUTES.SECURITY, element: guard(ROUTES.SECURITY, <Security />) },
      { path: ROUTES.USERS, element: guard(ROUTES.USERS, <Users />) },
      { path: ROUTES.DIRECTORY, element: guard(ROUTES.DIRECTORY, <Directory />) },
    ],
  },
  { path: '*', element: <Navigate to={ROUTES.HOME} replace /> },
]);

export default routes;
