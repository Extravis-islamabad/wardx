import { Alert } from 'antd';
import Button from '@/components/button';
import { ErrorStateVariant } from '@/constants/enums/components';
import { apiErrorStatus, errorMessage } from '@/utils/notifyApiError';

const FORBIDDEN = 403;

interface ErrorStateProps {
  error?: unknown;
  title?: string;
  onRetry?: () => void;
  variant?: ErrorStateVariant;
}

/** A failed load, in words — never disguised as an empty state. */
const ErrorState = ({ error, title, onRetry, variant = ErrorStateVariant.BANNER }: ErrorStateProps) => {
  const forbidden = apiErrorStatus(error) === FORBIDDEN;
  const alert = (
    <Alert
      type="error"
      showIcon
      title={title ?? (forbidden ? "You don't have access to this" : "Couldn't load this")}
      description={error ? errorMessage(error) : undefined}
      action={
        onRetry && !forbidden ? (
          <Button variant="admin" size="small" onClick={onRetry}>
            Retry
          </Button>
        ) : undefined
      }
    />
  );
  return variant === ErrorStateVariant.BLOCK ? <div className="py-6 text-left">{alert}</div> : alert;
};

export default ErrorState;
