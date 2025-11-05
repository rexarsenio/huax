import { useMemo } from "react";
import { ResponsiveContainer, LineChart, Line, CartesianGrid, Tooltip, XAxis, YAxis, Legend } from "recharts";
import { useMarketOil } from "../hooks/useApi";
import { Skeleton } from "./Skeleton";
import { useTranslation } from "react-i18next";

type Props = {
  series?: string[];
  range?: string;
};

type MergedPoint = {
  ds: string;
  [key: string]: number | string;
};

const COLOR_MAP: Record<string, string> = {
  RBRTE: "#f97316",
  RWTC: "#60a5fa",
};

export const MarketContext = ({ series = ["RBRTE", "RWTC"], range = "180d" }: Props) => {
  const { t, i18n } = useTranslation();
  const locale = i18n.language;
  const query = useMarketOil(series, range);

  const mergedData = useMemo<MergedPoint[]>(() => {
    if (!query.data) return [];
    const merger = new Map<string, MergedPoint>();
    for (const entry of query.data.series) {
      for (const point of entry.points) {
        const key = point.ds;
        const existing = merger.get(key) ?? { ds: key };
        if (point.value != null) {
          existing[entry.id] = point.value;
        }
        merger.set(key, existing);
      }
    }
    return Array.from(merger.values()).sort((a, b) => (a.ds < b.ds ? -1 : 1));
  }, [query.data]);

  if (query.isLoading) {
    return (
      <div className="rounded-2xl border border-foreground/10 bg-foreground/5 p-4">
        <div className="mb-3 text-sm font-semibold text-foreground/80">
          {t("dashboard.marketContext.title", { defaultValue: "Market Context" })}
        </div>
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  if (query.isError || !query.data || mergedData.length === 0) {
    return null;
  }

  return (
    <div className="rounded-2xl border border-foreground/10 bg-foreground/5 p-4">
      <div className="mb-3 flex items-baseline justify-between">
        <div>
          <p className="text-sm font-semibold text-foreground">
            {t("dashboard.marketContext.title", { defaultValue: "Market Context" })}
          </p>
          <p className="text-xs text-foreground/60">
            {t("dashboard.marketContext.subtitle", { defaultValue: "Daily Brent & WTI (EIA/FRED)" })}
          </p>
        </div>
        <div className="text-xs text-foreground/60">{t("dashboard.marketContext.disclaimer", { defaultValue: "For context only" })}</div>
      </div>
      <div className="h-48 w-full">
        <ResponsiveContainer>
          <LineChart data={mergedData}>
            <CartesianGrid stroke="rgba(148, 163, 184, 0.15)" strokeDasharray="4 4" />
            <XAxis
              dataKey="ds"
              stroke="rgba(148, 163, 184, 0.6)"
              tickFormatter={(value) =>
                new Date(value).toLocaleDateString(locale, { month: "short", day: "numeric" })
              }
              minTickGap={32}
            />
            <YAxis stroke="rgba(148, 163, 184, 0.6)" tickFormatter={(value) => `$${value.toFixed(0)}`} />
            <Tooltip
              contentStyle={{
                backgroundColor: "#020617",
                borderRadius: "0.75rem",
                border: "1px solid rgba(148,163,184,0.2)",
              }}
              labelFormatter={(value) =>
                new Date(value).toLocaleDateString(locale, { month: "short", day: "numeric", year: "numeric" })
              }
              formatter={(value: number, name: string) => [`$${value.toFixed(2)}`, name]}
            />
            <Legend verticalAlign="top" height={24} wrapperStyle={{ paddingBottom: 12 }} />
            {series.map((sid) => (
              <Line
                key={sid}
                type="monotone"
                dataKey={sid}
                dot={false}
                stroke={COLOR_MAP[sid] ?? "#22d3ee"}
                strokeWidth={2}
                isAnimationActive={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};
