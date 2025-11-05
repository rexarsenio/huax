interface SISBadgeProps {
  sisP90?: number;
  sis?: number;
  waveHeight?: number;
  currentSpeed?: number;  // NEW: Current speed in knots
  windSpeed?: number;     // NEW: Wind speed in knots
  corridor?: string;
  compact?: boolean;
  showDetails?: boolean;  // NEW: Show component breakdown
}

export function SISBadge({
  sisP90,
  sis,
  waveHeight,
  currentSpeed,
  windSpeed,
  corridor,
  compact = false,
  showDetails = false
}: SISBadgeProps) {
  // Use either sisP90 (legacy) or sis (new), prefer sis_mean
  const score = sis ?? sisP90 ?? 0;

  const level = score >= 0.7 ? "HIGH" : score >= 0.5 ? "ELEVATED" : "GOOD";
  const icon = level === "HIGH" ? "⚠" : level === "ELEVATED" ? "~" : "✓";

  const baseClasses = "inline-flex items-center gap-1.5 px-2 py-1 rounded-xl text-xs font-medium uppercase tracking-wide";
  const colorClasses =
    level === "HIGH"
      ? "bg-red-500/20 text-red-600 dark:text-red-400 border border-red-500/30"
      : level === "ELEVATED"
      ? "bg-yellow-500/20 text-yellow-700 dark:text-yellow-400 border border-yellow-500/30"
      : "bg-green-500/20 text-green-700 dark:text-green-300 border border-green-500/30";

  // Build detailed tooltip with all components
  const components = [];
  if (waveHeight !== undefined && waveHeight > 0) {
    components.push(`Waves: ${waveHeight.toFixed(1)}m`);
  }
  if (currentSpeed !== undefined && currentSpeed > 0) {
    components.push(`Current: ${currentSpeed.toFixed(1)}kn`);
  }
  if (windSpeed !== undefined && windSpeed > 0) {
    components.push(`Wind: ${windSpeed.toFixed(1)}kn`);
  }

  const tooltipBase = corridor
    ? `Sea Impact Score: ${(score * 100).toFixed(0)}% - ${level} conditions in ${corridor}`
    : `Sea Impact Score: ${(score * 100).toFixed(0)}%`;

  const tooltip = components.length > 0
    ? `${tooltipBase}\n${components.join(' | ')}`
    : tooltipBase;

  if (compact) {
    return (
      <span className={`${baseClasses} ${colorClasses}`} title={tooltip}>
        <span aria-hidden>{icon}</span>
      </span>
    );
  }

  if (showDetails) {
    // Detailed view with all components
    return (
      <div className="space-y-2">
        <span className={`${baseClasses} ${colorClasses}`} title={tooltip}>
          <span aria-hidden>{icon}</span>
          <span>{level}</span>
          <span className="opacity-70">• {(score * 100).toFixed(0)}%</span>
        </span>
        {components.length > 0 && (
          <div className="flex flex-wrap gap-2 text-xs">
            {waveHeight !== undefined && waveHeight > 0 && (
              <span className="flex items-center gap-1 text-foreground/60">
                <span title="Wave Height">🌊</span>
                <span>{waveHeight.toFixed(1)}m</span>
              </span>
            )}
            {currentSpeed !== undefined && currentSpeed > 0 && (
              <span className="flex items-center gap-1 text-foreground/60">
                <span title="Current Speed">🌀</span>
                <span>{currentSpeed.toFixed(1)}kn</span>
              </span>
            )}
            {windSpeed !== undefined && windSpeed > 0 && (
              <span className="flex items-center gap-1 text-foreground/60">
                <span title="Wind Speed">💨</span>
                <span>{windSpeed.toFixed(1)}kn</span>
              </span>
            )}
          </div>
        )}
      </div>
    );
  }

  // Standard view (backward compatible)
  return (
    <span className={`${baseClasses} ${colorClasses}`} title={tooltip}>
      <span aria-hidden>{icon}</span>
      <span>{level}</span>
      {waveHeight !== undefined && waveHeight > 0 && (
        <span className="opacity-70">• {waveHeight.toFixed(1)}m</span>
      )}
    </span>
  );
}
