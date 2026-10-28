import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { ROUTE_ACCESS } from '@/constants/routeAccess';
import { ROUTES } from '@/constants/enums/routes';
import { PageLoader } from '@/components/SuspenseBoundary';

type Props = {
  children: React.ReactNode;
  /** Required module code(s). */
  module?: string | string[];
  /** Required permission codename(s) — user must have at least one. */
  permission?: string | string[];
};

const ProtectedRoute: React.FC<Props> = ({ children, module, permission }) => {
  const { user, loading, needsMfaEnrolment, canAccess } = useAuth();
  const { pathname } = useLocation();

  if (loading) return <PageLoader />;
  if (!user) return <Navigate to={ROUTES.LOGIN} replace />;

  // A role that requires MFA can only reach the Security page until it is on.
  if (needsMfaEnrolment && pathname !== ROUTES.SECURITY) {
    return <Navigate to={ROUTES.SECURITY} replace />;
  }

  const routeConfig = ROUTE_ACCESS[pathname];
  if (!canAccess({ module: module ?? routeConfig?.module, permission: permission ?? routeConfig?.permission })) {
    return <Navigate to={ROUTES.HOME} replace />;
  }

  return <>{children}</>;
};

export default ProtectedRoute;
