import type { ReactNode } from 'react';
import { Flex } from 'antd';
import Text from '@/components/text';

interface PageTitleProps {
  title: ReactNode;
  /** One-line subtitle under the heading. */
  description?: ReactNode;
  /** Right-aligned action bar — buttons, search, a segmented control. */
  actions?: ReactNode;
  className?: string;
}

/** The house page-heading block: an `h1` at the `h2` type scale, a caption, and an action bar. */
const PageTitle = ({ title, description, actions, className = '' }: PageTitleProps) => (
  <Flex align="center" justify="space-between" wrap gap={12} className={className}>
    <Flex vertical gap={4} className="min-w-0">
      <Text as="h1" variant="h2">
        {title}
      </Text>
      {description ? (
        <Text as="div" variant="caption">
          {description}
        </Text>
      ) : null}
    </Flex>
    {actions ? (
      <Flex align="center" gap={8} wrap>
        {actions}
      </Flex>
    ) : null}
  </Flex>
);

export default PageTitle;
export { PageTitle };
