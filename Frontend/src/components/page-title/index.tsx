import type { ReactNode } from 'react';
import { Flex } from 'antd';
import Text from '@/components/text';

interface PageTitleProps {
  title: ReactNode;
  /** One-line subtitle, set beside the heading to save a row. */
  description?: ReactNode;
  /** Right-aligned action bar — buttons, search, a segmented control. */
  actions?: ReactNode;
  className?: string;
}

/** The house page-heading row: a compact `h1`, its caption inline, and an action bar. */
const PageTitle = ({ title, description, actions, className = '' }: PageTitleProps) => (
  <Flex
    align="center"
    justify="space-between"
    wrap
    gap={8}
    className={`min-h-7 ${className}`}
  >
    <Flex align="baseline" gap={8} wrap className="min-w-0">
      <Text as="h1" variant="h3_black">
        {title}
      </Text>
      {description ? (
        <Text as="div" variant="caption">
          {description}
        </Text>
      ) : null}
    </Flex>
    {actions ? (
      <Flex align="center" gap={6} wrap className="wx-page-actions">
        {actions}
      </Flex>
    ) : null}
  </Flex>
);

export default PageTitle;
export { PageTitle };
