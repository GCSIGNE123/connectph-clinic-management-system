"use client";

import type { SeriesPoint } from "@/features/analytics/types";

export interface LineChartProps {
  data: SeriesPoint[];
  height?: number;
  formatValue?: (value: number) => string;
  color?: string;
}

/** Zero-dependency inline SVG line chart for trend series (Daily Patient
 * Trend, Monthly Revenue, etc.) - see `BarChart.tsx` for the same rationale. */
export function LineChart({ data, height = 220, formatValue, color = "var(--color-primary, #2563eb)" }: LineChartProps) {
  if (data.length === 0) {
    return <div className="flex h-[220px] items-center justify-center text-sm text-muted-foreground">No data for this period</div>;
  }

  const maxValue = Math.max(...data.map((d) => d.value), 1);
  const minValue = Math.min(...data.map((d) => d.value), 0);
  const range = maxValue - minValue || 1;
  const width = Math.max(data.length * 48, 320);
  const chartHeight = height - 40;
  const padding = 24;

  const points = data.map((point, i) => {
    const x = data.length === 1 ? width / 2 : (i / (data.length - 1)) * (width - padding * 2) + padding;
    const y = chartHeight - ((point.value - minValue) / range) * chartHeight + 10;
    return { x, y, point };
  });

  const pathD = points.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x} ${p.y}`).join(" ");

  return (
    <div className="w-full overflow-x-auto">
      <svg viewBox={`0 0 ${width} ${height}`} width="100%" height={height} role="img" aria-label="Line chart">
        <path d={pathD} fill="none" stroke={color} strokeWidth={2} />
        {points.map(({ x, y, point }, i) => (
          <g key={`${point.label}-${i}`}>
            <circle cx={x} cy={y} r={3} fill={color}>
              <title>{`${point.label}: ${formatValue ? formatValue(point.value) : point.value}`}</title>
            </circle>
            {i % Math.ceil(points.length / 8 || 1) === 0 ? (
              <text x={x} y={chartHeight + 26} textAnchor="middle" className="fill-current text-[10px] text-muted-foreground">
                {point.label.length > 8 ? point.label.slice(5) : point.label}
              </text>
            ) : null}
          </g>
        ))}
      </svg>
    </div>
  );
}
