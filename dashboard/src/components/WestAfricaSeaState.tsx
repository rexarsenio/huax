import { Card } from "./Card";
import { Skeleton } from "./Skeleton";
import { useSeaStateSummary } from "../hooks/useApi";

const formatNumber = (value: number | null | undefined, fractionDigits = 2) => {
  if (value === null || value === undefined) {
    return "—";
  }
  return value.toFixed(fractionDigits);
};

const formatTimestamp = (iso: string | null | undefined) => {
  if (!iso) {
    return "—";
  }
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) {
    return "—";
  }
  return parsed.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZoneName: "short",
  });
};

type WestAfricaSeaStateProps = {
  className?: string;
};

export const WestAfricaSeaState = ({ className }: WestAfricaSeaStateProps) => {
  const { data, isLoading, isError } = useSeaStateSummary("h24", "west_africa");
  const regions = data?.regions ?? [];
  const hasCoverage = regions.some((region) => region.samples > 0);

  return (
    <Card
      className={className}
      title="West Africa Sea State"
      subtitle="Bonny, Escravos, and Gulf of Guinea overnight conditions"
    >
      {isLoading ? (
        <Skeleton className="h-40 w-full" />
      ) : isError ? (
        <p className="text-sm text-warning">
          Unable to load West Africa sea state coverage. Check the API service and try again.
        </p>
      ) : regions.length === 0 ? (
        <p className="text-sm text-foreground/60">No sea state coverage available for this window.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[540px] table-fixed border-collapse text-sm">
            <thead>
              <tr className="text-foreground/70">
                <th className="pb-2 text-left font-medium">Region</th>
                <th className="pb-2 text-right font-medium">Tracklets (24h)</th>
                <th className="pb-2 text-right font-medium">Wave ⌀ (m)</th>
                <th className="pb-2 text-right font-medium">Wave p90 (m)</th>
                <th className="pb-2 text-right font-medium">Head current p90 (kn)</th>
                <th className="pb-2 text-right font-medium">Head wind p90 (m/s)</th>
                <th className="pb-2 text-right font-medium">Last sample</th>
              </tr>
            </thead>
            <tbody>
              {regions.map((region) => (
                <tr key={region.id} className="border-t border-border/40">
                  <td className="py-2 pr-4">
                    <div className="flex flex-col">
                      <span className="font-medium text-foreground">{region.label}</span>
                      <span className="text-xs uppercase tracking-wide text-foreground/50">{region.id}</span>
                    </div>
                  </td>
                  <td className="py-2 text-right tabular-nums text-foreground/80">
                    {formatNumber(region.flux_h, 0)}
                  </td>
                  <td className="py-2 text-right tabular-nums text-foreground/80">{formatNumber(region.hs_mean)}</td>
                  <td className="py-2 text-right tabular-nums text-foreground/80">{formatNumber(region.hs_p90)}</td>
                  <td className="py-2 text-right tabular-nums text-foreground/80">
                    {formatNumber(region.head_current_kn_p90)}
                  </td>
                  <td className="py-2 text-right tabular-nums text-foreground/80">
                    {formatNumber(region.head_wind_ms_p90)}
                  </td>
                  <td className="py-2 text-right text-foreground/60">{formatTimestamp(region.last_sample)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {!hasCoverage && !isLoading && !isError && (
        <p className="mt-3 text-xs text-foreground/50">
          Coverage is still building for the Gulf of Guinea terminals. Restart the overnight consumer to gather
          additional wave and current samples.
        </p>
      )}
    </Card>
  );
};
