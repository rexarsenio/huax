import { useEffect, useRef, useState, useMemo } from "react";
import { hasWebGL } from "../lib/webgl";
import { SimpleMap } from "./SimpleMap";

interface SISData {
  sis_mean: number;
  sis_p90: number;
  we_p90_m: number;
  corridor_id: string;
}

interface SeaStateSnapshot {
  hsZ?: number;
  oppCurrent?: number;
  asOf?: string;
}

interface VesselMapWithFallbackProps {
  className?: string;
  initialViewState?: {
    longitude: number;
    latitude: number;
    zoom: number;
  };
  seaStateByRegion?: Record<string, SeaStateSnapshot>;
  sisDataMap?: Record<string, SISData>;
}

type MapMode = "init" | "webgl" | "fallback";

export const VesselMapWithFallback = ({
  className = "",
  initialViewState,
  seaStateByRegion,
  sisDataMap,
}: VesselMapWithFallbackProps) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [mode, setMode] = useState<{ type: MapMode; reason?: string }>({ type: "init" });
  const mapRef = useRef<any>(null);

  // Prepare chokepoints for SimpleMap fallback
  const chokepoints = useMemo(() => {
    const CHOKEPOINTS = [
      {
        id: "strait-of-malacca",
        name: "Strait of Malacca",
        coords: [100.35, 1.4] as [number, number],
        description: "Singapore/Malacca chokepoint",
      },
      {
        id: "singapore-strait",
        name: "Singapore Strait",
        coords: [104.0, 1.3] as [number, number],
        description: "Critical APAC oil route",
      },
      {
        id: "suez-canal",
        name: "Suez Canal",
        coords: [32.3, 30.0] as [number, number],
        description: "Europe-Asia maritime route",
      },
      {
        id: "strait-of-hormuz",
        name: "Strait of Hormuz",
        coords: [56.25, 26.5] as [number, number],
        description: "~21% of global petroleum",
      },
    ];

    return CHOKEPOINTS.map((cp) => {
      const sisData = sisDataMap?.[cp.id] ?? sisDataMap?.[cp.name];
      return {
        ...cp,
        sisData: sisData
          ? {
              sis_mean: sisData.sis_mean,
              we_p90_m: sisData.we_p90_m,
            }
          : undefined,
      };
    });
  }, [sisDataMap]);

  useEffect(() => {
    // Check if WebGL is available
    const { ok, reason } = hasWebGL();

    if (!ok) {
      console.warn(`WebGL not available (${reason}), falling back to SimpleMap`);
      setMode({ type: "fallback", reason });
      return;
    }

    let mapInstance: any;
    let cancelled = false;

    (async () => {
      try {
        // Dynamically import mapbox-gl only if WebGL is available
        const mapboxgl = (await import("mapbox-gl")).default;

        // Check if container is ready
        const node = containerRef.current;
        if (!node || !node.isConnected) {
          throw new Error("container-missing");
        }

        // Optional: Mapbox built-in support check
        if (
          typeof (mapboxgl as any).supported === "function" &&
          !(mapboxgl as any).supported({ failIfMajorPerformanceCaveat: false })
        ) {
          setMode({ type: "fallback", reason: "mapbox-not-supported" });
          return;
        }

        mapboxgl.accessToken = import.meta.env.VITE_MAPBOX_TOKEN as string;

        mapInstance = new mapboxgl.Map({
          container: node,
          style: "mapbox://styles/mapbox/dark-v11",
          center: [
            initialViewState?.longitude ?? 30,
            initialViewState?.latitude ?? 25,
          ],
          zoom: initialViewState?.zoom ?? 2.5,
          failIfMajorPerformanceCaveat: false,
          antialias: false,
          preserveDrawingBuffer: false,
        });

        mapRef.current = mapInstance;

        mapInstance.on("load", () => {
          if (!cancelled) {
            setMode({ type: "webgl" });
            console.log("✅ Mapbox GL initialized successfully");
          }
        });

        mapInstance.on("error", (e: any) => {
          console.error("Mapbox error:", e?.error || e);
          if (!cancelled) {
            setMode({ type: "fallback", reason: "load-error" });
          }
        });
      } catch (err) {
        console.error("Map initialization failed:", err);
        if (!cancelled) {
          setMode({ type: "fallback", reason: (err as Error)?.message || "init-exception" });
        }
      }
    })();

    return () => {
      cancelled = true;
      try {
        if (mapInstance) {
          mapInstance.remove();
        }
      } catch (e) {
        // Ignore cleanup errors
      }
    };
  }, [initialViewState]);

  // Render fallback mode
  if (mode.type === "fallback") {
    return (
      <div className={`relative ${className}`}>
        <SimpleMap className="h-full w-full" chokepoints={chokepoints} />
        <div className="absolute left-4 top-4 rounded-lg bg-amber-500/20 border border-amber-500/30 px-3 py-2 text-xs font-medium text-amber-300 shadow-lg backdrop-blur-sm">
          <div className="flex items-center gap-2">
            <span className="text-base">⚠️</span>
            <div>
              <div className="font-semibold">Limited Mode (No WebGL)</div>
              {mode.reason && (
                <div className="opacity-80 text-[10px]">Reason: {mode.reason}</div>
              )}
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Render loading state
  if (mode.type === "init") {
    return (
      <div className={`relative ${className} bg-background-secondary/50 flex items-center justify-center`}>
        <div className="text-center">
          <div className="animate-spin h-8 w-8 border-4 border-accent border-t-transparent rounded-full mx-auto mb-3"></div>
          <p className="text-sm text-foreground/60">Initializing map...</p>
        </div>
      </div>
    );
  }

  // Render WebGL container
  return <div ref={containerRef} className={`h-full w-full ${className}`} />;
};
