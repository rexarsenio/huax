import { useCallback, useMemo, useState } from "react";
import { Card } from "../components/Card";
import { Skeleton } from "../components/Skeleton";
import { TimeSeriesChart } from "../components/TimeSeriesChart";
import { ChokepointTable } from "../components/ChokepointTable";
import { OpenSeaPanel } from "../components/OpenSeaPanel";
import { MarketContext } from "../components/MarketContext";
import { ComponentCard } from "../components/ComponentCard";
import { HeroKpi } from "../components/HeroKpi";
import {
  useLatestIndex,
  useGlobalIndex,
  useBasinIndex,
  useBasinComponents,
  useOpsHealth,
  useSignalsSnapshot,
} from "../hooks/useApi";
import type {
  Basin,
  ComponentPoint,
  GlobalIndexPoint,
  BasinIndexPoint,
  RelativeStressPayload,
} from "../api/types";
import { clsx } from "clsx";
import { useTranslation } from "react-i18next";
import { downloadBasinCsv } from "../api/client";
import { appConfig } from "../config";

const BASINS: Basin[] = ["GLOBAL", "APAC", "NAM", "SAM", "MED"];

const BASIN_LABELS: Record<Basin, string> = {
  GLOBAL: "Global",
  APAC: "APAC",
  NAM: "North America",
  SAM: "South America",
  MED: "Mediterranean",
};

const BASIN_COMPONENTS: Partial<Record<Basin, string[]>> = {
  APAC: ["CQ_SG", "CQ_HRZ", "CQ_TR", "PORT_EU"],
  NAM: ["CQ_PAN", "PORT_US"],
  SAM: ["CQ_PAN_S", "PORT_BR"],
  MED: ["CQ_SUEZ", "CQ_GIBRALTAR", "PORT_MED"],
};

const BETA_BASINS = new Set<Basin>(["SAM", "MED"]);

type LatestIndexCardProps = {
  title: string;
  subtitle?: string;
  value?: number;
  previous?: number;
  loading: boolean;
  weatherFlag?: number;
  relativeStress?: RelativeStressPayload;
  latestPoint?: IndexPoint;
};

const ordinal = (value: number) => {
  const rank = Math.round(value);
  if (10 <= rank % 100 && rank % 100 <= 20) {
    return `${rank}th`;
  }
  const suffixMap: Record<number, string> = { 1: "st", 2: "nd", 3: "rd" };
  const suffix = suffixMap[rank % 10] ?? "th";
  return `${rank}${suffix}`;
};

