import { Card, Col, Row, Statistic } from 'antd';
import { useNavigate } from 'react-router-dom';
import { ROUTES } from '@/constants/enums/routes';
import type { DashboardSummary } from '@/services/dashboard-services';

interface Tile {
  title: string;
  value?: number;
  to: ROUTES;
  warn?: boolean;
}

const tilesFor = (data: DashboardSummary | undefined): Tile[] => [
  { title: 'My active check-outs', value: data?.my_active_checkouts, to: ROUTES.CHECKOUTS },
  { title: 'My open requests', value: data?.my_open_requests, to: ROUTES.REQUESTS },
  { title: 'Pending approvals', value: data?.pending_requests, to: ROUTES.REQUESTS },
  { title: 'Active check-outs (all)', value: data?.active_checkouts, to: ROUTES.CHECKOUTS },
  { title: 'Targets', value: data?.targets, to: ROUTES.TARGETS },
  { title: 'Privileged accounts', value: data?.accounts, to: ROUTES.ACCOUNTS },
  {
    title: 'Accounts without a secret',
    value: data?.accounts_without_secret,
    to: ROUTES.ACCOUNTS,
    warn: !!data?.accounts_without_secret,
  },
];

export function SummaryTiles({ data, loading }: { data?: DashboardSummary; loading: boolean }) {
  const navigate = useNavigate();
  return (
    <Row gutter={[16, 16]}>
      {tilesFor(data)?.map((t) => (
        <Col key={t.title} xs={24} sm={12} lg={6}>
          <Card hoverable loading={loading} onClick={() => navigate(t.to)}>
            <Statistic
              title={t.title}
              value={t.value ?? 0}
              styles={t.warn ? { content: { color: 'var(--warning)' } } : undefined}
            />
          </Card>
        </Col>
      ))}
    </Row>
  );
}

export default SummaryTiles;
