export const paginationInitial = { page: 1, page_size: 25 } as const;

/** Lists that feed a picker load one large page instead of paging. */
export const PICKER_PAGE = { page: 1, page_size: 200 } as const;
