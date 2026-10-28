import { theme, type ThemeConfig } from 'antd';
import { ThemeMode } from '@/constants/enums/theme';

// antd derives its palette from a parseable colour, so the brand seed lives here beside the CSS tokens.
const BRAND_PRIMARY = '#5b6cff';

export const getAntdThemeConfig = (mode: ThemeMode): ThemeConfig => ({
  algorithm: mode === ThemeMode.DARK ? theme.darkAlgorithm : theme.defaultAlgorithm,
  token: { colorPrimary: BRAND_PRIMARY, borderRadius: 8 },
});
