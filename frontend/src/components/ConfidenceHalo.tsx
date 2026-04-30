"use client";

import { cn } from "@/lib/utils";

interface ConfidenceHaloProps {
  confidence: number; // 0..1
  sampleSize: number;
  size?: number;
  className?: string;
}

/**
 * Confidence Halo (§4.3 of DESIGN_SYSTEM.md)
 * - Ring thickness encodes sample size (thin=few samples, thick=many)
 * - Ring fullness encodes confidence interval width
 * - Color encodes calibration maturity (warm orange in warmup, emerald when mature)
 */
export function ConfidenceHalo({ confidence, sampleSize, size = 56, className }: ConfidenceHaloProps) {
  const radius = size / 2 - 4;
  const circumference = 2 * Math.PI * radius;
  const fullness = Math.max(0.2, Math.min(1, confidence));
  const dashOffset = circumference * (1 - fullness);
  const strokeWidth = sampleSize < 30 ? 2 : sampleSize < 100 ? 3 : 4;
  const isMature = sampleSize >= 30;
  const stroke = isMature ? "#10B981" : "#F97316";

  return (
    <div
      className={cn("relative inline-flex items-center justify-center", className)}
      style={{ width: size, height: size }}
    >
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="#1A1A1A"
          strokeWidth={strokeWidth}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={stroke}
          strokeWidth={strokeWidth}
          strokeDasharray={circumference}
          strokeDashoffset={dashOffset}
          strokeLinecap="round"
          style={{ transition: "stroke-dashoffset 600ms cubic-bezier(0,0,0.2,1)" }}
        />
      </svg>
      <div className="absolute inset-0 flex items-center justify-center font-mono text-sm font-semibold tabular-nums">
        {Math.round(confidence * 100)}
      </div>
    </div>
  );
}
