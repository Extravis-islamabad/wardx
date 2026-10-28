import type { TokenPair } from '@/services/auth-services';

type Tokens = Pick<TokenPair, 'access_token' | 'refresh_token'>;

const ACCESS_KEY = 'wardx.access';
const REFRESH_KEY = 'wardx.refresh';

export const tokens = {
  access: () => localStorage.getItem(ACCESS_KEY),
  refresh: () => localStorage.getItem(REFRESH_KEY),
  set(pair: Tokens) {
    localStorage.setItem(ACCESS_KEY, pair.access_token);
    localStorage.setItem(REFRESH_KEY, pair.refresh_token);
  },
  clear() {
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
  },
};
