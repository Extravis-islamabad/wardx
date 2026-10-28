import { SafetyCertificateOutlined } from '@ant-design/icons';
import { Card } from 'antd';
import { Navigate } from 'react-router-dom';
import { PageShell, Text } from '@/components';
import { ROUTES } from '@/constants/enums/routes';
import { useAuth } from '@/context/AuthContext';
import { LoginForm, MfaCodeStep } from '@/features/auth/components';

export default function Login() {
  const { user, awaitingCode } = useAuth();
  if (user) return <Navigate to={ROUTES.HOME} replace />;

  return (
    <PageShell bare className="flex min-h-screen items-center justify-center p-4">
      <Card className="w-full max-w-sm">
        <div className="mb-6 flex flex-col items-center gap-2">
          <SafetyCertificateOutlined className="text-4xl text-(--primary)" />
          <Text as="h1" variant="h1">
            WardX
          </Text>
          <Text as="span" variant="caption">
            Privileged access management
          </Text>
        </div>
        {awaitingCode ? <MfaCodeStep /> : <LoginForm />}
      </Card>
    </PageShell>
  );
}
