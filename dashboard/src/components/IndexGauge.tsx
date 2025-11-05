import { useMemo } from "react";
import { useTranslation } from "react-i18next";

interface IndexGaugeProps {
  value: number;
  /**
   * Bandwidth thresholds:
   * - Normal: [normalMin, tenseMin)
   * - Tense: [tenseMin, stressMin)
   * - Stress: [stressMin, maxValue]
   */
  normalMin?: number;
  tenseMin?: number;
  stressMin?: number;
  maxValue?: number;
  minValue?: number;
  label?: string;
}

export const IndexGauge = ({
  value,
  normalMin = 80,
  tenseMin = 120,
  stressMin = 150,
  maxValue = 200,
  minValue = 50,
  label,
}: IndexGaugeProps) => {
  const { t } = useTranslation();

  const { angle, band, bandColor, bandLabel } = useMemo(() => {
    // Clamp value to range
    const clampedValue = Math.max(minValue, Math.min(maxValue, value));

    // Calculate angle: -90° (left) to +90° (right) for semicircle gauge
    const range = maxValue - minValue;
    const normalizedValue = (clampedValue - minValue) / range;
    const angle = normalizedValue * 180 - 90; // -90 to +90 degrees

    // Determine band
    let band: "normal" | "tense" | "stress";
    let bandColor: string;
    let bandLabel: string;

    if (value < tenseMin) {
      band = "normal";
      bandColor = "#10b981"; // green
      bandLabel = t("dashboard.meta.band.normal", { defaultValue: "Normal" });
    } else if (value < stressMin) {
      band = "tense";
      bandColor = "#f59e0b"; // amber
      bandLabel = t("dashboard.meta.band.tense", { defaultValue: "Tense" });
    } else {
      band = "stress";
      bandColor = "#ef4444"; // red
      bandLabel = t("dashboard.meta.band.stress", { defaultValue: "Stress" });
    }

    return { angle, band, bandColor, bandLabel };
  }, [value, minValue, maxValue, normalMin, tenseMin, stressMin, t]);

  // Calculate arc positions for color bands
  const normalRange = ((tenseMin - minValue) / (maxValue - minValue)) * 180;
  const tenseRange = ((stressMin - tenseMin) / (maxValue - minValue)) * 180;
  const stressRange = ((maxValue - stressMin) / (maxValue - minValue)) * 180;

  return (
    <div className="flex flex-col items-center">
      <div className="relative" style={{ width: "240px", height: "140px" }}>
        {/* SVG Gauge */}
        <svg
          viewBox="0 0 200 120"
          className="w-full h-full"
          style={{ overflow: "visible" }}
        >
          {/* Background arc (gray) */}
          <path
            d="M 20 100 A 80 80 0 0 1 180 100"
            fill="none"
            stroke="currentColor"
            strokeWidth="20"
            className="text-foreground/10"
            strokeLinecap="round"
          />

          {/* Color bands */}
          {/* Normal band (green) */}
          <path
            d="M 20 100 A 80 80 0 0 1 180 100"
            fill="none"
            stroke="#10b981"
            strokeWidth="20"
            strokeLinecap="round"
            strokeDasharray={`${normalRange * 1.396} 1000`}
            strokeDashoffset="0"
            style={{ opacity: 0.4 }}
          />

          {/* Tense band (amber) */}
          <path
            d="M 20 100 A 80 80 0 0 1 180 100"
            fill="none"
            stroke="#f59e0b"
            strokeWidth="20"
            strokeLinecap="round"
            strokeDasharray={`${tenseRange * 1.396} 1000`}
            strokeDashoffset={-normalRange * 1.396}
            style={{ opacity: 0.4 }}
          />

          {/* Stress band (red) */}
          <path
            d="M 20 100 A 80 80 0 0 1 180 100"
            fill="none"
            stroke="#ef4444"
            strokeWidth="20"
            strokeLinecap="round"
            strokeDasharray={`${stressRange * 1.396} 1000`}
            strokeDashoffset={-(normalRange + tenseRange) * 1.396}
            style={{ opacity: 0.4 }}
          />

          {/* Needle/Arrow */}
          <g transform={`rotate(${angle} 100 100)`}>
            <line
              x1="100"
              y1="100"
              x2="100"
              y2="30"
              stroke={bandColor}
              strokeWidth="3"
              strokeLinecap="round"
            />
            {/* Arrow tip */}
            <polygon
              points="100,25 95,35 105,35"
              fill={bandColor}
            />
          </g>

          {/* Center dot */}
          <circle cx="100" cy="100" r="6" fill={bandColor} />
        </svg>

        {/* Value display */}
        <div className="absolute inset-0 flex flex-col items-center justify-end pb-2">
          <p className="text-3xl font-bold" style={{ color: bandColor }}>
            {value.toFixed(1)}
          </p>
          <p className="text-xs text-foreground/60 uppercase tracking-wide mt-1">
            {bandLabel}
          </p>
        </div>
      </div>

      {/* Legend */}
      <div className="mt-4 flex flex-wrap items-center justify-center gap-4 text-xs text-foreground/70">
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 rounded-full bg-green-500" />
          <span>
            {normalMin}–{tenseMin - 1}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 rounded-full bg-amber-500" />
          <span>
            {tenseMin}–{stressMin - 1}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 rounded-full bg-red-500" />
          <span>{stressMin}+</span>
        </div>
      </div>

      {label && (
        <p className="mt-2 text-sm text-foreground/60">{label}</p>
      )}
    </div>
  );
};
