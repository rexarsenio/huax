import { Card } from "./Card";
import { Skeleton } from "./Skeleton";
import { useIndexMeta, useGlobalIndex } from "../hooks/useApi";
import { useTranslation } from "react-i18next";

export const MetaHero = () => {
  const { data, isLoading, isError } = useIndexMeta();
  const globalQuery = useGlobalIndex("7d");
  const { t } = useTranslation();

  if (isLoading || globalQuery.isLoading) {
    return <Skeleton className="h-96 w-full" />;
  }

  if (isError || !data) {
    return (
      <Card title={t("dashboard.meta.title") ?? "SPVX-Lite"}>
        <p className="text-sm text-foreground/60">{t("dashboard.meta.error")}</p>
      </Card>
    );
  }

  const { index, methodology } = data;

  // ⚠️ CRITICAL: Use ONLY /api/index/global data - the single source of truth!
  const relativeStress = globalQuery.data?.relative_stress;
  const latestPoint = globalQuery.data?.latest;
  const latestStatus = relativeStress?.latest; // Use live data from /api/index/global, NOT /meta!
  const latestNarrative = relativeStress?.narrative;

  const currentValue = latestPoint?.spvx_global ?? 100;

  // All metrics MUST come from the live relative_stress data
  const zScore = latestStatus?.z_score ?? 0;
  const percentile = latestStatus?.percentile ?? 50;
  const seasonalMean = latestStatus?.seasonal_mean ?? 100;
  const deviationPct = latestStatus?.deviation_pct ?? 0;
  const dataGapRatio =
    latestStatus?.data_gap_ratio != null
      ? latestStatus.data_gap_ratio
      : latestPoint && typeof (latestPoint as { data_gap_ratio?: number | null }).data_gap_ratio === "number"
      ? ((latestPoint as { data_gap_ratio?: number | null }).data_gap_ratio as number)
      : undefined;
  const ingestLagSeconds =
    latestStatus?.ingest_lag_seconds != null
      ? latestStatus.ingest_lag_seconds
      : latestPoint &&
          typeof (latestPoint as { ingest_lag_seconds?: number | null }).ingest_lag_seconds === "number"
      ? ((latestPoint as { ingest_lag_seconds?: number | null }).ingest_lag_seconds as number)
      : undefined;

  // Simple, deterministic status classification based on z-score
  const getStatus = (z: number) => {
    if (z <= -0.5) return { label: "QUIET", color: "#6366f1", bg: "#6366f120" };
    if (z >= 0.5) return { label: "ELEVATED", color: "#f59e0b", bg: "#f59e0b20" };
    return { label: "NORMAL", color: "#10b981", bg: "#10b98120" };
  };

  const status = getStatus(zScore);
  const description = index.description_key
    ? t(index.description_key, { defaultValue: index.description_default ?? "" })
    : index.description_default ?? "";

  return (
    <Card
      title={`${index.name} · v${index.version}`}
      subtitle={`${index.fix_time_utc} UTC`}
    >
      <div className="space-y-6">
        <section className="space-y-4">
          <div className="flex items-center gap-3">
            <span
              className="rounded-lg px-3 py-1.5 text-sm font-semibold"
              style={{ backgroundColor: status.bg, color: status.color }}
            >
              {status.label}
            </span>
            <span className="text-sm text-foreground/60">vs seasonal normal</span>
          </div>

          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            {[
              { k: "SPVX", v: currentValue.toFixed(1) },
              { k: "Seasonal normal", v: seasonalMean.toFixed(1) },
              { k: "Deviation", v: `${deviationPct >= 0 ? "+" : ""}${deviationPct.toFixed(0)}%` },
              { k: "Percentile", v: `${Math.round(percentile)}th` },
            ].map((x) => (
              <div
                key={x.k}
                className="rounded-xl border border-foreground/10 bg-foreground/5 px-4 py-3"
              >
                <div className="text-[10px] uppercase tracking-wide text-foreground/50">{x.k}</div>
                <div className="text-2xl font-semibold text-foreground">{x.v}</div>
              </div>
            ))}
          </div>

          {latestNarrative && (
            <div className="rounded-xl border border-foreground/10 bg-foreground/5 p-4">
              <p className="text-sm text-foreground/80">{latestNarrative.summary}</p>
            </div>
          )}
        </section>

        {/* Methodology (Collapsed by default) */}
        <details className="rounded-xl border border-foreground/10 bg-foreground/5 px-4 py-3 text-sm text-foreground/80">
          <summary className="cursor-pointer text-sm font-medium text-foreground">
            {t("dashboard.meta.methodologyLink", { defaultValue: "Methodology & Details" })}
          </summary>
          <div className="mt-3 space-y-3">
            {description && <p className="text-xs text-foreground/70">{description}</p>}
            <p className="text-xs">
              {methodology.summary_key
                ? t(methodology.summary_key, { defaultValue: methodology.summary_default ?? "" })
                : methodology.summary_default ?? ""}
            </p>
            <div>
              <p className="mb-2 text-xs uppercase tracking-wide text-foreground/60">
                {t("dashboard.meta.tableTitle")}
              </p>
              <div className="overflow-x-auto rounded-lg border border-foreground/10">
                <table className="min-w-full divide-y divide-foreground/10 text-xs">
                  <thead className="bg-foreground/5 text-foreground/60">
                    <tr>
                      <th className="px-3 py-2 text-left font-medium">
                        {t("dashboard.meta.component")}
                      </th>
                      <th className="px-3 py-2 text-left font-medium">
                        {t("dashboard.meta.geofence")}
                      </th>
                      <th className="px-3 py-2 text-left font-medium">
                        {t("dashboard.meta.cadence")}
                      </th>
                      <th className="px-3 py-2 text-left font-medium">{t("dashboard.meta.note")}</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-foreground/10">
                    {methodology.table.map((row, idx) => (
                      <tr key={row.component_key ?? String(idx)}>
                        <td className="px-3 py-2 font-medium text-foreground">
                          {row.component_key
                            ? t(row.component_key, { defaultValue: row.component_default ?? "" })
                            : row.component_default ?? ""}
                        </td>
                        <td className="px-3 py-2">
                          {row.geofence_key
                            ? t(row.geofence_key, { defaultValue: row.geofence_default ?? "" })
                            : row.geofence_default ?? ""}
                        </td>
                        <td className="px-3 py-2">
                          {row.cadence_key
                            ? t(row.cadence_key, { defaultValue: row.cadence_default ?? "" })
                            : row.cadence_default ?? ""}
                        </td>
                        <td className="px-3 py-2">
                          {row.note_key
                            ? t(row.note_key, { defaultValue: row.note_default ?? "" })
                            : row.note_default ?? ""}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
            <p className="text-sm">
              {methodology.quality_key
                ? t(methodology.quality_key, { defaultValue: methodology.quality_default ?? "" })
                : methodology.quality_default ?? ""}
            </p>
            <div>
              <p className="mb-1 text-xs uppercase tracking-wide text-foreground/60">
                {t("dashboard.meta.transparency")}
              </p>
              <ul className="list-disc space-y-1 pl-5">
                {(methodology.transparency_keys ?? []).map((key, idx) => (
                  <li key={key}>
                    {t(key, {
                      defaultValue: methodology.transparency_defaults?.[idx] ?? "",
                    })}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </details>

        <p className="text-xs text-foreground/50">
          {methodology.disclaimer_key
            ? t(methodology.disclaimer_key, { defaultValue: methodology.disclaimer_default ?? "" })
            : methodology.disclaimer_default ?? ""}
        </p>
      </div>
    </Card>
  );
};
