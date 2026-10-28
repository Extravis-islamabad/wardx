import React from 'react';

interface BoxProps extends React.HTMLAttributes<HTMLDivElement> {
  children?: React.ReactNode;
  className?: string;
}

/** Plain bordered surface; inside a modal it is the one body wrapper (`className="px-2 border-0"`). */
export const Box = React.forwardRef<HTMLDivElement, BoxProps>(function Box({ children, className = '', ...rest }, ref) {
  return (
    <div ref={ref} className={`flex flex-col border border-(--border) py-2 ${className}`} {...rest}>
      <div className="min-h-0 flex-1 text-(--foreground)">{children}</div>
    </div>
  );
});

export default Box;
