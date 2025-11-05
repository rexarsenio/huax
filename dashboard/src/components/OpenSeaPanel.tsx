import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Card } from "./Card";
import { Skeleton } from "./Skeleton";
import { TimeSeriesChart } from "./TimeSeriesChart";
import { SISBadge } from "./SISBadge";
import { useGateFlux, useSIS, useSeaStateSummary, useOpenSeaSummary } from "../hooks/useApi";
import { appConfig } from "../config";
import { WarningIcon } from "./icons";

const formatPercent = (value: number, locale: string) =>
  (value * 100).toLocaleString(locale, { maximumFractionDigits: 1 }) + "%";

const DEFAULT_GATE_IDS = [
  "GATE_GIBRALTAR_E_v1",
  "GATE_GIBRALTAR_W_v1",
  "GATE_GIBRALTAR_MED_50NM",
  "GATE_GIBRALTAR_MED_100NM",
  "GATE_SICILY_v1",
  "GATE_OTRANTO_v1",
  "GATE_BOSPORUS_S_v1",
  "GATE_DARDANELLES_W_v1",
  "LANE_CANARY_E_v1",
  "LANE_CANARY_W_v1",
  "GATE_SUEZ_N_v1",
  "GATE_SUEZ_N_50NM",
  "GATE_SUEZ_N_100NM",
  "CHOKEPOINT_MALACCA",
  "WEST_AFRICA_BONNY",
  "WEST_AFRICA_ESCRAVOS",
  "WEST_AFRICA_GULF",
];

const GATE_NAME_OVERRIDES: Record<string, string> = {
  GATE_GIBRALTAR_E_v1: "Gibraltar Eastbound",
  GATE_GIBRALTAR_W_v1: "Gibraltar Westbound",
  GATE_GIBRALTAR_MED_50NM: "Gibraltar Approaches (50nm)",
  GATE_GIBRALTAR_MED_100NM: "Gibraltar Approaches (100nm)",
  GATE_SICILY_v1: "Strait of Sicily",
  GATE_OTRANTO_v1: "Strait of Otranto",
  GATE_BOSPORUS_S_v1: "Bosporus Southbound",
  GATE_DARDANELLES_W_v1: "Dardanelles Westbound",
  LANE_CANARY_E_v1: "Canary Lane Eastbound",
  LANE_CANARY_W_v1: "Canary Lane Westbound",
  GATE_SUEZ_N_v1: "Suez Canal Northbound",
  GATE_SUEZ_N_50NM: "Suez Approaches (50nm)",
  GATE_SUEZ_N_100NM: "Suez Approaches (100nm)",
  CHOKEPOINT_MALACCA: "Malacca / Singapore Strait",
  WEST_AFRICA_BONNY: "West Africa · Bonny",
  WEST_AFRICA_ESCRAVOS: "West Africa · Escravos",
  WEST_AFRICA_GULF: "West Africa · Gulf Corridor",
};

const CORRIDOR_PATTERNS: Array<[RegExp, string]> = [
  [/^GATE_GIBRALTAR/, "CHOKEPOINT_GIBRALTAR->UNK"],
  [/^GATE_SICILY/, "CHOKEPOINT_SICILY->UNK"],
  [/^GATE_OTRANTO/, "CHOKEPOINT_OTRANTO->UNK"],
  [/^GATE_BOSPORUS/, "CHOKEPOINT_BOSPORUS->UNK"],
  [/^GATE_DARDANELLES/, "CHOKEPOINT_DARDANELLES->UNK"],
  [/^LANE_CANARY_E/, "LANE_CANARY_E_v1->UNK"],
  [/^LANE_CANARY_W/, "LANE_CANARY_W_v1->UNK"],
  [/^GATE_SUEZ_N/, "CHOKEPOINT_SUEZ_NORTH->UNK"],
  [/^GATE_SUEZ_S/, "CHOKEPOINT_SUEZ_SOUTH->UNK"],
  [/^GATE_HORMUZ/, "CHOKEPOINT_HORMUZ->UNK"],
  [/^GATE_BABELMANDEB/, "CHOKEPOINT_BAB_EL_MANDEB->UNK"],
  [/^GATE_PANAMA/, "CHOKEPOINT_PANAMA->UNK"],
  [/^GATE_HOUSTON/, "CHOKEPOINT_US_GULF->UNK"],
  [/^WEST_AFRICA_BONNY$/, "WEST_AFRICA_BONNY->UNK"],
  [/^WEST_AFRICA_ESCRAVOS$/, "WEST_AFRICA_ESCRAVOS->UNK"],
  [/^WEST_AFRICA_GULF$/, "WEST_AFRICA_GULF->UNK"],
];

