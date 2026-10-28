import type { ReactNode } from 'react';
import { Card, Flex } from 'antd';
import PageTitle from '@/components/page-title';

interface PageShellProps {
  /** Page heading, rendered as the `h1`. */
  title?: ReactNode;
  /** One-line subtitle under the heading. */
  description?: ReactNode;
  /** Right-aligned action bar — buttons, search, a segmented control. */
  actions?: ReactNode;
  /** Gap between the header and each top-level content block, in px. */
  gap?: number;
  /** Skip the Card frame. Full-bleed surfaces only (Login). */
  bare?: boolean;
  className?: string;
  children: ReactNode;
}

/** The canonical page root: a Card frame wrapping a `PageTitle` header row and the page's content blocks. */
export const PageShell = ({
  title,
  description,
  actions,
  gap = 12,
  bare = false,
  className = '',
  children,
}: PageShellProps) => {
  const body = (
    <Flex vertical gap={gap} className="min-w-0">
      {title || actions ? <PageTitle title={title ?? ''} description={description} actions={actions} /> : null}
      {children}
    </Flex>
  );
  return bare ? (
    <div className={`min-w-0 ${className}`}>{body}</div>
  ) : (
    <Card className={`min-w-0 ${className}`}>{body}</Card>
  );
};

export default PageShell;
