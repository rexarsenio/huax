import { Card } from "../components/Card";
import { Skeleton } from "../components/Skeleton";
import { useHealthStatus, useMetrics, useRunMeta, useOpsHealth } from "../hooks/useApi";
import { appConfig } from "../config";
import { WarningIcon } from "../components/icons";
import { useTranslation } from "react-i18next";
import { RegistryPanel } from "../components/RegistryPanel";
import { SISBadge } from "../components/SISBadge";
import { useSISData } from "../hooks/useSISData";

export const OperationsPage = () => {
  const { data: health } = useHealthStatus();
  const { data: opsHealth } = useOpsHealth();
  const { data: runMeta, isLoading: runMetaLoading } = useRunMeta();
  const { data: metrics, isLoading: metricsLoading, isError: metricsError } = useMetrics();
  const { t, i18n } = useTranslation();

  // Fetch SIS data for key chokepoints
  const { data: malaccaSIS } = useSISData("CHOKEPOINT_MALACCA->UNK");
  const { data: singaporeSIS } = useSISData("CHOKEPOINT_SINGAPORE_STRAIT->UNK");
  const { data: suezSIS } = useSISData("CHOKEPOINT_SUEZ_NORTH->UNK");
  const locale = i18n.language;
  const formatTimestamp = (ts?: string) => (ts ? new Date(ts).toLocaleString(locale) : "—");
  const isReady = opsHealth?.ready ?? (health?.status === "ready");
  const translatedStatus = isReady ? t("status.ready") : t("status.not_ready");
  const componentsPresent = Object.entries(opsHealth?.components_present ?? {});
  const coverageEntries = Object.entries(opsHealth?.coverage_30d ?? {});
  const latestSnapshot = opsHealth?.latest_snapshot
    ? new Date(opsHealth.latest_snapshot).toLocaleString(locale)
    : undefined;

  return (
    <div className="space-y-8 max-w-[1600px] mx-auto">
      <RegistryPanel />

      <Card title={t("operations.systemHealth.title")} variant="elevated">
        <div className="grid gap-6 sm:grid-cols-2">
          <div className="rounded-lg border border-border/60 bg-background-elevated p-5 shadow-sm hover:shadow-md transition-all">
            <p className="text-sm uppercase tracking-wider text-foreground/70 font-semibold mb-3">{t("operations.systemHealth.status")}</p>
            <p className="text-2xl font-bold mb-3">{translatedStatus}</p>
            {health?.missing && health.missing.length > 0 && (
              <p className="mt-2 text-sm text-warning">
                {t("operations.systemHealth.missing")}: {health.missing.join(", ")}
              </p>
            )}
            {latestSnapshot && (
              <p className="mt-2 text-sm text-foreground/60">
                {t("operations.systemHealth.latestSnapshot", { defaultValue: "Latest snapshot" })}: {latestSnapshot}
              </p>
            )}
            {opsHealth && (
              <p className="text-sm text-foreground/60">
                {t("operations.systemHealth.revisionFlag", { defaultValue: "Revision flag" })}: {opsHealth.revision_flag ? t("common.yes", { defaultValue: "yes" }) : t("common.no", { defaultValue: "no" })}
              </p>
            )}
          </div>
          <div className="rounded-lg border border-border/60 bg-background-elevated p-5 shadow-sm hover:shadow-md transition-all">
            <p className="text-sm uppercase tracking-wider text-foreground/70 font-semibold mb-3">{t("operations.systemHealth.apiBaseUrl")}</p>
            <p className="text-lg font-bold mb-2 text-accent break-all">{appConfig.apiBaseUrl}</p>
            <p className="text-sm text-foreground/70 font-medium">
              {t("operations.systemHealth.refresh", { seconds: appConfig.refreshSeconds })}
            </p>
          </div>
        </div>
        {opsHealth && (
          <div className="mt-6 grid gap-5 md:grid-cols-3">
            <div className="rounded-lg border border-border/60 bg-background-elevated p-5 shadow-sm hover:shadow-md transition-all">
              <p className="text-sm uppercase tracking-wider text-foreground/70 font-semibold mb-4">{t("operations.systemHealth.componentsHeading", { defaultValue: "Components" })}</p>
              <ul className="space-y-2.5 text-sm text-foreground/80 font-medium">
                {componentsPresent.length > 0
                  ? componentsPresent.map(([key, value]) => (
                      <li key={key}>
                        {key}: {value.present}/{value.expected}
                      </li>
                    ))
                  : (
                      <li>{t("operations.systemHealth.noComponents", { defaultValue: "No component data." })}</li>
                    )}
              </ul>
            </div>
            <div className="rounded-lg border border-border/60 bg-background-elevated p-5 shadow-sm hover:shadow-md transition-all">
              <p className="text-sm uppercase tracking-wider text-foreground/70 font-semibold mb-4">{t("operations.systemHealth.coverageHeading", { defaultValue: "30d coverage" })}</p>
              <ul className="space-y-2.5 text-sm text-foreground/80 font-medium">
                {coverageEntries.length > 0
                  ? coverageEntries.map(([key, value]) => (
                      <li key={key}>
                        {key}: {value != null ? `${(value * 100).toFixed(0)}%` : "—"}
                      </li>
                    ))
                  : (
                      <li>{t("operations.systemHealth.noCoverage", { defaultValue: "No coverage window." })}</li>
                    )}
              </ul>
            </div>
            <div className="rounded-lg border border-border/60 bg-background-elevated p-5 shadow-sm hover:shadow-md transition-all">
              <p className="text-sm uppercase tracking-wider text-foreground/70 font-semibold mb-4">{t("operations.seaState.title", { defaultValue: "Sea State Conditions" })}</p>
              <div className="space-y-3">
                {malaccaSIS?.latest && (
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-foreground/80 font-medium">Malacca Strait</span>
                    <SISBadge
                      sis={malaccaSIS.latest.sis_mean}
                      waveHeight={malaccaSIS.latest.we_p90_m}
                      corridor="Malacca"
                    />
                  </div>
                )}
                {singaporeSIS?.latest && (
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-foreground/80 font-medium">Singapore Strait</span>
                    <SISBadge
                      sis={singaporeSIS.latest.sis_mean}
                      waveHeight={singaporeSIS.latest.we_p90_m}
                      corridor="Singapore"
                    />
                  </div>
                )}
                {suezSIS?.latest && (
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-foreground/80 font-medium">Suez Canal</span>
                    <SISBadge
                      sis={suezSIS.latest.sis_mean}
                      waveHeight={suezSIS.latest.we_p90_m}
                      corridor="Suez"
                    />
                  </div>
                )}
                {!malaccaSIS?.latest && !singaporeSIS?.latest && !suezSIS?.latest && (
                  <p className="text-sm text-foreground/60">{t("operations.seaState.noData", { defaultValue: "No sea state data available." })}</p>
                )}
              </div>
            </div>
          </div>
        )}
      </Card>

      <Card title={t("operations.runMeta.title")} subtitle={t("operations.runMeta.subtitle")} variant="elevated">
        {runMetaLoading && <Skeleton className="h-40 w-full" />}
        {!runMetaLoading && !runMeta && (
          <div className="flex items-center gap-3 text-sm text-warning bg-warning/10 border border-warning/30 rounded-lg p-4">
            <WarningIcon className="h-5 w-5" />
            <span className="font-medium">{t("operations.runMeta.empty")}</span>
          </div>
        )}
        {runMeta && (
          <div className="overflow-x-auto rounded-lg border border-border/60 shadow-sm">
            <table className="min-w-full divide-y divide-border/40 text-sm">
              <thead className="bg-background-secondary text-foreground/80">
                <tr>
                  <th className="px-4 py-3.5 text-left font-bold uppercase tracking-wider text-xs">{t("operations.runMeta.columns.step")}</th>
                  <th className="px-4 py-3.5 text-left font-bold uppercase tracking-wider text-xs">{t("operations.runMeta.columns.timestamp")}</th>
                  <th className="px-4 py-3.5 text-left font-bold uppercase tracking-wider text-xs">{t("operations.runMeta.columns.git")}</th>
                  <th className="px-4 py-3.5 text-left font-bold uppercase tracking-wider text-xs">{t("operations.runMeta.columns.hash")}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/30 bg-background-elevated">
                {Object.entries(runMeta).map(([step, payload]) => (
                  <tr key={step} className="hover:bg-background-secondary/50 transition-colors">
                    <td className="px-4 py-3.5 font-bold text-foreground">{step}</td>
                    <td className="px-4 py-3.5 text-foreground/80 font-medium">{formatTimestamp(payload.ts as string | undefined)}</td>
                    <td className="px-4 py-3.5">
                      <code className="rounded-md bg-accent/10 border border-accent/20 px-3 py-1.5 text-xs font-mono text-accent">{(payload.git as string | undefined) ?? "—"}</code>
                    </td>
                    <td className="px-4 py-3.5 font-mono text-foreground/70">{payload.data_hash ? (payload.data_hash as number) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card title={t("operations.metrics.title")} subtitle={appConfig.enableMetrics ? t("operations.metrics.subtitle") : t("operations.metrics.disabled")} variant="elevated">
        {!appConfig.enableMetrics ? (
          <p className="text-sm text-foreground/70 font-medium">{t("operations.metrics.disabled")}</p>
        ) : metricsLoading ? (
          <Skeleton className="h-40 w-full" />
        ) : metricsError ? (
          <div className="flex items-center gap-3 text-sm text-warning bg-warning/10 border border-warning/30 rounded-lg p-4">
            <WarningIcon className="h-5 w-5" />
            <span className="font-medium">{t("operations.metrics.error")}</span>
          </div>
        ) : (
          <pre className="max-h-80 overflow-auto whitespace-pre-wrap rounded-lg border border-border/60 bg-background-secondary/50 p-5 text-xs leading-relaxed font-mono shadow-inner">
            {metrics}
          </pre>
        )}
      </Card>
    </div>
  );
};
