"use client";

import { useId } from "react";

interface DriftSparklineProps {
  values: number[];
  threshold?: number;
}

export function DriftSparkline({ values, threshold = 0.25 }: DriftSparklineProps) {
  const gradientId = useId().replace(/:/g, "");
  const max = Math.max(threshold * 1.4, ...values, 0.3);
  const points = values.map((value, index) => ({
    x: (index / Math.max(values.length - 1, 1)) * 400,
    y: 180 - (value / max) * 150 - 15,
  }));
  const path = points
    .map((point, index) => `${index === 0 ? "M" : "L"} ${point.x} ${point.y}`)
    .join(" ");
  const area = `${path} L 400 180 L 0 180 Z`;
  const thresholdY = 180 - (threshold / max) * 150 - 15;

  return (
    <div className="h-48">
      <svg viewBox="0 0 400 180" className="h-full w-full">
        <defs>
          <linearGradient id={gradientId} x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="#38BDF8" stopOpacity="0.25" />
            <stop offset="100%" stopColor="#38BDF8" stopOpacity="0.02" />
          </linearGradient>
        </defs>
        <g className="zeus-chart-grid">
          {[0, 1, 2, 3].map((i) => (
            <line key={i} x1="0" y1={i * 60} x2="400" y2={i * 60} />
          ))}
        </g>
        <line x1="0" y1={thresholdY} x2="400" y2={thresholdY} stroke="#F59E0B" strokeWidth="1" strokeDasharray="4 4" opacity="0.7" />
        <text x="392" y={thresholdY - 6} textAnchor="end" className="fill-severity-high-fg font-mono text-[10px]">
          PSI {threshold.toFixed(2)}
        </text>
        <path d={area} fill={`url(#${gradientId})`} />
        <path d={path} fill="none" stroke="#38BDF8" strokeWidth="2" />
        {points.map((point, index) => (
          <circle key={index} cx={point.x} cy={point.y} r="2.5" fill="#38BDF8" />
        ))}
      </svg>
    </div>
  );
}
