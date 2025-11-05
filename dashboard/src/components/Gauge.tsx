import { useMemo } from "react";
import clsx from "clsx";
import { useTranslation } from "react-i18next";
import { gaugeModel } from "../lib/gaugeModel";
import { donutSegmentPath, polarToXY } from "../lib/arc";

type GaugeProps = {
  level?: number;
  baseline?: number;
  zscore?: number;
  dataGapRatio?: number | null;
  ingestLagSeconds?: number | null;
  className?: string;
};

const WIDTH = 320;
const HEIGHT = 220;
const CX = WIDTH / 2;
const CY = 178;
const R_OUT = 118;
const R_IN = 98;
const NEEDLE_LENGTH = 114;
const START_ANGLE = 210;
const END_ANGLE = -30;
const SWEEP = END_ANGLE - START_ANGLE;
const GAP_DEG = 2;
const FALLBACK_RATIO = 100;

const SEGMENTS: Array<{ from: number; to: number; color: string }> = [
  { from: 0, to: 80, color: "#FACC15" },
  { from: 80, to: 120, color: "#10B981" },
  { from: 120, to: 150, color: "#F97316" },
  { from: 150, to: 200, color: "#DC2626" },
];

const LABELS = [
  { value: 0, align: "start" as const },
  { value: 100, align: "middle" as const },
  { value: 200, align: "end" as const },
];

const angleFor = (pct: number) => START_ANGLE + (pct / 200) * SWEEP;

