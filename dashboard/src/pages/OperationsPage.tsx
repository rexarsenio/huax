import { Card } from "../components/Card";
import { Skeleton } from "../components/Skeleton";
import { useHealthStatus, useMetrics, useRunMeta, useOpsHealth } from "../hooks/useApi";
import { appConfig } from "../config";
import { WarningIcon } from "../components/icons";
import { useTranslation } from "react-i18next";

export const OperationsPage = () => {
  const { data: health } = useHealthStatus();
  const { data: opsHealth } = useOpsHealth();
  const { data: runMeta, isLoading: runMetaLoading } = useRunMeta();
  const { data: metrics, isLoading: metricsLoading, isError: metricsError } = useMetrics();
  const { t, i18n } = useTranslation();
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
    <div className="space-y-6">
      <Card title={t("operations.systemHealth.title")}>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="rounded-xl border border-foreground/10 bg-foreground/5 p-4">
            <p className="text-xs uppercase tracking-wide text-foreground/60">{t("operations.systemHealth.status")}</p>
            <p className="text-lg font-semibold">{translatedStatus}</p>
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
          <div className="rounded-xl border border-foreground/10 bg-foreground/5 p-4">
            <p className="text-xs uppercase tracking-wide text-foreground/60">{t("operations.systemHealth.apiBaseUrl")}</p>
            <p className="text-lg font-semibold">{appConfig.apiBaseUrl}</p>
            <p className="mt-2 text-sm text-foreground/60">
              {t("operations.systemHealth.refresh", { seconds: appConfig.refreshSeconds })}
            </p>
          </div>
        </div>
        {opsHealth && (
          <div className="mt-4 grid gap-4 md:grid-cols-3">
            <div className="rounded-xl border border-foreground/10 bg-foreground/5 p-4">
              <p className="text-xs uppercase tracking-wide text-foreground/60">{t("operations.systemHealth.componentsHeading", { defaultValue: "Components" })}</p>
              <ul className="mt-2 space-y-1 text-sm text-foreground/70">
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
            <div className="rounded-xl border border-foreground/10 bg-foreground/5 p-4">
              <p className="text-xs uppercase tracking-wide text-foreground/60">{t("operations.systemHealth.coverageHeading", { defaultValue: "30d coverage" })}</p>
              <ul className="mt-2 space-y-1 text-sm text-foreground/70">
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
            <div className="rounded-xl border border-foreground/10 bg-foreground/5 p-4">
              <p className="text-xs uppercase tracking-wide text-foreground/60">{t("dashboard.weather.flag", { defaultValue: "Weather flags" })}</p>
              <ul className="mt-2 space-y-1 text-sm text-foreground/70">
                {Object.entries(opsHealth.weather_flags ?? {}).length > 0
                  ? Object.entries(opsHealth.weather_flags ?? {}).map(([key, value]) => (
                      <li key={key}>
                        {key}: {value != null && Number(value) > 0 ? t("dashboard.weather.active", { defaultValue: "active" }) : t("dashboard.weather.clear", { defaultValue: "clear" })}
                      </li>
                    ))
                  : (
                      <li>{t("dashboard.weather.noData", { defaultValue: "No weather data." })}</li>
                    )}
              </ul>
            </div>
          </div>
        )}
      </Card>

      <Card title={t("operations.runMeta.title")} subtitle={t("operations.runMeta.subtitle")}>
        {runMetaLoading && <Skeleton className="h-40 w-full" />}
        {!runMetaLoading && !runMeta && (
          <div className="flex items-center gap-2 text-sm text-warning">
            <WarningIcon className="h-5 w-5" />
            {t("operations.runMeta.empty")}
          </div>
        )}
        {runMeta && (
          <div className="overflow-x-auto rounded-xl border border-foreground/10">
            <table className="min-w-full divide-y divide-foreground/10 text-sm">
              <thead className="bg-foreground/5 text-foreground/70">
                <tr>
                  <th className="px-3 py-2 text-left font-medium">{t("operations.runMeta.columns.step")}</th>
                  <th className="px-3 py-2 text-left font-medium">{t("operations.runMeta.columns.timestamp")}</th>
                  <th className="px-3 py-2 text-left font-medium">{t("operations.runMeta.columns.git")}</th>
                  <th className="px-3 py-2 text-left font-medium">{t("operations.runMeta.columns.hash")}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-foreground/10">
                {Object.entries(runMeta).map(([step, payload]) => (
                  <tr key={step}>
                    <td className="px-3 py-2 font-medium">{step}</td>
                    <td className="px-3 py-2">{formatTimestamp(payload.ts as string | undefined)}</td>
                    <td className="px-3 py-2">
                      <code className="rounded bg-foreground/10 px-2 py-1 text-xs">{(payload.git as string | undefined) ?? "—"}</code>
                    </td>
                    <td className="px-3 py-2">{payload.data_hash ? (payload.data_hash as number) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card title={t("operations.metrics.title")} subtitle={appConfig.enableMetrics ? t("operations.metrics.subtitle") : t("operations.metrics.disabled")}>
        {!appConfig.enableMetrics ? (
          <p className="text-sm text-foreground/60">{t("operations.metrics.disabled")}</p>
        ) : metricsLoading ? (
          <Skeleton className="h-40 w-full" />
        ) : metricsError ? (
          <div className="flex items-center gap-2 text-sm text-warning">
            <WarningIcon className="h-5 w-5" />
            {t("operations.metrics.error")}
          </div>
        ) : (
          <pre className="max-h-72 overflow-auto whitespace-pre-wrap rounded-xl border border-foreground/10 bg-foreground/5 p-4 text-xs leading-relaxed">
            {metrics}
          </pre>
        )}
      </Card>
    </div>
  );
};
