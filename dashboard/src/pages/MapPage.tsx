import { Card } from "../components/Card";
import { VesselMap } from "../components/VesselMap";
import { useTranslation } from "react-i18next";

export const MapPage = () => {
  const { t } = useTranslation();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold mb-2">
          {t("map.title", { defaultValue: "Maritime Chokepoints & Vessel Traffic" })}
        </h1>
        <p className="text-foreground/70">
          {t("map.subtitle", {
            defaultValue:
              "Real-time visualization of critical maritime chokepoints affecting global oil flows",
          })}
        </p>
      </div>

      <Card
        title={t("map.card.title", { defaultValue: "Global Vessel Map" })}
        subtitle={t("map.card.subtitle", {
          defaultValue: "Critical chokepoints and stress zones",
        })}
      >
        <VesselMap className="h-[600px] rounded-lg overflow-hidden" />
      </Card>

      <div className="grid gap-6 md:grid-cols-3">
        <Card
          title={t("map.stats.singapore.title", { defaultValue: "Singapore/Malacca" })}
          subtitle="CQ_SG"
        >
          <div className="space-y-2">
            <p className="text-sm text-foreground/70">
              {t("map.stats.singapore.description", {
                defaultValue: "Critical chokepoint for APAC oil flows",
              })}
            </p>
            <div className="flex items-baseline gap-2">
              <span className="text-2xl font-semibold text-foreground">~25%</span>
              <span className="text-sm text-foreground/60">
                {t("map.stats.singapore.throughput", { defaultValue: "global maritime oil" })}
              </span>
            </div>
          </div>
        </Card>

        <Card
          title={t("map.stats.turkish.title", { defaultValue: "Turkish Straits" })}
          subtitle="CQ_TR"
        >
          <div className="space-y-2">
            <p className="text-sm text-foreground/70">
              {t("map.stats.turkish.description", {
                defaultValue: "Bosporus & Dardanelles monitoring",
              })}
            </p>
            <div className="flex items-baseline gap-2">
              <span className="text-2xl font-semibold text-foreground">~3%</span>
              <span className="text-sm text-foreground/60">
                {t("map.stats.turkish.throughput", { defaultValue: "global maritime oil" })}
              </span>
            </div>
          </div>
        </Card>

        <Card
          title={t("map.stats.hormuz.title", { defaultValue: "Strait of Hormuz" })}
          subtitle="Middle East"
        >
          <div className="space-y-2">
            <p className="text-sm text-foreground/70">
              {t("map.stats.hormuz.description", {
                defaultValue: "World's most important oil chokepoint",
              })}
            </p>
            <div className="flex items-baseline gap-2">
              <span className="text-2xl font-semibold text-foreground">~21%</span>
              <span className="text-sm text-foreground/60">
                {t("map.stats.hormuz.throughput", { defaultValue: "global petroleum" })}
              </span>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
};
