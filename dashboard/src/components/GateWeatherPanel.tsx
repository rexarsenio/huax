import { useEffect, useState } from "react";
import { fetchGateWeather, GateWeatherData } from "../api/openSea";

interface GateWeatherPanelProps {
  window?: string;
  gateIds?: string[];
  title?: string;
}

export function GateWeatherPanel({
  window = "h24",
  gateIds,
  title = "Gate Weather Conditions",
}: GateWeatherPanelProps) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [gateData, setGateData] = useState<GateWeatherData[]>([]);
  const [lastUpdate, setLastUpdate] = useState<string>("");

  useEffect(() => {
    let mounted = true;

    const loadWeather = async () => {
      try {
        setLoading(true);
        setError(null);
        const response = await fetchGateWeather(window, gateIds);

        if (!mounted) return;

        if (response.message) {
          setError(response.message);
        }

        setGateData(response.gates);
        setLastUpdate(new Date().toLocaleTimeString());
      } catch (err) {
        if (!mounted) return;
        setError(err instanceof Error ? err.message : "Failed to load gate weather");
      } finally {
        if (mounted) {
          setLoading(false);
        }
      }
    };

    loadWeather();

    // Refresh every 30 minutes
    const interval = setInterval(loadWeather, 30 * 60 * 1000);

    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, [window, gateIds]);

  if (loading && gateData.length === 0) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
        <h3 className="text-lg font-semibold mb-4 text-gray-900 dark:text-white">{title}</h3>
        <div className="text-center text-gray-500 dark:text-gray-400">Loading weather data...</div>
      </div>
    );
  }

  if (error && gateData.length === 0) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
        <h3 className="text-lg font-semibold mb-4 text-gray-900 dark:text-white">{title}</h3>
        <div className="text-center text-yellow-600 dark:text-yellow-400">
          {error}
          <div className="text-sm mt-2 text-gray-600 dark:text-gray-400">
            Run <code className="bg-gray-100 dark:bg-gray-700 px-2 py-1 rounded">./COLLECT_GATE_WEATHER.sh</code> to collect data
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow">
      <div className="p-6 border-b border-gray-200 dark:border-gray-700">
        <div className="flex justify-between items-center">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white">{title}</h3>
          <span className="text-xs text-gray-500 dark:text-gray-400">
            Last update: {lastUpdate}
          </span>
        </div>
      </div>

      <div className="p-6">
        {gateData.length === 0 ? (
          <div className="text-center text-gray-500 dark:text-gray-400">
            No weather data available
          </div>
        ) : (
          <div className="space-y-4">
            {gateData.map((gate) => (
              <GateWeatherCard key={gate.gate_id} gate={gate} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function GateWeatherCard({ gate }: { gate: GateWeatherData }) {
  const { latest_observation: obs, statistics: stats } = gate;

  const waveColor =
    obs.waves.severity === "high"
      ? "text-red-600 dark:text-red-400"
      : obs.waves.severity === "moderate"
        ? "text-yellow-600 dark:text-yellow-400"
        : "text-green-600 dark:text-green-400";

  const currentColor =
    obs.currents.severity === "high"
      ? "text-red-600 dark:text-red-400"
      : obs.currents.severity === "moderate"
        ? "text-yellow-600 dark:text-yellow-400"
        : "text-green-600 dark:text-green-400";

  return (
    <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4 hover:bg-gray-50 dark:hover:bg-gray-750 transition">
      {/* Header */}
      <div className="flex justify-between items-start mb-3">
        <div>
          <h4 className="font-semibold text-gray-900 dark:text-white">{gate.gate_name}</h4>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            {gate.gate_id} • {gate.basin}
          </p>
        </div>
        {obs.observed_at && (
          <span className="text-xs text-gray-500 dark:text-gray-400">
            {new Date(obs.observed_at).toLocaleString()}
          </span>
        )}
      </div>

      {/* Weather Data Grid */}
      <div className="grid grid-cols-2 gap-4">
        {/* Waves */}
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <span className="text-2xl">🌊</span>
            <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Waves</span>
          </div>
          {obs.waves.height_m !== null ? (
            <>
              <div className={`text-2xl font-bold ${waveColor}`}>
                {obs.waves.height_m.toFixed(2)} m
              </div>
              <div className="text-xs text-gray-600 dark:text-gray-400 space-y-1">
                {obs.waves.period_s && <div>Period: {obs.waves.period_s.toFixed(1)}s</div>}
                {stats.waves.mean_height_m && (
                  <div>Mean: {stats.waves.mean_height_m.toFixed(2)}m</div>
                )}
                {stats.waves.p90_height_m && (
                  <div>P90: {stats.waves.p90_height_m.toFixed(2)}m</div>
                )}
              </div>
            </>
          ) : (
            <div className="text-sm text-gray-400 dark:text-gray-500">No data</div>
          )}
        </div>

        {/* Currents */}
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <span className="text-2xl">🌀</span>
            <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Currents</span>
          </div>
          {obs.currents.speed_knots !== null ? (
            <>
              <div className={`text-2xl font-bold ${currentColor}`}>
                {obs.currents.speed_knots.toFixed(2)} kn
              </div>
              <div className="text-xs text-gray-600 dark:text-gray-400 space-y-1">
                {obs.currents.u_knots !== null && obs.currents.v_knots !== null && (
                  <div>
                    U: {obs.currents.u_knots.toFixed(1)} / V: {obs.currents.v_knots.toFixed(1)}
                  </div>
                )}
                {stats.currents.mean_speed_kn && (
                  <div>Mean: {stats.currents.mean_speed_kn.toFixed(2)}kn</div>
                )}
                {stats.currents.p90_speed_kn && (
                  <div>P90: {stats.currents.p90_speed_kn.toFixed(2)}kn</div>
                )}
              </div>
            </>
          ) : (
            <div className="text-sm text-gray-400 dark:text-gray-500">No data</div>
          )}
        </div>
      </div>

      {/* Severity Indicators */}
      <div className="mt-3 flex gap-2">
        {obs.waves.severity !== "normal" && (
          <span className="text-xs px-2 py-1 rounded bg-yellow-100 dark:bg-yellow-900 text-yellow-800 dark:text-yellow-200">
            {obs.waves.severity === "high" ? "⚠️ High Waves" : "Moderate Waves"}
          </span>
        )}
        {obs.currents.severity !== "normal" && (
          <span className="text-xs px-2 py-1 rounded bg-yellow-100 dark:bg-yellow-900 text-yellow-800 dark:text-yellow-200">
            {obs.currents.severity === "high" ? "⚠️ Strong Current" : "Moderate Current"}
          </span>
        )}
      </div>

      {/* Sample Count */}
      <div className="mt-2 text-xs text-gray-500 dark:text-gray-400">
        Based on {stats.samples_count} observation{stats.samples_count !== 1 ? "s" : ""}
      </div>
    </div>
  );
}
