import { useMemo } from "react";
import { Card } from "./Card";
import { Skeleton } from "./Skeleton";
import { useSignalsSnapshot, useIndexMeta } from "../hooks/useApi";
import { RefreshIcon, WarningIcon } from "./icons";
import { useTranslation } from "react-i18next";

const formatPct = (value: number) => `${(value * 100).toFixed(1)}%`;
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
  const formattedAsOf = new Date(data.asof).toLocaleString(i18n.language);
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
  const spreadTopDecile =
    !spreadDegraded && spreadProb !== undefined
      ? spreadTopThreshold !== undefined
        ? spreadProb >= spreadTopThreshold
        : Boolean(data.spread_direction?.top_decile)
      : false;
  const spreadMode = spreadInfo?.mode ?? (spreadDegraded ? "fallback" : "model");

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
      {spreadDegraded && (
        <div className="mb-3 space-y-2 rounded-xl border border-warning/40 bg-warning/10 px-3 py-2 text-sm text-warning">
          <p>{t("dashboard.signals.degraded")}</p>
          {spreadReasons.length > 0 && (
            <ul className="space-y-1 text-xs text-warning/80">
              {spreadReasons.map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          )}
        </div>
      )}
      {spreadDegraded && fallbackDrivers.length > 0 && (
        <div className="mb-3 grid gap-2 rounded-xl border border-warning/30 bg-warning/5 px-3 py-2 text-xs text-warning/80 sm:grid-cols-3">
          {fallbackDrivers.map(([key, value]) => {
            const numeric = parseNumeric(value);
            return (
              <div key={key} className="flex items-center justify-between gap-3">
                <span className="uppercase tracking-wide text-warning/60">{key}</span>
                <span className="font-mono">{numeric !== undefined ? numeric.toFixed(3) : "—"}</span>
              </div>
            );
          })}
        </div>
      )}
      <div className="grid gap-4 md:grid-cols-3">
        <div>
          <p className="text-xs uppercase tracking-wide text-foreground/60">{t("dashboard.signals.spvxLite")}</p>
          {spvxLiteValue !== undefined ? (
            <>
              <p className="text-2xl font-semibold">{spvxLiteValue.toFixed(2)}</p>
              {spvxLiteChange !== undefined && (
                <p className={`text-sm ${spvxLiteChange >= 0 ? "text-success" : "text-danger"}`}>
                  {t("dashboard.signals.change")}: {spvxLiteChange >= 0 ? "+" : ""}
                  {spvxLiteChange.toFixed(2)}
                </p>
              )}
            </>
          ) : (
            <p className="text-sm text-foreground/50">{t("dashboard.signals.spread.notAvailable")}</p>
          )}
        </div>
        <div>
          <p className="text-xs uppercase tracking-wide text-foreground/60">{t("dashboard.signals.spread.label")}</p>
          {spreadProb !== undefined ? (
            <>
              <div className="flex items-baseline gap-2">
                <p className="text-2xl font-semibold">{formatPct(spreadProb)}</p>
                {spreadDegraded && (
                  <span className="rounded-full bg-warning/20 px-2 py-1 text-xs font-medium text-warning">
                    {t("dashboard.signals.spread.fallback", {
                      strategy: spreadMode,
                      defaultValue: `Fallback (${spreadMode})`
                    })}
                  </span>
                )}
              </div>
              {!spreadDegraded && (
                <span
                  className={`mt-1 inline-flex items-center rounded-full px-2 py-1 text-xs ${
                    spreadTopDecile ? "bg-success/20 text-success" : "bg-muted text-foreground/70"
                  }`}
                >
                  {spreadTopDecile
                    ? t("dashboard.signals.spread.topDecile")
                    : t("dashboard.signals.spread.outside")}
                </span>
              )}
            </>
          ) : (
            <p className="text-sm text-foreground/50">{t("dashboard.signals.spread.notAvailable")}</p>
          )}
        </div>
        <div>
          <p className="text-xs uppercase tracking-wide text-foreground/60">{t("dashboard.signals.throughput.label")}</p>
          {throughputMae != null ? (
            <>
              <p className="text-2xl font-semibold">{throughputMae.toFixed(1)}</p>
              <p className="text-sm text-foreground/50">{t("dashboard.signals.throughput.mae")}</p>
            </>
          ) : (
            <p className="text-sm text-foreground/50">{t("dashboard.signals.throughput.awaiting")}</p>
          )}
        </div>
      </div>
      {driverEntries.length > 0 && (
        <div className="mt-4">
          <p className="text-xs uppercase tracking-wide text-foreground/60 mb-2">{t("dashboard.signals.drivers")}</p>
          <ul className="grid gap-2 sm:grid-cols-3 text-sm">
            {driverEntries.map(([key, value]) => {
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
              return (
                <li
                  key={key}
                  className="rounded-lg border border-foreground/10 px-3 py-2"
                  title={tooltip}
                >
                  <span className="font-medium">{label}</span>
                  <span className="ml-2 text-foreground/60">
                    {numeric !== undefined ? numeric.toFixed(2) : "N/A"}
                  </span>
                </li>
              );
            })}
          </ul>
        </div>
      )}
      {nowcastEntries.length > 0 && (
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
                {nowcastEntries.map(([date, value]) => {
                  const numeric = parseNumeric(value);
                  return (
                    <tr key={String(date)}>
                      <td className="px-3 py-2">{String(date)}</td>
                      <td className="px-3 py-2">{numeric !== undefined ? numeric.toFixed(2) : "N/A"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </Card>
  );
};
