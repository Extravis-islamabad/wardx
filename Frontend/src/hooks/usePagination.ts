import { useCallback, useState } from 'react';
import type { TablePaginationConfig } from 'antd';
import { paginationInitial } from '@/constants/globals';

interface IUsePaginationOptions {
  defaultPage?: number;
  defaultPageSize?: number;
}

interface IUsePaginationReturn {
  page: number;
  page_size: number;
  setPage: (page: number) => void;
  /** The antd Table `pagination` prop for a server-paged list of `total` rows. */
  paginationFor: (total: number | undefined) => TablePaginationConfig;
}

/** Server-side paging state; a page-size change returns to page 1. */
export const usePagination = ({
  defaultPage = paginationInitial.page,
  defaultPageSize = paginationInitial.page_size,
}: IUsePaginationOptions = {}): IUsePaginationReturn => {
  const [page, setPage] = useState(defaultPage);
  const [page_size, setPageSize] = useState(defaultPageSize);

  const paginationFor = useCallback(
    (total: number | undefined): TablePaginationConfig => ({
      current: page,
      pageSize: page_size,
      total: total ?? 0,
      showSizeChanger: true,
      onChange: (nextPage, nextSize) => {
        setPage(nextSize !== page_size ? 1 : nextPage);
        setPageSize(nextSize);
      },
    }),
    [page, page_size],
  );

  return { page, page_size, setPage, paginationFor };
};
