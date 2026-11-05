import { Skeleton, Tooltip } from 'antd';
import { useNavigate } from 'react-router-dom';

/** What a KPI's number means for the operator; drives its colour rail. */
export enum KpiTone {
  DEFAULT = 'default',
  SUCCESS = 'success',
  WARNING = 'warning',
  DANGER = 'danger',
}

export interface KpiItem {
  label: string;
  value?: number | string | null;
  loading?: boolean;
  tone?: KpiTone;
  /** Shown on hover — what the number counts. */
  hint?: string;
  /** Route to open on click. */
  to?: string;
}

const TONE_CLASS: Record<KpiTone, { rail: string; value: string }> = {
  [KpiTone.DEFAULT]: { rail: '', value: 'text-(--foreground)' },
  [KpiTone.SUCCESS]: { rail: 'shadow-[inset_2px_0_0_var(--success)]', value: 'text-(--success-text)' },
  [KpiTone.WARNING]: { rail: 'shadow-[inset_2px_0_0_var(--warning)]', value: 'text-(--warning-text)' },
  [KpiTone.DANGER]: { rail: 'shadow-[inset_2px_0_0_var(--error)]', value: 'text-(--error-text)' },
};

/** Tone a count: a problem colour only when there is something to look at. */
export const toneIf = (count: number | null | undefined, tone: KpiTone): KpiTone =>
  count ? tone : KpiTone.DEFAULT;

/** The page KPI strip: one dense row of counters above the page's table. */
export const KpiBar = ({ items }: { items: KpiItem[] }) => {
  const navigate = useNavigate();
  return (
    <div className="grid grid-cols-[repeat(auto-fit,minmax(130px,1fr))] gap-px border border-(--border) bg-(--border)">
      {items.map((k) => {
        const tone = TONE_CLASS[k.tone ?? KpiTone.DEFAULT];
        const tile = (
          <div
            key={k.label}
            role={k.to ? 'link' : undefined}
            tabIndex={k.to ? 0 : undefined}
            onClick={k.to ? () => navigate(k.to as string) : undefined}
            onKeyDown={k.to ? (e) => e.key === 'Enter' && navigate(k.to as string) : undefined}
            className={`flex min-w-0 flex-col justify-between gap-0.5 bg-(--card) px-2.5 py-1.5 ${tone.rail} ${k.to ? 'cursor-pointer hover:bg-(--muted)' : ''}`}
          >
            <span className="wx-label truncate">{k.label}</span>
            {k.loading ? (
              <Skeleton.Input active size="small" className="!h-6 !w-10 !min-w-0" />
            ) : (
              <span className={`wx-mono truncate text-xl leading-6 font-semibold ${tone.value}`}>
                {k.value ?? '—'}
              </span>
            )}
          </div>
        );
        return k.hint ? (
          <Tooltip key={k.label} title={k.hint}>
            {tile}
          </Tooltip>
        ) : (
          tile
        );
      })}
    </div>
  );
};

export default KpiBar;
