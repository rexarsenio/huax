import { Card } from "./Card";
import { Skeleton } from "./Skeleton";
import { useIndexMeta } from "../hooks/useApi";
import { useTranslation } from "react-i18next";

export const MetaHero = () => {
  const { data, isLoading, isError } = useIndexMeta();
  const { t } = useTranslation();

  if (isLoading) {
    return <Skeleton className="h-32 w-full" />;
  }

  if (isError || !data) {
    return (
      <Card title={t("dashboard.meta.title") ?? "SPVX-Lite"}>
        <p className="text-sm text-foreground/60">{t("dashboard.meta.error")}</p>
      </Card>
    );
  }

  const { index, coverage, methodology } = data;
  const tagline = index.tagline_key
    ? t(index.tagline_key, { defaultValue: index.tagline_default ?? "" })
    : index.tagline_default ?? index.name;
  const description = index.description_key
    ? t(index.description_key, { defaultValue: index.description_default ?? "" })
    : index.description_default ?? "";
  const ruleOfThumb = index.rule_of_thumb_key
    ? t(index.rule_of_thumb_key, { defaultValue: index.rule_of_thumb_default ?? "" })
    : index.rule_of_thumb_default ?? "";
  const materialMoveLabel = t("dashboard.meta.materialMoveLabel", {
    points: index.material_move_points,
    defaultValue: ruleOfThumb,
  });

  return (
    <Card
      title={`${index.name} · v${index.version}`}
      subtitle={`${index.fix_time_utc} UTC`}>
      <div className="space-y-4">
        <div>
          <p className="text-lg font-semibold text-foreground">{tagline}</p>
          <p className="text-sm text-foreground/60 mt-1">{description}</p>
        </div>
        <div className="grid gap-6 md:grid-cols-2">
          <div className="space-y-2">
            <p className="text-xs uppercase tracking-wide text-foreground/60">{t("dashboard.meta.ruleOfThumb")}</p>
            <p className="text-sm text-foreground/80">{ruleOfThumb}</p>
            <ul className="mt-2 space-y-1 text-sm text-foreground/70">
              {index.bands.map((band, idx) => (
                <li key={band.label_key ?? String(idx)}>
                  <span className="font-medium">
                    {band.label_key ? t(band.label_key, { defaultValue: band.label_default ?? "" }) : band.label_default ?? ""}
                  </span>
                  : {band.range_key ? t(band.range_key, { defaultValue: band.range_default ?? "" }) : band.range_default ?? ""}
                </li>
              ))}
            </ul>
            <p className="text-xs text-foreground/50 mt-2">{materialMoveLabel}</p>
          </div>
          <div className="space-y-2">
            <p className="text-xs uppercase tracking-wide text-foreground/60">{t("dashboard.meta.coverage")}</p>
            <ul className="space-y-1 text-sm text-foreground/70">
              {coverage.map((item) => (
                <li key={item.id}>
                  <span className="font-medium">
                    {item.label_key ? t(item.label_key, { defaultValue: item.label_default ?? item.id }) : item.label_default ?? item.id}
                  </span>
                  : {item.description_key ? t(item.description_key, { defaultValue: item.description_default ?? "" }) : item.description_default ?? ""}
                  {item.cadence_key
                    ? ` (${t(item.cadence_key, { defaultValue: item.cadence_default ?? "" })})`
                    : item.cadence_default
                    ? ` (${item.cadence_default})`
                    : null}
                </li>
              ))}
            </ul>
          </div>
        </div>
        <details className="rounded-xl border border-foreground/10 bg-foreground/5 px-4 py-3 text-sm text-foreground/80">
          <summary className="cursor-pointer text-foreground font-medium">
            {t("dashboard.meta.methodologyLink")}
          </summary>
          <div className="mt-3 space-y-3">
            <p>
              {methodology.summary_key
                ? t(methodology.summary_key, { defaultValue: methodology.summary_default ?? "" })
                : methodology.summary_default ?? ""}
            </p>
            <p>
              {methodology.interpretation_key
                ? t(methodology.interpretation_key, { defaultValue: methodology.interpretation_default ?? "" })
                : methodology.interpretation_default ?? ""}
            </p>
            <div>
              <p className="text-xs uppercase tracking-wide text-foreground/60 mb-2">{t("dashboard.meta.tableTitle")}</p>
              <div className="overflow-x-auto rounded-lg border border-foreground/10">
                <table className="min-w-full divide-y divide-foreground/10 text-xs">
                  <thead className="bg-foreground/5 text-foreground/60">
                    <tr>
                      <th className="px-3 py-2 text-left font-medium">{t("dashboard.meta.component")}</th>
                      <th className="px-3 py-2 text-left font-medium">{t("dashboard.meta.geofence")}</th>
                      <th className="px-3 py-2 text-left font-medium">{t("dashboard.meta.cadence")}</th>
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
              <p className="text-xs uppercase tracking-wide text-foreground/60 mb-1">{t("dashboard.meta.transparency")}</p>
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
