import { ResponsiveContainer, AreaChart, Area, Tooltip, XAxis, YAxis, CartesianGrid, ReferenceLine } from "recharts";
import { useTranslation } from "react-i18next";
import { useMemo } from "react";
import type { RelativeStressPayload } from "../api/types";

type SeriesPoint = {
  d: string;
  value: number;
  seasonalMean?: number | null;
  seasonalStd?: number | null;
  seasonalLower?: number | null;
  seasonalUpper?: number | null;
  seasonalLowerExtreme?: number | null;
  seasonalUpperExtreme?: number | null;
  calmBase?: number;
  calmRange?: number;
  normalBase?: number;
  normalRange?: number;
  elevatedBase?: number;
  elevatedRange?: number;
};

type Props = {
  data: SeriesPoint[];
  label?: string;
  relativeStress?: RelativeStressPayload;
};

export const TimeSeriesChart = ({ data, label, relativeStress }: Props) => {
  const { t, i18n } = useTranslation();
  const locale = i18n.language;
  const seriesLabel = label ?? t("dashboard.latestIndex.label");

  const seasonalMeanRaw = relativeStress?.latest?.seasonal_mean ?? null;
  const seasonalStdRaw = relativeStress?.latest?.seasonal_std ?? null;
  const hasSeasonalData =
    seasonalMeanRaw != null &&
    Number.isFinite(seasonalMeanRaw) &&
    seasonalStdRaw != null &&
    Number.isFinite(seasonalStdRaw) &&
    seasonalStdRaw > 0;

  const { enrichedData, seasonalMean, seasonalStd } = useMemo(() => {
    if (!hasSeasonalData) {
      return { enrichedData: data, seasonalMean: null, seasonalStd: null };
    }

    const mean = seasonalMeanRaw as number;
    const std = seasonalStdRaw as number;
    const normalLower = Math.max(0, mean - std);
    const normalUpper = mean + std;
    const calmLower = Math.max(0, mean - 2 * std);
    const elevatedUpper = mean + 2 * std;

    const result = data.map((point) => ({
      ...point,
      seasonalMean: mean,
      seasonalStd: std,
      seasonalLower: normalLower,
      seasonalUpper: normalUpper,
      seasonalLowerExtreme: calmLower,
      seasonalUpperExtreme: elevatedUpper,
      calmBase: calmLower,
      calmRange: Math.max(0, normalLower - calmLower),
      normalBase: normalLower,
      normalRange: Math.max(0, normalUpper - normalLower),
      elevatedBase: normalUpper,
      elevatedRange: Math.max(0, elevatedUpper - normalUpper),
    }));

    return { enrichedData: result, seasonalMean: mean, seasonalStd: std };
  }, [data, hasSeasonalData, seasonalMeanRaw, seasonalStdRaw]);

  const currentValue = data[data.length - 1]?.value;
  const valueColor = useMemo(() => {
    if (!hasSeasonalData || !Number.isFinite(currentValue) || seasonalStd == null || seasonalStd === 0) {
      return "#38bdf8";
    }
    const zScore = ((currentValue ?? 0) - (seasonalMean ?? 0)) / seasonalStd;
    if (zScore > 2) return "#dc2626";
    if (zScore > 1) return "#f59e0b";
    if (zScore > -1) return "#10b981";
    if (zScore > -2) return "#3b82f6";
    return "#6366f1";
  }, [currentValue, hasSeasonalData, seasonalMean, seasonalStd]);

  return (
    <div className="h-72 w-full">
      <ResponsiveContainer>
        <AreaChart data={enrichedData}>
          <defs>
            <linearGradient id="colorIndex" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={valueColor} stopOpacity={0.8} />
              <stop offset="95%" stopColor={valueColor} stopOpacity={0.1} />
            </linearGradient>
            {hasSeasonalData && (
              <>
                <linearGradient id="normalRange" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#10b981" stopOpacity={0.18} />
                  <stop offset="100%" stopColor="#10b981" stopOpacity={0.05} />
                </linearGradient>
                <linearGradient id="elevatedRange" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#f59e0b" stopOpacity={0.15} />
                  <stop offset="100%" stopColor="#f59e0b" stopOpacity={0.06} />
                </linearGradient>
                <linearGradient id="calmRange" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#3b82f6" stopOpacity={0.15} />
                  <stop offset="100%" stopColor="#3b82f6" stopOpacity={0.06} />
                </linearGradient>
              </>
            )}
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(148, 163, 184, 0.25)" />
          <XAxis
            dataKey="d"
            tickFormatter={(value) => new Date(value).toLocaleDateString(locale, { month: "short", day: "numeric" })}
            minTickGap={32}
            stroke="rgba(248, 250, 252, 0.6)"
          />
          <YAxis
            allowDecimals={false}
            stroke="rgba(248, 250, 252, 0.6)"
            domain={["auto", "auto"]}
            tickFormatter={(value) => value.toFixed(0)}
          />
          <Tooltip
            cursor={{ stroke: `${valueColor}40`, strokeWidth: 2 }}
            contentStyle={{
              backgroundColor: "#020617",
              borderRadius: "0.75rem",
              border: "1px solid rgba(148,163,184,0.2)",
            }}
            labelFormatter={(value) => new Date(value).toLocaleDateString(locale)}
            formatter={(value: number, name: string) => {
              if (name === "value") return [`${value.toFixed(2)}`, seriesLabel];
              return null;
            }}
            content={({ active, payload }) => {
              if (!active || !payload || payload.length === 0) return null;
              const point = payload[0].payload as typeof enrichedData[number];
              const hasSeasonalPoint = "seasonalMean" in point;
              const seasonalValue = hasSeasonalPoint ? point.seasonalMean ?? null : null;
              const deviationPct =
                seasonalValue && seasonalValue !== 0
                  ? ((point.value - seasonalValue) / seasonalValue) * 100
                  : null;
              return (
                <div className="rounded-xl border border-foreground/20 bg-background/95 px-3 py-2 shadow-lg">
                  <p className="text-sm font-semibold text-foreground">
                    {new Date(point.d).toLocaleDateString(locale, {
                      month: "short",
                      day: "numeric",
                      year: "numeric",
                    })}
                  </p>
                  <p className="text-lg font-bold" style={{ color: valueColor }}>
                    {point.value.toFixed(2)}
                  </p>
                  {hasSeasonalData && hasSeasonalPoint && (
                    <div className="mt-2 space-y-1 text-xs text-foreground/70">
                      <p>Seasonal Normal: {point.seasonalMean != null ? point.seasonalMean.toFixed(1) : "—"}</p>
                      <p>
                        Deviation:{" "}
                        {deviationPct != null ? `${deviationPct >= 0 ? "+" : ""}${deviationPct.toFixed(1)}%` : "—"}
                      </p>
                    </div>
                  )}
                </div>
              );
            }}
          />

          {hasSeasonalData && (
            <>
              <Area
                type="monotone"
                dataKey="calmBase"
                stackId="calmBand"
                stroke="none"
                fillOpacity={0}
                isAnimationActive={false}
                activeDot={false}
              />
              <Area
                type="monotone"
                dataKey="calmRange"
                stackId="calmBand"
                stroke="none"
                fill="url(#calmRange)"
                fillOpacity={1}
                isAnimationActive={false}
                activeDot={false}
              />
              <Area
                type="monotone"
                dataKey="normalBase"
                stackId="normalBand"
                stroke="none"
                fillOpacity={0}
                isAnimationActive={false}
                activeDot={false}
              />
              <Area
                type="monotone"
                dataKey="normalRange"
                stackId="normalBand"
                stroke="none"
                fill="url(#normalRange)"
                fillOpacity={1}
                isAnimationActive={false}
                activeDot={false}
              />
              <Area
                type="monotone"
                dataKey="elevatedBase"
                stackId="elevatedBand"
                stroke="none"
                fillOpacity={0}
                isAnimationActive={false}
                activeDot={false}
              />
              <Area
                type="monotone"
                dataKey="elevatedRange"
                stackId="elevatedBand"
                stroke="none"
                fill="url(#elevatedRange)"
                fillOpacity={1}
                isAnimationActive={false}
                activeDot={false}
              />
              <ReferenceLine
                y={seasonalMean ?? undefined}
                stroke="#10b981"
                strokeDasharray="5 5"
                strokeWidth={2}
                label={{
                  value: "Seasonal Normal",
                  position: "insideTopRight",
                  fill: "#10b981",
                  fontSize: 12,
                  fontWeight: 600,
                }}
              />
              <ReferenceLine
                y={seasonalMean != null && seasonalStd != null ? seasonalMean + seasonalStd : undefined}
                stroke="#f59e0b"
                strokeDasharray="3 3"
                strokeWidth={1}
                strokeOpacity={0.5}
              />
              <ReferenceLine
                y={seasonalMean != null && seasonalStd != null ? Math.max(0, seasonalMean - seasonalStd) : undefined}
                stroke="#3b82f6"
                strokeDasharray="3 3"
                strokeWidth={1}
                strokeOpacity={0.5}
              />
              <ReferenceLine
                y={seasonalMean != null && seasonalStd != null ? seasonalMean + 2 * seasonalStd : undefined}
                stroke="#dc2626"
                strokeDasharray="2 4"
                strokeWidth={1}
                strokeOpacity={0.4}
              />
              <ReferenceLine
                y={seasonalMean != null && seasonalStd != null ? Math.max(0, seasonalMean - 2 * seasonalStd) : undefined}
                stroke="#6366f1"
                strokeDasharray="2 4"
                strokeWidth={1}
                strokeOpacity={0.4}
              />
            </>
          )}

          <Area
            type="monotone"
            dataKey="value"
            stroke={valueColor}
            strokeWidth={3}
            fillOpacity={1}
            fill="url(#colorIndex)"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
};
