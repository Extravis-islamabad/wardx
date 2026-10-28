import { notification } from 'antd';
import type { ArgsProps, NotificationInstance } from 'antd/es/notification/interface';
import { NotifyType } from '@/constants/enums/components';

// The `App.useApp()` instance reads theme context; the static API is only a pre-mount fallback.
let instance: NotificationInstance | null = null;
export const setNotifyInstance = (api: NotificationInstance | null) => {
  instance = api;
};
const api = () => instance ?? notification;

const open =
  (type: NotifyType) =>
  (args: string | ArgsProps): void => {
    const normalized: ArgsProps = typeof args === 'string' ? { title: args } : args;
    const heading = normalized.title;
    // Same type + text collapses into one toast instead of stacking duplicates.
    const key = normalized.key ?? `${type}:${typeof heading === 'string' ? heading : ''}`;
    api()[type]({ placement: 'topRight', duration: 4.5, ...normalized, key });
  };

export const notify = {
  success: open(NotifyType.SUCCESS),
  error: open(NotifyType.ERROR),
  info: open(NotifyType.INFO),
  warning: open(NotifyType.WARNING),
  /** Close every open toast. */
  clear: (): void => api().destroy(),
};

export default notify;
