import { BellOutlined } from '@ant-design/icons';
import { Badge, Button as AntdButton, Drawer, List, Segmented, Typography } from 'antd';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components';
import { ROUTES } from '@/constants/enums/routes';
import {
  useMarkAllNotificationsRead,
  useMarkNotificationRead,
  useNotifications,
  useUnreadCount,
} from '@/features/notify/hooks';
import type { AppNotification } from '@/services/notify-services';
import { fromNow } from '@/utils/format';

const PAGE = { page: 1, page_size: 50 } as const;
const DRAWER_SIZE = 420;

/** Header bell: unread count (polled), and a drawer of your notifications. */
export function NotificationBell() {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [unreadOnly, setUnreadOnly] = useState(false);
  const unread = useUnreadCount(true);
  const list = useNotifications({ ...PAGE, unread_only: unreadOnly }, open);
  const { mutate: markRead } = useMarkNotificationRead();
  const { mutate: markAllRead, isPending: markingAll } = useMarkAllNotificationsRead();

  const openItem = (n: AppNotification) => {
    if (!n.read_at) markRead(n.id);
    if (n.object_type === 'request') {
      setOpen(false);
      navigate(ROUTES.REQUESTS);
    }
  };

  return (
    <>
      <Badge count={unread.data ?? 0} size="small" overflowCount={99}>
        <AntdButton type="text" aria-label="Notifications" icon={<BellOutlined />} onClick={() => setOpen(true)} />
      </Badge>
      <Drawer
        open={open}
        onClose={() => setOpen(false)}
        size={DRAWER_SIZE}
        title="Notifications"
        extra={
          <Button variant="admin" size="small" loading={markingAll} onClick={() => markAllRead()}>
            Mark all read
          </Button>
        }
      >
        <Segmented
          className="!mb-3"
          value={unreadOnly ? 'unread' : 'all'}
          onChange={(v) => setUnreadOnly(v === 'unread')}
          options={[
            { value: 'all', label: 'All' },
            { value: 'unread', label: 'Unread' },
          ]}
        />
        <List
          loading={list.isLoading}
          locale={{ emptyText: 'Nothing here' }}
          dataSource={list.data?.data ?? []}
          renderItem={(n) => (
            <List.Item className="cursor-pointer" onClick={() => openItem(n)}>
              <List.Item.Meta
                title={
                  <Typography.Text strong={!n.read_at} type={n.read_at ? 'secondary' : undefined}>
                    {n.title}
                  </Typography.Text>
                }
                description={
                  <>
                    {n.body && <div>{n.body}</div>}
                    <Typography.Text type="secondary" className="text-xs">
                      {fromNow(n.created_at)}
                    </Typography.Text>
                  </>
                }
              />
            </List.Item>
          )}
        />
      </Drawer>
    </>
  );
}

export default NotificationBell;
