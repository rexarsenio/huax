import { clsx } from "clsx";

import type { RelativeStressClassification } from "../api/types";

type ComponentCardProps = {
  name: string;
  value: number | null;
  zScore?: number | null;
  trend?: number;
  weatherFlag?: number;
  observations?: number;
  seasonalMean?: number | null;
  deviationPct?: number | null;
  classification?: RelativeStressClassification | null;
};

const getStatusFromZScore = (z: number | null) => {
  if (z == null) return { label: "No Data", color: "foreground/30", emoji: "•" };

  if (z > 2) return { label: "Extreme", color: "#dc2626", emoji: "🔴" };
  if (z > 1) return { label: "Elevated", color: "#f59e0b", emoji: "🟡" };
  if (z > -1) return { label: "Normal", color: "#10b981", emoji: "🟢" };
  if (z > -2) return { label: "Below", color: "#3b82f6", emoji: "🔵" };
  return { label: "Very Low", color: "#6366f1", emoji: "🟣" };
};

export const ComponentCard = ({
  name,
  value,
  zScore,
  trend = 0,
  weatherFlag = 0,
  observations = 0,
  seasonalMean,
  deviationPct,
  classification,
}: ComponentCardProps) => {
  const fallbackStatus = getStatusFromZScore(zScore ?? null);
  const activeStatus = classification
    ? {
        label: classification.headline ?? classification.status.replace(/_/g, ' '),
        color: classification.color ?? fallbackStatus.color,
        emoji: classification.emoji ?? fallbackStatus.emoji,
      }
    : fallbackStatus;

  const trendIcon = trend > 0.01 ? "▲" : trend < -0.01 ? "▼" : "•";
  const hasWeather = weatherFlag > 0;

  const chipClass = clsx(
    "relative rounded-lg px-4 py-3.5 text-sm transition-all duration-200 border shadow-sm hover:shadow-md",
    hasWeather
      ? "border-warning/40 bg-warning-bg ring-1 ring-warning/20"
      : "border-border/60 bg-background-elevated hover:border-border hover:scale-[1.02]"
  );

  const statusColor = typeof activeStatus.color === 'string' ? activeStatus.color : undefined;

  return (
    <div className={chipClass}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-base" aria-hidden>
                {activeStatus.emoji}
              </span>
              <div>
                <p className="font-medium text-foreground text-sm">{name}</p>
                <p
                  className="text-xs font-medium uppercase tracking-wider mt-0.5"
                  style={{ color: statusColor }}
                >
                  {activeStatus.label}
                </p>
              </div>
            </div>
            {hasWeather && (
              <span
                className="text-warning text-sm"
                title="Weather flag active"
                aria-label="Weather flag"
              >
                ⚠
              </span>
            )}
          </div>

          <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
            <div className="flex justify-between">
              <span className="text-foreground/50">Z-Score:</span>
              <span className="font-medium text-foreground tabular-nums">
                {zScore != null ? `${zScore >= 0 ? '+' : ''}${zScore.toFixed(2)}σ` : 'n/a'}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-foreground/50">Value:</span>
              <span className="font-medium text-foreground tabular-nums">
                {value != null ? value.toFixed(2) : 'n/a'}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-foreground/50">Seasonal:</span>
              <span className="font-medium text-foreground tabular-nums">
                {seasonalMean != null ? seasonalMean.toFixed(2) : 'n/a'}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-foreground/50">Deviation:</span>
              <span className="font-medium text-foreground tabular-nums">
                {deviationPct != null ? `${deviationPct >= 0 ? '+' : ''}${deviationPct.toFixed(1)}%` : 'n/a'}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-foreground/50">Trend:</span>
              <span className="font-medium text-foreground">{trendIcon}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-foreground/50">Obs:</span>
              <span className="font-medium text-foreground tabular-nums">{observations}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
