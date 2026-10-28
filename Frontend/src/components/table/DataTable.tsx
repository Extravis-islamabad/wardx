import { Table, type TableProps } from 'antd';
import ErrorState from '@/components/state/ErrorState';
import { ErrorStateVariant } from '@/constants/enums/components';

export interface IDataTableProps<T> extends TableProps<T> {
  isError?: boolean;
  error?: unknown;
  onRetry?: () => void;
  errorTitle?: string;
}

/** antd Table that reports its own failed load instead of "No data". Spread `tableStateProps(query)` first. */
const DataTable = <T extends object>({
  dataSource,
  isError,
  error,
  onRetry,
  errorTitle,
  locale,
  ...rest
}: IDataTableProps<T>) => (
  <Table<T>
    {...rest}
    // Stale rows must not sit under an error — they read as current data.
    dataSource={isError ? [] : dataSource}
    locale={
      isError
        ? {
            ...locale,
            emptyText: (
              <ErrorState error={error} title={errorTitle} onRetry={onRetry} variant={ErrorStateVariant.BLOCK} />
            ),
          }
        : locale
    }
  />
);

export default DataTable;
