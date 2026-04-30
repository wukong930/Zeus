"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { CAUSAL_EDGES, CAUSAL_NODES, type CausalEdge, type CausalNode } from "@/data/mock";
import { cn } from "@/lib/utils";

type Mode = "live" | "replay" | "explorer";

interface CausalWebProps {
  variant?: "full" | "preview";
  className?: string;
}

interface PositionedNode extends CausalNode {
  x: number;
  y: number;
}

const NODE_COLORS: Record<CausalNode["type"], string> = {
  event: "#38BDF8",
  signal: "#10B981",
  metric: "#A3A3A3",
  alert: "#F97316",
  counter: "#EF4444",
};

function nodeShape(type: CausalNode["type"], cx: number, cy: number, size: number, color: string, opacity: number) {
  const half = size / 2;
  switch (type) {
    case "event":
      // Hexagon
      const hexPoints = Array.from({ length: 6 }, (_, i) => {
        const angle = (Math.PI / 3) * i - Math.PI / 2;
        return [cx + half * Math.cos(angle), cy + half * Math.sin(angle)].join(",");
      }).join(" ");
      return (
        <polygon
          points={hexPoints}
          fill={color}
          fillOpacity={opacity * 0.25}
          stroke={color}
          strokeWidth="1.5"
          strokeOpacity={opacity}
        />
      );
    case "signal":
      // Diamond
      return (
        <polygon
          points={`${cx},${cy - half} ${cx + half},${cy} ${cx},${cy + half} ${cx - half},${cy}`}
          fill={color}
          fillOpacity={opacity * 0.25}
          stroke={color}
          strokeWidth="1.5"
          strokeOpacity={opacity}
        />
      );
    case "metric":
      // Square
      return (
        <rect
          x={cx - half}
          y={cy - half}
          width={size}
          height={size}
          fill={color}
          fillOpacity={opacity * 0.2}
          stroke={color}
          strokeWidth="1.5"
          strokeOpacity={opacity}
        />
      );
    case "alert":
      // Circle with halo
      return (
        <>
          <circle
            cx={cx}
            cy={cy}
            r={half + 6}
            fill={color}
            fillOpacity={opacity * 0.15}
          />
          <circle
            cx={cx}
            cy={cy}
            r={half}
            fill={color}
            fillOpacity={opacity * 0.4}
            stroke={color}
            strokeWidth="2"
            strokeOpacity={opacity}
          />
        </>
      );
    case "counter":
      return (
        <>
          <circle
            cx={cx}
            cy={cy}
            r={half}
            fill="none"
            stroke={color}
            strokeWidth="1.5"
            strokeOpacity={opacity}
            strokeDasharray="3 2"
          />
          <line
            x1={cx - half * 0.6}
            y1={cy - half * 0.6}
            x2={cx + half * 0.6}
            y2={cy + half * 0.6}
            stroke={color}
            strokeWidth="2"
            strokeOpacity={opacity}
          />
          <line
            x1={cx + half * 0.6}
            y1={cy - half * 0.6}
            x2={cx - half * 0.6}
            y2={cy + half * 0.6}
            stroke={color}
            strokeWidth="2"
            strokeOpacity={opacity}
          />
        </>
      );
  }
}

// Layered topological layout — group nodes by their layer
function computeLayout(width: number, height: number): PositionedNode[] {
  // Simple hand-tuned layout for demo
  const layout: Record<string, [number, number]> = {
    n1: [0.10, 0.20], // 美国航母移动
    n2: [0.30, 0.20], // 中东局势升级
    n3: [0.50, 0.30], // 原油 SC 上涨
    n4: [0.70, 0.20], // 化工链上行
    n5: [0.85, 0.10], // PTA 上涨
    n6: [0.85, 0.30], // PP 走强
    n7: [0.40, 0.50], // CFTC 持仓未增 (counter)
    n8: [0.10, 0.60], // 产区暴雨
    n9: [0.30, 0.60], // NR/RU 看涨
    n10: [0.55, 0.75], // 焦煤回落
    n11: [0.75, 0.75], // 高炉利润转负
    n12: [0.92, 0.65], // 螺纹成本支撑
  };
  return CAUSAL_NODES.map((n) => {
    const [px, py] = layout[n.id] ?? [0.5, 0.5];
    return {
      ...n,
      x: px * width,
      y: py * height,
    };
  });
}

