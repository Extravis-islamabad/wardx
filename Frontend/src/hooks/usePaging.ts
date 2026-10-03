import { useState } from 'react';
import type { TablePaginationConfig } from 'antd';

/** Server-side paging state plus the antd Table pagination prop for it. */
export function usePaging(pageSize = 25) {
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(pageSize);
  const pagination = (total: number | undefined): TablePaginationConfig => ({
    current: page,
    pageSize: size,
    total: total ?? 0,
    showSizeChanger: true,
    onChange: (p, s) => {
      setPage(s !== size ? 1 : p);
      setSize(s);
    },
  });
  return { page, page_size: size, setPage, pagination };
}
