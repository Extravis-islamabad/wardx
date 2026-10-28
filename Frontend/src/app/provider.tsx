import React from 'react';
import { QueryClientProvider } from '@tanstack/react-query';
import ThemeProvider from '@/theme';
import { AuthProvider } from '@/context/AuthContext';
import { queryClient } from '@/lib/queryClient';

const RootProvider = ({ children }: { children: React.ReactNode }) => (
  <QueryClientProvider client={queryClient}>
    <ThemeProvider>
      <AuthProvider>{children}</AuthProvider>
    </ThemeProvider>
  </QueryClientProvider>
);

export default RootProvider;
