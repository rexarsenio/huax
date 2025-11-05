import { useMemo } from "react";
import clsx from "clsx";
import { useTranslation } from "react-i18next";
import { Card } from "./Card";
import { Skeleton } from "./Skeleton";
import type { LatestIndexSnapshot } from "../api/types";

type HeroKpiProps = {
  data?: LatestIndexSnapshot | null;
  isLoading?: boolean;
  isError?: boolean;
  onRetry?: () => void;
  asOf?: string | null;
  isStale?: boolean;
};

const BADGE_TONES: Record<string, string> = {
  green: "bg-success/15 text-success",
  yellow: "bg-warning/20 text-warning",
  orange: "bg-warning/20 text-warning",
  red: "bg-danger/20 text-danger",
  blue: "bg-accent/20 text-accent",
  teal: "bg-accent/20 text-accent",
  navy: "bg-foreground/15 text-foreground/80",
};

const ordinal = (value: number) => {
  const rank = Math.round(value);
  if (Number.isNaN(rank)) {
    return "—";
  }
  if (10 <= rank % 100 && rank % 100 <= 20) {
    return `${rank}th`;
  }
  const suffixMap: Record<number, string> = { 1: "st", 2: "nd", 3: "rd" };
  const suffix = suffixMap[rank % 10] ?? "th";
  return `${rank}${suffix}`;
};

const formatSigned = (value: number | null | undefined, digits = 1) => {
  if (value == null || !Number.isFinite(value)) {
    return "—";
  }
  const formatted = value.toFixed(digits);
  return value > 0 ? `+${formatted}` : formatted;
};

const formatPercent = (value: number | null | undefined, digits = 1) => {
  if (value == null || !Number.isFinite(value)) {
    return "—";
  }
  return `${value >= 0 ? "+" : ""}${value.toFixed(digits)}%`;
};

