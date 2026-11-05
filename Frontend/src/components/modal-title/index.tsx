import type { ReactNode } from 'react';
import Text from '@/components/text';

/** A modal's title, set in the dark title bar (Modal tokens) with the house padding. */
const ModalTitle = ({ children, className = '' }: { children: ReactNode; className?: string }) => (
  <div className={`flex items-center gap-2 px-4 py-2.5 pe-[40px] ${className}`}>
    <Text as="span" variant="h4" className="font-bold! text-(--status-on-solid)!">
      {children}
    </Text>
  </div>
);

export default ModalTitle;
export { ModalTitle };
