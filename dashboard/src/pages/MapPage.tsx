import { useMemo } from "react";
import { Card } from "../components/Card";
import { VesselMap } from "../components/VesselMap";
import { SISBadge } from "../components/SISBadge";
import { useSeaStateSummary, useSignalsSnapshot } from "../hooks/useApi";
import { useSISData } from "../hooks/useSISData";
import { useTranslation } from "react-i18next";
import huaxLogo from "../assets/landing/huaxlogo.png";
import { MediterraneanSeaState } from "../components/MediterraneanSeaState";
import { WestAfricaSeaState } from "../components/WestAfricaSeaState";

export const MapPage = () => {
  const { t } = useTranslation();
  const { data: signals } = useSignalsSnapshot();
  const { data: mediterraneanSummary } = useSeaStateSummary("h24", "mediterranean");
  const { data: westAfricaSummary } = useSeaStateSummary("h24", "west_africa");

  // Fetch SIS data for key chokepoints
  const { data: malaccaSIS } = useSISData("CHOKEPOINT_MALACCA->UNK");
  const { data: singaporeSIS } = useSISData("CHOKEPOINT_SINGAPORE_STRAIT->UNK");
  const { data: suezSIS } = useSISData("CHOKEPOINT_SUEZ_NORTH->UNK");
  const { data: gibraltarSIS } = useSISData("CHOKEPOINT_GIBRALTAR->UNK");
  const { data: bosporusSIS } = useSISData("CHOKEPOINT_BOSPORUS->UNK");
  const { data: hormuzSIS } = useSISData("CHOKEPOINT_HORMUZ->UNK");
  const { data: babElMandebSIS } = useSISData("CHOKEPOINT_BAB_EL_MANDEB->UNK");

  const seaStateByRegion = useMemo(() => {
    const map: Record<string, { hsZ?: number; oppCurrent?: number; asOf?: string }> = {};

    const raw = signals?.spread?.drivers?.sea_state;
    if (raw && typeof raw === "object") {
      const obj = raw as Record<string, unknown>;
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

      const hsZ = parseNumeric(obj["hs_z"]);
      const asOfRaw = obj["as_of"];
      const asOf = typeof asOfRaw === "string" && asOfRaw.trim() ? asOfRaw : undefined;
      if (hsZ !== undefined && asOf) {
        map.default = {
          hsZ,
          oppCurrent: parseNumeric(obj["opp_current"]),
          asOf,
        };
      }
    }

    const assignRegion = (regionId: string, label: string, snapshot: { hsZ?: number; oppCurrent?: number; asOf?: string }) => {
      const aliases = [regionId, label];
      switch (regionId) {
        case "CHOKEPOINT_GIBRALTAR":
          aliases.push("strait-of-gibraltar", "Strait of Gibraltar");
          break;
        case "CHOKEPOINT_BOSPORUS":
          aliases.push("bosporus", "Bosporus Strait");
          break;
        case "CHOKEPOINT_DARDANELLES":
          aliases.push("dardanelles", "Dardanelles Strait");
          break;
        case "CHOKEPOINT_SICILY":
          aliases.push("strait-of-sicily");
          break;
        case "CHOKEPOINT_OTRANTO":
          aliases.push("strait-of-otranto");
          break;
      case "LANE_CANARY":
        aliases.push("LANE_CANARY_E_v1", "LANE_CANARY_W_v1");
        break;
      case "US_GULF":
        aliases.push("us-gulf", "US Gulf", "Houston Ship Channel");
        break;
        case "WEST_AFRICA_BONNY":
          aliases.push("WEST_AFRICA_BONNY", "Bonny Terminal", "west-africa-bonny");
          break;
        case "WEST_AFRICA_ESCRAVOS":
          aliases.push("WEST_AFRICA_ESCRAVOS", "Escravos Offshore", "west-africa-escravos");
          break;
        case "WEST_AFRICA_GULF":
          aliases.push("WEST_AFRICA_GULF", "Gulf of Guinea Offshore", "west-africa-gulf");
          break;
        default:
          break;
      }

      aliases.forEach((key) => {
        map[key] = snapshot;
      });
    };

    const ingestSummary = (summary?: { regions?: { id: string; label: string; hs_p90?: number | null; we_p90?: number | null; head_current_kn_p90?: number | null; last_sample?: string | null }[] }) => {
      summary?.regions?.forEach((region) => {
        const hsValue = region.hs_p90 ?? region.we_p90 ?? undefined;
        const snapshot = {
          hsZ: typeof hsValue === "number" ? hsValue : undefined,
          oppCurrent: region.head_current_kn_p90 ?? undefined,
          asOf: region.last_sample ?? undefined,
        };
        assignRegion(region.id, region.label, snapshot);
      });
    };

    ingestSummary(mediterraneanSummary);
    ingestSummary(westAfricaSummary);

    return Object.keys(map).length > 0 ? map : undefined;
  }, [signals, mediterraneanSummary, westAfricaSummary]);

  // Build SIS data map for the VesselMap
  const sisDataMap = useMemo(() => {
    const map: Record<string, { sis_mean: number; sis_p90: number; we_p90_m: number; corridor_id: string }> = {};

    if (malaccaSIS?.latest) {
      map["strait-of-malacca"] = {
        sis_mean: malaccaSIS.latest.sis_mean,
        sis_p90: malaccaSIS.latest.sis_p90,
        we_p90_m: malaccaSIS.latest.we_p90_m,
        corridor_id: malaccaSIS.corridor,
      };
      map["Strait of Malacca"] = map["strait-of-malacca"];
    }

    if (singaporeSIS?.latest) {
      map["singapore-strait"] = {
        sis_mean: singaporeSIS.latest.sis_mean,
        sis_p90: singaporeSIS.latest.sis_p90,
        we_p90_m: singaporeSIS.latest.we_p90_m,
        corridor_id: singaporeSIS.corridor,
      };
    }

    if (suezSIS?.latest) {
      map["suez-canal"] = {
        sis_mean: suezSIS.latest.sis_mean,
        sis_p90: suezSIS.latest.sis_p90,
        we_p90_m: suezSIS.latest.we_p90_m,
        corridor_id: suezSIS.corridor,
      };
      map["Suez Canal"] = map["suez-canal"];
    }

    if (gibraltarSIS?.latest) {
      map["strait-of-gibraltar"] = {
        sis_mean: gibraltarSIS.latest.sis_mean,
        sis_p90: gibraltarSIS.latest.sis_p90,
        we_p90_m: gibraltarSIS.latest.we_p90_m,
        corridor_id: gibraltarSIS.corridor,
      };
      map["Strait of Gibraltar"] = map["strait-of-gibraltar"];
    }

    if (bosporusSIS?.latest) {
      map["bosporus"] = {
        sis_mean: bosporusSIS.latest.sis_mean,
        sis_p90: bosporusSIS.latest.sis_p90,
        we_p90_m: bosporusSIS.latest.we_p90_m,
        corridor_id: bosporusSIS.corridor,
      };
      map["Bosporus"] = map["bosporus"];
    }

    if (hormuzSIS?.latest) {
      map["strait-of-hormuz"] = {
        sis_mean: hormuzSIS.latest.sis_mean,
        sis_p90: hormuzSIS.latest.sis_p90,
        we_p90_m: hormuzSIS.latest.we_p90_m,
        corridor_id: hormuzSIS.corridor,
      };
      map["Strait of Hormuz"] = map["strait-of-hormuz"];
    }

    if (babElMandebSIS?.latest) {
      map["bab-el-mandeb"] = {
        sis_mean: babElMandebSIS.latest.sis_mean,
        sis_p90: babElMandebSIS.latest.sis_p90,
        we_p90_m: babElMandebSIS.latest.we_p90_m,
        corridor_id: babElMandebSIS.corridor,
      };
      map["Bab el-Mandeb"] = map["bab-el-mandeb"];
    }

    return Object.keys(map).length > 0 ? map : undefined;
  }, [malaccaSIS, singaporeSIS, suezSIS, gibraltarSIS, bosporusSIS, hormuzSIS, babElMandebSIS]);

  return (
    <div className="space-y-6">
      <div className="flex items-center">
        <img
          src={huaxLogo}
          alt={t("map.logoAlt", { defaultValue: "Huax logo" })}
          className="h-10 w-auto opacity-80"
        />
      </div>
      <Card
        title={t("map.card.title", { defaultValue: "Global Vessel Map" })}
        subtitle={t("map.card.subtitle", {
          defaultValue: "Critical chokepoints and stress zones",
        })}
      >
        <VesselMap
          className="h-[600px] rounded-lg overflow-hidden"
          seaStateByRegion={seaStateByRegion}
          sisDataMap={sisDataMap}
        />
      </Card>

      <div className="grid gap-6 md:grid-cols-3">
        <MediterraneanSeaState className="md:col-span-3" />
        <WestAfricaSeaState className="md:col-span-3" />
        <Card
          title={t("map.stats.singapore.title", { defaultValue: "Singapore/Malacca" })}
          subtitle="CQ_SG"
        >
          <div className="space-y-3">
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
            {malaccaSIS?.latest && (
              <div className="pt-2 border-t border-border/50">
                <SISBadge
                  sis={malaccaSIS.latest.sis_mean}
                  waveHeight={malaccaSIS.latest.we_p90_m}
                  currentSpeed={malaccaSIS.latest.hc_p90_kn}
                  windSpeed={malaccaSIS.latest.hw_p90_ms * 1.94384}
                  corridor="Malacca"
                  showDetails
                />
              </div>
            )}
          </div>
        </Card>

        <Card
          title={t("map.stats.turkish.title", { defaultValue: "Suez Canal" })}
          subtitle="CQ_SUEZ"
        >
          <div className="space-y-3">
            <p className="text-sm text-foreground/70">
              {t("map.stats.turkish.description", {
                defaultValue: "Critical Europe-Asia maritime route",
              })}
            </p>
            <div className="flex items-baseline gap-2">
              <span className="text-2xl font-semibold text-foreground">~12%</span>
              <span className="text-sm text-foreground/60">
                {t("map.stats.turkish.throughput", { defaultValue: "global trade" })}
              </span>
            </div>
            {suezSIS?.latest && (
              <div className="pt-2 border-t border-border/50">
                <SISBadge
                  sis={suezSIS.latest.sis_mean}
                  waveHeight={suezSIS.latest.we_p90_m}
                  currentSpeed={suezSIS.latest.hc_p90_kn}
                  windSpeed={suezSIS.latest.hw_p90_ms * 1.94384}
                  corridor="Suez"
                  showDetails
                />
              </div>
            )}
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

      <div className="grid gap-6 md:grid-cols-2 mt-6">
        <Card
          title={t("map.stats.gibraltar.title", { defaultValue: "Strait of Gibraltar" })}
          subtitle="CQ_GIBRALTAR"
        >
          <div className="space-y-3">
            <p className="text-sm text-foreground/70">
              {t("map.stats.gibraltar.description", {
                defaultValue: "Gateway between Atlantic and Mediterranean",
              })}
            </p>
            <div className="flex items-baseline gap-2">
              <span className="text-2xl font-semibold text-foreground">~10%</span>
              <span className="text-sm text-foreground/60">
                {t("map.stats.gibraltar.throughput", { defaultValue: "European oil imports" })}
              </span>
            </div>
            {gibraltarSIS?.latest && (
              <div className="pt-2 border-t border-border/50">
                <SISBadge
                  sis={gibraltarSIS.latest.sis_mean}
                  waveHeight={gibraltarSIS.latest.we_p90_m}
                  currentSpeed={gibraltarSIS.latest.hc_p90_kn}
                  windSpeed={gibraltarSIS.latest.hw_p90_ms * 1.94384}
                  corridor="Gibraltar"
                  showDetails
                />
              </div>
            )}
          </div>
        </Card>

        <Card
          title={t("map.stats.bosporus.title", { defaultValue: "Bosporus Strait" })}
          subtitle="CQ_BOSPORUS"
        >
          <div className="space-y-3">
            <p className="text-sm text-foreground/70">
              {t("map.stats.bosporus.description", {
                defaultValue: "Black Sea connection, critical for energy flows",
              })}
            </p>
            <div className="flex items-baseline gap-2">
              <span className="text-2xl font-semibold text-foreground">~3%</span>
              <span className="text-sm text-foreground/60">
                {t("map.stats.bosporus.throughput", { defaultValue: "global oil supply" })}
              </span>
            </div>
            {bosporusSIS?.latest && (
              <div className="pt-2 border-t border-border/50">
                <SISBadge
                  sis={bosporusSIS.latest.sis_mean}
                  waveHeight={bosporusSIS.latest.we_p90_m}
                  currentSpeed={bosporusSIS.latest.hc_p90_kn}
                  windSpeed={bosporusSIS.latest.hw_p90_ms * 1.94384}
                  corridor="Bosporus"
                  showDetails
                />
              </div>
            )}
          </div>
        </Card>
      </div>
    </div>
  );
};
