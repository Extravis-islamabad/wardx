import { createContext, useContext } from 'react';

/**
 * The header element a page's heading is portalled into. `BaseLayout` owns it;
 * `PageShell` renders into it. Null outside the layout (Login), where the
 * heading stays in the page.
 */
export const PageHeadingSlotContext = createContext<HTMLElement | null>(null);

export const usePageHeadingSlot = () => useContext(PageHeadingSlotContext);
