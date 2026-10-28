import { Spin } from 'antd';
import React, { Suspense } from 'react';

export const PageLoader = () => (
  <div className="flex min-h-[50vh] items-center justify-center">
    <Spin size="large" />
  </div>
);

const SuspenseBoundary = ({ children, fallback }: { children: React.ReactNode; fallback?: React.ReactNode }) => (
  <Suspense fallback={fallback ?? <PageLoader />}>{children}</Suspense>
);

export default SuspenseBoundary;