interface ParticleAnimation {
  id: string;
  edgeId: string;
  startTime: number;
}

export function CausalWeb({ variant = "full", className }: CausalWebProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ width: 800, height: 500 });
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [mode, setMode] = useState<Mode>("live");
  const [particles, setParticles] = useState<ParticleAnimation[]>([]);

  useEffect(() => {
    const update = () => {
      if (containerRef.current) {
        const rect = containerRef.current.getBoundingClientRect();
        setSize({ width: rect.width, height: rect.height });
      }
    };
    update();
    window.addEventListener("resize", update);
    return () => window.removeEventListener("resize", update);
  }, []);

  const positioned = useMemo(() => computeLayout(size.width, size.height), [size]);

  // Highlight chain for selected/hovered node
  const focusId = selectedNode ?? hoveredNode;
  const highlightedNodeIds = useMemo(() => {
    if (!focusId) return new Set<string>();
    const ids = new Set<string>([focusId]);
    // Forward + backward traversal
    const visit = (id: string, dir: "fwd" | "bwd") => {
      CAUSAL_EDGES.forEach((e) => {
        if (dir === "fwd" && e.source === id && !ids.has(e.target)) {
          ids.add(e.target);
          visit(e.target, "fwd");
        }
        if (dir === "bwd" && e.target === id && !ids.has(e.source)) {
          ids.add(e.source);
          visit(e.source, "bwd");
        }
      });
    };
    visit(focusId, "fwd");
    visit(focusId, "bwd");
    return ids;
  }, [focusId]);

  const highlightedEdgeIds = useMemo(() => {
    if (!focusId) return new Set<string>();
    return new Set(
      CAUSAL_EDGES.filter(
        (e) => highlightedNodeIds.has(e.source) && highlightedNodeIds.has(e.target)
      ).map((e) => e.id)
    );
  }, [focusId, highlightedNodeIds]);

  // Live particle animation — every few seconds, pulse particles along active edges
  useEffect(() => {
    if (mode !== "live") return;
    const activeEdges = CAUSAL_EDGES.filter((e) => {
      const src = CAUSAL_NODES.find((n) => n.id === e.source);
      const tgt = CAUSAL_NODES.find((n) => n.id === e.target);
      return src?.active || tgt?.active;
    });
    if (activeEdges.length === 0) return;
    const interval = setInterval(() => {
      const edge = activeEdges[Math.floor(Math.random() * activeEdges.length)];
      const id = `p-${Date.now()}-${Math.random()}`;
      setParticles((prev) => [...prev, { id, edgeId: edge.id, startTime: Date.now() }]);
      setTimeout(() => {
        setParticles((prev) => prev.filter((p) => p.id !== id));
      }, 1800);
    }, 1500);
    return () => clearInterval(interval);
  }, [mode]);

  return (
    <div className={cn("relative w-full h-full bg-bg-base", className)} ref={containerRef}>
      {variant === "full" && (
        <div className="absolute top-4 left-4 z-10 flex gap-1 bg-bg-surface-overlay border border-border-default rounded-sm p-1">
          {(["live", "replay", "explorer"] as Mode[]).map((m) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              className={cn(
                "px-3 h-7 text-xs font-medium rounded-xs transition-colors",
                mode === m
                  ? "bg-brand-emerald text-white"
                  : "text-text-secondary hover:text-text-primary hover:bg-bg-surface-raised"
              )}
            >
              {m === "live" ? "Live" : m === "replay" ? "Replay" : "Explorer"}
            </button>
          ))}
        </div>
      )}

      <svg
        width={size.width}
        height={size.height}
        className="block"
        style={{ background: "radial-gradient(circle at center, #0a0a0a 0%, #000 80%)" }}
      >
        <defs>
          {/* Gradients for edges */}
          <linearGradient id="bullishEdge" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#F97316" stopOpacity="0.3" />
            <stop offset="100%" stopColor="#10B981" stopOpacity="0.7" />
          </linearGradient>
          <linearGradient id="bearishEdge" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#EF4444" stopOpacity="0.3" />
            <stop offset="100%" stopColor="#FB7185" stopOpacity="0.7" />
          </linearGradient>
          <filter id="glow">
            <feGaussianBlur stdDeviation="2" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* Edges */}
        {CAUSAL_EDGES.map((edge) => {
          const src = positioned.find((n) => n.id === edge.source)!;
          const tgt = positioned.find((n) => n.id === edge.target)!;
          const stroke =
            edge.direction === "bullish"
              ? "#F97316"
              : edge.direction === "bearish"
              ? "#EF4444"
              : "#737373";
          const isHighlighted = highlightedEdgeIds.has(edge.id);
          const isFaded = focusId !== null && !isHighlighted;
          const opacity = isFaded ? 0.15 : isHighlighted ? 1 : 0.5;
          const width = Math.max(1, edge.confidence * 4);

          // Compute path with slight curve
          const dx = tgt.x - src.x;
          const dy = tgt.y - src.y;
          const len = Math.sqrt(dx * dx + dy * dy);
          const curveOffset = Math.min(40, len * 0.15);
          const midX = (src.x + tgt.x) / 2;
          const midY = (src.y + tgt.y) / 2 - curveOffset;

          return (
            <g key={edge.id}>
              <path
                d={`M ${src.x} ${src.y} Q ${midX} ${midY} ${tgt.x} ${tgt.y}`}
                fill="none"
                stroke={stroke}
                strokeWidth={width}
                strokeOpacity={opacity}
                strokeDasharray={edge.verified ? "0" : "5 3"}
                strokeLinecap="round"
              />
              {/* Edge label on hover */}
              {isHighlighted && (
                <g>
                  <rect
                    x={midX - 32}
                    y={midY - 8}
                    width={64}
                    height={16}
                    rx={2}
                    fill="#1F1F1F"
                    stroke="#404040"
                    strokeWidth="0.5"
                  />
                  <text
                    x={midX}
                    y={midY + 3}
                    textAnchor="middle"
                    className="text-[10px] fill-text-secondary font-mono"
                  >
                    {edge.lag} · {(edge.hitRate * 100).toFixed(0)}%
                  </text>
                </g>
              )}
            </g>
          );
        })}

        {/* Particle animations along active edges */}
        {particles.map((p) => {
          const edge = CAUSAL_EDGES.find((e) => e.id === p.edgeId);
          if (!edge) return null;
          const src = positioned.find((n) => n.id === edge.source)!;
          const tgt = positioned.find((n) => n.id === edge.target)!;
          return (
            <ParticleDot key={p.id} src={src} tgt={tgt} startTime={p.startTime} />
          );
        })}

        {/* Nodes */}
        {positioned.map((node) => {
          const baseSize = [24, 32, 40, 48][node.influence - 1];
          const opacity = focusId !== null && !highlightedNodeIds.has(node.id) ? 0.2 : Math.max(0.4, node.freshness);
          const color = NODE_COLORS[node.type];
          const isFocused = node.id === focusId;
          const isActive = node.active;
          return (
            <g
              key={node.id}
              style={{ cursor: "pointer" }}
              onMouseEnter={() => setHoveredNode(node.id)}
              onMouseLeave={() => setHoveredNode(null)}
              onClick={() => setSelectedNode(selectedNode === node.id ? null : node.id)}
            >
              {/* Active pulse ring */}
              {isActive && !isFocused && (
                <circle
                  cx={node.x}
                  cy={node.y}
                  r={baseSize / 2 + 4}
                  fill="none"
                  stroke={color}
                  strokeWidth="1"
                  strokeOpacity={0.4}
                  className="animate-heartbeat"
                />
              )}
              {nodeShape(node.type, node.x, node.y, baseSize, color, opacity)}
              {/* Label */}
              <text
                x={node.x}
                y={node.y + baseSize / 2 + 14}
                textAnchor="middle"
                className="text-[11px] font-medium fill-text-primary pointer-events-none"
                style={{ opacity, filter: isFocused ? "url(#glow)" : "none" }}
              >
                {node.label}
              </text>
            </g>
          );
        })}
      </svg>

      {/* Selected node details */}
      {selectedNode && variant === "full" && (
        <div className="absolute top-16 right-4 w-72 bg-bg-surface-overlay border border-border-default rounded-sm p-4 shadow-md animate-fade-in">
          {(() => {
            const node = CAUSAL_NODES.find((n) => n.id === selectedNode)!;
            const upstream = CAUSAL_EDGES.filter((e) => e.target === selectedNode);
            const downstream = CAUSAL_EDGES.filter((e) => e.source === selectedNode);
            return (
              <>
                <div className="flex items-center justify-between mb-3">
                  <span className="text-h3 font-semibold">{node.label}</span>
                  <button
                    className="text-text-muted hover:text-text-primary"
                    onClick={() => setSelectedNode(null)}
                  >
                    ✕
                  </button>
                </div>
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-text-muted">类型</span>
                    <span className="font-medium" style={{ color: NODE_COLORS[node.type] }}>
                      {node.type}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-text-muted">影响力</span>
                    <span className="font-mono">{node.influence} / 4</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-text-muted">活跃度</span>
                    <span>{node.active ? "🟢 活跃" : "○ 静默"}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-text-muted">新鲜度</span>
                    <span className="font-mono">{(node.freshness * 100).toFixed(0)}%</span>
                  </div>
                </div>
                {upstream.length > 0 && (
                  <div className="mt-4">
                    <div className="text-caption text-text-muted uppercase mb-1">上游 {upstream.length}</div>
                    {upstream.map((e) => {
                      const src = CAUSAL_NODES.find((n) => n.id === e.source);
                      return (
                        <div key={e.id} className="text-caption text-text-secondary">
                          ← {src?.label} <span className="font-mono text-text-muted">({(e.hitRate * 100).toFixed(0)}%)</span>
                        </div>
                      );
                    })}
                  </div>
                )}
                {downstream.length > 0 && (
                  <div className="mt-3">
                    <div className="text-caption text-text-muted uppercase mb-1">下游 {downstream.length}</div>
                    {downstream.map((e) => {
                      const tgt = CAUSAL_NODES.find((n) => n.id === e.target);
                      return (
                        <div key={e.id} className="text-caption text-text-secondary">
                          → {tgt?.label} <span className="font-mono text-text-muted">({(e.hitRate * 100).toFixed(0)}%)</span>
                        </div>
                      );
                    })}
                  </div>
                )}
              </>
            );
          })()}
        </div>
      )}

      {/* Legend */}
      {variant === "full" && (
        <div className="absolute bottom-4 left-4 bg-bg-surface-overlay border border-border-default rounded-sm p-3 text-caption space-y-1">
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded-full" style={{ background: NODE_COLORS.event, opacity: 0.5 }} /> 事件
          </div>
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rotate-45" style={{ background: NODE_COLORS.signal, opacity: 0.5 }} /> 信号
          </div>
          <div className="flex items-center gap-2">
            <div className="w-3 h-3" style={{ background: NODE_COLORS.metric, opacity: 0.5 }} /> 指标
          </div>
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded-full" style={{ background: NODE_COLORS.alert }} /> 预警
          </div>
          <div className="flex items-center gap-2 text-data-down">
            <span>✕</span> 反证
          </div>
        </div>
      )}
    </div>
  );
}

