import { useMemo } from "react";
import { Card } from "./Card";
import { Skeleton } from "./Skeleton";
import { useSignalsSnapshot, useIndexMeta } from "../hooks/useApi";
import { RefreshIcon, WarningIcon } from "./icons";
import { SeaStateChip } from "./SeaStateChip";
import { useTranslation } from "react-i18next";

const formatPct = (value: number) => `${(value * 100).toFixed(1)}%`;
const humanizeKey = (value: string) =>
  value
    .replace(/[_\s]+/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
const parseNumeric = (value: unknown): number | undefined => {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : undefined;
  }
  return undefined;
};

export const SignalSummary = () => {
  const { data, isLoading, isError, refetch, isFetching } = useSignalsSnapshot();
  const { data: meta } = useIndexMeta();
  const { t, i18n } = useTranslation();

  const driverMetaMap = useMemo(() => {
    if (!meta?.drivers) {
      return new Map<string, { label_key?: string; label_default?: string; title_key?: string; title_default?: string; tooltip_key?: string; tooltip_default?: string }>();
    }
    return new Map(meta.drivers.map((item) => [item.id, item]));
  }, [meta?.drivers]);

  if (isLoading) {
    return (
      <Card title={t("dashboard.signals.title")}>
        <Skeleton className="h-16 w-full" />
      </Card>
    );
  }

  if (isError || !data) {
    return (
      <Card title={t("dashboard.signals.title")} subtitle={t("dashboard.signals.errorTitle")}>
        <div className="flex items-center gap-2 text-danger text-sm">
          <WarningIcon className="h-5 w-5" />
          <span>{t("dashboard.signals.errorBody")}</span>
        </div>
      </Card>
    );
  }

  const driverEntries = Object.entries(data.drivers ?? {});
  const nowcastEntries = Object.entries(data.throughput_72h?.nowcast ?? {});
  const throughputMae = parseNumeric(data.throughput_72h?.mae_units);
  const asOfDate = data.asof ? new Date(data.asof) : undefined;
  const formattedAsOf =
    asOfDate && !Number.isNaN(asOfDate.getTime())
      ? asOfDate.toLocaleString(i18n.language, { dateStyle: "medium", timeStyle: "short" })
      : data.asof;
  const spvxLiteValue = parseNumeric(data.spvx_lite);
  const spvxLiteChange = parseNumeric(data.spvx_lite_chg);
  const spreadInfo = data.spread;
  const spreadDegraded = Boolean(spreadInfo?.degraded ?? data.degraded);
  const spreadProb = parseNumeric(spreadInfo?.prob_up ?? data.spread_direction?.["t+1_prob_up"]);
  const spreadTopThreshold = parseNumeric(spreadInfo?.top_decile_threshold);
  const spreadReasons = Array.isArray(spreadInfo?.reasons) ? (spreadInfo?.reasons as string[]) : [];
  const fallbackDrivers = Object.entries(spreadInfo?.drivers ?? {}).filter(([, value]) => {
    const numericValue = parseNumeric(value);
    return numericValue !== undefined;
  });
  const seaStateDriver = spreadInfo?.drivers?.sea_state;
  const seaState = (() => {
    if (!seaStateDriver || typeof seaStateDriver !== "object") {
      return null;
    }
    const payload = seaStateDriver as Record<string, unknown>;
    const hsZ = parseNumeric(payload["hs_z"]);
    const asOfRaw = payload["as_of"];
    const asOf = typeof asOfRaw === "string" && asOfRaw.trim() ? asOfRaw : undefined;
    if (hsZ === undefined || !asOf) {
      return null;
    }
    const oppCurrent = parseNumeric(payload["opp_current"]);
    return { hsZ, oppCurrent, asOf };
  })();
  const spreadTopDecile =
    !spreadDegraded && spreadProb !== undefined
      ? spreadTopThreshold !== undefined
        ? spreadProb >= spreadTopThreshold
        : Boolean(data.spread_direction?.top_decile)
      : false;
  const spreadMode = spreadInfo?.mode ?? (spreadDegraded ? "fallback" : "model");
  const annotations = Array.isArray(data.annotations)
    ? data.annotations
        .map((item) => (typeof item === "string" ? item.trim() : ""))
        .filter(Boolean)
    : [];
  const annotationItems = annotations.map((item) => ({ raw: item, label: humanizeKey(item) }));
  const reasonItems = spreadReasons.map((reason) => ({ raw: reason, label: humanizeKey(reason) }));
  const driverRows = driverEntries
    .map(([key, value]) => {
      const numeric = parseNumeric(value);
      const driverInfo = driverMetaMap.get(key) ?? driverMetaMap.get(key.toUpperCase());
      const label = driverInfo?.label_key
        ? t(driverInfo.label_key, { defaultValue: driverInfo.label_default ?? key })
        : driverInfo?.title_key
        ? t(driverInfo.title_key, { defaultValue: driverInfo.title_default ?? key })
        : driverInfo?.title_default ?? key;
      const tooltip = driverInfo?.tooltip_key
        ? t(driverInfo.tooltip_key, { defaultValue: driverInfo.tooltip_default ?? undefined })
        : driverInfo?.tooltip_default;
      return { key, numeric, label, tooltip };
    })
    .sort((a, b) => {
      const aVal = a.numeric != null ? Math.abs(a.numeric) : -Infinity;
      const bVal = b.numeric != null ? Math.abs(b.numeric) : -Infinity;
      return bVal - aVal;
    });
  const fallbackDriverRows = fallbackDrivers
    .map(([key, value]) => {
      const numeric = parseNumeric(value);
      return { key, numeric };
    })
    .sort((a, b) => {
      const aVal = a.numeric != null ? Math.abs(a.numeric) : -Infinity;
      const bVal = b.numeric != null ? Math.abs(b.numeric) : -Infinity;
      return bVal - aVal;
    });
  const nowcastRows = nowcastEntries
    .map(([date, value]) => {
      const numeric = parseNumeric(value);
      let parsedDate: number | null = null;
      if (typeof date === "string") {
        const timestamp = Date.parse(date);
        parsedDate = Number.isNaN(timestamp) ? null : timestamp;
      }
      return { date: String(date), numeric, sortKey: parsedDate ?? Number.POSITIVE_INFINITY };
    })
    .sort((a, b) => a.sortKey - b.sortKey);

  return (
    <Card
      title={t("dashboard.signals.title")}
      subtitle={t("dashboard.signals.subtitle", { datetime: formattedAsOf })}
      action={
        <button
          type="button"
          onClick={() => refetch()}
          disabled={isFetching}
          className="inline-flex items-center gap-2 text-sm text-accent hover:text-foreground transition-colors"
        >
          <RefreshIcon className={`h-4 w-4 ${isFetching ? "animate-spin" : ""}`} />
          {t("actions.refresh")}
        </button>
      }
    >
      {(spreadDegraded || annotationItems.length > 0) && (
        <div className="mb-4 space-y-3">
          {spreadDegraded && (
            <div className="rounded-2xl border border-warning/40 bg-warning/10 px-4 py-3 text-sm text-warning">
              <div className="flex items-start gap-3">
                <WarningIcon className="h-5 w-5 mt-0.5" />
                <div className="space-y-2">
                  <p className="font-medium">{t("dashboard.signals.degraded")}</p>
                  {reasonItems.length > 0 && (
                    <div>
                      <p className="text-xs uppercase tracking-wide text-warning/60">
                        {t("dashboard.signals.reasons", { defaultValue: "Degradation notes" })}
                      </p>
                      <ul className="mt-1 space-y-1 text-xs text-warning/80">
                        {reasonItems.map(({ raw, label }) => (
                          <li key={raw}>{label}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              </div>
              {fallbackDriverRows.length > 0 && (
                <div className="mt-3 border-t border-warning/20 pt-3">
                  <p className="mb-2 text-xs uppercase tracking-wide text-warning/60">
                    {t("dashboard.signals.fallback", { defaultValue: "Fallback inputs" })}
                  </p>
                  <div className="grid gap-2 text-xs text-warning/80 sm:grid-cols-3">
                    {fallbackDriverRows.map(({ key, numeric }) => (
                      <div key={key} className="flex items-center justify-between gap-3 rounded-lg bg-warning/5 px-3 py-2">
                        <span className="uppercase tracking-wide text-warning/60">{key}</span>
                        <span className="font-mono">{numeric !== undefined ? numeric.toFixed(3) : "—"}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
          {annotationItems.length > 0 && (
            <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-foreground/10 bg-foreground/5 px-3 py-2 text-xs text-foreground/70">
              <span className="uppercase tracking-wide text-foreground/50">
                {t("dashboard.signals.qualityChecks", { defaultValue: "Quality checks" })}
              </span>
              {annotationItems.map(({ raw, label }) => (
                <span
                  key={raw}
                  className="inline-flex items-center rounded-full bg-foreground/10 px-2 py-1 font-medium text-foreground"
                >
                  {label}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
      <div className="grid gap-3 md:grid-cols-3">
        <div className="rounded-2xl border border-foreground/10 bg-foreground/5 px-4 py-3">
          <p className="text-xs uppercase tracking-wide text-foreground/60">{t("dashboard.signals.spvxLite")}</p>
          {spvxLiteValue !== undefined ? (
            <div className="space-y-1">
              <p className="text-3xl font-semibold leading-tight">{spvxLiteValue.toFixed(2)}</p>
              {spvxLiteChange !== undefined && (
                <p className={`text-sm font-medium ${spvxLiteChange >= 0 ? "text-success" : "text-danger"}`}>
                  {t("dashboard.signals.change")}: {spvxLiteChange >= 0 ? "+" : ""}
                  {spvxLiteChange.toFixed(2)}
                </p>
              )}
            </div>
          ) : (
            <p className="text-sm text-foreground/50">{t("dashboard.signals.spread.notAvailable")}</p>
          )}
        </div>
        <div className="rounded-2xl border border-foreground/10 bg-foreground/5 px-4 py-3">
          <p className="text-xs uppercase tracking-wide text-foreground/60">{t("dashboard.signals.spread.label")}</p>
          {spreadProb !== undefined ? (
            <div className="space-y-2">
              <div className="flex items-baseline gap-2">
                <p className="text-3xl font-semibold leading-tight">{formatPct(spreadProb)}</p>
                <span
                  className={`inline-flex items-center rounded-full px-2 py-1 text-xs font-medium ${
                    spreadDegraded ? "bg-warning/10 text-warning" : "bg-accent/10 text-accent"
                  }`}
                >
                  {spreadDegraded
                    ? t("dashboard.signals.spread.fallback", {
                        strategy: spreadMode,
                        defaultValue: `Fallback (${spreadMode})`,
                      })
                    : t("dashboard.signals.spread.model", { defaultValue: "Model signal" })}
                </span>
              </div>
              {!spreadDegraded && (
                <span
                  className={`inline-flex items-center rounded-full px-2 py-1 text-xs ${
                    spreadTopDecile ? "bg-success/15 text-success" : "bg-foreground/10 text-foreground/70"
                  }`}
                >
                  {spreadTopDecile
                    ? t("dashboard.signals.spread.topDecile")
                    : t("dashboard.signals.spread.outside")}
                </span>
              )}
            </div>
          ) : (
            <p className="text-sm text-foreground/50">{t("dashboard.signals.spread.notAvailable")}</p>
          )}
        </div>
        <div className="rounded-2xl border border-foreground/10 bg-foreground/5 px-4 py-3">
          <p className="text-xs uppercase tracking-wide text-foreground/60">{t("dashboard.signals.throughput.label")}</p>
          {throughputMae != null ? (
            <div className="space-y-1">
              <p className="text-3xl font-semibold leading-tight">{throughputMae.toFixed(1)}</p>
              <p className="text-xs uppercase tracking-wide text-foreground/50">
                {t("dashboard.signals.throughput.mae")}
              </p>
            </div>
          ) : (
            <p className="text-sm text-foreground/50">{t("dashboard.signals.throughput.awaiting")}</p>
          )}
        </div>
      </div>
      {seaState && (
        <div className="mt-4">
          <SeaStateChip hsZ={seaState.hsZ} oppCurrent={seaState.oppCurrent} asOf={seaState.asOf} />
        </div>
      )}
      {driverRows.length > 0 && (
        <div className="mt-4">
          <p className="text-xs uppercase tracking-wide text-foreground/60 mb-2">{t("dashboard.signals.drivers")}</p>
          <ul className="grid gap-2 sm:grid-cols-3 text-sm">
            {driverRows.map(({ key, numeric, label, tooltip }) => (
              <li
                key={key}
                className="rounded-lg border border-foreground/10 bg-foreground/5 px-3 py-2"
                title={tooltip}
              >
                <div className="flex items-center justify-between gap-3">
                  <span className="font-medium">{label}</span>
                  <span className="text-foreground/60">
                    {numeric !== undefined ? numeric.toFixed(2) : "N/A"}
                  </span>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
      {nowcastRows.length > 0 && (
        <div className="mt-4">
          <p className="text-xs uppercase tracking-wide text-foreground/60 mb-2">{t("dashboard.signals.nowcast.label")}</p>
          <div className="overflow-x-auto rounded-xl border border-foreground/10">
            <table className="min-w-full divide-y divide-foreground/10 text-sm">
              <thead className="bg-foreground/5 text-foreground/70">
                <tr>
                  <th className="px-3 py-2 text-left font-medium">{t("dashboard.signals.nowcast.date")}</th>
                  <th className="px-3 py-2 text-left font-medium">{t("dashboard.signals.nowcast.value")}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-foreground/10">
                {nowcastRows.map(({ date, numeric }) => (
                  <tr key={date}>
                    <td className="px-3 py-2">{date}</td>
                    <td className="px-3 py-2">{numeric !== undefined ? numeric.toFixed(2) : "N/A"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </Card>
  );
};
