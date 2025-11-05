import { useEffect, useRef, useState } from "react";
import mapboxgl, { type ExpressionSpecification } from "mapbox-gl";
import "mapbox-gl/dist/mapbox-gl.css";
import { fetchCorridorView, type CorridorFeature } from "../api/openSea";
import { fetchChokepointSummary } from "../api/client";
import type { ChokepointSummaryResponse } from "../api/types";

const MAPBOX_TOKEN = import.meta.env.VITE_MAPBOX_TOKEN;

const MEDITERRANEAN_CORRIDORS: Record<
  string,
  {
    name: string;
    coordinates: [number, number][];
  }
> = {
  LANE_CANARY_E_v1: {
    name: "Canary Lane Eastbound",
    coordinates: [
      [-18.5, 27.5],
      [-16.5, 27.9],
      [-14.2, 28.6],
      [-12.0, 29.3],
    ],
  },
  LANE_CANARY_W_v1: {
    name: "Canary Lane Westbound",
    coordinates: [
      [-12.0, 29.3],
      [-14.2, 28.6],
      [-16.5, 27.9],
      [-18.5, 27.5],
    ],
  },
  GATE_GIBRALTAR_E_v1: {
    name: "Gibraltar Eastbound",
    coordinates: [
      [-6.6, 36.2],
      [-5.6, 36.0],
      [-4.3, 36.1],
    ],
  },
  GATE_GIBRALTAR_W_v1: {
    name: "Gibraltar Westbound",
    coordinates: [
      [-4.3, 36.1],
      [-5.6, 36.0],
      [-6.6, 36.2],
    ],
  },
  GATE_GIBRALTAR_MED_50NM: {
    name: "Gibraltar Approaches (Med 50nm)",
    coordinates: [
      [-3.0, 36.5],
      [-4.3, 36.1],
      [-5.8, 35.9],
    ],
  },
  GATE_SICILY_v1: {
    name: "Strait of Sicily",
    coordinates: [
      [12.2, 37.4],
      [13.2, 36.9],
      [14.3, 36.5],
    ],
  },
  GATE_OTRANTO_v1: {
    name: "Strait of Otranto",
    coordinates: [
      [18.4, 41.4],
      [18.9, 40.7],
      [19.4, 39.9],
    ],
  },
  GATE_DARDANELLES_W_v1: {
    name: "Dardanelles Westbound",
    coordinates: [
      [26.9, 40.4],
      [26.6, 40.3],
      [26.1, 40.4],
    ],
  },
  GATE_BOSPORUS_S_v1: {
    name: "Bosporus Southbound",
    coordinates: [
      [29.1, 41.2],
      [29.05, 41.02],
      [28.95, 40.95],
    ],
  },
  GATE_SUEZ_N_v1: {
    name: "Suez Canal Northbound",
    coordinates: [
      [32.3, 30.0],
      [32.3, 30.7],
      [32.4, 31.5],
    ],
  },
  GATE_SUEZ_N_50NM: {
    name: "Suez Approaches (50nm)",
    coordinates: [
      [32.6, 29.0],
      [32.4, 30.0],
      [32.3, 31.2],
    ],
  },
  GATE_SUEZ_N_100NM: {
    name: "Suez Approaches (100nm)",
    coordinates: [
      [33.0, 27.8],
      [32.7, 29.0],
      [32.5, 30.5],
    ],
  },
  GATE_SUEZ_N_150NM: {
    name: "Suez Approaches (150nm)",
    coordinates: [
      [33.3, 26.8],
      [33.0, 28.2],
      [32.6, 29.8],
    ],
  },
};

// Key chokepoints for maritime oil flows
const CHOKEPOINTS = [
  {
    id: "strait-of-hormuz",
    name: "Strait of Hormuz",
    coords: [56.25, 26.5] as [number, number],
    description: "~21% of global petroleum",
  },
  {
    id: "strait-of-malacca",
    name: "Strait of Malacca",
    coords: [100.35, 1.4] as [number, number],
    description: "Singapore/Malacca chokepoint",
  },
  {
    id: "bab-el-mandeb",
    name: "Bab el-Mandeb",
    coords: [43.3, 12.6] as [number, number],
    description: "Red Sea - Gulf of Aden",
  },
  {
    id: "suez-canal",
    name: "Suez Canal",
    coords: [32.3, 30.5] as [number, number],
    description: "Mediterranean - Red Sea",
  },
  {
    id: "strait-of-gibraltar",
    name: "Strait of Gibraltar",
    coords: [-5.4, 36.0] as [number, number],
    description: "~10% European oil imports",
  },
  {
    id: "bosporus",
    name: "Bosporus Strait",
    coords: [29.09, 41.17] as [number, number],
    description: "Black Sea connection, ~3% global oil",
  },
  {
    id: "dardanelles",
    name: "Dardanelles Strait",
    coords: [26.25, 40.21] as [number, number],
    description: "Marmara Sea gateway",
  },
  {
    id: "strait-of-sicily",
    name: "Strait of Sicily",
    coords: [12.5, 36.95] as [number, number],
    description: "Mediterranean inner strait",
  },
  {
    id: "strait-of-otranto",
    name: "Strait of Otranto",
    coords: [19.37, 39.85] as [number, number],
    description: "Adriatic Sea entrance",
  },
  {
    id: "us-gulf",
    name: "US Gulf",
    coords: [-94.0, 28.5] as [number, number],
    description: "Houston Ship Channel",
  },
  {
    id: "WEST_AFRICA_BONNY",
    name: "Bonny Terminal",
    coords: [7.17, 4.45] as [number, number],
    description: "Nigeria crude export hub",
  },
  {
    id: "WEST_AFRICA_ESCRAVOS",
    name: "Escravos Offshore",
    coords: [5.52, 5.55] as [number, number],
    description: "Western Nigeria offshore loading",
  },
  {
    id: "WEST_AFRICA_GULF",
    name: "Gulf of Guinea Offshore",
    coords: [3.6, 4.0] as [number, number],
    description: "Gulf of Guinea shipping corridor",
  },
  {
    id: "panama-canal",
    name: "Panama Canal",
    coords: [-79.9, 9.0] as [number, number],
    description: "Atlantic - Pacific",
  },
  {
    id: "cape-of-good-hope",
    name: "Cape of Good Hope",
    coords: [18.5, -34.4] as [number, number],
    description: "Alternative to Suez",
  },
];

