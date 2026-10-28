import { forwardRef, type HTMLAttributes } from 'react';
import { Tag } from 'antd';
import { StatusVariant, statusVariantOf } from '@/constants/enums/status';

type StatusTagProps = {
  label: string;
  variant?: StatusVariant;
};

const BASE = '!m-0 !px-2 !py-0 !rounded !shadow-none';

const classNames: Record<StatusVariant, string> = {
  [StatusVariant.SUCCESS]: `${BASE} !bg-(--success) !border-(--success) !text-(--status-on-solid)`,
  [StatusVariant.DANGER]: `${BASE} !bg-(--error) !border-(--error) !text-(--status-on-solid)`,
  [StatusVariant.WARNING]: `${BASE} !bg-(--warning) !border-(--warning) !text-(--status-on-solid)`,
  [StatusVariant.INFO]: `${BASE} !bg-(--status-info) !border-(--status-info) !text-(--status-on-solid)`,
  [StatusVariant.PRIMARY]: `${BASE} !bg-(--status-primary) !border-(--status-primary) !text-(--status-on-solid)`,
  [StatusVariant.NEUTRAL]: `${BASE} !bg-(--status-neutral) !border-(--status-neutral) !text-(--status-on-neutral)`,
  [StatusVariant.OUTLINE]: '!m-0 !px-1.5 !py-0 !rounded !shadow-none !bg-transparent !border-(--border) !text-(--foreground)',
};

/** Every chip in the console. Without a variant, the label is read as an API status word. */
const StatusTag = forwardRef<HTMLSpanElement, StatusTagProps & Omit<HTMLAttributes<HTMLSpanElement>, 'children'>>(
  ({ label, variant, ...domProps }, ref) => (
    <Tag ref={ref} {...domProps} className={classNames[variant ?? statusVariantOf(label)]}>
      {label}
    </Tag>
  ),
);

StatusTag.displayName = 'StatusTag';

export default StatusTag;
