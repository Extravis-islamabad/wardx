/** The slice of a react-query result this needs. Structural, so any version fits. */
type QueryLike = {
  isLoading: boolean;
  isError: boolean;
  error?: unknown;
  refetch?: () => unknown;
};

export type TableStateProps = {
  loading: boolean;
  isError: boolean;
  error: unknown;
  onRetry?: () => void;
  errorTitle?: string;
};

/** The loading / error half of a `DataTable`'s props, so a failed load never reads as "No data". */
export const tableStateProps = (query: QueryLike | undefined, errorTitle?: string): TableStateProps => ({
  loading: Boolean(query?.isLoading),
  isError: Boolean(query?.isError),
  error: query?.error,
  onRetry: query?.refetch ? () => void query.refetch?.() : undefined,
  errorTitle,
});

export default tableStateProps;