function ParticleDot({
  src,
  tgt,
  startTime,
}: {
  src: PositionedNode;
  tgt: PositionedNode;
  startTime: number;
}) {
  const [t, setT] = useState(0);

  useEffect(() => {
    let raf = 0;
    const animate = () => {
      const elapsed = (Date.now() - startTime) / 1500; // 1.5s travel time
      if (elapsed >= 1) return;
      setT(elapsed);
      raf = requestAnimationFrame(animate);
    };
    raf = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(raf);
  }, [startTime]);

  const dx = tgt.x - src.x;
  const dy = tgt.y - src.y;
  const len = Math.sqrt(dx * dx + dy * dy);
  const curveOffset = Math.min(40, len * 0.15);
  // Quadratic bezier interpolation
  const midX = (src.x + tgt.x) / 2;
  const midY = (src.y + tgt.y) / 2 - curveOffset;
  const x = (1 - t) * (1 - t) * src.x + 2 * (1 - t) * t * midX + t * t * tgt.x;
  const y = (1 - t) * (1 - t) * src.y + 2 * (1 - t) * t * midY + t * t * tgt.y;

  return (
    <circle
      cx={x}
      cy={y}
      r={3}
      fill="#F97316"
      opacity={Math.sin(t * Math.PI)}
      filter="url(#glow)"
    />
  );
}
