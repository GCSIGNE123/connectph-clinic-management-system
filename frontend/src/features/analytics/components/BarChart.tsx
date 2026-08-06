"use client";

import type { SeriesPoint } from "@/features/analytics/types";

export interface BarChartProps {
  data: SeriesPoint[];
  height?: number;
  formatValue?: (value: number) => string;
  color?: string;
}

/**
 * Zero-dependency inline SVG bar chart, consistent with this project's
 * convention of not pulling in a charting library (see `package.json` -
 * no chart package exists anywhere else in the app either). Responsive via
 * `viewBox` + `width="100%"`.
 */
export function BarChart({ data, height = 220, formatValue, color = "var(--color-primary, #2563eb)" }: BarChartProps) {
  if (data.length === 0) {
    return <div className="flex h-[220px] items-center justify-center text-sm text-muted-foreground">No data for this period</div>;
  }

  const maxValue = Math.max(...data.map((d) => d.value), 1);
  const width = Math.max(data.length * 56, 320);
  const chartHeight = height - 40;
  const barWidth = Math.min(40, (width / data.length) * 0.6);

  return (
    <div className="w-full overflow-x-auto">
      <svg viewBox={`0 0 ${width} ${height}`} width="100%" height={height} role="img" aria-label="Bar chart">
        {data.map((point, i) => {
          const barHeight = (point.value / maxValue) * chartHeight;
          const x = (i + 0.5) * (width / data.length) - barWidth / 2;
          const y = chartHeight - barHeight;
          return (
            <g key={`${point.label}-${i}`}>
              <rect x={x} y={y} width={barWidth} height={Math.max(barHeight, 1)} rx={3} fill={color} opacity={0.85}>
                <title>{`${point.label}: ${formatValue ? formatValue(point.value) : point.value}`}</title>
              </rect>
              <text x={x + barWidth / 2} y={chartHeight + 16} textAnchor="middle" className="fill-current text-[10px] text-muted-foreground">
                {point.label.length > 8 ? `${point.label.slice(0, 7)}…` : point.label}
              </text>
              <text x={x + barWidth / 2} y={y - 4} textAnchor="middle" className="fill-current text-[10px] text-foreground">
                {formatValue ? formatValue(point.value) : point.value}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
