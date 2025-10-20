import { ResponsiveContainer, AreaChart, Area, Tooltip, XAxis, YAxis, CartesianGrid } from "recharts";
import { useTranslation } from "react-i18next";

type SeriesPoint = {
  d: string;
  value: number;
};

type Props = {
  data: SeriesPoint[];
  label?: string;
};

export const TimeSeriesChart = ({ data, label }: Props) => {
  const { t, i18n } = useTranslation();
  const locale = i18n.language;
  const seriesLabel = label ?? t("dashboard.latestIndex.label");

  return (
    <div className="h-72 w-full">
      <ResponsiveContainer>
        <AreaChart data={data}>
          <defs>
            <linearGradient id="colorIndex" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#38bdf8" stopOpacity={0.8} />
              <stop offset="95%" stopColor="#38bdf8" stopOpacity={0.1} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(148, 163, 184, 0.25)" />
          <XAxis
            dataKey="d"
            tickFormatter={(value) => new Date(value).toLocaleDateString(locale, { month: "short", day: "numeric" })}
            minTickGap={32}
            stroke="rgba(248, 250, 252, 0.6)"
          />
          <YAxis
            allowDecimals={false}
            stroke="rgba(248, 250, 252, 0.6)"
            domain={["auto", "auto"]}
            tickFormatter={(value) => value.toFixed(0)}
          />
          <Tooltip
            cursor={{ stroke: "rgba(56, 189, 248, 0.4)", strokeWidth: 1 }}
            contentStyle={{ backgroundColor: "#020617", borderRadius: "0.75rem", border: "1px solid rgba(148,163,184,0.2)" }}
            labelFormatter={(value) => new Date(value).toLocaleDateString(locale)}
            formatter={(value: number) => [`${value.toFixed(2)}`, seriesLabel]}
          />
          <Area type="monotone" dataKey="value" stroke="#38bdf8" fillOpacity={1} fill="url(#colorIndex)" />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
};