export const Gauge = ({
  level,
  baseline,
  zscore,
  dataGapRatio,
  ingestLagSeconds,
  className,
}: GaugeProps) => {
  const { t, i18n } = useTranslation();
  const locale = i18n.language;
  const model = useMemo(() => gaugeModel(level, baseline), [level, baseline]);

  const ratioPercent = model.state === "ok" ? Math.round(model.ratio) : null;
  const pointerAngle = model.state === "ok" ? model.angleDeg : angleFor(FALLBACK_RATIO);
  const pointerColor = model.state === "ok" ? model.color : "#94a3b8";
  const zoneLabel =
    model.state === "ok"
      ? t(`dashboard.gauge.zone.${model.zone.toLowerCase()}`, { defaultValue: model.zone })
      : t("dashboard.gauge.zone.na", { defaultValue: "Baseline unavailable" });
  const seasonalText =
    model.state === "ok" && baseline != null
      ? baseline.toLocaleString(locale, { maximumFractionDigits: 1 })
      : undefined;
  const degraded =
    (dataGapRatio != null && Number.isFinite(dataGapRatio) && dataGapRatio > 0.1) ||
    (ingestLagSeconds != null && Number.isFinite(ingestLagSeconds) && ingestLagSeconds > 900);

  const [needleX, needleY] = polarToXY(CX, CY, NEEDLE_LENGTH, pointerAngle);
  const ratioDisplay = ratioPercent != null ? `${ratioPercent}%` : "—";
  const levelDisplay =
    level != null && Number.isFinite(level) ? level.toLocaleString(locale, { maximumFractionDigits: 1 }) : "—";
  const levelLine = t("dashboard.gauge.levelLabel", {
    defaultValue: "Index {{value}}",
    value: levelDisplay,
  });

  return (
    <div className={clsx("relative flex w-full flex-col items-center gap-5 p-4", className)}>
      {degraded && (
        <span
          className="absolute -top-1 right-2 rounded-lg bg-warning/20 border border-warning/40 px-3 py-1.5 text-xs font-bold uppercase tracking-wide text-warning shadow-sm"
          title={t("dashboard.gauge.degradedTooltip", {
            defaultValue: "Recent ingest metrics flagged (gap >10% or lag >15m).",
          })}
        >
          {t("dashboard.gauge.degraded", { defaultValue: "Degraded" })}
        </span>
      )}

      <div className="flex flex-col items-center gap-1 text-center">
        <span className="text-sm font-semibold uppercase tracking-wide text-foreground/70">
          {t("dashboard.gauge.seasonalRatio", { defaultValue: "Seasonal ratio" })}
        </span>
        <span className="text-xs text-foreground/50">
          {seasonalText
            ? t("dashboard.gauge.baselineHint", {
                defaultValue: "Baseline: {{value}} → 100%",
                value: seasonalText,
              })
            : t("dashboard.gauge.baselineUnavailable", { defaultValue: "Baseline unavailable" })}
        </span>
      </div>

      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="w-full max-w-[440px] drop-shadow-lg">
        <path
          d={donutSegmentPath(CX, CY, R_IN, R_OUT, START_ANGLE, END_ANGLE, 0)}
          fill="#1F2937"
          opacity={0.4}
        />

        {SEGMENTS.map((segment) => {
          const start = angleFor(segment.from);
          const end = angleFor(segment.to);
          return (
            <path
              key={`${segment.from}-${segment.to}`}
              d={donutSegmentPath(CX, CY, R_IN, R_OUT, start, end, GAP_DEG)}
              fill={model.state === "ok" ? segment.color : "#E5E7EB"}
              fillOpacity={model.state === "ok" ? 0.95 : 1}
              className="transition-all duration-300"
            />
          );
        })}

        {LABELS.map((label) => {
          const [lx, ly] = polarToXY(CX, CY, R_OUT + 16, angleFor(label.value));
          const [tx1, ty1] = polarToXY(CX, CY, R_OUT + 4, angleFor(label.value));
          const [tx2, ty2] = polarToXY(CX, CY, R_OUT + 12, angleFor(label.value));
          return (
            <g key={label.value}>
              <line
                x1={tx1}
                y1={ty1}
                x2={tx2}
                y2={ty2}
                stroke="#9CA3AF"
                strokeWidth={2.5}
                strokeLinecap="round"
                vectorEffect="non-scaling-stroke"
              />
              <text
                x={lx}
                y={ly}
                textAnchor={label.align}
                alignmentBaseline="middle"
                className="fill-foreground text-sm font-bold"
              >
                {`${label.value}%`}
              </text>
            </g>
          );
        })}

        <line
          x1={CX}
          y1={CY}
          x2={needleX}
          y2={needleY}
          stroke="#F9FAFB"
          strokeWidth={5}
          strokeLinecap="round"
          vectorEffect="non-scaling-stroke"
          className="drop-shadow-lg"
          style={{ transition: "x2 0.8s cubic-bezier(0.4, 0, 0.2, 1), y2 0.8s cubic-bezier(0.4, 0, 0.2, 1)" }}
        />
        <circle cx={CX} cy={CY} r={10} fill="#1F2937" opacity={0.8} />
        <circle cx={CX} cy={CY} r={6} fill={pointerColor} className="drop-shadow-md" />
        <circle cx={CX} cy={CY} r={2} fill="#F9FAFB" opacity={0.9} />

        <text x={CX} y={CY - 24} textAnchor="middle" className="fill-foreground text-4xl font-bold drop-shadow-lg">
          {ratioDisplay}
        </text>
        <text x={CX} y={CY + 2} textAnchor="middle" className="fill-foreground/75 text-sm font-medium">
          {levelLine}
        </text>
      </svg>

      <div className="flex flex-col items-center gap-1 text-sm">
        <span className="rounded-lg px-4 py-1 font-semibold uppercase tracking-wide text-foreground shadow-sm" style={{ backgroundColor: `${pointerColor}20`, color: pointerColor }}>
          {zoneLabel}
        </span>
        <span className="text-xs text-foreground/60">
          {t("dashboard.gauge.zScoreLabel", { defaultValue: "Z-score" })}:{" "}
          <span className="font-mono text-foreground/80">
            {zscore != null && Number.isFinite(zscore) ? `${zscore >= 0 ? "+" : ""}${zscore.toFixed(2)}σ` : "—"}
          </span>
        </span>
      </div>
    </div>
  );
};