export const HeroKpi = ({ data, isLoading, isError, onRetry, asOf, isStale }: HeroKpiProps) => {
  const { t, i18n } = useTranslation();
  const locale = i18n.language;
  const asOfDate = useMemo(() => {
    const source = asOf ?? data?.ts;
    if (!source) {
      return null;
    }
    const parsed = new Date(source);
    return Number.isNaN(parsed.getTime()) ? null : parsed;
  }, [asOf, data?.ts]);
  const formattedAsOf = useMemo(() => {
    if (!asOfDate) {
      return undefined;
    }
    return asOfDate.toLocaleString(locale, {
      year: "numeric",
      month: "short",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      timeZone: "UTC",
      timeZoneName: "short",
    });
  }, [asOfDate, locale]);
  const subtitleText = formattedAsOf
    ? isStale
      ? t("dashboard.latestIndex.staleSubtitle", {
          defaultValue: "Stale snapshot · last fix {{datetime}}",
          datetime: formattedAsOf,
        })
      : t("dashboard.latestIndex.subtitle", { defaultValue: "As of {{datetime}}", datetime: formattedAsOf })
    : undefined;

  if (isLoading) {
    return (
      <Card
        title={t("dashboard.latestIndex.title")}
        subtitle={t("dashboard.latestIndex.loading", { defaultValue: "Loading latest snapshot…" })}
      >
        <Skeleton className="h-48 w-full" />
      </Card>
    );
  }

  if (isError || !data) {
    return (
      <Card
        title={t("dashboard.latestIndex.title")}
        subtitle={t("dashboard.latestIndex.unavailable", { defaultValue: "Latest snapshot unavailable." })}
      >
        <div className="flex flex-col gap-4 rounded-xl border border-foreground/20 bg-foreground/5 p-6">
          <div className="flex items-center gap-3">
            <span className="text-3xl">⏳</span>
            <div>
              <p className="text-lg font-semibold text-foreground">{t("dashboard.latestIndex.unavailable", { defaultValue: "Data is currently being collected" })}</p>
              <p className="text-sm text-foreground/70">{t("dashboard.latestIndex.retryHint", { defaultValue: "Data collection is ongoing. Please check back shortly." })}</p>
            </div>
          </div>
          {onRetry && (
            <button
              type="button"
              onClick={onRetry}
              className="inline-flex w-fit items-center rounded-full border border-foreground/20 px-4 py-2 text-sm text-foreground/70 hover:border-accent hover:text-accent"
            >
              {t("actions.refresh", { defaultValue: "Refresh" })}
            </button>
          )}
        </div>
      </Card>
    );
  }

  const classification = data.classification ?? undefined;
  const badgeClasses = classification ? BADGE_TONES[classification.color] ?? "bg-foreground/10 text-foreground/80" : "bg-foreground/10 text-foreground/80";
  const badgeLabel = classification?.headline ?? classification?.status ?? t("dashboard.latestIndex.statusUnknown", { defaultValue: "Status unavailable" });
  const seasonalBaselineText =
    data.seasonal_baseline != null && Number.isFinite(data.seasonal_baseline)
      ? t("dashboard.latestIndex.seasonalBaseline", {
          defaultValue: "Seasonal baseline {{value}}",
          value: data.seasonal_baseline.toLocaleString(locale, { maximumFractionDigits: 1 }),
        })
      : undefined;

  const tiles = [
    {
      key: "spvx",
      label: t("dashboard.latestIndex.tiles.spvxToday", { defaultValue: "SPVX (today)" }),
      primary: data.spvx.toLocaleString(locale, { maximumFractionDigits: 2 }),
    },
    {
      key: "deviation",
      label: t("dashboard.latestIndex.deviation", { defaultValue: "Deviation vs seasonal" }),
      primary: formatPercent(data.deviation_pct),
      primaryClass:
        data.deviation_pct != null && Number.isFinite(data.deviation_pct)
          ? data.deviation_pct >= 0
            ? "text-success"
            : "text-danger"
          : "text-foreground/70",
      secondary:
        data.zscore != null && Number.isFinite(data.zscore)
          ? t("dashboard.latestIndex.zScoreLabel", {
              defaultValue: "{{value}}σ",
              value: formatSigned(data.zscore, 2),
            })
          : undefined,
    },
    {
      key: "percentile",
      label: t("dashboard.latestIndex.tiles.percentile70d", { defaultValue: "Percentile (70d)" }),
      primary:
        data.percentile_70d != null && Number.isFinite(data.percentile_70d)
          ? ordinal(data.percentile_70d)
          : "—",
      secondary: t("dashboard.latestIndex.tiles.percentileWindow", { defaultValue: "Last 70 days" }),
    },
    {
      key: "delta",
      label: t("dashboard.latestIndex.tiles.deltaDay", { defaultValue: "Δ vs prior day" }),
      primary:
        data.delta_day_points != null && Number.isFinite(data.delta_day_points)
          ? `${formatSigned(data.delta_day_points, 2)} ${t("dashboard.latestIndex.tiles.points", { defaultValue: "pts" })}`
          : "—",
      primaryClass:
        data.delta_day_points != null && Number.isFinite(data.delta_day_points)
          ? data.delta_day_points >= 0
            ? "text-success"
            : "text-danger"
          : "text-foreground/70",
      secondary:
        data.delta_day_pct != null && Number.isFinite(data.delta_day_pct)
          ? formatPercent(data.delta_day_pct)
          : t("dashboard.latestIndex.tiles.noDelta", { defaultValue: "Awaiting change window" }),
    },
  ];

  return (
    <Card
      title={t("dashboard.latestIndex.title")}
      subtitle={subtitleText}
      action={
        seasonalBaselineText ? (
          <span className="text-xs font-medium uppercase tracking-wide text-foreground/50">{seasonalBaselineText}</span>
        ) : undefined
      }
    >
      <div className="flex flex-wrap items-center gap-3">
        <span className={clsx("inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-wide", badgeClasses)}>
          {classification?.emoji && <span aria-hidden>{classification.emoji}</span>}
          {badgeLabel}
        </span>
        {isStale && formattedAsOf && (
          <span className="inline-flex items-center gap-2 rounded-full bg-warning/10 px-3 py-1 text-xs font-semibold text-warning">
            ⚠ {t("dashboard.refresh.stale", { defaultValue: "Stale since {{datetime}}", datetime: formattedAsOf })}
          </span>
        )}
        <span className="text-sm text-foreground/60">
          {t("dashboard.latestIndex.scopeLabel", { defaultValue: "Scope: {{scope}}", scope: data.scope.toUpperCase() })}
        </span>
      </div>

        <div className="space-y-6">
          <div className="grid gap-3 sm:grid-cols-2">
            {tiles.map((tile) => (
              <div
                key={tile.key}
                className="rounded-2xl border border-foreground/10 bg-foreground/5 px-4 py-3 text-center shadow-sm"
              >
                <p className="text-xs uppercase tracking-wide text-foreground/60">{tile.label}</p>
                <div className="mt-2 space-y-1">
                  <p className={clsx("text-3xl font-semibold leading-tight", tile.primaryClass)}>
                    {tile.primary}
                  </p>
                  {tile.secondary && <p className="text-sm text-foreground/60">{tile.secondary}</p>}
                </div>
              </div>
            ))}
          </div>
        </div>
    </Card>
  );
};
