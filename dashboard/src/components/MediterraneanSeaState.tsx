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

type MediterraneanSeaStateProps = {
  className?: string;
};

export const MediterraneanSeaState = ({ className }: MediterraneanSeaStateProps) => {
  const { data, isLoading, isError } = useSeaStateSummary("h24", "mediterranean");
  const regions = data?.regions ?? [];
  const hasCoverage = regions.some((region) => region.samples > 0);

  return (
    <Card
      className={className}
      title="Mediterranean Sea State"
      subtitle="Wave, current, and wind conditions from overnight tracklets"
    >
      {isLoading ? (
        <Skeleton className="h-40 w-full" />
      ) : isError ? (
        <p className="text-sm text-warning">
          Unable to load sea state coverage. Check the API service and try again.
        </p>
      ) : regions.length === 0 ? (
        <p className="text-sm text-foreground/60">No sea state coverage available for this window.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[520px] table-fixed border-collapse text-sm">
            <thead>
              <tr className="text-foreground/70">
                <th className="pb-2 text-left font-medium">Region</th>
                <th className="pb-2 text-right font-medium">Samples</th>
                <th className="pb-2 text-right font-medium">Wave ⌀ (m)</th>
                <th className="pb-2 text-right font-medium">Wave p90 (m)</th>
                <th className="pb-2 text-right font-medium">Head current ⌀ (kn)</th>
                <th className="pb-2 text-right font-medium">Head wind ⌀ (m/s)</th>
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
                  <td className="py-2 text-right tabular-nums text-foreground/80">{region.samples.toLocaleString()}</td>
                  <td className="py-2 text-right tabular-nums text-foreground/80">{formatNumber(region.hs_mean)}</td>
                  <td className="py-2 text-right tabular-nums text-foreground/80">{formatNumber(region.hs_p90)}</td>
                  <td className="py-2 text-right tabular-nums text-foreground/80">
                    {formatNumber(region.head_current_kn_mean)}
                  </td>
                  <td className="py-2 text-right tabular-nums text-foreground/80">
                    {formatNumber(region.head_wind_ms_mean)}
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
          Coverage is still building for the Mediterranean gates. Restart the overnight consumer to gather additional
          wave and current samples.
        </p>
      )}
    </Card>
  );
};

