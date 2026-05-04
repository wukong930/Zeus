"use client";

import { useId } from "react";

interface ReliabilityPoint {
  x: number;
  y: number;
}

interface ReliabilityCurveProps {
  points: ReliabilityPoint[];
  label?: string;
}

export function ReliabilityCurve({ points, label }: ReliabilityCurveProps) {
  const gradientId = useId().replace(/:/g, "");
  const rendered = points.length >= 2 ? points : [{ x: 0, y: 0 }, { x: 1, y: 1 }];
  const path = rendered
    .map((point, index) => `${index === 0 ? "M" : "L"} ${point.x * 400} ${(1 - point.y) * 240}`)
    .join(" ");
  const area = `${path} L ${rendered[rendered.length - 1].x * 400} 240 L ${rendered[0].x * 400} 240 Z`;

  return (
    <div className="relative h-64">
      <svg viewBox="0 0 400 240" className="h-full w-full">
        <defs>
          <linearGradient id={gradientId} x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="#10B981" stopOpacity="0.28" />
            <stop offset="100%" stopColor="#10B981" stopOpacity="0.02" />
          </linearGradient>
        </defs>
        <g className="zeus-chart-grid">
          {[0, 1, 2, 3, 4].map((i) => (
            <g key={i}>
              <line x1={i * 100} y1="0" x2={i * 100} y2="240" />
              <line x1="0" y1={i * 60} x2="400" y2={i * 60} />
            </g>
          ))}
        </g>
        <line x1="0" y1="240" x2="400" y2="0" stroke="#737373" strokeWidth="1" strokeDasharray="4 4" opacity="0.55" />
        <path d={area} fill={`url(#${gradientId})`} />
        <path d={path} className="zeus-data-line" fill="none" stroke="#10B981" strokeWidth="2" />
        {rendered.map((point, index) => (
          <circle
            key={`${point.x}-${point.y}-${index}`}
            cx={point.x * 400}
            cy={(1 - point.y) * 240}
            r="4"
            fill="#0A0A0A"
            stroke="#10B981"
            strokeWidth="2"
          />
        ))}
        <text x="10" y="18" className="fill-text-muted text-[10px]">
          observed hit rate
        </text>
        <text x="390" y="232" textAnchor="end" className="fill-text-muted text-[10px]">
          predicted confidence
        </text>
        {label && (
          <text x="200" y="22" textAnchor="middle" className="fill-text-secondary text-[11px]">
            {label}
          </text>
        )}
      </svg>
    </div>
  );
}
