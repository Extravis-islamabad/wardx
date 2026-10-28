import { Alert } from 'antd';
import type { ChainVerification } from '@/services/audit-services';
import { errorMessage } from '@/utils/notifyApiError';

/** The verify call opts out of the toast, so its failure is worded here. */
export function ChainVerificationResult({ result, error }: { result?: ChainVerification; error?: unknown }) {
  if (error) return <Alert type="error" showIcon title={errorMessage(error)} />;
  if (!result) return null;
  return (
    <Alert
      showIcon
      type={result?.ok ? 'success' : 'error'}
      title={
        result?.ok
          ? `Hash chain intact: ${result?.checked} events verified.`
          : `Chain broken at event #${result?.broken_at_seq}: ${result?.reason}. Events after this point cannot be trusted.`
      }
    />
  );
}

export default ChainVerificationResult;