const CHOKEPOINT_CONNECTIONS: Array<{ id: string; path: [number, number][] }> = [
  {
    id: "hormuz-bab-el-mandeb",
    path: [
      [56.25, 26.5],
      [57, 24],
      [53, 20],
      [48, 16],
      [45, 14],
      [43.3, 12.6],
    ],
  },
  {
    id: "bab-el-mandeb-suez",
    path: [
      [43.3, 12.6],
      [42, 16],
      [40, 19],
      [36, 23],
      [34, 27],
      [32.3, 30.5],
    ],
  },
  {
    id: "suez-gibraltar",
    path: [
      [32.3, 30.5],
      [28, 34],
      [23, 35],
      [16, 36.5],
      [-5.4, 36],
    ],
  },
  {
    id: "gibraltar-sicily",
    path: [
      [-5.4, 36],
      [0, 36.5],
      [6, 37],
      [10, 37],
      [12.5, 36.95],
    ],
  },
  {
    id: "sicily-otranto",
    path: [
      [12.5, 36.95],
      [14, 38],
      [17, 39.5],
      [19.37, 39.85],
    ],
  },
  {
    id: "otranto-dardanelles",
    path: [
      [19.37, 39.85],
      [22, 40.3],
      [24.5, 40.5],
      [26.25, 40.21],
    ],
  },
  {
    id: "dardanelles-bosporus",
    path: [
      [26.25, 40.21],
      [27.5, 40.5],
      [28.5, 40.9],
      [29.09, 41.17],
    ],
  },
  {
    id: "bonny-escravos",
    path: [
      [7.17, 4.45],
      [6.4, 4.6],
      [5.9, 5.1],
      [5.52, 5.55],
    ],
  },
  {
    id: "escravos-gulf",
    path: [
      [5.52, 5.55],
      [4.8, 5.3],
      [4.0, 4.7],
      [3.6, 4.0],
    ],
  },
  {
    id: "gulf-gibraltar",
    path: [
      [3.6, 4.0],
      [2.0, 6.0],
      [0.0, 8.5],
      [-3.0, 12.0],
      [-7.0, 18.0],
      [-10.5, 24.0],
      [-12.0, 29.0],
      [-9.0, 33.0],
      [-5.4, 36.0],
    ],
  },
  {
    id: "malacca-bab-el-mandeb",
    path: [
      [100.35, 1.4],
      [95.0, 4.0],
      [90.0, 6.0],
      [85.0, 7.5],
      [80.0, 8.5],
      [75.0, 9.5],
      [70.0, 11.0],
      [65.0, 12.0],
      [60.0, 12.0],
      [55.0, 12.0],
      [50.0, 12.0],
      [47.0, 12.2],
      [44.5, 12.4],
      [43.3, 12.6],
    ],
  },
  {
    id: "malacca-hormuz",
    path: [
      [100.35, 1.4],
      [95, 5],
      [85, 10],
      [75, 15],
      [65, 20],
      [56.25, 26.5],
    ],
  },
  {
    id: "gibraltar-panama",
    path: [
      [-5.4, 36],
      [-7.5, 35],
      [-12.0, 33],
      [-18.0, 29],
      [-25.0, 26],
      [-35.0, 23],
      [-45.0, 20],
      [-55.0, 16],
      [-65.0, 13],
      [-72.0, 9],
      [-79.9, 9],
    ],
  },
  {
    id: "panama-cape-good-hope",
    path: [
      [-79.9, 9],
      [-83.0, 6],
      [-85.0, 2],
      [-84.0, -4],
      [-81.5, -9],
      [-76.0, -18],
      [-70.0, -24],
      [-60.0, -30],
      [-48.0, -33],
      [-36.0, -35],
      [-24.0, -35],
      [-10.0, -34],
      [2.0, -34],
      [10.0, -34],
      [18.5, -34.4],
    ],
  },
  {
    id: "us-gulf-panama",
    path: [
      [-94.0, 28.5],
      [-90.0, 25.5],
      [-85.0, 23.0],
      [-80.0, 20.0],
      [-79.9, 9.0],
    ],
  },
];

interface SeaStateSnapshot {
  hsZ?: number;
  oppCurrent?: number;
  asOf?: string;
}

interface SISData {
  sis_mean: number;
  sis_p90: number;
  we_p90_m: number;
  corridor_id: string;
}

const buildChokepointFeatures = (
  seaStateByRegion?: Record<string, SeaStateSnapshot>,
  sisDataMap?: Record<string, SISData>
) =>
  CHOKEPOINTS.map((cp) => {
    const seaState =
      seaStateByRegion?.[cp.id] ?? seaStateByRegion?.[cp.name] ?? seaStateByRegion?.default ?? null;

    // Try to find SIS data for this chokepoint
    const sisData = sisDataMap?.[cp.id] ?? sisDataMap?.[cp.name];

    return {
      type: "Feature" as const,
      geometry: {
        type: "Point" as const,
        coordinates: cp.coords,
      },
      properties: {
        id: cp.id,
        region: cp.name,
        name: cp.name,
        description: cp.description,
        hs_z: seaState?.hsZ ?? null,
        opp_current: seaState?.oppCurrent ?? null,
        sea_timestamp: seaState?.asOf ?? null,
        // Add SIS data
        sis_mean: sisData?.sis_mean ?? null,
        sis_p90: sisData?.sis_p90 ?? null,
        we_p90_m: sisData?.we_p90_m ?? null,
      },
    };
  });

