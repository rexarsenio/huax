export type OilSeriesPoint = {
  ds: string;
  value: number | null;
};

export type OilSeriesResponse = {
  series: Array<{
    id: string;
    points: OilSeriesPoint[];
  }>;
  latest: Record<string, OilSeriesPoint | null>;
};

export async function fetchOil(series: string[] = ["RBRTE", "RWTC"], range = "180d"): Promise<OilSeriesResponse> {
  const params = new URLSearchParams({
    series: series.join(","),
    range,
  });
  const response = await fetch(`/api/market/oil?${params.toString()}`);
  if (!response.ok) {
    throw new Error("Failed to fetch oil market data");
  }
  return response.json() as Promise<OilSeriesResponse>;
}
