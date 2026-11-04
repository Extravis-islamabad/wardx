/**
 * Maps the theme's CSS variables to antd tokens — the MoneTX mapping, trimmed
 * to the components WardX renders. Call it only after `<html data-theme>` is
 * set, since it reads the computed values of the active theme.
 */
import { theme, type ThemeConfig } from 'antd';
import { ThemeMode } from '@/constants/enums/theme';
import { withAlpha } from '@/utils/colorAlpha';

const cssVar = (name: string): string =>
  getComputedStyle(document.documentElement).getPropertyValue(name).trim();

export const getAntdThemeConfig = (mode: ThemeMode): ThemeConfig => {
  const background = cssVar('--background');
  const foreground = cssVar('--foreground');
  const card = cssVar('--card');
  const muted = cssVar('--muted');
  const mutedForeground = cssVar('--muted-foreground');
  const input = cssVar('--input');
  const border = cssVar('--border');
  const primary = cssVar('--primary');
  const primaryHover = cssVar('--primary-hover');
  const primaryForeground = cssVar('--primary-foreground');
  const danger = cssVar('--danger');
  const dangerHover = cssVar('--danger-hover');
  const success = cssVar('--success');
  const warning = cssVar('--warning');
  const error = cssVar('--error');
  const info = cssVar('--info');
  const textPrimary = cssVar('--text-primary');
  const textSecondary = cssVar('--text-secondary');
  const textTertiary = cssVar('--text-tertiary');
  const navBackground = cssVar('--nav-background');
  const navItem = cssVar('--nav-item-color');
  const navHover = cssVar('--nav-hover-bg');
  const navSelectedBg = cssVar('--nav-selected-bg');
  const navSelected = cssVar('--nav-selected-color');
  const onSolid = cssVar('--status-on-solid');
  const fontSans = cssVar('--font-sans');
  const fontMono = cssVar('--font-mono');

  return {
    algorithm: mode === ThemeMode.DARK ? theme.darkAlgorithm : theme.defaultAlgorithm,
    token: {
      colorPrimary: primary,
      colorPrimaryHover: primaryHover,
      colorSuccess: success,
      colorWarning: warning,
      colorError: error,
      colorInfo: info,
      colorLink: primary,
      colorLinkHover: primaryHover,

      colorBgBase: background,
      colorBgContainer: card,
      colorBgElevated: card,
      colorBgLayout: background,
      colorBgSpotlight: muted,
      colorBgMask: cssVar('--scrim'),

      colorText: foreground,
      colorTextSecondary: textSecondary,
      colorTextTertiary: textTertiary,
      colorTextQuaternary: textTertiary,
      colorTextPlaceholder: mutedForeground,
      colorTextDisabled: mutedForeground,

      colorBorder: border,
      colorBorderSecondary: border,
      colorSplit: border,

      // NOC aesthetic: sharp edges, 2px keeps chips and inputs from looking cut.
      borderRadius: 2,
      borderRadiusLG: 2,
      borderRadiusSM: 2,
      borderRadiusXS: 0,

      fontFamily: fontSans,
      // Secrets, recovery codes and commands read in mono.
      fontFamilyCode: fontMono,
      fontSize: 13,
      fontSizeHeading1: 32,
      fontSizeHeading2: 24,
      fontSizeHeading3: 19,
      fontSizeHeading4: 16,
      fontSizeHeading5: 14,
      lineHeight: 1.5,

      // Density — minimal whitespace, maximum information.
      controlHeight: 28,
      controlHeightSM: 22,
      controlHeightLG: 34,
      padding: 12,
      paddingSM: 8,
      paddingXS: 6,
      paddingLG: 16,
      margin: 12,
      marginSM: 8,
      marginXS: 6,
      marginLG: 16,
    },
    components: {
      Layout: {
        bodyBg: background,
        headerBg: card,
        headerHeight: 40,
        headerPadding: '0 12px',
        siderBg: navBackground,
        triggerBg: navBackground,
      },
      Menu: {
        // The sider is dark in both themes (the NOC nav signature).
        darkItemBg: navBackground,
        darkSubMenuItemBg: navBackground,
        darkPopupBg: navBackground,
        darkItemColor: navItem,
        darkItemHoverBg: navHover,
        darkItemHoverColor: onSolid,
        darkItemSelectedBg: navSelectedBg,
        darkItemSelectedColor: navSelected,
        itemBorderRadius: 0,
        itemMarginInline: 0,
        itemHeight: 32,
        collapsedWidth: 48,
        collapsedIconSize: 16,
        iconSize: 14,
        // Light menus (Dropdown) sit on --card.
        itemBg: card,
        itemColor: foreground,
        itemHoverBg: muted,
        itemHoverColor: foreground,
        itemSelectedBg: muted,
        itemSelectedColor: foreground,
      },
      Skeleton: {
        gradientFromColor: cssVar('--skeleton-from'),
        gradientToColor: cssVar('--skeleton-to'),
      },
      Button: {
        colorPrimary: primary,
        colorPrimaryHover: primaryHover,
        primaryColor: primaryForeground,
        // Keep antd's own danger buttons (Popconfirm) on the theme's red.
        colorError: danger,
        colorErrorHover: dangerHover,
        // Default buttons stay neutral on hover instead of flashing the accent.
        defaultBg: muted,
        defaultColor: foreground,
        defaultBorderColor: border,
        defaultHoverBg: card,
        defaultHoverColor: foreground,
        defaultHoverBorderColor: primary,
        defaultActiveBg: card,
        defaultActiveColor: foreground,
        defaultActiveBorderColor: primary,
        primaryShadow: 'none',
        defaultShadow: 'none',
        dangerShadow: 'none',
      },
      Input: {
        colorBgContainer: input,
        activeBorderColor: primary,
        hoverBorderColor: primary,
        activeShadow: `0 0 0 2px ${withAlpha(primary, 0.15)}`,
        colorIcon: foreground,
        colorIconHover: primary,
      },
      InputNumber: {
        colorBgContainer: input,
        activeBorderColor: primary,
        hoverBorderColor: primary,
        activeShadow: `0 0 0 2px ${withAlpha(primary, 0.15)}`,
      },
      Select: {
        colorBgContainer: input,
        colorBgElevated: card,
        colorTextQuaternary: mutedForeground,
        optionSelectedBg: withAlpha(primary, 0.16),
        optionSelectedColor: foreground,
        optionActiveBg: muted,
        activeOutlineColor: withAlpha(primary, 0.15),
      },
      DatePicker: {
        colorBgContainer: input,
        colorBgElevated: card,
        colorTextQuaternary: mutedForeground,
        cellHoverBg: muted,
        cellActiveWithRangeBg: withAlpha(primary, 0.14),
        colorIcon: foreground,
        colorIconHover: primary,
      },
      Tooltip: {
        // An elevated surface, not an inverted block; the border is in index.css.
        colorBgSpotlight: card,
        colorTextLightSolid: foreground,
      },
      Card: {
        colorBgContainer: card,
        colorBorderSecondary: border,
        headerHeight: 32,
        headerHeightSM: 28,
        headerPadding: 10,
        headerPaddingSM: 8,
        bodyPadding: 12,
        bodyPaddingSM: 10,
        headerFontSize: 13,
        headerFontSizeSM: 12,
      },
      Alert: {
        colorSuccessBg: muted,
        colorSuccessBorder: success,
        colorInfoBg: muted,
        colorInfoBorder: info,
        colorWarningBg: muted,
        colorWarningBorder: warning,
        colorErrorBg: muted,
        colorErrorBorder: error,
      },
      Table: {
        colorBgContainer: card,
        headerBg: muted,
        headerColor: mutedForeground,
        headerSplitColor: border,
        borderColor: border,
        rowHoverBg: muted,
        rowSelectedBg: withAlpha(primary, 0.12),
        rowSelectedHoverBg: withAlpha(primary, 0.2),
        cellPaddingBlock: 4,
        cellPaddingInline: 6,
        cellPaddingBlockMD: 4,
        cellPaddingInlineMD: 6,
        cellPaddingBlockSM: 4,
        cellPaddingInlineSM: 6,
        fontSize: 12,
      },
      Descriptions: {
        itemPaddingBottom: 4,
        padding: 8,
        titleMarginBottom: 6,
        labelBg: muted,
        labelColor: mutedForeground,
        titleColor: foreground,
      },
      Modal: {
        contentBg: card,
        // A dark title bar in both themes, like the nav. Each modal supplies its
        // own padding through `ModalTitle` and `Box`.
        headerBg: navBackground,
        titleColor: onSolid,
        titleFontSize: 12,
        colorIcon: onSolid,
        colorIconHover: cssVar('--nav-accent'),
        colorTextHeading: foreground,
        paddingMD: 0,
        paddingContentHorizontalLG: 0,
        paddingContentVerticalLG: 0,
        padding: 0,
      },
      Drawer: {
        colorBgElevated: card,
      },
      Notification: {
        colorBgElevated: card,
        colorIcon: mutedForeground,
        colorIconHover: primary,
      },
      Message: {
        contentBg: card,
      },
      Tabs: {
        itemColor: textTertiary,
        itemActiveColor: textPrimary,
        itemSelectedColor: primary,
        itemHoverColor: primary,
        inkBarColor: primary,
        cardBg: muted,
        horizontalItemGutter: 16,
        horizontalItemPadding: '6px 2px',
        horizontalMargin: '0 0 12px 0',
        titleFontSize: 13,
      },
      Segmented: {
        trackBg: muted,
        itemColor: mutedForeground,
        itemHoverColor: foreground,
        itemSelectedBg: primary,
        itemSelectedColor: primaryForeground,
      },
      Switch: {
        handleBg: '#ffffff',
      },
      Steps: {
        colorTextDescription: mutedForeground,
      },
    },
  };
};
