import type { ReactNode } from 'react';
import Text from '@/components/text';

/** Form field label with a red asterisk when `required` is true. */
export const FieldLabel = ({
  children,
  required,
  htmlFor,
}: {
  children: ReactNode;
  required?: boolean;
  /** The input's `id`, so the label names it for screen readers. */
  htmlFor?: string;
}) => (
  <Text as="label" htmlFor={htmlFor} variant="inputLabel" className="mb-1 block">
    {children}
    {required && (
      <Text as="span" variant="errorInline" className="ml-0.5" aria-hidden>
        *
      </Text>
    )}
  </Text>
);

/** Inline error displayed below an RHF-controlled field. */
export const FieldError = ({ message, id }: { message?: string; id?: string }) =>
  message ? (
    <Text id={id} as="div" variant="caption" className="mt-0.5 text-(--error)!">
      {message}
    </Text>
  ) : null;

/** Muted helper line under a field. */
export const FieldHint = ({ children }: { children?: ReactNode }) =>
  children ? (
    <Text as="div" variant="caption" className="mt-0.5">
      {children}
    </Text>
  ) : null;

/** Label above, control, then hint and error: the layout every RHF field shares. */
export const FormField = ({
  label,
  htmlFor,
  required,
  hint,
  error,
  className = 'mb-3',
  children,
}: {
  label?: ReactNode;
  htmlFor?: string;
  required?: boolean;
  hint?: ReactNode;
  error?: string;
  className?: string;
  children: ReactNode;
}) => (
  <div className={className}>
    {label ? (
      <FieldLabel htmlFor={htmlFor} required={required}>
        {label}
      </FieldLabel>
    ) : null}
    {children}
    <FieldHint>{hint}</FieldHint>
    <FieldError message={error} />
  </div>
);

/** Action bar at the bottom of a modal body; Cancel `admin`, confirm `primary` / `danger`. */
export const ModalFooter = ({ children, start }: { children: ReactNode; start?: ReactNode }) => (
  <div
    className={`sticky bottom-0 z-[1] mt-2 flex items-center gap-2 border-t border-(--border) pt-3 ${start ? 'justify-between' : 'justify-end'}`}
  >
    {start ? <div className="min-w-0">{start}</div> : null}
    <div className="flex gap-2">{children}</div>
  </div>
);
