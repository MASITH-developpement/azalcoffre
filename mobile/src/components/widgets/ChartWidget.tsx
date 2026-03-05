import React, { useMemo } from 'react';

export interface ChartDataPoint {
  /** Label for the data point */
  label: string;
  /** Numeric value */
  value: number;
}

export type ChartType = 'bar' | 'line';

export interface ChartWidgetProps {
  /** Widget title */
  title: string;
  /** Data points to display */
  data: ChartDataPoint[];
  /** Chart type */
  type?: ChartType;
  /** Chart color (CSS color or Tailwind class) */
  color?: string;
  /** Loading state */
  loading?: boolean;
  /** Chart height in pixels */
  height?: number;
}

/**
 * Skeleton loader for ChartWidget
 */
const ChartSkeleton: React.FC<{ height: number }> = ({ height }) => (
  <div className="bg-white rounded-xl border border-gray-100 shadow-sm overflow-hidden animate-pulse">
    <div className="px-4 py-3 border-b border-gray-100">
      <div className="h-5 w-32 bg-gray-200 rounded" />
    </div>
    <div className="p-4">
      <div
        style={{ height }}
        className="bg-gray-100 rounded-lg flex items-end justify-around gap-2 p-4"
      >
        {Array.from({ length: 7 }).map((_, i) => (
          <div
            key={i}
            className="bg-gray-200 rounded-t"
            style={{
              width: '100%',
              height: `${20 + Math.random() * 60}%`,
            }}
          />
        ))}
      </div>
    </div>
  </div>
);

/**
 * Empty state for no data
 */
const EmptyChart: React.FC<{ height: number }> = ({ height }) => (
  <div
    style={{ height }}
    className="flex items-center justify-center text-gray-400"
  >
    <div className="text-center">
      <svg
        className="w-10 h-10 mx-auto text-gray-300"
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
        strokeWidth={1.5}
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z"
        />
      </svg>
      <p className="mt-2 text-sm">Aucune donnee</p>
    </div>
  </div>
);

/**
 * Bar Chart Component (SVG-based)
 */
const BarChart: React.FC<{
  data: ChartDataPoint[];
  color: string;
  height: number;
}> = ({ data, color, height }) => {
  const maxValue = useMemo(
    () => Math.max(...data.map((d) => d.value), 1),
    [data]
  );

  const barWidth = 100 / data.length;
  const barGap = barWidth * 0.2;
  const actualBarWidth = barWidth - barGap;

  return (
    <div style={{ height }}>
      <svg
        width="100%"
        height="100%"
        viewBox={`0 0 100 ${height}`}
        preserveAspectRatio="none"
        className="overflow-visible"
      >
        {data.map((point, index) => {
          const barHeight = (point.value / maxValue) * (height - 24);
          const x = index * barWidth + barGap / 2;
          const y = height - barHeight - 20;

          return (
            <g key={point.label}>
              {/* Bar */}
              <rect
                x={`${x}%`}
                y={y}
                width={`${actualBarWidth}%`}
                height={barHeight}
                fill={color}
                rx="2"
                className="transition-all duration-300"
              />
              {/* Label */}
              <text
                x={`${x + actualBarWidth / 2}%`}
                y={height - 4}
                textAnchor="middle"
                className="text-[8px] fill-gray-500"
              >
                {point.label}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
};

/**
 * Line Chart Component (SVG-based)
 */
const LineChart: React.FC<{
  data: ChartDataPoint[];
  color: string;
  height: number;
}> = ({ data, color, height }) => {
  const maxValue = useMemo(
    () => Math.max(...data.map((d) => d.value), 1),
    [data]
  );

  const points = useMemo(() => {
    return data.map((point, index) => {
      const x = (index / (data.length - 1 || 1)) * 100;
      const y = height - 24 - (point.value / maxValue) * (height - 40);
      return { x, y, ...point };
    });
  }, [data, height, maxValue]);

  const pathD = useMemo(() => {
    const firstPoint = points[0];
    if (points.length === 0 || !firstPoint) return '';
    const start = `M ${firstPoint.x} ${firstPoint.y}`;
    const lines = points.slice(1).map((p) => `L ${p.x} ${p.y}`);
    return `${start} ${lines.join(' ')}`;
  }, [points]);

  const areaD = useMemo(() => {
    const firstPoint = points[0];
    const lastPoint = points[points.length - 1];
    if (points.length === 0 || !firstPoint || !lastPoint) return '';
    const chartBottom = height - 24;
    const start = `M ${firstPoint.x} ${chartBottom}`;
    const toFirst = `L ${firstPoint.x} ${firstPoint.y}`;
    const lines = points.slice(1).map((p) => `L ${p.x} ${p.y}`);
    const toLast = `L ${lastPoint.x} ${chartBottom}`;
    return `${start} ${toFirst} ${lines.join(' ')} ${toLast} Z`;
  }, [points, height]);

  return (
    <div style={{ height }}>
      <svg
        width="100%"
        height="100%"
        viewBox={`0 0 100 ${height}`}
        preserveAspectRatio="none"
        className="overflow-visible"
      >
        {/* Area fill */}
        <path d={areaD} fill={color} fillOpacity="0.1" />

        {/* Line */}
        <path
          d={pathD}
          fill="none"
          stroke={color}
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          vectorEffect="non-scaling-stroke"
        />

        {/* Points */}
        {points.map((point) => (
          <circle
            key={point.label}
            cx={point.x}
            cy={point.y}
            r="3"
            fill="white"
            stroke={color}
            strokeWidth="2"
            vectorEffect="non-scaling-stroke"
          />
        ))}

        {/* Labels */}
        {points.map((point, index) => {
          // Only show some labels to avoid crowding
          const showLabel =
            data.length <= 7 || index === 0 || index === data.length - 1;
          if (!showLabel) return null;

          return (
            <text
              key={point.label}
              x={point.x}
              y={height - 4}
              textAnchor="middle"
              className="text-[8px] fill-gray-500"
            >
              {point.label}
            </text>
          );
        })}
      </svg>
    </div>
  );
};

/**
 * ChartWidget - Simple bar/line chart widget for dashboards.
 * Uses basic SVG for minimal bundle size (no heavy chart library).
 * Mobile-optimized with responsive sizing.
 */
export const ChartWidget: React.FC<ChartWidgetProps> = ({
  title,
  data,
  type = 'bar',
  color = '#2563EB', // Primary blue
  loading = false,
  height = 120,
}) => {
  if (loading) {
    return <ChartSkeleton height={height} />;
  }

  return (
    <div className="bg-white rounded-xl border border-gray-100 shadow-sm overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-gray-100">
        <h3 className="text-base font-semibold text-gray-900">{title}</h3>
      </div>

      {/* Chart */}
      <div className="p-4">
        {data.length === 0 ? (
          <EmptyChart height={height} />
        ) : type === 'bar' ? (
          <BarChart data={data} color={color} height={height} />
        ) : (
          <LineChart data={data} color={color} height={height} />
        )}
      </div>
    </div>
  );
};

ChartWidget.displayName = 'ChartWidget';

export default ChartWidget;