const inferCorridorId = (gateId: string | undefined): string | undefined => {
  if (!gateId) {
    return undefined;
  }
  for (const [pattern, corridor] of CORRIDOR_PATTERNS) {
    if (pattern.test(gateId)) {
      return corridor;
    }
  }
  if (gateId.startsWith("CHOKEPOINT_")) {
    return `${gateId}->UNK`;
  }
  return undefined;
};

const corridorToRegionId = (corridor: string | undefined) => {
  if (!corridor) return undefined;
  return corridor.split("->")[0];
};

const formatNumber = (value: number | null | undefined, digits = 2) => {
  if (value == null || Number.isNaN(value)) {
    return "N/A";
  }
  return value.toFixed(digits);
};

export const OpenSeaPanel = () => {
  const { t, i18n } = useTranslation();
  const locale = i18n.language;

  // State for selected gate
  const [selectedGateId, setSelectedGateId] = useState(appConfig.openSea.gateId);

  const gateWindow = appConfig.openSea.gateWindow === "d7" ? "d7" : "h24";
  const sisWindow = appConfig.openSea.sisWindow || "d7";

  const openSeaSummaryQuery = useOpenSeaSummary(gateWindow);

  const gateOptions = useMemo(() => {
    const options: GateOption[] = [];
    const seen = new Set<string>();

    for (const corridor of openSeaSummaryQuery.data?.corridors ?? []) {
      const gateId = corridor.gate_id;
      if (!gateId || seen.has(gateId)) {
        continue;
      }
      const corridorId = inferCorridorId(gateId);
      const name = GATE_NAME_OVERRIDES[gateId] ?? corridor.label ?? gateId;
      options.push({
        id: gateId,
        name,
        corridorId,
        flux: corridor.flux ?? 0,
      });
      seen.add(gateId);
    }

    for (const id of DEFAULT_GATE_IDS) {
      if (seen.has(id)) continue;
      options.push({
        id,
        name: GATE_NAME_OVERRIDES[id] ?? id,
        corridorId: inferCorridorId(id),
        flux: 0,
      });
      seen.add(id);
    }

    return options.sort((a, b) => (b.flux ?? 0) - (a.flux ?? 0));
  }, [openSeaSummaryQuery.data]);

  useEffect(() => {
    if (gateOptions.length === 0) {
      return;
    }
    if (!gateOptions.some((option) => option.id === selectedGateId)) {
      setSelectedGateId(gateOptions[0].id);
    }
  }, [gateOptions, selectedGateId]);

  const selectedGateMeta = gateOptions.find((option) => option.id === selectedGateId);
  const selectedCorridorId =
    selectedGateMeta?.corridorId ?? inferCorridorId(selectedGateId) ?? appConfig.openSea.corridorId;
  const summaryRegionId = corridorToRegionId(selectedCorridorId);
  const summaryScope = summaryRegionId?.startsWith("WEST_AFRICA") ? "west_africa" : "mediterranean";
  const isWestAfricaSynthetic = summaryScope === "west_africa";

  const seaStateSummaryQuery = useSeaStateSummary("d7", summaryScope);
  const summaryRegion = seaStateSummaryQuery.data?.regions.find((region) => region.id === summaryRegionId);

  const gateFluxQuery = useGateFlux(selectedGateId, gateWindow, undefined, { enabled: !isWestAfricaSynthetic });
  const sisQuery = useSIS(selectedCorridorId, sisWindow);

  const gateFluxSeries = useMemo(
    () =>
      (gateFluxQuery.data?.series ?? []).map((row) => ({
        d: row.ts,
        value: row.crossings ?? 0,
      })),
    [gateFluxQuery.data?.series],
  );
  const gateFluxUnavailable = isWestAfricaSynthetic;
  const gateLatestInfo = useMemo(() => {
    const series = gateFluxQuery.data?.series;
    if (!series || series.length === 0) {
      return { label: null, stale: false };
    }
    const latest = series[series.length - 1];
    const ts = latest?.ts;
    if (!ts) {
      return { label: null, stale: false };
    }
    const parsed = new Date(ts);
    if (Number.isNaN(parsed.getTime())) {
      return { label: ts, stale: false };
    }
    const label = parsed.toLocaleString(locale, {
      year: "numeric",
      month: "short",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      timeZone: "UTC",
      timeZoneName: "short",
    });
    const threshold = gateWindow.startsWith("h") ? 6 * 60 * 60 * 1000 : 24 * 60 * 60 * 1000;
    return { label, stale: Date.now() - parsed.getTime() > threshold };
  }, [gateFluxQuery.data?.series, gateWindow, locale]);

  const gateWindowLabel = gateWindow.startsWith("h")
    ? t("dashboard.openSea.windowHours", { defaultValue: "Last {{hours}} hours", hours: Number(gateWindow.slice(1)) })
    : t("dashboard.openSea.windowDays", { defaultValue: "Last {{days}} days", days: Number(gateWindow.slice(1)) });

  const sisLatest = sisQuery.data?.latest;
  const sisSeries = sisQuery.data?.series ?? [];

  const sisBadgeProps = useMemo(() => {
    const wave = Number.isFinite(sisLatest?.we_p90_m) ? sisLatest!.we_p90_m : summaryRegion?.we_p90 ?? undefined;
    const current = Number.isFinite(sisLatest?.hc_p90_kn)
      ? sisLatest!.hc_p90_kn
      : summaryRegion?.head_current_kn_p90 ?? undefined;
    const wind = Number.isFinite(sisLatest?.hw_p90_ms)
      ? sisLatest!.hw_p90_ms
      : summaryRegion?.head_wind_ms_p90 ?? undefined;

    const sisP90 = Number.isFinite(sisLatest?.sis_p90) ? sisLatest!.sis_p90 : undefined;

    if (
      sisP90 === undefined &&
      (wave === undefined || Number.isNaN(wave)) &&
      (current === undefined || Number.isNaN(current)) &&
      (wind === undefined || Number.isNaN(wind))
    ) {
      return null;
    }

    return {
      sisP90,
      waveHeight: wave,
      currentSpeed: current,
      windSpeed: wind,
      corridor: selectedGateMeta?.name ?? summaryRegionId?.replace(/_/g, " ") ?? undefined,
    };
  }, [sisLatest, summaryRegion, summaryRegionId, selectedGateMeta?.name]);
  const sisWindowLabel = sisWindow.startsWith("d")
    ? t("dashboard.openSea.windowDays", { defaultValue: "Last {{days}} days", days: Number(sisWindow.slice(1)) })
    : t("dashboard.openSea.windowHours", { defaultValue: "Last {{hours}} hours", hours: Number(sisWindow.slice(1)) });
  const sisSummary = sisLatest
    ? [
        {
          label: t("dashboard.openSea.sisMean", { defaultValue: "SIS mean" }),
          value: Number.isFinite(sisLatest.sis_mean) ? sisLatest.sis_mean.toFixed(2) : "N/A",
        },
        {
          label: t("dashboard.openSea.highImpactShare", { defaultValue: "≥0.70 share" }),
          value: Number.isFinite(sisLatest.pct_sis_gt_0_7) ? formatPercent(sisLatest.pct_sis_gt_0_7, locale) : "N/A",
        },
        {
          label: t("dashboard.openSea.headCurrent", { defaultValue: "Head current p90 (kn)" }),
          value: Number.isFinite(sisLatest.hc_p90_kn)
            ? sisLatest.hc_p90_kn.toFixed(2)
            : summaryRegion
            ? formatNumber(summaryRegion.head_current_kn_p90, 2)
            : "N/A",
        },
        {
          label: t("dashboard.openSea.headWind", { defaultValue: "Head wind p90 (m/s)" }),
          value: Number.isFinite(sisLatest.hw_p90_ms)
            ? sisLatest.hw_p90_ms.toFixed(2)
            : summaryRegion
            ? formatNumber(summaryRegion.head_wind_ms_p90, 2)
            : "N/A",
        },
        {
          label: t("dashboard.openSea.waveEncounter", { defaultValue: "Wave encounter p90 (m)" }),
          value: Number.isFinite(sisLatest.we_p90_m)
            ? sisLatest.we_p90_m.toFixed(2)
            : summaryRegion
            ? formatNumber(summaryRegion.we_p90, 2)
            : "N/A",
        },
      ]
    : summaryRegion
    ? [
        {
          label: t("dashboard.openSea.headCurrent", { defaultValue: "Head current p90 (kn)" }),
          value: formatNumber(summaryRegion.head_current_kn_p90, 2),
        },
        {
          label: t("dashboard.openSea.headWind", { defaultValue: "Head wind p90 (m/s)" }),
          value: formatNumber(summaryRegion.head_wind_ms_p90, 2),
        },
        {
          label: t("dashboard.openSea.waveEncounter", { defaultValue: "Wave encounter p90 (m)" }),
          value: formatNumber(summaryRegion.we_p90, 2),
        },
      ]
    : [];

  const sampleCount = sisLatest?.n_samples ?? summaryRegion?.samples ?? 0;

  const sisLatestLabel = useMemo(() => {
    if (!sisLatest?.ds) {
      return null;
    }
    const parsed = new Date(sisLatest.ds);
    if (Number.isNaN(parsed.getTime())) {
      return sisLatest.ds;
    }
    return parsed.toLocaleString(locale, {
      year: "numeric",
      month: "short",
      day: "2-digit",
    });
  }, [locale, sisLatest?.ds]);
  const sisIsStale = useMemo(() => {
    if (!sisLatest?.ds) {
      return false;
    }
    const parsed = new Date(sisLatest.ds);
    if (Number.isNaN(parsed.getTime())) {
      return false;
    }
    const threshold = sisWindow.startsWith("d") ? 3 * 24 * 60 * 60 * 1000 : 24 * 60 * 60 * 1000;
    return Date.now() - parsed.getTime() > threshold;
  }, [sisLatest?.ds, sisWindow]);

  const fallbackLatestLabel = useMemo(() => {
    if (sisLatestLabel) {
      return sisLatestLabel;
    }
    if (!summaryRegion?.last_sample) {
      return null;
    }
    const parsed = new Date(summaryRegion.last_sample);
    if (Number.isNaN(parsed.getTime())) {
      return summaryRegion.last_sample;
    }
    return parsed.toLocaleString(locale, {
      year: "numeric",
      month: "short",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      timeZone: "UTC",
      timeZoneName: "short",
    });
  }, [locale, sisLatestLabel, summaryRegion?.last_sample]);

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
      <Card
        title={
          <div className="flex items-center gap-3">
            <span>{t("dashboard.openSea.gateFluxTitle", { defaultValue: "Gate flux" })}</span>
            <select
              value={selectedGateId}
              onChange={(e) => setSelectedGateId(e.target.value)}
              className="rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground hover:border-foreground/40 focus:outline-none focus:ring-2 focus:ring-primary/50"
            >
              {gateOptions.map((gate) => (
                <option key={gate.id} value={gate.id}>
                  {gate.name}
                </option>
              ))}
            </select>
          </div>
        }
        subtitle={gateWindowLabel}
      >
        {gateLatestInfo.stale && gateLatestInfo.label && (
          <div className="mb-3 rounded-lg border border-warning/40 bg-warning/10 px-3 py-2 text-xs text-warning">
            {t("dashboard.openSea.staleGate", {
              defaultValue: "Flux data stale since {{datetime}}",
              datetime: gateLatestInfo.label,
            })}
          </div>
        )}
        {gateFluxQuery.isLoading ? (
          <Skeleton className="h-72 w-full" />
        ) : gateFluxUnavailable ? (
          <p className="text-sm text-foreground/60">
            {t("dashboard.openSea.gateFluxPending", {
              defaultValue: "Flux tracking for this West Africa corridor will appear after the next overnight aggregation.",
            })}
          </p>
        ) : gateFluxQuery.isError ? (
          <div className="flex items-center gap-2 rounded-xl border border-warning/40 bg-warning/10 px-3 py-2 text-sm text-warning">
            <WarningIcon className="h-5 w-5" />
            {t("dashboard.openSea.gateFluxError", { defaultValue: "Failed to load gate flux." })}
          </div>
        ) : gateFluxSeries.length === 0 ? (
          <p className="text-sm text-foreground/60">
            {t("dashboard.openSea.gateFluxEmpty", { defaultValue: "No gate crossings observed in the selected window." })}
          </p>
        ) : (
          <div className="space-y-4">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div>
                <p className="text-xs uppercase tracking-wide text-foreground/60">
                  {t("dashboard.openSea.totalCrossings", { defaultValue: "Total crossings" })}
                </p>
                <p className="text-3xl font-semibold">
                  {gateFluxQuery.data?.total_crossings.toLocaleString(locale)}
                </p>
              </div>
              {gateFluxQuery.data?.direction && (
                <span className="rounded-full bg-foreground/10 px-3 py-1 text-xs uppercase tracking-wide text-foreground/60">
                  {gateFluxQuery.data.direction}
                </span>
              )}
            </div>
            <TimeSeriesChart
              data={gateFluxSeries}
              label={t("dashboard.openSea.crossingsLabel", { defaultValue: "Crossings" })}
            />
          </div>
        )}
      </Card>

      <Card
        title={t("dashboard.openSea.sisTitle", { defaultValue: "SIS status" })}
        subtitle={`${selectedCorridorId} · ${sisWindowLabel}`}
      >
        {sisIsStale && sisLatestLabel && (
          <div className="mb-3 rounded-lg border border-warning/40 bg-warning/10 px-3 py-2 text-xs text-warning">
            {t("dashboard.openSea.staleSis", {
              defaultValue: "SIS data stale since {{datetime}}",
              datetime: sisLatestLabel,
            })}
          </div>
        )}
        {sisQuery.isLoading ? (
          <Skeleton className="h-40 w-full" />
        ) : !sisLatest && !summaryRegion ? (
          <p className="text-sm text-foreground/60">
            {t("dashboard.openSea.sisEmpty", { defaultValue: "No SIS samples for the selected corridor." })}
          </p>
        ) : (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-3">
              {sisBadgeProps && (
                <SISBadge
                  sisP90={sisBadgeProps.sisP90}
                  waveHeight={sisBadgeProps.waveHeight}
                  currentSpeed={sisBadgeProps.currentSpeed}
                  windSpeed={sisBadgeProps.windSpeed}
                  corridor={sisBadgeProps.corridor}
                />
              )}
              <span className="text-sm text-foreground/60">
                {t("dashboard.openSea.latestAsOf", {
                  defaultValue: "Latest {{date}}",
                  date: fallbackLatestLabel ?? "—",
                })}
              </span>
            </div>
            <dl className="space-y-2 text-sm text-foreground/70">
              {sisSummary.map((item) => (
                <div key={item.label} className="flex items-center justify-between gap-3">
                  <dt className="uppercase tracking-wide text-foreground/50">{item.label}</dt>
                  <dd className="font-mono text-foreground">{item.value}</dd>
                </div>
              ))}
              <div className="flex items-center justify-between gap-3 text-xs text-foreground/50">
                <span>{t("dashboard.openSea.sampleCount", { defaultValue: "Samples" })}</span>
                <span>{sampleCount.toLocaleString(locale)}</span>
              </div>
            </dl>
            {sisSeries.length > 1 && (
              <div className="rounded-lg border border-foreground/10 bg-foreground/5 px-3 py-2 text-xs text-foreground/60">
                <p className="mb-1 uppercase tracking-wide">
                  {t("dashboard.openSea.recentSis", { defaultValue: "Recent SIS p90" })}
                </p>
                <ul className="space-y-1">
                  {sisSeries.slice(0, 5).map((row) => (
                    <li key={row.ds} className="flex items-center justify-between">
                      <span>{new Date(row.ds).toLocaleDateString(locale)}</span>
                      <span className="font-mono text-foreground/80">
                        {row.sis_p90 != null ? row.sis_p90.toFixed(2) : "N/A"}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </Card>
    </div>
  );
};

type GateOption = {
  id: string;
  name: string;
  corridorId?: string;
  flux?: number;
};
