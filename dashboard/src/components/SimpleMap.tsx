import { useMemo } from "react";
import { SISBadge } from "./SISBadge";

interface Chokepoint {
  id: string;
  name: string;
  coords: [number, number]; // [lng, lat]
  description: string;
  sisData?: {
    sis_mean: number;
    we_p90_m: number;
  };
}

interface SimpleMapProps {
  className?: string;
  chokepoints: Chokepoint[];
}

export const SimpleMap = ({ className = "", chokepoints }: SimpleMapProps) => {
  // Convert lng/lat to x/y percentage for positioning
  const projectPoint = (lng: number, lat: number): [number, number] => {
    // Simple equirectangular projection
    const x = ((lng + 180) / 360) * 100;
    const y = ((90 - lat) / 180) * 100;
    return [x, y];
  };

  const projectedPoints = useMemo(
    () =>
      chokepoints.map((point) => {
        const [x, y] = projectPoint(point.coords[0], point.coords[1]);
        return { ...point, x, y };
      }),
    [chokepoints]
  );

  return (
    <div className={`relative ${className}`}>
      {/* World map background - simple gradient to represent ocean */}
      <div className="absolute inset-0 bg-gradient-to-br from-blue-900/20 via-blue-800/10 to-blue-900/20 rounded-lg overflow-hidden">
        {/* Grid overlay for map feel */}
        <svg className="absolute inset-0 w-full h-full opacity-20">
          <defs>
            <pattern
              id="grid"
              width="40"
              height="40"
              patternUnits="userSpaceOnUse"
            >
              <path
                d="M 40 0 L 0 0 0 40"
                fill="none"
                stroke="currentColor"
                strokeWidth="0.5"
                className="text-blue-400"
              />
            </pattern>
          </defs>
          <rect width="100%" height="100%" fill="url(#grid)" />
        </svg>

        {/* Simple landmass shapes - stylized continents */}
        <svg className="absolute inset-0 w-full h-full" viewBox="0 0 1000 500">
          {/* Africa/Europe rough shape */}
          <ellipse
            cx="500"
            cy="200"
            rx="120"
            ry="100"
            className="fill-background-elevated/40"
          />
          {/* Asia rough shape */}
          <ellipse
            cx="700"
            cy="200"
            rx="150"
            ry="80"
            className="fill-background-elevated/40"
          />
          {/* Middle East */}
          <ellipse
            cx="580"
            cy="220"
            rx="60"
            ry="40"
            className="fill-background-elevated/40"
          />
        </svg>

        {/* Chokepoint markers */}
        {projectedPoints.map((point) => (
          <div
            key={point.id}
            className="absolute transform -translate-x-1/2 -translate-y-1/2 group"
            style={{ left: `${point.x}%`, top: `${point.y}%` }}
          >
            {/* Pulse animation for active chokepoints */}
            <div className="absolute inset-0 animate-ping">
              <div className="w-3 h-3 rounded-full bg-accent/40"></div>
            </div>

            {/* Main marker */}
            <div className="relative w-6 h-6 rounded-full bg-accent border-2 border-background shadow-lg flex items-center justify-center cursor-pointer hover:scale-110 transition-transform">
              <div className="w-2 h-2 rounded-full bg-white"></div>
            </div>

            {/* Tooltip on hover */}
            <div className="absolute left-1/2 -translate-x-1/2 top-8 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-10 whitespace-nowrap">
              <div className="bg-background-elevated border border-border rounded-lg shadow-xl p-3 min-w-[200px]">
                <div className="font-bold text-sm text-foreground mb-1">
                  {point.name}
                </div>
                <div className="text-xs text-foreground/70 mb-2">
                  {point.description}
                </div>
                {point.sisData && (
                  <SISBadge
                    sis={point.sisData.sis_mean}
                    waveHeight={point.sisData.we_p90_m}
                    corridor={point.name}
                  />
                )}
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Legend */}
      <div className="absolute bottom-4 right-4 bg-background-elevated/90 backdrop-blur border border-border rounded-lg p-3 text-xs">
        <div className="font-semibold mb-2 text-foreground">Chokepoints</div>
        <div className="flex items-center gap-2 text-foreground/70">
          <div className="w-3 h-3 rounded-full bg-accent border border-background"></div>
          <span>Critical maritime route</span>
        </div>
        <div className="mt-2 text-foreground/60 text-[10px]">
          Hover over markers for details
        </div>
      </div>
    </div>
  );
};
