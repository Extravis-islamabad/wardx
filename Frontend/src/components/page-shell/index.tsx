import type { ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { Card, Flex } from 'antd';
import { usePageHeadingSlot } from '@/components/layout/PageHeadingSlot';
import PageTitle from '@/components/page-title';
import Text from '@/components/text';

interface PageShellProps {
  /** Page heading, rendered as the `h1` — in the top bar when the layout provides one. */
  title?: ReactNode;
  /** One-line subtitle beside the heading. */
  description?: ReactNode;
  /** Right-aligned action bar — buttons, search, a segmented control. */
  actions?: ReactNode;
  /** The page's KPI strip (`KpiBar`), set above the action bar and content. */
  kpis?: ReactNode;
  /** Gap between the action bar and each top-level content block, in px. */
  gap?: number;
  /** Skip the Card frame. Full-bleed surfaces only (Login). */
  bare?: boolean;
  className?: string;
  children: ReactNode;
}

/** The heading as it sits in the top bar: title, then the description cut to one line. */
const HeaderHeading = ({ title, description }: { title: ReactNode; description?: ReactNode }) => (
  <Flex align="baseline" gap={8} className="min-w-0">
    <Text as="h1" variant="h3_black" className="shrink-0 whitespace-nowrap">
      {title}
    </Text>
    {description ? (
      <Text
        as="div"
        variant="caption"
        className="min-w-0 truncate"
        title={typeof description === 'string' ? description : undefined}
      >
        {description}
      </Text>
    ) : null}
  </Flex>
);

/**
 * The canonical page root: a Card frame holding the page's action bar and content
 * blocks. Inside the console layout the heading moves to the top bar, saving a row.
 */
export const PageShell = ({
  title,
  description,
  actions,
  kpis,
  gap = 12,
  bare = false,
  className = '',
  children,
}: PageShellProps) => {
  const headingSlot = usePageHeadingSlot();
  const inHeader = Boolean(headingSlot && title);

  const body = (
    <Flex vertical gap={gap} className="min-w-0">
      {kpis}
      {inHeader ? (
        actions ? (
          <Flex align="center" justify="flex-end" gap={6} wrap className="wx-page-actions">
            {actions}
          </Flex>
        ) : null
      ) : title || actions ? (
        <PageTitle title={title ?? ''} description={description} actions={actions} />
      ) : null}
      {children}
    </Flex>
  );

  return (
    <>
      {inHeader && headingSlot
        ? createPortal(<HeaderHeading title={title} description={description} />, headingSlot)
        : null}
      {bare ? (
        <div className={`min-w-0 ${className}`}>{body}</div>
      ) : (
        <Card className={`min-w-0 ${className}`}>{body}</Card>
      )}
    </>
  );
};

export default PageShell;
