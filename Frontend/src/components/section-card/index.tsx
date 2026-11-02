import type { ReactNode } from 'react';
import { Card } from 'antd';
import Text from '@/components/text';

interface SectionCardProps {
  /** Rendered as the house uppercase-tracked `label` when given a string. */
  title: ReactNode;
  /** Right-side slot — search, filters, per-section actions. */
  extra?: ReactNode;
  className?: string;
  /** Drop body padding, for tables that own their own inset. */
  flush?: boolean;
  size?: 'default' | 'small';
  loading?: boolean;
  children: ReactNode;
}

/** A titled content block inside a page (the MoneTX `SectionCard`). */
export const SectionCard = ({
  title,
  extra,
  className = '',
  flush,
  size = 'small',
  loading,
  children,
}: SectionCardProps) => (
  <Card
    size={size}
    loading={loading}
    className={className}
    styles={flush ? { body: { padding: 0 } } : undefined}
    title={
      typeof title === 'string' ? (
        <Text as="span" variant="label" className="uppercase tracking-[0.4px]">
          {title}
        </Text>
      ) : (
        title
      )
    }
    extra={extra}
  >
    {children}
  </Card>
);

export default SectionCard;
