import { useMemo } from "react";
import type { RelativeStressPayload } from "../api/types";

type SeasonalGaugeProps = {
  current: number;
  relativeStress?: RelativeStressPayload;
  label?: string;
};

const STATUS_COLORS: Record<string, string> = {
  "EXTREMELY STRESSED": "#dc2626",
  "STRESSED": "#ea580c",
  "ELEVATED": "#f59e0b",
  "NORMAL": "#10b981",
  "BELOW NORMAL": "#06b6d4",
  "CALM": "#3b82f6",
  "UNUSUALLY CALM": "#6366f1",
  "QUIET": "#3b82f6",
};

export const SeasonalGauge = ({ current, relativeStress, label }: SeasonalGaugeProps) => {
  const stressLatest = relativeStress?.latest;
  const seasonalMean = stressLatest?.seasonal_mean ?? 100;
  const seasonalStd = stressLatest?.seasonal_std ?? 15;
  const zScore = stressLatest?.z_score ?? 0;
  const classification = stressLatest?.classification;
  const status = classification?.status ?? "NORMAL";

  // Define segments based on z-score ranges (±1σ standard for normal)
  const segments = useMemo(() => {
    const mean = seasonalMean;
    const std = seasonalStd;

    // Calculate min/max for gauge scale
    // Show range from -2.5σ to +2.5σ for better visualization
    const minValue = Math.max(0, mean - 2.5 * std);
    const maxValue = mean + 2.5 * std;

    return {
      minValue,
      maxValue,
      segments: [
        {
          min: minValue,
          max: Math.max(minValue, mean - 2 * std),
          color: "#6366f1",
          label: "Very Calm",
          zRange: "< -2σ",
        },
        {
          min: Math.max(minValue, mean - 2 * std),
          max: Math.max(minValue, mean - std),
          color: "#3b82f6",
          label: "Below Normal",
          zRange: "-2σ to -1σ",
        },
        {
          min: Math.max(minValue, mean - std),
          max: Math.min(maxValue, mean + std),
          color: "#10b981",
          label: "Normal",
          zRange: "±1σ",
        },
        {
          min: Math.min(maxValue, mean + std),
          max: Math.min(maxValue, mean + 2 * std),
          color: "#f59e0b",
          label: "Elevated",
          zRange: "+1σ to +2σ",
        },
        {
          min: Math.min(maxValue, mean + 2 * std),
          max: maxValue,
          color: "#dc2626",
          label: "Stressed",
          zRange: "> +2σ",
        },
      ],
    };
  }, [seasonalMean, seasonalStd]);

  const { minValue, maxValue } = segments;

  // Calculate gauge position (0-100%) based on the dynamic scale
  const currentPercent = Math.min(
    100,
    Math.max(0, ((current - minValue) / (maxValue - minValue)) * 100)
  );
  const meanPercent = ((seasonalMean - minValue) / (maxValue - minValue)) * 100;

  // SVG dimensions
  const size = 280;
  const strokeWidth = 40;
  const center = size / 2;
  const radius = (size - strokeWidth) / 2;

  // Arc angles (we'll use a 3/4 circle, from 135° to 45°)
  const startAngle = 135;
  const endAngle = 45;
  const totalAngle = 360 - startAngle + endAngle; // 270°

  const polarToCartesian = (angle: number, r: number) => {
    const rad = ((angle - 90) * Math.PI) / 180;
    return {
      x: center + r * Math.cos(rad),
      y: center + r * Math.sin(rad),
    };
  };

  const describeArc = (startAngle: number, endAngle: number, r: number) => {
    const start = polarToCartesian(startAngle, r);
    const end = polarToCartesian(endAngle, r);
    const largeArc = endAngle - startAngle <= 180 ? 0 : 1;
    return `M ${start.x} ${start.y} A ${r} ${r} 0 ${largeArc} 1 ${end.x} ${end.y}`;
  };

  // Calculate segment arcs
  const segmentArcs = segments.segments.map((segment) => {
    const segmentStartPercent = ((segment.min - minValue) / (maxValue - minValue)) * 100;
    const segmentEndPercent = ((segment.max - minValue) / (maxValue - minValue)) * 100;
    const segmentStartAngle = startAngle + (segmentStartPercent / 100) * totalAngle;
    const segmentEndAngle = startAngle + (segmentEndPercent / 100) * totalAngle;

    return {
      ...segment,
      path: describeArc(segmentStartAngle, segmentEndAngle, radius),
    };
  });

  // Needle position
  const needleAngle = startAngle + (currentPercent / 100) * totalAngle;
  const needleEnd = polarToCartesian(needleAngle, radius - strokeWidth / 2);

  // Mean marker position
  const meanAngle = startAngle + (meanPercent / 100) * totalAngle;
  const meanOuter = polarToCartesian(meanAngle, radius + strokeWidth / 2 + 5);
  const meanInner = polarToCartesian(meanAngle, radius - strokeWidth / 2 - 5);

  const statusColor = STATUS_COLORS[status] ?? "#64748b";

  return (
    <div className="flex flex-col items-center gap-4">
      <svg width={size} height={size} className="overflow-visible">
        {/* Background segments */}
        {segmentArcs.map((segment, idx) => (
          <path
            key={idx}
            d={segment.path}
            fill="none"
            stroke={segment.color}
            strokeWidth={strokeWidth}
            strokeOpacity={0.6}
            strokeLinecap="round"
          />
        ))}

        {/* Seasonal mean marker - Bold green line showing "Normal" center */}
        <line
          x1={meanInner.x}
          y1={meanInner.y}
          x2={meanOuter.x}
          y2={meanOuter.y}
          stroke="#10b981"
          strokeWidth="4"
          strokeLinecap="round"
          opacity={0.9}
        />

        {/* Current value needle */}
        <line
          x1={center}
          y1={center}
          x2={needleEnd.x}
          y2={needleEnd.y}
          stroke={statusColor}
          strokeWidth="4"
          strokeLinecap="round"
        />
        <circle cx={center} cy={center} r="8" fill={statusColor} />

        {/* Center text - Remove emoji, focus on data */}
        <text
          x={center}
          y={center + 40}
          textAnchor="middle"
          className="fill-foreground text-5xl font-bold"
        >
          {current.toFixed(1)}
        </text>
        <text
          x={center}
          y={center + 65}
          textAnchor="middle"
          className="fill-foreground/60 text-sm"
        >
          {label ?? "Current"}
        </text>
        <text
          x={center}
          y={center + 85}
          textAnchor="middle"
          className="fill-foreground/50 text-xs font-semibold"
          style={{ fill: statusColor }}
        >
          {zScore >= 0 ? "+" : ""}
          {zScore.toFixed(2)}σ
        </text>
      </svg>

      {/* Simplified Legend - Z-Score based */}
      <div className="w-full space-y-2">
        <div className="grid grid-cols-5 gap-1 text-xs">
          {segments.segments.map((seg, idx) => (
            <div key={idx} className="flex flex-col items-center gap-1">
              <div
                className="h-3 w-full rounded"
                style={{ backgroundColor: seg.color, opacity: 0.7 }}
              />
              <span className="text-center text-[10px] text-foreground/60">{seg.zRange}</span>
            </div>
          ))}
        </div>
        <div className="flex justify-between text-xs text-foreground/70">
          <span>Current: {current.toFixed(1)}</span>
          <span className="font-semibold text-emerald-500">Normal: {seasonalMean.toFixed(1)}</span>
        </div>
      </div>
    </div>
  );
};
