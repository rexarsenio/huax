import { useCallback, useMemo, useState } from "react";
import { Card } from "../components/Card";
import { Skeleton } from "../components/Skeleton";
import { TimeSeriesChart } from "../components/TimeSeriesChart";
import { SignalSummary } from "../components/SignalSummary";
import { MetaHero } from "../components/MetaHero";
import {
  useGlobalIndex,
  useBasinIndex,
  useBasinComponents,
  useSpreadSignals,
  useThroughputNowcast,
  useOpsHealth,
} from "../hooks/useApi";
import type { Basin, ComponentPoint } from "../api/types";
import { clsx } from "clsx";
import { useTranslation } from "react-i18next";
import { downloadBasinCsv } from "../api/client";

const BASINS: Basin[] = ["GLOBAL", "EUR", "APAC", "NAM", "SAM"];

const BASIN_LABELS: Record<Basin, string> = {
  GLOBAL: "Global",
  EUR: "Europe",
  APAC: "APAC",
  NAM: "North America",
  SAM: "South America",
};

const BASIN_COMPONENTS: Partial<Record<Basin, string[]>> = {
  EUR: ["CQ_TR", "PORT_EU"],
  APAC: ["CQ_SG", "CQ_HRZ"],
  NAM: ["CQ_PAN", "PORT_US"],
  SAM: ["CQ_PAN_S", "PORT_BR"],
};

const BETA_BASINS = new Set<Basin>(["SAM"]);

type LatestIndexCardProps = {
  title: string;
  subtitle?: string;
  value?: number;
  previous?: number;
  loading: boolean;
  weatherFlag?: number;
};

const LatestIndexCard = ({ title, subtitle, value, previous, loading, weatherFlag }: LatestIndexCardProps) => {
  const { t, i18n } = useTranslation();
  const locale = i18n.language;

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

  return (
    <Card title={title} subtitle={subtitle}>
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
    </Card>
  );
};

