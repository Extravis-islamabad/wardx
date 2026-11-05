import { App as AntdApp, ConfigProvider } from 'antd';
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { ThemeMode } from '@/constants/enums/theme';
import { setNotifyInstance } from '@/utils/notify';
import { getAntdThemeConfig } from './antdThemeConfig';
import './light.css';
import './dark.css';

const THEME_STORAGE_KEY = 'wardx.theme';

interface ThemeContextValue {
  mode: ThemeMode;
  toggle: () => void;
}

const ThemeContext = createContext<ThemeContextValue>({
  mode: ThemeMode.DARK,
  toggle: () => undefined,
});

const readSavedMode = (): ThemeMode => {
  try {
    const saved = localStorage.getItem(THEME_STORAGE_KEY);
    if (saved === ThemeMode.LIGHT || saved === ThemeMode.DARK) return saved;
  } catch {
    // Storage blocked: fall through to the default.
  }
  return ThemeMode.DARK;
};

/**
 * Put the theme on `<html>` synchronously. `getAntdThemeConfig` reads the CSS
 * variables, so the attribute must change before the render that builds it —
 * not in an effect after, which would hand antd the previous theme's colours.
 */
const applyMode = (mode: ThemeMode) => {
  document.documentElement.dataset.theme = mode;
};

const initialMode = (): ThemeMode => {
  const mode = readSavedMode();
  applyMode(mode);
  return mode;
};

/** Hands `notify` the themed `App` notification instance. */
const NotifyBridge = () => {
  const { notification } = AntdApp.useApp();
  useEffect(() => {
    setNotifyInstance(notification);
    return () => setNotifyInstance(null);
  }, [notification]);
  return null;
};

const ThemeProvider = ({ children }: { children: ReactNode }) => {
  const [mode, setMode] = useState<ThemeMode>(initialMode);

  useEffect(() => {
    try {
      localStorage.setItem(THEME_STORAGE_KEY, mode);
    } catch {
      // Not persisted; fine.
    }
  }, [mode]);

  const value = useMemo<ThemeContextValue>(
    () => ({
      mode,
      toggle: () => {
        const next = mode === ThemeMode.DARK ? ThemeMode.LIGHT : ThemeMode.DARK;
        applyMode(next);
        setMode(next);
      },
    }),
    [mode],
  );

  // Rebuilt per theme only; the attribute is already set, so the reads are current.
  const antdTheme = useMemo(() => getAntdThemeConfig(mode), [mode]);

  return (
    <ThemeContext.Provider value={value}>
      <ConfigProvider theme={antdTheme}>
        <AntdApp>
          <NotifyBridge />
          {children}
        </AntdApp>
      </ConfigProvider>
    </ThemeContext.Provider>
  );
};

export const useTheme = () => useContext(ThemeContext);

/** A theme token's resolved value, for APIs that need a literal colour (canvas, QR codes). */
export const cssVar = (name: `--${string}`): string =>
  getComputedStyle(document.documentElement).getPropertyValue(name).trim();

export default ThemeProvider;
