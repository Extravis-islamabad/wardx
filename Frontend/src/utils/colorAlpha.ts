const HEX = /^#([0-9a-f]{3,4}|[0-9a-f]{6}|[0-9a-f]{8})$/i;
const RGB = /^rgba?\(\s*([^)]+)\)$/i;

const clamp01 = (n: number) => Math.min(1, Math.max(0, n));

/**
 * Scale a colour's opacity by `alpha` (0–1) and return `rgba(r, g, b, a)`.
 * Handles `#rgb`, `#rgba`, `#rrggbb`, `#rrggbbaa` and `rgb()`/`rgba()`;
 * anything else (named, oklch, gradients) passes through unchanged.
 */
export const withAlpha = (color: string, alpha: number): string => {
  const source = (color ?? '').trim();
  const hex = HEX.exec(source)?.[1];
  if (hex) {
    const full =
      hex.length <= 4
        ? hex
            .split('')
            .map((c) => c + c)
            .join('')
        : hex;
    const r = parseInt(full.slice(0, 2), 16);
    const g = parseInt(full.slice(2, 4), 16);
    const b = parseInt(full.slice(4, 6), 16);
    const base = full.length === 8 ? parseInt(full.slice(6, 8), 16) / 255 : 1;
    return `rgba(${r}, ${g}, ${b}, ${clamp01(base * alpha)})`;
  }
  const rgb = RGB.exec(source)?.[1];
  if (rgb) {
    const parts = rgb.split(/[\s,/]+/).filter(Boolean);
    const [r, g, b, rawBase] = parts;
    if (r === undefined || g === undefined || b === undefined) return color;
    const base =
      rawBase === undefined ? 1 : rawBase.endsWith('%') ? parseFloat(rawBase) / 100 : parseFloat(rawBase);
    return `rgba(${r}, ${g}, ${b}, ${clamp01((Number.isNaN(base) ? 1 : base) * alpha)})`;
  }
  return color;
};
