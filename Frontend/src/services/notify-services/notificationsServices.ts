/** Wraps /api/v1/notifications/*: your in-app notifications (no email). */
import { apiClient } from '@/lib/apiClient';
import type { ApiResponse, PageQuery, Paginated } from '@/types/api';

export interface AppNotification {
  id: string;
  kind: string;
  title: string;
  body: string | null;
  object_type: string | null;
  object_id: string | null;
  created_at: string;
  read_at: string | null;
}

const BASE = 'notifications';

export const notificationsService = {
  async list(params: PageQuery): Promise<Paginated<AppNotification>> {
    const { data } = await apiClient.get<Paginated<AppNotification>>(BASE, { params });
    return data;
  },

  // Polled by the header bell; a failed poll has nothing useful to toast.
  async unreadCount(): Promise<ApiResponse<{ unread: number }>> {
    const { data } = await apiClient.get<ApiResponse<{ unread: number }>>(`${BASE}/unread-count`, {
      skipErrorNotify: true,
    });
    return data;
  },

  async markRead(id: string): Promise<ApiResponse<null>> {
    const { data } = await apiClient.post<ApiResponse<null>>(`${BASE}/${id}/read`);
    return data;
  },

  async markAllRead(): Promise<ApiResponse<{ unread: number }>> {
    const { data } = await apiClient.post<ApiResponse<{ unread: number }>>(`${BASE}/read-all`);
    return data;
  },
};

export default notificationsService;
