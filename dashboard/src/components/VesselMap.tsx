import { useEffect, useRef } from "react";
import mapboxgl from "mapbox-gl";
import "mapbox-gl/dist/mapbox-gl.css";

const MAPBOX_TOKEN = import.meta.env.VITE_MAPBOX_TOKEN;

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
    id: "turkish-straits",
    name: "Turkish Straits",
    coords: [29.0, 41.0] as [number, number],
    description: "Bosporus & Dardanelles",
  },
  {
    id: "suez-canal",
    name: "Suez Canal",
    coords: [32.3, 30.5] as [number, number],
    description: "Mediterranean - Red Sea",
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

interface VesselMapProps {
  className?: string;
  initialViewState?: {
    longitude: number;
    latitude: number;
    zoom: number;
  };
}

export const VesselMap = ({ className = "", initialViewState }: VesselMapProps) => {
  const mapContainer = useRef<HTMLDivElement>(null);
  const map = useRef<mapboxgl.Map | null>(null);

  useEffect(() => {
    if (!mapContainer.current || map.current) return;

    mapboxgl.accessToken = MAPBOX_TOKEN;

    const defaultView = initialViewState || {
      longitude: 30,
      latitude: 25,
      zoom: 2.5,
    };

    map.current = new mapboxgl.Map({
      container: mapContainer.current,
      style: "mapbox://styles/mapbox/dark-v11",
      center: [defaultView.longitude, defaultView.latitude],
      zoom: defaultView.zoom,
    });

    // Add navigation controls
    map.current.addControl(new mapboxgl.NavigationControl(), "top-right");

    // Wait for map to load before adding markers and layers
    map.current.on("load", () => {
      if (!map.current) return;

      // Add chokepoint markers
      CHOKEPOINTS.forEach((cp) => {
        const el = document.createElement("div");
        el.className = "chokepoint-marker";
        el.innerHTML = `
          <div style="position: relative; cursor: pointer;">
            <div style="position: absolute; inset: -8px; background: rgba(239, 68, 68, 0.2); border-radius: 50%; animation: ping 1.5s cubic-bezier(0, 0, 0.2, 1) infinite;"></div>
            <div style="position: relative; width: 16px; height: 16px; background: rgb(239, 68, 68); border-radius: 50%; border: 2px solid white; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);"></div>
          </div>
        `;
        el.title = `${cp.name}: ${cp.description}`;

        new mapboxgl.Marker(el)
          .setLngLat(cp.coords)
          .setPopup(
            new mapboxgl.Popup({ offset: 25 }).setHTML(
              `<div style="padding: 8px;">
                <h3 style="font-weight: bold; margin-bottom: 4px;">${cp.name}</h3>
                <p style="font-size: 12px; color: rgba(255, 255, 255, 0.7);">${cp.description}</p>
              </div>`
            )
          )
          .addTo(map.current!);
      });

      // Add GeoJSON source for chokepoint areas
      const chokepointAreas = {
        type: "FeatureCollection" as const,
        features: CHOKEPOINTS.map((cp) => ({
          type: "Feature" as const,
          geometry: {
            type: "Point" as const,
            coordinates: cp.coords,
          },
          properties: {
            id: cp.id,
            name: cp.name,
            description: cp.description,
          },
        })),
      };

      map.current!.addSource("chokepoints", {
        type: "geojson",
        data: chokepointAreas,
      });

      // Add circle layer for chokepoint visualization
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

      // Add labels
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
    });

    // Cleanup
    return () => {
      map.current?.remove();
      map.current = null;
    };
  }, [initialViewState]);

  return (
    <div className={`relative ${className}`}>
      <div ref={mapContainer} style={{ width: "100%", height: "100%" }} />

      {/* Add ping animation CSS */}
      <style>{`
        @keyframes ping {
          75%, 100% {
            transform: scale(2);
            opacity: 0;
          }
        }
      `}</style>

      {/* Legend */}
      <div className="absolute bottom-4 left-4 bg-background/90 backdrop-blur-sm rounded-lg border border-foreground/10 p-3 shadow-lg text-xs z-10">
        <h3 className="font-semibold mb-2">Maritime Chokepoints</h3>
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 bg-red-500 rounded-full border border-white" />
            <span className="text-foreground/80">Critical Chokepoint</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 bg-red-500/30 rounded-full" />
            <span className="text-foreground/80">Stress Zone</span>
          </div>
        </div>
        <div className="mt-2 pt-2 border-t border-foreground/10 text-xs text-foreground/60">
          Click markers for details
        </div>
      </div>
    </div>
  );
};
