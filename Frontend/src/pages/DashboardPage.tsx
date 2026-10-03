import { useQuery } from '@tanstack/react-query';
import { Card, Col, Row, Statistic, Typography } from 'antd';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { queryKeys } from '@/lib/queryKeys';
import { dashboardApi } from '@/services/api';

export default function DashboardPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const { data, isLoading } = useQuery({
    queryKey: queryKeys.dashboard,
    queryFn: async () => (await dashboardApi.summary()).data,
    refetchInterval: 30_000,
  });

  const tiles: { title: string; value?: number; to: string; warn?: boolean }[] = [
    { title: 'My active check-outs', value: data?.my_active_checkouts, to: '/checkouts' },
    { title: 'My open requests', value: data?.my_open_requests, to: '/requests' },
    { title: 'Pending approvals', value: data?.pending_requests, to: '/requests' },
    { title: 'Active check-outs (all)', value: data?.active_checkouts, to: '/checkouts' },
    { title: 'Targets', value: data?.targets, to: '/targets' },
    { title: 'Privileged accounts', value: data?.accounts, to: '/accounts' },
    {
      title: 'Accounts without a secret',
      value: data?.accounts_without_secret,
      to: '/accounts',
      warn: !!data?.accounts_without_secret,
    },
  ];

  return (
    <>
      <Typography.Title level={3}>Welcome, {user?.full_name || user?.username}</Typography.Title>
      <Row gutter={[16, 16]}>
        {tiles.map((t) => (
          <Col key={t.title} xs={24} sm={12} lg={6}>
            <Card hoverable loading={isLoading} onClick={() => navigate(t.to)}>
              <Statistic
                title={t.title}
                value={t.value ?? 0}
                styles={t.warn ? { content: { color: '#faad14' } } : undefined}
              />
            </Card>
          </Col>
        ))}
      </Row>
    </>
  );
}
