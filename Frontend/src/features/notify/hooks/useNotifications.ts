import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { notificationsService } from '@/services/notify-services';
import type { PageQuery } from '@/types/api';
import { accessKeys } from '@/features/access/hooks/accessKeys';
import { notifyKeys } from './notifyKeys';

/** The bell polls about every 30 s. */
const UNREAD_POLL_MS = 30_000;

export function useUnreadCount(enabled: boolean) {
  const qc = useQueryClient();
  return useQuery({
    queryKey: notifyKeys.unread(),
    queryFn: async () => {
      const unread = (await notificationsService.unreadCount()).data.unread;
      // Something new usually means a request moved: refresh the requests lists too.
      void qc.invalidateQueries({ queryKey: accessKeys.requestsAll() });
      return unread;
    },
    refetchInterval: UNREAD_POLL_MS,
    enabled,
  });
}

export function useNotifications(params: PageQuery, enabled: boolean) {
  return useQuery({
    queryKey: notifyKeys.list(params),
    queryFn: () => notificationsService.list(params),
    enabled,
  });
}

export function useMarkNotificationRead() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => notificationsService.markRead(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: notifyKeys.all }),
  });
}

export function useMarkAllNotificationsRead() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => notificationsService.markAllRead(),
    onSuccess: () => qc.invalidateQueries({ queryKey: notifyKeys.all }),
  });
}