const extractValue = (point: unknown): number | undefined => {
  if (!point || typeof point !== "object") {
    return undefined;
  }
  const candidate = point as Record<string, unknown>;
  if (typeof candidate["spvx_global"] === "number") {
    return candidate["spvx_global"] as number;
  }
  if (typeof candidate["spvx_basin"] === "number") {
    return candidate["spvx_basin"] as number;
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
  const spreadQuery = useSpreadSignals();
  const throughputQuery = useThroughputNowcast();
  const opsHealthQuery = useOpsHealth();
  const { t, i18n } = useTranslation();
  const locale = i18n.language;

  const isGlobal = basin === "GLOBAL";
  const indexData = isGlobal ? globalIndexQuery.data : basinIndexQuery.data;
  const indexSeries = indexData?.series ?? [];
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

  const latestPoint = indexData?.latest ?? indexSeries.at(-1);
  const previousPoint = indexSeries.length > 1 ? indexSeries[indexSeries.length - 2] : undefined;
  const latestValue = extractValue(latestPoint);
  const previousValue = extractValue(previousPoint);
  const latestDate = latestPoint && typeof latestPoint === "object" ? (latestPoint as Record<string, string>).d : undefined;
  const latestSubtitle = latestDate ? new Date(latestDate).toLocaleDateString(locale) : undefined;
  const basinLabel = t(`dashboard.basins.${basin.toLowerCase()}`, {
    defaultValue: BASIN_LABELS[basin] ?? basin,
  });
  const latestWeatherFlag =
    latestPoint && typeof latestPoint === "object" && typeof (latestPoint as Record<string, unknown>).weather_flag === "number"
      ? Number((latestPoint as Record<string, unknown>).weather_flag)
      : 0;

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

  const spreadSeries = Array.isArray(spreadQuery.data?.series) ? spreadQuery.data!.series : [];
  const throughputSeries = Array.isArray(throughputQuery.data?.series) ? throughputQuery.data!.series : [];

  return (
    <div className="space-y-6">
      <MetaHero />

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

      <LatestIndexCard
        title={`${t("dashboard.latestIndex.title")} · ${basinLabel}`}
        subtitle={latestSubtitle}
        value={latestValue}
        previous={previousValue}
        loading={isGlobal ? globalIndexQuery.isLoading : basinIndexQuery.isLoading}
        weatherFlag={latestWeatherFlag}
      />

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
        {((isGlobal ? globalIndexQuery.isLoading : basinIndexQuery.isLoading) || chartSeries.length === 0) ? (
          <Skeleton className="h-72 w-full" />
        ) : (
          <TimeSeriesChart data={chartSeries} label={basinLabel} />
        )}
      </Card>

      {!isGlobal && (
        <Card title={t("dashboard.components.title", { defaultValue: "Drivers" })} subtitle={componentsRange}>
          {componentsQuery.isLoading ? (
            <Skeleton className="h-16 w-full" />
          ) : (
            <div className="flex flex-wrap gap-2">
              {componentList.map((comp) => {
            const entry = latestComponentMap.get(comp);
            const zValue = entry?.z_value ?? null;
            const trend = componentTrend.get(comp) ?? 0;
            const weatherFlag = entry?.weather_flag ?? 0;
            const direction = zValue == null ? "" : trend > 0.1 ? "▲" : trend < -0.1 ? "▼" : "•";
            const chipClass = zValue == null
              ? "bg-foreground/5 text-foreground/60"
              : zValue >= 0
              ? "bg-success/10 text-success"
              : "bg-danger/10 text-danger";
            const baseClasses = clsx("rounded-2xl px-3 py-1 text-sm font-medium", chipClass);
            const className = weatherFlag
              ? clsx(baseClasses, "ring-2 ring-warning/70")
              : baseClasses;
            const tooltip = entry
              ? `${comp}: ${zValue?.toFixed(2) ?? "n/a"} (${t("dashboard.components.observations", { defaultValue: "n_obs" })}: ${entry.n_obs ?? 0})`
              : `${comp}: n/a`;
            return (
              <span key={comp} className={className} title={tooltip}>
                {comp}: {zValue != null ? zValue.toFixed(2) : "n/a"} {direction} {weatherFlag ? "⚠" : ""}
              </span>
            );
          })}
              {componentList.length === 0 && (
                <p className="text-sm text-foreground/60">{t("dashboard.components.noConfig", { defaultValue: "No component configuration available." })}</p>
              )}
            </div>
          )}
        </Card>
      )}

      <div className="grid gap-6 md:grid-cols-2">
        <SignalSummary />
        <Card title={t("dashboard.modelActivity.title")} subtitle={t("dashboard.modelActivity.subtitle")}>
          {spreadQuery.isLoading && throughputQuery.isLoading ? (
            <Skeleton className="h-40 w-full" />
          ) : (
            <div className="space-y-4 text-sm">
              <div>
                <p className="text-xs uppercase tracking-wide text-foreground/60 mb-1">{t("dashboard.modelActivity.spread")}</p>
                <div className="space-y-1 text-foreground/70">
                  {spreadSeries.length > 0
                    ? spreadSeries.slice(-5).map((row, idx) => {
                        const dateLabel = String(row["date"] ?? t("dashboard.modelActivity.placeholder"));
                        const probValue = row["prob_up"];
                        const prob =
                          typeof probValue === "number"
                            ? probValue.toFixed(2)
                            : t("dashboard.modelActivity.placeholder");
                        return (
                          <span key={idx} className="block">
                            {dateLabel}: {prob}
                          </span>
                        );
                      })
                    : t("dashboard.modelActivity.placeholder")}
                </div>
              </div>
              <div>
                <p className="text-xs uppercase tracking-wide text-foreground/60 mb-1">{t("dashboard.modelActivity.throughput")}</p>
                <div className="space-y-1 text-foreground/70">
                  {throughputSeries.length > 0
                    ? throughputSeries.slice(-5).map((row, idx) => {
                        const dateLabel = String(row["date"] ?? t("dashboard.modelActivity.placeholder"));
                        const valueRaw = row["throughput_pred_72h"];
                        const value =
                          typeof valueRaw === "number"
                            ? valueRaw.toFixed(2)
                            : t("dashboard.modelActivity.placeholder");
                        return (
                          <span key={idx} className="block">
                            {dateLabel}: {value}
                          </span>
                        );
                      })
                    : t("dashboard.modelActivity.placeholder")}
                </div>
              </div>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
};