const buildChokepointConnectionFeatures = () =>
  CHOKEPOINT_CONNECTIONS.map((connection) => ({
    type: "Feature" as const,
    geometry: {
      type: "LineString" as const,
      coordinates: connection.path,
    },
    properties: {
      id: connection.id,
    },
  }));

const buildFallbackCorridors = (): CorridorFeature[] => [
  {
    corridor_id: "ARABIAN_GULF->HORMUZ",
    geometry: {
      type: "LineString",
      coordinates: [
        [50.5, 26.5],
        [55.0, 26.3],
        [56.25, 26.5],
        [58.0, 25.5],
      ],
    },
    flux_h: 145,
    flux_z: 2.1,
    delay_ratio: 1.2,
    sis_p90: 0.65,
    as_of: new Date().toISOString(),
  },
  {
    corridor_id: "MALACCA_STRAIT",
    geometry: {
      type: "LineString",
      coordinates: [
        [98.0, 2.5],
        [100.35, 1.4],
        [103.0, 1.2],
        [104.0, 1.3],
      ],
    },
    flux_h: 180,
    flux_z: 2.8,
    delay_ratio: 1.4,
    sis_p90: 0.72,
    as_of: new Date().toISOString(),
  },
  {
    corridor_id: "SUEZ->MED",
    geometry: {
      type: "LineString",
      coordinates: [
        [32.3, 30.5],
        [30.0, 32.0],
        [25.0, 34.0],
        [20.0, 36.0],
      ],
    },
    flux_h: 95,
    flux_z: 1.2,
    delay_ratio: 1.1,
    sis_p90: 0.45,
    as_of: new Date().toISOString(),
  },
  {
    corridor_id: "TURKISH_STRAITS",
    geometry: {
      type: "LineString",
      coordinates: [
        [28.0, 40.5],
        [29.0, 41.0],
        [30.0, 41.2],
      ],
    },
    flux_h: 65,
    flux_z: 0.8,
    delay_ratio: 1.3,
    sis_p90: 0.38,
    as_of: new Date().toISOString(),
  },
  {
    corridor_id: "BAB_EL_MANDEB",
    geometry: {
      type: "LineString",
      coordinates: [
        [42.0, 11.5],
        [43.3, 12.6],
        [44.5, 13.5],
      ],
    },
    flux_h: 75,
    flux_z: 1.0,
    delay_ratio: 1.15,
    sis_p90: 0.52,
    as_of: new Date().toISOString(),
  },
  {
    corridor_id: "ATLANTIC->GIBRALTAR",
    geometry: {
      type: "LineString",
      coordinates: [
        [-8.0, 36.0],
        [-5.5, 36.0],
        [-3.0, 36.5],
        [0.0, 37.0],
      ],
    },
    flux_h: 42,
    flux_z: 0.3,
    delay_ratio: 0.95,
    sis_p90: 0.28,
    as_of: new Date().toISOString(),
  },
  {
    corridor_id: "SINGAPORE->CHINA",
    geometry: {
      type: "LineString",
      coordinates: [
        [103.8, 1.3],
        [108.0, 8.0],
        [112.0, 15.0],
        [116.0, 22.0],
      ],
    },
    flux_h: 120,
    flux_z: 1.8,
    delay_ratio: 1.1,
    sis_p90: 0.58,
    as_of: new Date().toISOString(),
  },
  {
    corridor_id: "ROTTERDAM->NORTH_SEA",
    geometry: {
      type: "LineString",
      coordinates: [
        [4.0, 51.9],
        [3.0, 53.0],
        [2.0, 55.0],
        [0.0, 57.0],
      ],
    },
    flux_h: 88,
    flux_z: 1.1,
    delay_ratio: 1.05,
    sis_p90: 0.42,
    as_of: new Date().toISOString(),
  },
  {
    corridor_id: "US_GULF",
    geometry: {
      type: "LineString",
      coordinates: [
        [-95.0, 28.5],
        [-92.0, 28.0],
        [-88.0, 28.5],
        [-85.0, 29.0],
      ],
    },
    flux_h: 55,
    flux_z: 0.6,
    delay_ratio: 0.98,
    sis_p90: 0.32,
    as_of: new Date().toISOString(),
  },
  {
    corridor_id: "CAPE_ROUTE",
    geometry: {
      type: "LineString",
      coordinates: [
        [15.0, -30.0],
        [18.5, -34.4],
        [22.0, -33.0],
        [30.0, -30.0],
      ],
    },
    flux_h: 28,
    flux_z: -0.5,
    delay_ratio: 0.9,
    sis_p90: 0.22,
    as_of: new Date().toISOString(),
  },
];

const buildCorridorsFromSummary = (summary: ChokepointSummaryResponse): CorridorFeature[] => {
  if (!summary?.corridors?.length) {
    return [];
  }

  const features: CorridorFeature[] = [];
  for (const entry of summary.corridors) {
    const config = MEDITERRANEAN_CORRIDORS[entry.gate_id];
    if (!config) {
      continue;
    }
    if (!entry.flux || entry.flux <= 0) {
      continue;
    }
    features.push({
      corridor_id: config.name ?? entry.label ?? entry.gate_id,
      geometry: {
        type: "LineString",
        coordinates: config.coordinates,
      },
      flux_h: entry.flux,
      flux_z: entry.flux_z ?? 0,
      delay_ratio: entry.delay_ratio ?? 1.0,
      sis_p90: entry.sis_p90 ?? 0,
      as_of: summary.as_of,
    });
  }

  return features.sort((a, b) => b.flux_h - a.flux_h);
};