const LatestIndexCard = ({
  title,
  subtitle,
  value,
  previous,
  loading,
  weatherFlag,
  relativeStress,
  latestPoint,
}: LatestIndexCardProps) => {
  const { t, i18n } = useTranslation();
  const locale = i18n.language;
  const stressLatest = relativeStress?.latest;
  const narrative = relativeStress?.narrative;
  const historyPreview = relativeStress?.history?.slice(-5) ?? [];
  const baseline =
    stressLatest?.seasonal_mean != null ? stressLatest.seasonal_mean : undefined;
  const pointMetrics =
    latestPoint as { data_gap_ratio?: number | null; ingest_lag_seconds?: number | null } | undefined;
  const dataGapRatio =
    stressLatest?.data_gap_ratio != null
      ? stressLatest.data_gap_ratio
      : pointMetrics?.data_gap_ratio != null
      ? pointMetrics.data_gap_ratio
      : undefined;
  const ingestLagSeconds =
    stressLatest?.ingest_lag_seconds != null
      ? stressLatest.ingest_lag_seconds
      : pointMetrics?.ingest_lag_seconds != null
      ? pointMetrics.ingest_lag_seconds
      : undefined;

  if (loading) {
    return (
      <Card title={title} subtitle={subtitle}>
        <Skeleton className="h-24 w-full" />
      </Card>
    );
  }

  if (value === undefined) {
    return (
      <Card title={title} subtitle={subtitle}>
        <p className="text-sm text-foreground/60">{t("dashboard.latestIndex.unavailable")}</p>
      </Card>
    );
  }

  const formattedValue = value.toLocaleString(locale, { maximumFractionDigits: 2 });
  const delta = previous !== undefined ? value - previous : undefined;
  const pct = previous !== undefined && previous !== 0 ? (delta! / previous) * 100 : undefined;
  const percentileLabel =
    stressLatest?.percentile != null ? ordinal(stressLatest.percentile) : undefined;
  const deviationLabel =
    stressLatest?.deviation_pct != null
      ? `${stressLatest.deviation_pct >= 0 ? "+" : ""}${stressLatest.deviation_pct.toFixed(1)}%`
      : undefined;
  const zScoreLabel = stressLatest ? `${stressLatest.z_score >= 0 ? "+" : ""}${stressLatest.z_score.toFixed(1)}σ` : undefined;
  const baselineLabel =
    stressLatest?.seasonal_mean != null
      ? `${stressLatest.seasonal_mean.toLocaleString(locale, { maximumFractionDigits: 1 })}${
          stressLatest.seasonal_label ? ` · ${stressLatest.seasonal_label}` : ""
        }`
      : undefined;

  return (
    <Card title={title} subtitle={subtitle}>
      <div className="space-y-4">
        <div className="flex flex-wrap items-end gap-4">
          <div>
            <p className="text-4xl font-semibold">{formattedValue}</p>
            <p className="text-sm text-foreground/50">{t("dashboard.latestIndex.label")}</p>
          </div>
          {delta !== undefined && pct !== undefined && Number.isFinite(pct) && (
            <div
              className={clsx(
                "rounded-xl px-3 py-2 text-sm font-medium",
                delta >= 0 ? "bg-success/10 text-success" : "bg-danger/10 text-danger",
              )}
            >
              {delta >= 0 ? "+" : ""}
              {delta.toFixed(2)} ({pct >= 0 ? "+" : ""}
                  {pct.toFixed(2)}%)
            </div>
          )}
          {weatherFlag && weatherFlag > 0 && (
            <span className="inline-flex items-center gap-1 rounded-xl bg-warning/10 px-3 py-2 text-sm font-medium text-warning">
              ⚠ {t("dashboard.weather.flag", { defaultValue: "Weather flag active" })}
            </span>
          )}
        </div>
        <div className="space-y-3">
          {stressLatest ? (
            <>
              <div className="space-y-2 rounded-xl border border-foreground/10 bg-foreground/5 px-4 py-3">
                <div className="flex items-start gap-3">
                  <span className="text-2xl" aria-hidden>
                    {stressLatest.classification.emoji ?? "•"}
                  </span>
                  <div className="space-y-1">
                    <p className="text-xs font-semibold uppercase tracking-wide">
                      {stressLatest.classification.status}
                    </p>
                    <p className="text-sm font-semibold text-foreground">
                      {narrative?.headline ?? stressLatest.classification.headline ?? ""}
                    </p>
                    <p className="text-sm text-foreground/70">
                      {narrative?.summary ??
                        t("dashboard.latestIndex.seasonalSummary", {
                          defaultValue: "{{zScore}} · {{percentile}} percentile",
                          zScore: zScoreLabel ?? "—",
                          percentile: percentileLabel ?? "—",
                        })}
                    </p>
                  </div>
                </div>
              </div>
              <div className="grid gap-3 text-xs text-foreground/70 sm:grid-cols-2 lg:grid-cols-4">
                <div className="text-center">
                  <p className="uppercase tracking-wide text-foreground/50">
                    {t("dashboard.latestIndex.zScore", { defaultValue: "Z-score" })}
                  </p>
                  <p className="text-sm font-semibold text-foreground">{zScoreLabel ?? "—"}</p>
                </div>
                <div className="text-center">
                  <p className="uppercase tracking-wide text-foreground/50">
                    {t("dashboard.latestIndex.percentile", { defaultValue: "Percentile" })}
                  </p>
                  <p className="text-sm font-semibold text-foreground">
                    {percentileLabel
                      ? `${percentileLabel}${stressLatest.lookback_samples ? ` · ${stressLatest.lookback_samples}d` : ""}`
                      : "—"}
                  </p>
                </div>
                <div className="text-center">
                  <p className="uppercase tracking-wide text-foreground/50">
                    {t("dashboard.latestIndex.baseline", { defaultValue: "Seasonal baseline" })}
                  </p>
                  <p className="text-sm font-semibold text-foreground">{baselineLabel ?? "—"}</p>
                </div>
                <div className="text-center">
                  <p className="uppercase tracking-wide text-foreground/50">
                    {t("dashboard.latestIndex.deviation", { defaultValue: "Deviation" })}
                  </p>
                  <p className="text-sm font-semibold text-foreground">{deviationLabel ?? "—"}</p>
                </div>
              </div>
              {historyPreview.length > 0 && (
                <div className="space-y-2">
                  <p className="text-xs uppercase tracking-wide text-foreground/50">
                    {t("dashboard.latestIndex.history", { defaultValue: "Recent seasonal context" })}
                  </p>
                  <div className="grid gap-2 sm:grid-cols-3 lg:grid-cols-5">
                    {historyPreview.map((row) => {
                      const dateLabel = new Date(row.date).toLocaleDateString(locale, {
                        month: "short",
                        day: "numeric",
                      });
                      const valueLabel = Number.isFinite(row.value)
                        ? row.value.toLocaleString(locale, { maximumFractionDigits: 1 })
                        : "—";
                      const rowZ =
                        row.z_score != null
                          ? `${row.z_score >= 0 ? "+" : ""}${row.z_score.toFixed(1)}σ`
                          : "—";
                      return (
                        <div
                          key={row.date}
                          className="rounded-lg border border-foreground/10 bg-background/80 px-3 py-2 text-xs"
                        >
                          <p className="text-sm font-semibold text-foreground">{valueLabel}</p>
                          <p className="text-foreground/60">{dateLabel}</p>
                          <p className="text-foreground/50">{rowZ}</p>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </>
          ) : (
            <div className="rounded-xl border border-foreground/10 bg-foreground/5 px-4 py-3 text-sm text-foreground/70">
              {t("dashboard.latestIndex.contextUnavailable", {
                defaultValue: "Seasonal context unavailable. Awaiting baseline calibration.",
              })}
            </div>
          )}
        </div>
      </div>
    </Card>
  );
};

type IndexPoint = GlobalIndexPoint | BasinIndexPoint;

const extractValue = (point: IndexPoint | undefined): number | undefined => {
  if (!point) {
    return undefined;
  }
  if ("spvx_global" in point && typeof point.spvx_global === "number") {
    return point.spvx_global;
  }
  if ("spvx_basin" in point && typeof point.spvx_basin === "number") {
    return point.spvx_basin;
  }
  return undefined;
};

const buildComponentMap = (data?: ComponentPoint[]) => {
  if (!data || data.length === 0) {
    return { date: undefined, map: new Map<string, ComponentPoint>() };
  }
  let latestDate = data[0].d;
  for (const row of data) {
    if (row.d > latestDate) {
      latestDate = row.d;
    }
  }
  const map = new Map<string, ComponentPoint>();
  for (const row of data) {
    if (row.d === latestDate) {
      map.set(row.comp, row);
    }
  }
  return { date: latestDate, map };
};

export const DashboardPage = () => {
  const [windowSize, setWindowSize] = useState<90 | 180 | 365>(90);
  const [basin, setBasin] = useState<Basin>("GLOBAL");
  const [downloading, setDownloading] = useState(false);
  const rangeParam = `${windowSize}d`;
  const componentsRange = "30d";

  const globalIndexQuery = useGlobalIndex(rangeParam);
  const basinIndexQuery = useBasinIndex(basin, rangeParam);
  const componentsQuery = useBasinComponents(basin, componentsRange);
  const opsHealthQuery = useOpsHealth();
  const overviewV16 = Boolean(appConfig.features?.overviewV16);
  const latestIndexQuery = useLatestIndex("global", overviewV16);
  const signalsSnapshotQuery = useSignalsSnapshot();
  const { t, i18n } = useTranslation();
  const locale = i18n.language;
  const refreshSeconds = appConfig.refreshSeconds;

  const isGlobal = basin === "GLOBAL";
  const indexData = isGlobal ? globalIndexQuery.data : basinIndexQuery.data;
  const indexSeries = (indexData?.series ?? []) as IndexPoint[];
  const chartSeries = useMemo(
    () =>
      indexSeries
        .map((point) => {
          const value = extractValue(point);
          return value !== undefined ? { d: point.d, value } : null;
        })
        .filter(Boolean) as { d: string; value: number }[],
    [indexSeries],
  );

  const latestPoint: IndexPoint | undefined =
    (indexData?.latest as IndexPoint | undefined) ?? indexSeries.at(-1);
  const previousPoint = indexSeries.length > 1 ? indexSeries[indexSeries.length - 2] : undefined;
  const latestValue = extractValue(latestPoint);
  const previousValue = extractValue(previousPoint);
  const latestDate = latestPoint?.d;
  const latestSubtitle = latestDate ? new Date(latestDate).toLocaleDateString(locale) : undefined;
  const basinLabel = t(`dashboard.basins.${basin.toLowerCase()}`, {
    defaultValue: BASIN_LABELS[basin] ?? basin,
  });
  const latestWeatherFlag = typeof latestPoint?.weather_flag === "number" ? latestPoint.weather_flag ?? 0 : 0;
  const relativeStress = indexData?.relative_stress;
  const heroSnapshot = latestIndexQuery.data;
  const heroLoading = latestIndexQuery.isLoading || (latestIndexQuery.isFetching && !latestIndexQuery.data);
  const heroError = latestIndexQuery.isError;
  const signalsAsOf = signalsSnapshotQuery.data?.asof ?? null;
  const heroTimestamp = heroSnapshot?.ts ?? null;
  const heroAsOfRaw = useMemo(() => {
    const candidates = [heroTimestamp, signalsAsOf].filter(Boolean) as string[];
    if (candidates.length === 0) {
      return null;
    }
    const sorted = candidates
      .map((value) => ({ value, date: new Date(value) }))
      .filter((item) => !Number.isNaN(item.date.getTime()))
      .sort((a, b) => b.date.getTime() - a.date.getTime());
    return sorted[0]?.value ?? candidates[0];
  }, [heroTimestamp, signalsAsOf]);
  const heroAsOfDate = useMemo(() => {
    if (!heroAsOfRaw) {
      return null;
    }
    const parsed = new Date(heroAsOfRaw);
    return Number.isNaN(parsed.getTime()) ? null : parsed;
  }, [heroAsOfRaw]);
  const heroAsOfUtc = useMemo(() => {
    if (!heroAsOfDate) {
      return null;
    }
    return new Intl.DateTimeFormat(locale, {
      year: "numeric",
      month: "short",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      timeZone: "UTC",
      timeZoneName: "short",
      hourCycle: "h23",
    }).format(heroAsOfDate);
  }, [heroAsOfDate, locale]);
  const heroIsStale = useMemo(() => {
    if (!heroAsOfDate) {
      return false;
    }
    const diffMs = Date.now() - heroAsOfDate.getTime();
    const twoDays = 48 * 60 * 60 * 1000;
    return diffMs > twoDays;
  }, [heroAsOfDate]);

  const componentsData = componentsQuery.data?.series ?? [];
  const { map: latestComponentMap } = useMemo(() => buildComponentMap(componentsData), [componentsData]);

  const componentTrend = useMemo(() => {
    const trend = new Map<string, number>();
    if (componentsData.length === 0) {
      return trend;
    }
    const grouped = new Map<string, ComponentPoint[]>();
    for (const row of componentsData) {
      if (!grouped.has(row.comp)) {
        grouped.set(row.comp, []);
      }
      grouped.get(row.comp)!.push(row);
    }
    grouped.forEach((rows, comp) => {
      const sorted = rows.slice().sort((a, b) => a.d.localeCompare(b.d));
      const latest = sorted.at(-1);
      if (!latest || latest.z_value == null) {
        trend.set(comp, 0);
        return;
      }
      const recent = sorted
        .filter((item) => item.z_value != null)
        .slice(-7);
      if (recent.length === 0) {
        trend.set(comp, 0);
        return;
      }
      const avg =
        recent.reduce((sum, item) => sum + (item.z_value ?? 0), 0) /
        recent.length;
      trend.set(comp, (latest.z_value ?? 0) - avg);
    });
    return trend;
  }, [componentsData]);

  const componentList = BASIN_COMPONENTS[basin] ?? [];

  const opsStatusLine = useMemo(() => {
    const ops = opsHealthQuery.data;
    if (!ops) {
      return null;
    }
    const componentsEntries = Object.entries(ops.components_present ?? {});
    const coverageEntries = Object.entries(ops.coverage_30d ?? {});
    const weatherEntries = Object.entries(ops.weather_flags ?? {});
    const componentsText = componentsEntries
      .map(([key, value]) => `${key} ${value.present}/${value.expected}`)
      .join(" | ");
    const coverageText = coverageEntries
      .map(([key, value]) => `${key} ${value != null ? `${(value * 100).toFixed(0)}%` : "—"}`)
      .join(" | ");
    const weatherText = weatherEntries
      .filter(([, value]) => value != null && Number(value) > 0)
      .map(([key]) => `${key}`)
      .join(" | ");
    const latest = ops.latest_snapshot
      ? new Date(ops.latest_snapshot).toLocaleDateString(locale)
      : null;
    return {
      ready: ops.ready,
      latest,
      componentsText,
      coverageText,
      revision: ops.revision_flag,
      weatherText,
    };
  }, [locale, opsHealthQuery.data]);

  const handleDownload = useCallback(async () => {
    try {
      setDownloading(true);
      const blob = await downloadBasinCsv(basin, rangeParam);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${basin.toLowerCase()}_${rangeParam}.csv`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } finally {
      setDownloading(false);
    }
  }, [basin, rangeParam]);

  return (
    <div className="space-y-8 max-w-[1600px] mx-auto">

      {overviewV16 && (
        <div className="flex flex-wrap items-center gap-3 text-sm text-foreground/60">
          {heroLoading ? (
            <Skeleton className="h-6 w-48 rounded-full" />
          ) : heroAsOfUtc ? (
            <span
              className={clsx(
                "inline-flex items-center gap-2 rounded-full px-3 py-1 font-medium",
                heroIsStale ? "bg-warning/10 text-warning" : "bg-foreground/10 text-foreground/80",
              )}
            >
              {heroIsStale
                ? t("dashboard.refresh.stale", {
                    defaultValue: "Stale since {{datetime}}",
                    datetime: heroAsOfUtc,
                  })
                : t("dashboard.refresh.asOf", {
                    defaultValue: "As of {{datetime}}",
                    datetime: heroAsOfUtc,
                  })}
            </span>
          ) : null}
          <span className="inline-flex items-center gap-2 rounded-full bg-foreground/5 px-3 py-1 text-xs uppercase tracking-wide text-foreground/60">
            {t("dashboard.refresh.auto", { defaultValue: "Auto-refresh ✓" })}
            <span className="font-mono text-foreground/50">
              {refreshSeconds >= 60
                ? t("dashboard.refresh.intervalMinutes", {
                    defaultValue: "{{minutes}} min",
                    minutes: Math.round(refreshSeconds / 60),
                  })
                : t("dashboard.refresh.intervalSeconds", {
                    defaultValue: "{{seconds}} s",
                    seconds: refreshSeconds,
                  })}
            </span>
          </span>
        </div>
      )}

      {opsStatusLine && (
        <div
          className={clsx(
            "flex flex-wrap items-center gap-3 rounded-xl border border-foreground/10 px-4 py-2 text-sm",
            opsStatusLine.ready ? "bg-success/5 text-success" : "bg-warning/10 text-warning",
          )}
        >
          <span className="font-semibold">{opsStatusLine.ready ? t("status.ready") : t("status.not_ready")}</span>
          {opsStatusLine.latest && <span>• {t("dashboard.ops.latest", { defaultValue: "Snapshot", date: opsStatusLine.latest })}</span>}
          {opsStatusLine.componentsText && <span>• {t("dashboard.ops.components", { defaultValue: "components" })}: {opsStatusLine.componentsText}</span>}
        {opsStatusLine.coverageText && <span>• {t("dashboard.ops.coverage", { defaultValue: "coverage 30d" })}: {opsStatusLine.coverageText}</span>}
        {opsStatusLine.revision && <span>• {t("dashboard.ops.revisionFlag", { defaultValue: "revision>0.10" })}</span>}
        {opsStatusLine.weatherText && (
          <span>• {t("dashboard.weather.flag", { defaultValue: "Weather flag" })}: {opsStatusLine.weatherText}</span>
        )}
      </div>
    )}

      <div className="flex flex-wrap gap-2">
        {BASINS.map((candidate) => {
          const label = t(`dashboard.basins.${candidate.toLowerCase()}`, {
            defaultValue: BASIN_LABELS[candidate] ?? candidate,
          });
          return (
            <button
              key={candidate}
              type="button"
              onClick={() => setBasin(candidate)}
              className={clsx(
                "rounded-2xl px-3 py-1 text-sm shadow",
                basin === candidate
                  ? "bg-accent/20 text-accent"
                  : "bg-foreground/5 text-foreground/70 hover:bg-accent/10 hover:text-accent",
              )}
            >
              {label}
              {BETA_BASINS.has(candidate) && <span className="ml-2 rounded bg-foreground/10 px-2 py-0.5 text-xs uppercase">beta</span>}
            </button>
          );
        })}
      </div>

      {overviewV16 ? (
        <HeroKpi
          data={heroSnapshot}
          isLoading={heroLoading}
          isError={heroError}
          onRetry={() => latestIndexQuery.refetch()}
          asOf={heroAsOfRaw}
          isStale={heroIsStale}
        />
      ) : (
        <LatestIndexCard
          title={`${t("dashboard.latestIndex.title")} · ${basinLabel}`}
          subtitle={latestSubtitle}
          value={latestValue}
          previous={previousValue}
          loading={isGlobal ? globalIndexQuery.isLoading : basinIndexQuery.isLoading}
          weatherFlag={latestWeatherFlag}
          relativeStress={relativeStress}
          latestPoint={latestPoint}
        />
      )}

      <Card
        title={t("dashboard.indexPerformance.title")}
        subtitle={basinLabel}
        action={
          <div className="flex flex-wrap items-center gap-2 text-sm">
            {[90, 180, 365].map((value) => (
              <button
                key={value}
                type="button"
                className={clsx(
                  "rounded-full border px-3 py-1 transition-colors",
                  windowSize === value
                    ? "border-accent bg-accent/20 text-accent"
                    : "border-foreground/20 text-foreground/60 hover:border-accent/40 hover:text-accent",
                )}
                onClick={() => setWindowSize(value as typeof windowSize)}
              >
                {t("dashboard.indexPerformance.window", { days: value })}
              </button>
            ))}
            <button
              type="button"
              onClick={handleDownload}
              disabled={downloading}
              className="inline-flex items-center rounded-full border border-foreground/20 px-3 py-1 text-sm text-foreground/70 hover:border-accent/40 hover:text-accent disabled:opacity-60"
            >
              {downloading ? t("actions.downloading", { defaultValue: "Downloading…" }) : t("actions.downloadCsv", { defaultValue: "CSV" })}
            </button>
          </div>
        }
      >
        {(isGlobal ? globalIndexQuery.isLoading : basinIndexQuery.isLoading) ? (
          <Skeleton className="h-72 w-full" />
        ) : chartSeries.length === 0 ? (
          <div className="flex h-72 items-center justify-center">
            <div className="text-center space-y-2">
              <p className="text-lg font-medium text-foreground/70">⏳ {t("dashboard.indexPerformance.collecting", { defaultValue: "Historical data is being collected" })}</p>
              <p className="text-sm text-foreground/50">{t("dashboard.indexPerformance.collectingHint", { defaultValue: "Chart will display once sufficient data is available" })}</p>
            </div>
          </div>
        ) : (
          <TimeSeriesChart data={chartSeries} label={basinLabel} relativeStress={relativeStress} />
        )}
      </Card>

      {!isGlobal && (
        <Card title={t("dashboard.components.title", { defaultValue: "Drivers" })} subtitle={componentsRange}>
          {componentsQuery.isLoading ? (
            <Skeleton className="h-16 w-full" />
          ) : (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {componentList.map((comp) => {
                const entry = latestComponentMap.get(comp);
                const zValue = entry?.z_value ?? null;
                const rawValue = entry?.raw_value ?? null;
                const trend = componentTrend.get(comp) ?? 0;
                const weatherFlag = entry?.weather_flag ?? 0;
                const observations = entry?.n_obs ?? 0;
                const seasonalMean = entry?.seasonal_mean ?? null;
                const deviationPct = entry?.deviation_pct ?? null;
                const classification = entry?.classification ?? null;

                return (
                  <ComponentCard
                    key={comp}
                    name={comp}
                    value={rawValue}
                    zScore={zValue}
                    trend={trend}
                    weatherFlag={weatherFlag}
                    observations={observations}
                    seasonalMean={seasonalMean ?? undefined}
                    deviationPct={deviationPct ?? undefined}
                    classification={classification ?? undefined}
                  />
                );
              })}
              {componentList.length === 0 && (
                <p className="text-sm text-foreground/60">
                  {t("dashboard.components.noConfig", {
                    defaultValue: "No component configuration available.",
                  })}
                </p>
              )}
            </div>
          )}
        </Card>
      )}

      <ChokepointTable />
      <OpenSeaPanel />
      <MarketContext />
    </div>
  );
};
