import { clsx } from "clsx";

export interface SeaStateChipProps {
  hsZ: number;
  oppCurrent?: number;
  asOf: string;
}

const severityIcon = (severity: "high" | "medium" | "normal") => {
  switch (severity) {
    case "high":
      return "🌊";
    case "medium":
      return "〰️";
    default:
      return "▫️";
  }
};

export function SeaStateChip({ hsZ, oppCurrent, asOf }: SeaStateChipProps) {
  const severity: "high" | "medium" | "normal" = hsZ > 2 ? "high" : hsZ > 1 ? "medium" : "normal";
  const icon = severityIcon(severity);
  const severityClasses =
    severity === "high"
      ? "border-danger/40 bg-danger/10 text-danger"
      : severity === "medium"
      ? "border-warning/40 bg-warning/10 text-warning"
      : "border-foreground/20 bg-foreground/5 text-foreground";

  const tooltip = `Sea state as of ${new Date(asOf).toLocaleString()}`;
  const hasOpposingCurrent = typeof oppCurrent === "number" && Number.isFinite(oppCurrent);

  return (
    <div
      className={clsx(
        "inline-flex items-center gap-3 rounded-2xl border px-3 py-2 text-sm transition-colors",
        severityClasses,
      )}
      title={tooltip}
      data-testid="sea-state-chip"
    >
      <span className="flex items-center gap-1 font-medium">
        <span aria-hidden>{icon}</span>
        Wave Height: {hsZ.toFixed(2)}σ
      </span>
      {hasOpposingCurrent && (
        <span className="text-foreground/70">
          Current: {oppCurrent!.toFixed(2)}
          <span className="ml-1 text-xs uppercase tracking-wide text-foreground/40">m/s</span>
        </span>
      )}
    </div>
  );
}
