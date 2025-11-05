export type GaugeZone = "QUIET" | "NORMAL" | "ELEVATED" | "HOT";

export type GaugeState =
  | { state: "ok"; ratio: number; ratioClamped: number; angleDeg: number; zone: GaugeZone; color: string }
  | { state: "no-data" };

export function gaugeModel(level?: number, baseline?: number): GaugeState {
  if (!baseline || !Number.isFinite(baseline) || baseline <= 0 || !Number.isFinite(level ?? NaN)) {
    return { state: "no-data" };
  }

  const ratio = (level! / baseline) * 100;
  const ratioClamped = Math.max(0, Math.min(200, ratio));
  const angleDeg = 210 + (ratioClamped / 200) * -240;

  const zone: GaugeZone =
    ratioClamped < 80 ? "QUIET" : ratioClamped < 120 ? "NORMAL" : ratioClamped < 150 ? "ELEVATED" : "HOT";

  const color =
    zone === "QUIET" ? "#FACC15" : zone === "NORMAL" ? "#10B981" : zone === "ELEVATED" ? "#F97316" : "#DC2626";

  return { state: "ok", ratio, ratioClamped, angleDeg, zone, color };
}
