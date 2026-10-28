import type { ReactNode } from 'react';
import Text from '@/components/text';

const ModalTitle = ({ children, className = '' }: { children: ReactNode; className?: string }) => (
  <div className={`flex items-center gap-2 pe-[40px] ${className}`}>
    <Text as="span" variant="h3" className="font-semibold!">
      {children}
    </Text>
  </div>
);

export default ModalTitle;
export { ModalTitle };
