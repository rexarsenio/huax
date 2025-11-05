import { useMemo, useState } from "react";
import clsx from "clsx";
import { useTranslation } from "react-i18next";
import { Card } from "./Card";
import { Skeleton } from "./Skeleton";
import { useOpenSeaSummary } from "../hooks/useApi";

const DEFAULT_WINDOW = "h24";

const formatNumber = (value: number | null | undefined, locale: string, digits = 0) => {
  if (value == null || !Number.isFinite(value)) {
    return "—";
  }
  return value.toLocaleString(locale, { maximumFractionDigits: digits });
};

const formatZScore = (value: number | null | undefined) => {
  if (value == null || !Number.isFinite(value)) {
    return "—";
  }
  const formatted = value.toFixed(2);
  return value > 0 ? `+${formatted}` : formatted;
};

const formatDelayRatio = (value: number | null | undefined) => {
  if (value == null || !Number.isFinite(value)) {
    return "—";
  }
  return `${value.toFixed(2)}×`;
};

export const ChokepointTable = () => {
  const { t, i18n } = useTranslation();
  const locale = i18n.language;
  const [selectedGate, setSelectedGate] = useState<string>("ALL");
  const summaryQuery = useOpenSeaSummary(DEFAULT_WINDOW, selectedGate === "ALL" ? undefined : selectedGate);

  const corridors = useMemo(() => summaryQuery.data?.corridors ?? [], [summaryQuery.data]);
  const options = useMemo(() => {
    const ids = new Set<string>();
    const labels: Array<{ id: string; label: string }> = [];
    for (const item of corridors) {
      if (!ids.has(item.gate_id)) {
        ids.add(item.gate_id);
        labels.push({ id: item.gate_id, label: item.label ?? item.gate_id });
      }
    }

    const manualWestAfrica = [
      {
        id: "WEST_AFRICA_BONNY",
        label: t("dashboard.openSeaSummary.filters.westAfricaBonny", {
          defaultValue: "West Africa · Bonny",
        }),
      },
      {
        id: "WEST_AFRICA_ESCRAVOS",
        label: t("dashboard.openSeaSummary.filters.westAfricaEscravos", {
          defaultValue: "West Africa · Escravos",
        }),
      },
      {
        id: "WEST_AFRICA_GULF",
        label: t("dashboard.openSeaSummary.filters.westAfricaGulf", {
          defaultValue: "West Africa · Gulf Corridor",
        }),
      },
    ];

    for (const option of manualWestAfrica) {
      if (!ids.has(option.id)) {
        ids.add(option.id);
        labels.push(option);
      }
    }

    labels.sort((a, b) => a.label.localeCompare(b.label));
    return [{ id: "ALL", label: t("dashboard.openSeaSummary.filterAll", { defaultValue: "All chokepoints" }) }, ...labels];
  }, [corridors, t]);

  const { asOfLabel, asOfStale } = useMemo(() => {
    const timestamp = summaryQuery.data?.as_of;
    if (!timestamp) {
      return { asOfLabel: null, asOfStale: false };
    }
    const parsed = new Date(timestamp);
    if (Number.isNaN(parsed.getTime())) {
      return { asOfLabel: timestamp, asOfStale: false };
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
    const diffMs = Date.now() - parsed.getTime();
    const twelveHours = 12 * 60 * 60 * 1000;
    return { asOfLabel: label, asOfStale: diffMs > twelveHours };
  }, [locale, summaryQuery.data?.as_of]);

  return (
    <Card
      title={t("dashboard.openSeaSummary.title", { defaultValue: "Chokepoints (24h)" })}
      subtitle={
        asOfLabel
          ? asOfStale
            ? t("dashboard.openSeaSummary.stale", {
                defaultValue: "Stale snapshot · last update {{datetime}}",
                datetime: asOfLabel,
              })
            : t("dashboard.openSeaSummary.asOf", { defaultValue: "As of {{datetime}}", datetime: asOfLabel })
          : undefined
      }
      action={
        options.length > 1 ? (
          <select
            value={selectedGate}
            onChange={(event) => setSelectedGate(event.target.value)}
            className="rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground hover:border-foreground/40 focus:outline-none focus:ring-2 focus:ring-primary/40"
          >
            {options.map((option) => (
              <option key={option.id} value={option.id}>
                {option.label}
              </option>
            ))}
          </select>
        ) : null
      }
    >
      {summaryQuery.isLoading ? (
        <Skeleton className="h-48 w-full" />
      ) : summaryQuery.isError ? (
        <div className="rounded-lg border border-warning/40 bg-warning/10 px-3 py-2 text-sm text-warning">
          {t("dashboard.openSeaSummary.error", { defaultValue: "Unable to load chokepoint summary." })}
        </div>
      ) : corridors.length === 0 ? (
        <div className="rounded-lg border border-foreground/10 bg-foreground/5 px-3 py-2 text-sm text-foreground/60">
          {t("dashboard.openSeaSummary.empty", { defaultValue: "No crossings in this window. Try a longer range." })}
        </div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-foreground/10">
          <table className="min-w-full text-sm">
            <thead className="bg-foreground/5 text-foreground/70">
              <tr>
                <th className="px-3 py-2 text-left font-semibold uppercase tracking-wide text-xs">
                  {t("dashboard.openSeaSummary.headers.corridor", { defaultValue: "Corridor" })}
                </th>
                <th className="px-3 py-2 text-right font-semibold uppercase tracking-wide text-xs">
                  {t("dashboard.openSeaSummary.headers.throughput", { defaultValue: "Flux 24h" })}
                </th>
                <th className="px-3 py-2 text-right font-semibold uppercase tracking-wide text-xs">
                  {t("dashboard.openSeaSummary.headers.fluxZ", { defaultValue: "Flux z" })}
                </th>
                <th className="px-3 py-2 text-right font-semibold uppercase tracking-wide text-xs">
                  {t("dashboard.openSeaSummary.headers.delay", { defaultValue: "Delay ratio" })}
                </th>
                <th className="px-3 py-2 text-right font-semibold uppercase tracking-wide text-xs">
                  {t("dashboard.openSeaSummary.headers.sis", { defaultValue: "SIS p90" })}
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-foreground/10 text-foreground">
              {corridors.map((entry) => {
                const fluxCritical = entry.flux_z != null && Number.isFinite(entry.flux_z) && entry.flux_z >= 2;
                const delayCritical =
                  entry.delay_ratio != null && Number.isFinite(entry.delay_ratio) && entry.delay_ratio >= 1.3;
                const critical = fluxCritical || delayCritical;
                return (
                  <tr key={entry.gate_id} className={clsx(critical && "bg-danger/5")}>
                    <td className="px-3 py-3">
                      <div className="flex flex-col">
                        <span className="font-medium text-foreground">{entry.label ?? entry.gate_id}</span>
                        <span className="text-xs uppercase tracking-wide text-foreground/40">{entry.gate_id}</span>
                      </div>
                    </td>
                    <td className="px-3 py-3 text-right font-mono text-sm">
                      {formatNumber(entry.flux, locale)}
                    </td>
                    <td
                      className={clsx(
                        "px-3 py-3 text-right font-mono text-sm",
                        fluxCritical ? "text-danger font-semibold" : "text-foreground/70",
                      )}
                    >
                      {formatZScore(entry.flux_z ?? null)}
                    </td>
                    <td
                      className={clsx(
                        "px-3 py-3 text-right font-mono text-sm",
                        delayCritical ? "text-danger font-semibold" : "text-foreground/70",
                      )}
                    >
                      {formatDelayRatio(entry.delay_ratio ?? null)}
                    </td>
                    <td className="px-3 py-3 text-right font-mono text-sm text-foreground/70">
                      {formatNumber(entry.sis_p90 ?? null, locale, 2)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
};
