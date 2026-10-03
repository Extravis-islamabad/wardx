import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';

dayjs.extend(relativeTime);

export const fmtTime = (iso: string | null | undefined) =>
  iso ? dayjs(iso).format('YYYY-MM-DD HH:mm:ss') : '—';

export const fromNow = (iso: string | null | undefined) => (iso ? dayjs(iso).fromNow() : '—');

export const isFuture = (iso: string) => dayjs(iso).isAfter(dayjs());
