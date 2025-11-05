import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

interface RegistryStatus {
  total_vessels: number;
  tankers: number;
  tanker_percentage: number;
  avg_confidence: number | null;
  sources: Array<{
    source: string;
    count: number;
    avg_confidence: number | null;
  }>;
  top_polygons: Array<{
    polygon_id: string;
    kind: string;
    visit_count: number;
    total_dwell_hours: number;
    unique_vessels: number;
  }>;
  recent_events_24h: {
    event_count: number;
    unique_vessels: number;
    total_dwell_hours: number;
  };
  timestamp: string;
}

export function RegistryPanel() {
  const { t } = useTranslation();
  const [data, setData] = useState<RegistryStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const response = await fetch('http://localhost:8000/api/registry/status');
        if (!response.ok) throw new Error('Failed to fetch registry status');
        const json = await response.json();
        setData(json);
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unknown error');
      } finally {
        setLoading(false);
      }
    };

    fetchData();
    const interval = setInterval(fetchData, 60000); // Refresh every minute
    return () => clearInterval(interval);
  }, []);

  if (loading) {
    return (
      <div className="bg-background-secondary border border-border rounded-lg p-6">
        <div className="animate-pulse">
          <div className="h-4 bg-border rounded w-1/4 mb-4"></div>
          <div className="h-8 bg-border rounded w-1/2"></div>
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="bg-background-secondary border border-border rounded-lg p-6">
        <div className="text-red-400">
          <p className="font-semibold">Error loading registry data</p>
          <p className="text-sm">{error || 'No data available'}</p>
        </div>
      </div>
    );
  }

  const sourceLabels: Record<string, string> = {
    'PORT_BEHAVIOR': 'Terminal Dwell',
    'STS_BEHAVIOR': 'STS Zone',
    'CORRIDOR': 'Corridor Pattern',
    'TYPE5': 'AIS Type 5',
    'MANUAL': 'Manual',
  };

  return (
    <div className="space-y-4">
      {/* Main Stats Card */}
      <div className="bg-background-secondary border border-border rounded-lg p-6">
        <h2 className="text-lg font-semibold text-text-primary mb-4">
          Ship Registry & Tanker Classification
        </h2>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <div>
            <p className="text-sm text-text-secondary mb-1">Total Vessels</p>
            <p className="text-2xl font-bold text-text-primary">
              {data.total_vessels.toLocaleString()}
            </p>
          </div>

          <div>
            <p className="text-sm text-text-secondary mb-1">Identified Tankers</p>
            <p className="text-2xl font-bold text-accent">
              {data.tankers.toLocaleString()}
            </p>
          </div>

          <div>
            <p className="text-sm text-text-secondary mb-1">Tanker %</p>
            <p className="text-2xl font-bold text-text-primary">
              {data.tanker_percentage}%
            </p>
          </div>

          <div>
            <p className="text-sm text-text-secondary mb-1">Avg Confidence</p>
            <p className="text-2xl font-bold text-text-primary">
              {data.avg_confidence ? data.avg_confidence.toFixed(2) : 'N/A'}
            </p>
          </div>
        </div>

        {/* Classification Sources */}
        <div className="mb-6">
          <h3 className="text-sm font-semibold text-text-secondary mb-3">
            Classification Sources
          </h3>
          <div className="space-y-2">
            {data.sources.map((source) => (
              <div
                key={source.source}
                className="flex items-center justify-between bg-background p-3 rounded"
              >
                <div>
                  <p className="text-sm font-medium text-text-primary">
                    {sourceLabels[source.source] || source.source}
                  </p>
                  <p className="text-xs text-text-secondary">
                    Confidence: {source.avg_confidence?.toFixed(2) || 'N/A'}
                  </p>
                </div>
                <p className="text-lg font-bold text-accent">
                  {source.count.toLocaleString()}
                </p>
              </div>
            ))}
          </div>
        </div>

        {/* Recent Activity */}
        <div>
          <h3 className="text-sm font-semibold text-text-secondary mb-3">
            Recent Activity (24h)
          </h3>
          <div className="grid grid-cols-3 gap-4">
            <div className="bg-background p-3 rounded">
              <p className="text-xs text-text-secondary mb-1">Events</p>
              <p className="text-lg font-bold text-text-primary">
                {data.recent_events_24h.event_count}
              </p>
            </div>
            <div className="bg-background p-3 rounded">
              <p className="text-xs text-text-secondary mb-1">Vessels</p>
              <p className="text-lg font-bold text-text-primary">
                {data.recent_events_24h.unique_vessels}
              </p>
            </div>
            <div className="bg-background p-3 rounded">
              <p className="text-xs text-text-secondary mb-1">Total Dwell</p>
              <p className="text-lg font-bold text-text-primary">
                {data.recent_events_24h.total_dwell_hours.toLocaleString()}h
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Top Polygons Card */}
      <div className="bg-background-secondary border border-border rounded-lg p-6">
        <h3 className="text-lg font-semibold text-text-primary mb-4">
          Top Terminal & STS Activity (7d)
        </h3>
        <div className="space-y-2">
          {data.top_polygons.slice(0, 5).map((polygon, idx) => (
            <div
              key={`${polygon.polygon_id}-${idx}`}
              className="flex items-center justify-between bg-background p-3 rounded"
            >
              <div className="flex-1">
                <p className="text-sm font-medium text-text-primary">
                  {polygon.polygon_id.replace(/_/g, ' ')}
                </p>
                <p className="text-xs text-text-secondary">
                  {polygon.kind === 'OIL_TERMINAL' ? 'Terminal' : 'STS Zone'} •{' '}
                  {polygon.unique_vessels} vessels
                </p>
              </div>
              <div className="text-right">
                <p className="text-sm font-bold text-accent">
                  {polygon.visit_count} visits
                </p>
                <p className="text-xs text-text-secondary">
                  {polygon.total_dwell_hours.toLocaleString()}h dwell
                </p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