interface VesselMapProps {
  className?: string;
  initialViewState?: {
    longitude: number;
    latitude: number;
    zoom: number;
  };
  seaStateByRegion?: Record<string, SeaStateSnapshot>;
  sisDataMap?: Record<string, SISData>;
  gateWeatherMap?: Record<string, any>;
}

export const VesselMap = ({ className = "", initialViewState, seaStateByRegion, sisDataMap, gateWeatherMap }: VesselMapProps) => {
  const mapContainer = useRef<HTMLDivElement>(null);
  const map = useRef<mapboxgl.Map | null>(null);
  const [corridors, setCorridors] = useState<CorridorFeature[]>([]);
  const [mapLoaded, setMapLoaded] = useState(false);

  // Load corridor data on mount
  useEffect(() => {
    let isCancelled = false;

    const loadCorridors = async () => {
      const [corridorResult, summaryResult] = await Promise.allSettled([
        fetchCorridorView("h24"),
        fetchChokepointSummary("h24"),
      ]);

      const mergedMap = new Map<string, CorridorFeature>();

      if (corridorResult.status === "fulfilled" && corridorResult.value.length > 0) {
        corridorResult.value.forEach((feature) => {
          mergedMap.set(feature.corridor_id, feature);
        });
      } else if (corridorResult.status === "rejected") {
        console.warn("Failed to load corridor data from API:", corridorResult.reason);
      }

      if (summaryResult.status === "fulfilled") {
        const medFeatures = buildCorridorsFromSummary(summaryResult.value);
        medFeatures.forEach((feature) => {
          mergedMap.set(feature.corridor_id, feature);
        });
      } else if (summaryResult.status === "rejected") {
        console.warn("Failed to build Mediterranean corridors from summary:", summaryResult.reason);
      }

      let features = Array.from(mergedMap.values()).sort((a, b) => b.flux_h - a.flux_h);

      if (features.length === 0) {
        console.warn("Falling back to static corridor presets");
        features = buildFallbackCorridors();
      }

      if (!isCancelled) {
        setCorridors(features);
      }
    };

    loadCorridors();

    return () => {
      isCancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!mapContainer.current || map.current) return;

    mapboxgl.accessToken = MAPBOX_TOKEN;

    const defaultView = initialViewState || {
      longitude: 30,
      latitude: 25,
      zoom: 2.5,
    };

    try {
      map.current = new mapboxgl.Map({
        container: mapContainer.current,
        style: "mapbox://styles/mapbox/dark-v11",
        center: [defaultView.longitude, defaultView.latitude],
        zoom: defaultView.zoom,
        // WebGL fallback options - try to force software rendering
        preserveDrawingBuffer: true,
        failIfMajorPerformanceCaveat: false,
        antialias: false,
      });
    } catch (error) {
      console.error("Failed to initialize Mapbox map:", error);
      throw error;
    }

    map.current.addControl(new mapboxgl.NavigationControl(), "top-right");

    let handleClick: ((event: mapboxgl.MapLayerMouseEvent) => void) | null = null;
    let handleEnter: (() => void) | null = null;
    let handleLeave: (() => void) | null = null;

    map.current.on("load", () => {
      if (!map.current) return;

      CHOKEPOINTS.forEach((cp) => {
        // Get SIS data for color coding
        const sisData = sisDataMap?.[cp.id] ?? sisDataMap?.[cp.name];
        const sisMean = sisData?.sis_mean ?? null;

        // Get gate weather data
        const gateWeather = gateWeatherMap?.[cp.id] ?? gateWeatherMap?.[cp.name];
        const gateLatest = gateWeather?.latest;

        // Determine color based on SIS level
        let markerColor = 'rgb(239, 68, 68)'; // Default: red
        let glowColor = 'rgba(239, 68, 68, 0.2)';

        if (sisMean !== null) {
          if (sisMean < 0.5) {
            // GOOD: Green
            markerColor = 'rgb(34, 197, 94)';
            glowColor = 'rgba(34, 197, 94, 0.2)';
          } else if (sisMean < 0.7) {
            // ELEVATED: Yellow
            markerColor = 'rgb(234, 179, 8)';
            glowColor = 'rgba(234, 179, 8, 0.2)';
          } else {
            // HIGH: Red
            markerColor = 'rgb(239, 68, 68)';
            glowColor = 'rgba(239, 68, 68, 0.2)';
          }
        }

        const el = document.createElement("div");
        el.className = "chokepoint-marker";
        el.innerHTML = `
          <div style="position: relative; cursor: pointer;">
            <div style="position: absolute; inset: -8px; background: ${glowColor}; border-radius: 50%; animation: ping 1.5s cubic-bezier(0, 0, 0.2, 1) infinite;"></div>
            <div style="position: relative; width: 16px; height: 16px; background: ${markerColor}; border-radius: 50%; border: 2px solid white; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);"></div>
          </div>
        `;
        el.title = `${cp.name}: ${cp.description}`;

        // Add click event to show SIS popup
        el.addEventListener('click', () => {
          if (!map.current) return;

          // Determine SIS level and color
          let sisLevel = "N/A";
          let sisColor = "#9ca3af";
          let sisIcon = "—";

          if (sisMean !== null && Number.isFinite(sisMean)) {
            if (sisMean < 0.5) {
              sisLevel = "GOOD";
              sisColor = "#22c55e";
              sisIcon = "✓";
            } else if (sisMean < 0.7) {
              sisLevel = "ELEVATED";
              sisColor = "#eab308";
              sisIcon = "~";
            } else {
              sisLevel = "HIGH";
              sisColor = "#ef4444";
              sisIcon = "⚠";
            }
          }

          const waveP90 = sisData?.we_p90_m ?? null;

          const popupHtml = `
            <div class="map-popup" style="min-width: 240px;">
              <h4 style="margin-bottom: 10px; font-size: 15px;">${cp.name}</h4>
              <p class="description" style="font-size: 12px; margin-bottom: 12px; opacity: 0.8;">${cp.description}</p>

              ${sisMean !== null ? `
                <div style="padding: 10px; background: rgba(0,0,0,0.2); border-radius: 8px; border-left: 3px solid ${sisColor}; margin-bottom: 10px;">
                  <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 6px;">
                    <span style="font-size: 18px;">${sisIcon}</span>
                    <strong style="color: ${sisColor}; font-size: 14px;">${sisLevel}</strong>
                  </div>
                  <div style="font-size: 12px; opacity: 0.9;">
                    <p style="margin: 3px 0;"><strong>Sea Impact Score:</strong> ${(sisMean * 100).toFixed(0)}%</p>
                    ${waveP90 !== null && Number.isFinite(waveP90) ? `<p style="margin: 3px 0;"><strong>Wave Height (P90):</strong> ${waveP90.toFixed(1)}m</p>` : ''}
                  </div>
                </div>
              ` : ''}

              ${gateLatest ? `
                <div style="padding: 10px; background: rgba(0,0,0,0.2); border-radius: 8px; border-left: 3px solid #3b82f6;">
                  <div style="font-size: 13px; font-weight: 600; margin-bottom: 8px; color: #3b82f6;">🌊 Current Conditions</div>
                  ${gateLatest.waves?.height_m !== null && gateLatest.waves?.height_m !== undefined ? `
                    <div style="font-size: 12px; margin-bottom: 6px;">
                      <strong>Waves:</strong> ${gateLatest.waves.height_m.toFixed(2)}m
                      <span style="color: ${gateLatest.waves.severity === 'high' ? '#ef4444' : gateLatest.waves.severity === 'moderate' ? '#f97316' : '#22c55e'};">
                        (${gateLatest.waves.severity})
                      </span>
                    </div>
                  ` : ''}
                  ${gateLatest.currents?.speed_knots !== null && gateLatest.currents?.speed_knots !== undefined ? `
                    <div style="font-size: 12px;">
                      <strong>Current:</strong> ${gateLatest.currents.speed_knots.toFixed(2)}kn
                      <span style="color: ${gateLatest.currents.severity === 'high' ? '#ef4444' : gateLatest.currents.severity === 'moderate' ? '#f97316' : '#22c55e'};">
                        (${gateLatest.currents.severity})
                      </span>
                    </div>
                  ` : ''}
                  ${gateLatest.observed_at ? `
                    <div style="font-size: 10px; opacity: 0.7; margin-top: 6px;">
                      Updated: ${new Date(gateLatest.observed_at).toLocaleString('de-DE', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })}
                    </div>
                  ` : ''}
                </div>
              ` : (!sisMean ? '<p style="font-size: 11px; opacity: 0.7;">No weather data available</p>' : '')}
            </div>
          `;

          new mapboxgl.Popup({ offset: 25 })
            .setLngLat(cp.coords)
            .setHTML(popupHtml)
            .addTo(map.current);
        });

        new mapboxgl.Marker(el).setLngLat(cp.coords).addTo(map.current!);
      });

      const chokepointAreas = {
        type: "FeatureCollection" as const,
        features: buildChokepointFeatures(seaStateByRegion, sisDataMap),
      };

      map.current!.addSource("chokepoints", {
        type: "geojson",
        data: chokepointAreas,
      });

      map.current!.addSource("chokepoint-connections", {
        type: "geojson",
        data: {
          type: "FeatureCollection",
          features: buildChokepointConnectionFeatures(),
        },
      });

      map.current!.addLayer({
        id: "chokepoint-connections",
        type: "line",
        source: "chokepoint-connections",
        layout: {
          "line-cap": "round",
          "line-join": "round",
        },
        paint: {
          "line-color": "rgba(148, 163, 184, 0.6)",
          "line-dasharray": [2, 2],
          "line-width": [
            "interpolate",
            ["linear"],
            ["zoom"],
            2, 0.5,
            4, 1.2,
            6, 2.4,
          ],
        },
      });

      map.current!.addLayer({
        id: "chokepoint-circles",
        type: "circle",
        source: "chokepoints",
        paint: {
          "circle-radius": [
            "interpolate",
            ["linear"],
            ["zoom"],
            2, 8,
            4, 15,
            6, 25,
          ],
          "circle-color": "#ef4444",
          "circle-opacity": 0.3,
          "circle-stroke-width": 2,
          "circle-stroke-color": "#fff",
          "circle-stroke-opacity": 0.5,
        },
      });

      map.current!.addLayer({
        id: "chokepoint-labels",
        type: "symbol",
        source: "chokepoints",
        layout: {
          "text-field": ["get", "name"],
          "text-size": 12,
          "text-offset": [0, 1.5],
          "text-anchor": "top",
        },
        paint: {
          "text-color": "#ffffff",
          "text-halo-color": "#000000",
          "text-halo-width": 1,
        },
      });

      // Add corridor flow layers
      map.current!.addSource("corridors", {
        type: "geojson",
        data: {
          type: "FeatureCollection",
          features: [],
        },
      });

      // Shadow layer for depth effect
      map.current!.addLayer({
        id: "corridor-shadow",
        type: "line",
        source: "corridors",
        minzoom: 2,
        layout: {
          "line-join": "round",
          "line-cap": "round",
        },
        paint: {
          "line-width": [
            "interpolate",
            ["exponential", 1.5],
            ["zoom"],
            2, [
              "interpolate",
              ["linear"],
              ["get", "flux_h"],
              0, 3,
              50, 5,
              100, 7,
              200, 10,
            ],
            8, [
              "interpolate",
              ["linear"],
              ["get", "flux_h"],
              0, 8,
              50, 14,
              100, 22,
              200, 32,
            ],
          ],
          "line-color": "#000000",
          "line-opacity": 0.4,
          "line-blur": 4,
          "line-offset": [
            "interpolate",
            ["linear"],
            ["zoom"],
            2, 2,
            8, 3,
          ],
        },
      });

      // Main corridor flow lines - ENHANCED
      map.current!.addLayer({
        id: "corridor-flow",
        type: "line",
        source: "corridors",
        minzoom: 2,
        layout: {
          "line-join": "round",
          "line-cap": "round",
        },
        paint: {
          // Dickere, prominentere Linien
          "line-width": [
            "interpolate",
            ["exponential", 1.5],
            ["zoom"],
            2, [
              "interpolate",
              ["linear"],
              ["get", "flux_h"],
              0, 2.5,
              50, 4,
              100, 6,
              200, 8,
            ],
            8, [
              "interpolate",
              ["linear"],
              ["get", "flux_h"],
              0, 6,
              50, 12,
              100, 20,
              200, 30,
            ],
          ],
          // Smoothere Farbübergänge: Hell-grün → Knall-rot
          "line-color": [
            "interpolate",
            ["linear"],
            ["coalesce", ["get", "flux_h"], 0],
            0, "#a7f3d0",    // Very light green
            15, "#86efac",   // Light green
            30, "#4ade80",   // Green
            45, "#22c55e",   // Dark green
            60, "#eab308",   // Yellow-green
            75, "#facc15",   // Yellow
            90, "#fb923c",   // Orange
            105, "#f97316",  // Dark orange
            120, "#ef4444",  // Red
            135, "#dc2626",  // Dark red
            150, "#b91c1c",  // Darker red
            180, "#991b1b",  // Very dark red
            200, "#7f1d1d",  // Knall-rot (darkest red)
          ],
          "line-opacity": 0.95,
          // Stärkerer Glow für hohen Verkehr
          "line-blur": [
            "interpolate",
            ["linear"],
            ["get", "flux_h"],
            0, 0,
            50, 0.5,
            100, 1.5,
            150, 2.5,
            200, 3.5,
          ],
        },
      });

      // Delay/slowdown heat overlay (semi-transparent)
      map.current!.addLayer({
        id: "corridor-delay-heat",
        type: "line",
        source: "corridors",
        minzoom: 3,
        paint: {
          "line-width": [
            "interpolate",
            ["linear"],
            ["zoom"],
            3, 8,
            6, 16,
          ],
          "line-color": [
            "interpolate",
            ["linear"],
            ["get", "delay_ratio"],
            0.8, "#3498db",  // Blue: faster than normal
            1.0, "#95a5a6",  // Gray: normal
            1.5, "#e74c3c",  // Red: slowdown
          ],
          "line-opacity": 0.3,
          "line-blur": 2,
        },
      });

      // Directional arrow symbols - ENHANCED (größer, klarer, prominenter)
      map.current!.addLayer({
        id: "corridor-arrows",
        type: "symbol",
        source: "corridors",
        minzoom: 2,
        layout: {
          "symbol-placement": "line",  // Pfeile entlang der gesamten Linie
          "symbol-spacing": [
            "interpolate",
            ["linear"],
            ["zoom"],
            2, 150,   // Mehr Abstand bei niedrigem Zoom
            4, 100,
            6, 60,
            8, 40,
          ],
          "text-field": "▶",
          "text-size": [
            "interpolate",
            ["exponential", 1.5],
            ["zoom"],
            2, [
              "interpolate",
              ["linear"],
              ["get", "flux_h"],
              0, 24,     // Größere Basis-Größe
              100, 32,
              200, 42,
            ],
            8, [
              "interpolate",
              ["linear"],
              ["get", "flux_h"],
              0, 40,
              100, 56,
              200, 72,
            ],
          ],
          "text-keep-upright": false,
          "text-rotation-alignment": "map",
          "text-pitch-alignment": "map",
          "text-allow-overlap": true,
        },
        paint: {
          // Smoothere Farbübergänge wie bei den Linien
          "text-color": [
            "interpolate",
            ["linear"],
            ["coalesce", ["get", "flux_h"], 0],
            0, "#a7f3d0",
            15, "#86efac",
            30, "#4ade80",
            45, "#22c55e",
            60, "#eab308",
            75, "#facc15",
            90, "#fb923c",
            105, "#f97316",
            120, "#ef4444",
            135, "#dc2626",
            150, "#b91c1c",
            180, "#991b1b",
            200, "#7f1d1d",
          ],
          "text-halo-color": "rgba(0, 0, 0, 0.9)",
          "text-halo-width": 3,
          "text-opacity": 1.0,
          "text-halo-blur": 2,
        },
      });

      const handleChokepointClick = (event: mapboxgl.MapLayerMouseEvent) => {
        if (!map.current) return;
        const feature = event.features?.[0];
        if (!feature) return;
        const geometry = feature.geometry;
        const coords: [number, number] =
          geometry.type === "Point"
            ? (geometry.coordinates as [number, number])
            : [event.lngLat.lng, event.lngLat.lat] as [number, number];
        const props = (feature.properties ?? {}) as Record<string, unknown>;
        const region = String(props.name ?? props.region ?? "Chokepoint");
        const description = props.description ? String(props.description) : "";
        const hsValue = props.hs_z != null && props.hs_z !== ""
          ? Number(props.hs_z)
          : null;
        const oppValue = props.opp_current != null && props.opp_current !== ""
          ? Number(props.opp_current)
          : null;
        const timestampRaw = props.sea_timestamp;
        const timestampText = typeof timestampRaw === "string" && timestampRaw
          ? new Date(timestampRaw).toLocaleString()
          : timestampRaw instanceof Date
          ? new Date(timestampRaw).toLocaleString()
          : "N/A";
        const waveText = hsValue != null && Number.isFinite(hsValue) ? `${hsValue.toFixed(2)} m` : "N/A";
        const currentText = oppValue != null && Number.isFinite(oppValue) ? `${oppValue.toFixed(2)} kn` : "N/A";

        // Get SIS data from properties
        const sisMean = props.sis_mean != null ? Number(props.sis_mean) : null;
        const waveP90 = props.we_p90_m != null ? Number(props.we_p90_m) : null;

        // Determine SIS level and color
        let sisLevel = "N/A";
        let sisColor = "#9ca3af";
        let sisIcon = "—";

        if (sisMean !== null && Number.isFinite(sisMean)) {
          if (sisMean < 0.5) {
            sisLevel = "GOOD";
            sisColor = "#22c55e";
            sisIcon = "✓";
          } else if (sisMean < 0.7) {
            sisLevel = "ELEVATED";
            sisColor = "#eab308";
            sisIcon = "~";
          } else {
            sisLevel = "HIGH";
            sisColor = "#ef4444";
            sisIcon = "⚠";
          }
        }

        const hasSeaState = waveText !== "N/A" || currentText !== "N/A";

        const popupHtml = `
          <div class="map-popup" style="min-width: 240px;">
            <h4 style="margin-bottom: 10px; font-size: 15px;">${region}</h4>
            ${description ? `<p class="description" style="font-size: 12px; margin-bottom: 12px; opacity: 0.8;">${description}</p>` : ""}

            ${sisMean !== null ? `
              <div style="padding: 10px; background: rgba(0,0,0,0.2); border-radius: 8px; border-left: 3px solid ${sisColor};">
                <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 6px;">
                  <span style="font-size: 18px;">${sisIcon}</span>
                  <strong style="color: ${sisColor}; font-size: 14px;">${sisLevel}</strong>
                </div>
                <div style="font-size: 12px; opacity: 0.9;">
                  <p style="margin: 3px 0;"><strong>Sea Impact Score:</strong> ${(sisMean * 100).toFixed(0)}%</p>
                  ${waveP90 !== null && Number.isFinite(waveP90) ? `<p style="margin: 3px 0;"><strong>Wave Height (P90):</strong> ${waveP90.toFixed(1)}m</p>` : ''}
                </div>
              </div>
            ` : hasSeaState ? `
              <div style="padding: 10px; background: rgba(0,0,0,0.15); border-radius: 8px;">
                <p style="margin: 4px 0; font-size: 12px; opacity: 0.85;"><strong>Wave Height (P90):</strong> ${waveText}</p>
                <p style="margin: 4px 0; font-size: 12px; opacity: 0.85;"><strong>Opposing Current:</strong> ${currentText}</p>
                <p style="margin: 4px 0; font-size: 11px; opacity: 0.65;">As of: ${timestampText}</p>
              </div>
            ` : '<p style="font-size: 11px; opacity: 0.7;">No weather impact data available</p>'}
          </div>
        `;

        new mapboxgl.Popup({ offset: 25 }).setLngLat(coords).setHTML(popupHtml).addTo(map.current);
      };

      const handleCorridorClick = (event: mapboxgl.MapLayerMouseEvent) => {
        if (!map.current) return;
        const feature = event.features?.[0];
        if (!feature) return;

        const props = (feature.properties ?? {}) as Record<string, unknown>;
        const corridorId = String(props.corridor_id ?? "Unknown");
        const fluxH = Number(props.flux_h ?? 0);
        const fluxZ = Number(props.flux_z ?? 0);
        const delayRatio = Number(props.delay_ratio ?? 1.0);
        const sisP90 = Number(props.sis_p90 ?? 0);
        const asOf = props.as_of ? new Date(String(props.as_of)).toLocaleString() : "N/A";

        // Determine status text based on flux_z
        const getFluxStatus = (z: number) => {
          if (z < -1) return "Low (Fluid)";
          if (z > 1.5) return "High (Congestion)";
          return "Normal";
        };

        const getDelayStatus = (ratio: number) => {
          if (ratio > 1.2) return "Slowdown";
          if (ratio < 0.95) return "Fast";
          return "Normal";
        };

        const popupHtml = `
          <div class="map-popup" style="min-width: 220px;">
            <h4 style="margin-bottom: 8px;">${corridorId}</h4>
            <div style="font-size: 12px; line-height: 1.6;">
              <p><strong>Flux (24h):</strong> ${fluxH.toFixed(0)} crossings</p>
              <p><strong>Flux Z-score:</strong> ${fluxZ.toFixed(2)} (${getFluxStatus(fluxZ)})</p>
              <p><strong>Delay Ratio:</strong> ${delayRatio.toFixed(2)}x (${getDelayStatus(delayRatio)})</p>
              <p><strong>Sea Impact (p90):</strong> ${sisP90.toFixed(2)}</p>
              <p class="timestamp" style="margin-top: 8px; font-size: 11px; opacity: 0.8;">As of: ${asOf}</p>
            </div>
          </div>
        `;

        // Get center of linestring for popup placement
        const geometry = feature.geometry as any;
        const coords = geometry.coordinates[Math.floor(geometry.coordinates.length / 2)] as [number, number];

        new mapboxgl.Popup({ offset: 25 }).setLngLat(coords).setHTML(popupHtml).addTo(map.current);
      };

      handleClick = handleChokepointClick;

      handleEnter = () => {
        if (map.current) {
          map.current.getCanvas().style.cursor = "pointer";
        }
      };

      handleLeave = () => {
        if (map.current) {
          map.current.getCanvas().style.cursor = "";
        }
      };

      map.current!.on("click", "chokepoint-circles", handleClick);
      map.current!.on("mouseenter", "chokepoint-circles", handleEnter);
      map.current!.on("mouseleave", "chokepoint-circles", handleLeave);

      // Add corridor interaction handlers
      map.current!.on("click", "corridor-flow", handleCorridorClick);
      map.current!.on("mouseenter", "corridor-flow", handleEnter);
      map.current!.on("mouseleave", "corridor-flow", handleLeave);

      // Mark map as loaded
      setMapLoaded(true);

      // Enhanced animation: Pulsing arrows + flowing effect
      let arrowOpacity = 1.0;
      let glowIntensity = 0;
      let direction = -1;
      let glowDirection = 1;

      const animateTraffic = () => {
        if (!map.current) return;

        // Pulsing arrows (smooth breathing effect)
        arrowOpacity += direction * 0.008;
        if (arrowOpacity <= 0.7) {
          direction = 1;
        } else if (arrowOpacity >= 1.0) {
          direction = -1;
        }

        // Pulsing glow for high-traffic routes
        glowIntensity += glowDirection * 0.02;
        if (glowIntensity <= 0) {
          glowDirection = 1;
        } else if (glowIntensity >= 0.5) {
          glowDirection = -1;
        }

        try {
          map.current.setPaintProperty("corridor-arrows", "text-opacity", arrowOpacity);

          // Add subtle pulse to line width for high-traffic routes
          const currentBlur = map.current.getPaintProperty("corridor-flow", "line-blur");
          if (Array.isArray(currentBlur)) {
            // Keep existing blur formula but add subtle animation to base values
            const enhancedBlur: ExpressionSpecification = [
              "interpolate",
              ["linear"],
              ["get", "flux_h"],
              0, glowIntensity * 0.2,
              50, 0.5 + glowIntensity * 0.3,
              100, 1.5 + glowIntensity * 0.5,
              150, 2.5 + glowIntensity * 0.8,
              200, 3.5 + glowIntensity * 1.0,
            ];
            map.current.setPaintProperty("corridor-flow", "line-blur", enhancedBlur);
          }
        } catch (e) {
          // Ignore errors if layer not yet ready
        }

        requestAnimationFrame(animateTraffic);
      };

      animateTraffic();
    });

    return () => {
      if (map.current) {
        if (handleClick) {
          map.current.off("click", "chokepoint-circles", handleClick);
        }
        if (handleEnter) {
          map.current.off("mouseenter", "chokepoint-circles", handleEnter);
        }
        if (handleLeave) {
          map.current.off("mouseleave", "chokepoint-circles", handleLeave);
        }
        map.current.remove();
        map.current = null;
      }
    };
  }, [initialViewState, seaStateByRegion]);

  useEffect(() => {
    if (!map.current) return;
    const source = map.current.getSource("chokepoints") as mapboxgl.GeoJSONSource | undefined;
    if (!source) return;
    const data = {
      type: "FeatureCollection" as const,
      features: buildChokepointFeatures(seaStateByRegion, sisDataMap),
    };
    source.setData(data as any);
  }, [seaStateByRegion, sisDataMap, gateWeatherMap]);

  // Update corridor data when loaded
  useEffect(() => {
    if (!map.current || !mapLoaded || corridors.length === 0) {
      return;
    }
    const source = map.current.getSource("corridors") as mapboxgl.GeoJSONSource | undefined;
    if (!source) {
      return;
    }

    const features = corridors.map((c) => ({
      type: "Feature" as const,
      geometry: c.geometry,
      properties: {
        corridor_id: c.corridor_id,
        flux_h: c.flux_h,
        flux_z: c.flux_z,
        delay_ratio: c.delay_ratio,
        sis_p90: c.sis_p90,
        as_of: c.as_of,
      },
    }));

    source.setData({
      type: "FeatureCollection",
      features,
    } as any);
  }, [corridors, mapLoaded]);

  return (
    <div className={`relative ${className}`}>
      <div ref={mapContainer} style={{ width: "100%", height: "100%" }} />

      {/* Add ping animation CSS and arrow pulse animation */}
      <style>{`
        @keyframes ping {
          75%, 100% {
            transform: scale(2);
            opacity: 0;
          }
        }
      `}</style>

      {/* Enhanced Legend with Traffic Color Scale */}
      <div className="absolute bottom-4 left-4 bg-background/95 backdrop-blur-md rounded-lg border border-foreground/20 p-4 shadow-2xl text-xs z-10 max-w-xs">
        <h3 className="font-bold mb-3 text-sm">Tanker Traffic Intensity</h3>

        {/* Traffic Scale */}
        <div className="mb-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-[10px] text-foreground/70">0 vessels</span>
            <span className="text-[10px] text-foreground/70">200+ vessels</span>
          </div>
          <div className="h-3 rounded-full" style={{
            background: 'linear-gradient(to right, #a7f3d0, #4ade80, #facc15, #fb923c, #ef4444, #b91c1c, #7f1d1d)'
          }} />
          <div className="flex items-center justify-between mt-1">
            <span className="text-[9px] text-green-400">Calm</span>
            <span className="text-[9px] text-yellow-400">Normal</span>
            <span className="text-[9px] text-orange-400">High</span>
            <span className="text-[9px] text-red-500">Critical</span>
          </div>
        </div>

        {/* Visual Elements */}
        <div className="space-y-2 mb-3">
          <div className="flex items-center gap-2">
            <div className="w-6 h-1 rounded-full" style={{ background: 'linear-gradient(to right, #4ade80, #facc15)' }} />
            <span className="text-foreground/80 text-[11px]">Thickness = Traffic volume</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-lg" style={{ color: '#ef4444' }}>▶</span>
            <span className="text-foreground/80 text-[11px]">Arrows = Traffic direction</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 bg-red-500 rounded-full border border-white animate-pulse" />
            <span className="text-foreground/80 text-[11px]">Chokepoints (Bottleneck)</span>
          </div>
        </div>

        <div className="pt-2 border-t border-foreground/20 text-[10px] text-foreground/60">
          💡 Click for details • Animation shows live flow
        </div>
      </div>
    </div>
  );
};
