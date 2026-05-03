"use client";

import { useCallback, useMemo, useState } from "react";
import {
  Background,
  BackgroundVariant,
  BaseEdge,
  Controls,
  EdgeLabelRenderer,
  Handle,
  MarkerType,
  MiniMap,
  Panel,
  Position,
  ReactFlow,
  ReactFlowProvider,
  getBezierPath,
  useReactFlow,
  type Edge,
  type EdgeProps,
  type EdgeTypes,
  type Node,
  type NodeProps,
  type NodeTypes,
  type ReactFlowInstance,
} from "@xyflow/react";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  CircleDot,
  GitBranch,
  Maximize2,
  Network,
  Pause,
  Play,
  RotateCcw,
  Search,
  ShieldX,
  X,
} from "lucide-react";
import { CAUSAL_EDGES, CAUSAL_NODES, type CausalEdge, type CausalNode } from "@/data/mock";
import { cn } from "@/lib/utils";

type Mode = "live" | "replay" | "explorer";

interface CausalWebProps {
  variant?: "full" | "preview";
  className?: string;
}

interface CausalFlowNodeData extends Record<string, unknown> {
  causal: CausalNode;
  upstream: number;
  downstream: number;
  focused: boolean;
  dimmed: boolean;
  variant: "full" | "preview";
}

interface CausalFlowEdgeData extends Record<string, unknown> {
  causal: CausalEdge;
  focused: boolean;
  dimmed: boolean;
  live: boolean;
  showLabel: boolean;
}

type CausalFlowNode = Node<CausalFlowNodeData, "causalNode">;
type CausalFlowEdge = Edge<CausalFlowEdgeData, "causalEdge">;

const NODE_COLORS: Record<CausalNode["type"], string> = {
  event: "#38BDF8",
  signal: "#10B981",
  metric: "#A3A3A3",
  alert: "#F97316",
  counter: "#EF4444",
};

const EDGE_COLORS: Record<CausalEdge["direction"], string> = {
  bullish: "#F97316",
  bearish: "#EF4444",
  neutral: "#737373",
};

const NODE_LABELS: Record<CausalNode["type"], string> = {
  event: "事件",
  signal: "信号",
  metric: "指标",
  alert: "预警",
  counter: "反证",
};

const MODE_META: Record<Mode, { label: string; icon: typeof Play }> = {
  live: { label: "Live", icon: Play },
  replay: { label: "Replay", icon: RotateCcw },
  explorer: { label: "Explorer", icon: Search },
};

const FLOW_LAYOUT: Record<string, { x: number; y: number }> = {
  n1: { x: 40, y: 110 },
  n2: { x: 280, y: 100 },
  n3: { x: 530, y: 190 },
  n4: { x: 760, y: 110 },
  n5: { x: 1040, y: 40 },
  n6: { x: 1050, y: 220 },
  n7: { x: 340, y: 360 },
  n8: { x: 40, y: 470 },
  n9: { x: 300, y: 480 },
  n10: { x: 560, y: 620 },
  n11: { x: 810, y: 610 },
  n12: { x: 1060, y: 500 },
};

const fitViewOptions = { padding: 0.18, duration: 500 };
const previewFitViewOptions = { padding: 0.08, duration: 500 };

const nodeTypes = {
  causalNode: CausalNodeCard,
} satisfies NodeTypes;

const edgeTypes = {
  causalEdge: CausalEdgeLine,
} satisfies EdgeTypes;

export function CausalWeb(props: CausalWebProps) {
  return (
    <ReactFlowProvider>
      <CausalWebCanvas {...props} />
    </ReactFlowProvider>
  );
}

function CausalWebCanvas({ variant = "full", className }: CausalWebProps) {
  const flow = useReactFlow<CausalFlowNode, CausalFlowEdge>();
  const [mode, setMode] = useState<Mode>("live");
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const focusId = selectedNode ?? hoveredNode;
  const isFull = variant === "full";

  const highlightedNodeIds = useMemo(() => causalChainIds(focusId), [focusId]);
  const highlightedEdgeIds = useMemo(() => {
    if (!focusId) return new Set<string>();
    return new Set(
      CAUSAL_EDGES.filter(
        (edge) => highlightedNodeIds.has(edge.source) && highlightedNodeIds.has(edge.target)
      ).map((edge) => edge.id)
    );
  }, [focusId, highlightedNodeIds]);

  const relationCounts = useMemo(() => {
    const counts = new Map<string, { upstream: number; downstream: number }>();
    for (const node of CAUSAL_NODES) {
      counts.set(node.id, { upstream: 0, downstream: 0 });
    }
    for (const edge of CAUSAL_EDGES) {
      const source = counts.get(edge.source);
      const target = counts.get(edge.target);
      if (source) source.downstream += 1;
      if (target) target.upstream += 1;
    }
    return counts;
  }, []);

  const nodes = useMemo<CausalFlowNode[]>(
    () =>
      CAUSAL_NODES.map((node) => {
        const counts = relationCounts.get(node.id) ?? { upstream: 0, downstream: 0 };
        const focused = focusId === node.id || highlightedNodeIds.has(node.id);
        const dimmed = Boolean(focusId) && !focused;
        return {
          id: node.id,
          type: "causalNode",
          position: FLOW_LAYOUT[node.id] ?? { x: 520, y: 320 },
          data: {
            causal: node,
            upstream: counts.upstream,
            downstream: counts.downstream,
            focused,
            dimmed,
            variant,
          },
          draggable: isFull && mode === "explorer",
          selectable: isFull,
        };
      }),
    [focusId, highlightedNodeIds, isFull, mode, relationCounts, variant]
  );

  const edges = useMemo<CausalFlowEdge[]>(
    () =>
      CAUSAL_EDGES.map((edge) => {
        const focused = highlightedEdgeIds.has(edge.id);
        const dimmed = Boolean(focusId) && !focused;
        const live =
          mode === "live" &&
          (CAUSAL_NODES.find((node) => node.id === edge.source)?.active ||
            CAUSAL_NODES.find((node) => node.id === edge.target)?.active);
        const color = EDGE_COLORS[edge.direction];
        return {
          id: edge.id,
          type: "causalEdge",
          source: edge.source,
          target: edge.target,
          animated: live && !dimmed,
          markerEnd: {
            type: MarkerType.ArrowClosed,
            width: 18,
            height: 18,
            color,
          },
          data: {
            causal: edge,
            focused,
            dimmed,
            live: Boolean(live),
            showLabel: isFull && (focused || mode === "explorer"),
          },
        };
      }),
    [focusId, highlightedEdgeIds, isFull, mode]
  );

  const selected = selectedNode ? CAUSAL_NODES.find((node) => node.id === selectedNode) : null;

  const fitCanvas = useCallback(() => {
    void flow.fitView(isFull ? fitViewOptions : previewFitViewOptions);
  }, [flow, isFull]);

  const onInit = useCallback(
    (instance: ReactFlowInstance<CausalFlowNode, CausalFlowEdge>) => {
      window.setTimeout(() => {
        void instance.fitView(isFull ? fitViewOptions : previewFitViewOptions);
      }, 0);
    },
    [isFull]
  );

  return (
    <div className={cn("causal-web-flow relative h-full w-full overflow-hidden bg-bg-base", className)}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onInit={onInit}
        onNodeMouseEnter={(_, node) => setHoveredNode(node.id)}
        onNodeMouseLeave={() => setHoveredNode(null)}
        onNodeClick={(_, node) => {
          if (isFull) setSelectedNode((current) => (current === node.id ? null : node.id));
        }}
        onPaneClick={() => {
          setSelectedNode(null);
          setHoveredNode(null);
        }}
        fitView
        fitViewOptions={isFull ? fitViewOptions : previewFitViewOptions}
        minZoom={0.35}
        maxZoom={1.8}
        nodesDraggable={isFull && mode === "explorer"}
        nodesConnectable={false}
        edgesFocusable={isFull}
        elementsSelectable={isFull}
        panOnDrag={isFull}
        zoomOnScroll={isFull}
        zoomOnPinch={isFull}
        zoomOnDoubleClick={isFull}
        preventScrolling={isFull}
        proOptions={{ hideAttribution: true }}
      >
        <Background
          variant={BackgroundVariant.Dots}
          gap={26}
          size={1}
          color="rgba(115, 115, 115, 0.22)"
        />

        {isFull && (
          <>
            <Panel position="top-left" className="m-4">
              <div className="flex items-center gap-2 rounded-sm border border-border-default bg-bg-surface-overlay p-1 shadow-md">
                {(Object.keys(MODE_META) as Mode[]).map((item) => {
                  const meta = MODE_META[item];
                  const Icon = meta.icon;
                  return (
                    <button
                      key={item}
                      type="button"
                      title={meta.label}
                      onClick={() => setMode(item)}
                      className={cn(
                        "flex h-8 items-center gap-2 rounded-xs px-3 text-xs font-medium transition-colors",
                        mode === item
                          ? "bg-brand-emerald text-white"
                          : "text-text-secondary hover:bg-bg-surface-raised hover:text-text-primary"
                      )}
                    >
                      <Icon className="h-3.5 w-3.5" />
                      {meta.label}
                    </button>
                  );
                })}
                <button
                  type="button"
                  title="Fit view"
                  onClick={fitCanvas}
                  className="flex h-8 w-8 items-center justify-center rounded-xs text-text-secondary transition-colors hover:bg-bg-surface-raised hover:text-text-primary"
                >
                  <Maximize2 className="h-3.5 w-3.5" />
                </button>
              </div>
            </Panel>

            <Panel position="top-right" className="m-4">
              <GraphStats focusId={focusId} mode={mode} />
            </Panel>

            <Panel position="bottom-left" className="m-4">
              <Legend />
            </Panel>

            <Controls
              position="bottom-right"
              showInteractive={false}
              fitViewOptions={fitViewOptions}
            />

            <MiniMap
              position="bottom-right"
              pannable
              zoomable
              nodeColor={(node) => NODE_COLORS[(node.data as CausalFlowNodeData).causal.type]}
              nodeStrokeWidth={2}
              className="!bottom-20 !right-4 !h-28 !w-44 !rounded-sm !border !border-border-default !bg-bg-surface-overlay"
            />
          </>
        )}
      </ReactFlow>

      {isFull && selected && (
        <NodeDetails node={selected} onClose={() => setSelectedNode(null)} />
      )}
    </div>
  );
}

function CausalNodeCard({ data, selected }: NodeProps<CausalFlowNode>) {
  const node = data.causal;
  const color = NODE_COLORS[node.type];
  const compact = data.variant === "preview";
  const Icon = nodeIcon(node.type);

  return (
    <div
      className={cn(
        "group relative rounded-sm border bg-bg-surface-overlay shadow-md transition duration-200",
        compact ? "min-w-[136px] px-3 py-2" : "min-w-[172px] px-3.5 py-3",
        data.dimmed && "scale-[0.98] opacity-30",
        data.focused && "shadow-lg",
        selected && "ring-1 ring-brand-emerald"
      )}
      style={{
        borderColor: data.focused ? color : "rgba(64, 64, 64, 0.92)",
        boxShadow: data.focused
          ? `0 0 0 1px ${color}55, 0 18px 42px rgba(0, 0, 0, 0.35)`
          : undefined,
      }}
    >
      <Handle type="target" position={Position.Left} className="!h-2 !w-2 !opacity-0" />
      <Handle type="source" position={Position.Right} className="!h-2 !w-2 !opacity-0" />

      {node.active && (
        <span
          className="pointer-events-none absolute -inset-1 rounded-sm border opacity-40 animate-heartbeat"
          style={{ borderColor: color }}
        />
      )}

      <div className="flex items-start gap-3">
        <div
          className={cn(
            "mt-0.5 flex shrink-0 items-center justify-center border",
            compact ? "h-7 w-7" : "h-8 w-8",
            node.type === "event" && "causal-node-hex",
            node.type === "signal" && "rotate-45",
            node.type === "metric" && "rounded-xs",
            node.type === "alert" && "rounded-full",
            node.type === "counter" && "rounded-full border-dashed"
          )}
          style={{
            backgroundColor: `${color}26`,
            borderColor: color,
            color,
          }}
        >
          <Icon className={cn("h-4 w-4", node.type === "signal" && "-rotate-45")} />
        </div>

        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="truncate text-sm font-semibold text-text-primary">{node.label}</span>
            {node.active && (
              <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-brand-emerald-bright" />
            )}
          </div>
          <div className="mt-1 flex items-center gap-2 text-caption text-text-muted">
            <span style={{ color }}>{NODE_LABELS[node.type]}</span>
            <span className="font-mono">{Math.round(node.freshness * 100)}%</span>
            {!compact && <span className="font-mono">I{node.influence}</span>}
          </div>
        </div>
      </div>

      {!compact && (
        <div className="mt-3 grid grid-cols-2 gap-2 border-t border-border-subtle pt-2 text-caption">
          <div className="flex items-center gap-1.5 text-text-muted">
            <GitBranch className="h-3 w-3" />
            <span className="font-mono">{data.upstream}</span>
            <span>上游</span>
          </div>
          <div className="flex items-center justify-end gap-1.5 text-text-muted">
            <span>下游</span>
            <span className="font-mono">{data.downstream}</span>
            <Network className="h-3 w-3" />
          </div>
        </div>
      )}
    </div>
  );
}

function CausalEdgeLine({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  markerEnd,
  data,
}: EdgeProps<CausalFlowEdge>) {
  const edge = data?.causal;
  if (!edge) return null;

  const color = EDGE_COLORS[edge.direction];
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
    curvature: 0.28,
  });
  const strokeWidth = Math.max(1.4, edge.confidence * 4.6);
  const opacity = data.dimmed ? 0.18 : data.focused ? 0.95 : 0.58;

  return (
    <>
      <BaseEdge
        id={id}
        path={edgePath}
        markerEnd={markerEnd}
        style={{
          stroke: color,
          strokeWidth,
          opacity,
          strokeDasharray: edge.verified ? undefined : "6 5",
        }}
      />
      {data.live && !data.dimmed && (
        <BaseEdge
          path={edgePath}
          style={{
            stroke: color,
            strokeWidth: Math.max(1, strokeWidth - 1),
            opacity: 0.72,
            strokeDasharray: "8 18",
            animation: "causal-flow-dash 1.4s linear infinite",
          }}
        />
      )}
      {data.showLabel && !data.dimmed && (
        <EdgeLabelRenderer>
          <div
            className="nodrag nopan absolute rounded-xs border border-border-default bg-bg-surface-overlay px-2 py-1 text-caption text-text-secondary shadow-sm"
            style={{
              transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
            }}
          >
            <span className="font-mono text-text-primary">{edge.lag}</span>
            <span className="mx-1 text-text-muted">·</span>
            <span className="font-mono">{Math.round(edge.hitRate * 100)}%</span>
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}

function GraphStats({ focusId, mode }: { focusId: string | null; mode: Mode }) {
  const activeNodes = CAUSAL_NODES.filter((node) => node.active).length;
  const verifiedEdges = CAUSAL_EDGES.filter((edge) => edge.verified).length;
  const ModeIcon = mode === "live" ? Activity : mode === "replay" ? RotateCcw : Search;

  return (
    <div className="grid grid-cols-3 gap-2 rounded-sm border border-border-default bg-bg-surface-overlay p-2 shadow-md">
      <StatCell icon={ModeIcon} label="Mode" value={mode} />
      <StatCell icon={CircleDot} label="Active" value={`${activeNodes}/${CAUSAL_NODES.length}`} />
      <StatCell icon={CheckCircle2} label="Verified" value={`${verifiedEdges}/${CAUSAL_EDGES.length}`} />
      {focusId && (
        <div className="col-span-3 border-t border-border-subtle pt-2 text-caption text-text-muted">
          Focus: <span className="text-text-primary">{CAUSAL_NODES.find((node) => node.id === focusId)?.label}</span>
        </div>
      )}
    </div>
  );
}

function StatCell({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof Activity;
  label: string;
  value: string;
}) {
  return (
    <div className="min-w-24 rounded-xs bg-bg-base px-3 py-2">
      <div className="flex items-center gap-1.5 text-caption text-text-muted">
        <Icon className="h-3 w-3" />
        {label}
      </div>
      <div className="mt-1 font-mono text-sm text-text-primary">{value}</div>
    </div>
  );
}

function NodeDetails({ node, onClose }: { node: CausalNode; onClose: () => void }) {
  const upstream = CAUSAL_EDGES.filter((edge) => edge.target === node.id);
  const downstream = CAUSAL_EDGES.filter((edge) => edge.source === node.id);
  const color = NODE_COLORS[node.type];
  const Icon = nodeIcon(node.type);

  return (
    <div className="absolute right-4 top-20 z-20 w-80 rounded-sm border border-border-default bg-bg-surface-overlay p-4 shadow-xl animate-fade-in">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <div
            className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-sm border"
            style={{ borderColor: color, backgroundColor: `${color}22`, color }}
          >
            <Icon className="h-4 w-4" />
          </div>
          <div>
            <div className="text-h3 text-text-primary">{node.label}</div>
            <div className="mt-1 text-caption" style={{ color }}>
              {NODE_LABELS[node.type]}
            </div>
          </div>
        </div>
        <button
          type="button"
          title="Close"
          onClick={onClose}
          className="flex h-7 w-7 items-center justify-center rounded-xs text-text-muted transition-colors hover:bg-bg-surface-raised hover:text-text-primary"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="mt-4 grid grid-cols-3 gap-2">
        <DetailMetric label="Fresh" value={`${Math.round(node.freshness * 100)}%`} />
        <DetailMetric label="Impact" value={`${node.influence}/4`} />
        <DetailMetric label="State" value={node.active ? "Active" : "Quiet"} />
      </div>

      <EdgeList title="上游" edges={upstream} side="source" />
      <EdgeList title="下游" edges={downstream} side="target" />
    </div>
  );
}

function DetailMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xs bg-bg-base p-2">
      <div className="text-caption text-text-muted">{label}</div>
      <div className="mt-1 font-mono text-sm text-text-primary">{value}</div>
    </div>
  );
}

function EdgeList({
  title,
  edges,
  side,
}: {
  title: string;
  edges: CausalEdge[];
  side: "source" | "target";
}) {
  if (edges.length === 0) return null;
  return (
    <div className="mt-4">
      <div className="mb-2 text-caption uppercase tracking-wide text-text-muted">
        {title} {edges.length}
      </div>
      <div className="space-y-2">
        {edges.map((edge) => {
          const peer = CAUSAL_NODES.find((node) => node.id === edge[side]);
          const color = EDGE_COLORS[edge.direction];
          return (
            <div key={edge.id} className="rounded-xs border border-border-subtle bg-bg-base p-2">
              <div className="flex items-center justify-between gap-2">
                <span className="truncate text-sm text-text-secondary">{peer?.label}</span>
                <span className="font-mono text-caption" style={{ color }}>
                  {Math.round(edge.confidence * 100)}%
                </span>
              </div>
              <div className="mt-1 flex items-center justify-between text-caption text-text-muted">
                <span>{edge.lag}</span>
                <span className="font-mono">hit {Math.round(edge.hitRate * 100)}%</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function Legend() {
  return (
    <div className="rounded-sm border border-border-default bg-bg-surface-overlay p-3 shadow-md">
      <div className="mb-2 flex items-center gap-2 text-caption font-medium text-text-secondary">
        <Network className="h-3.5 w-3.5" />
        Causal Layers
      </div>
      <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-caption text-text-muted">
        {(Object.keys(NODE_LABELS) as CausalNode["type"][]).map((type) => {
          const Icon = nodeIcon(type);
          return (
            <div key={type} className="flex items-center gap-2">
              <span
                className="flex h-4 w-4 items-center justify-center rounded-xs border"
                style={{ borderColor: NODE_COLORS[type], color: NODE_COLORS[type] }}
              >
                <Icon className="h-2.5 w-2.5" />
              </span>
              {NODE_LABELS[type]}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function causalChainIds(focusId: string | null): Set<string> {
  if (!focusId) return new Set<string>();
  const ids = new Set<string>([focusId]);
  const visit = (id: string, direction: "forward" | "backward") => {
    for (const edge of CAUSAL_EDGES) {
      if (direction === "forward" && edge.source === id && !ids.has(edge.target)) {
        ids.add(edge.target);
        visit(edge.target, "forward");
      }
      if (direction === "backward" && edge.target === id && !ids.has(edge.source)) {
        ids.add(edge.source);
        visit(edge.source, "backward");
      }
    }
  };
  visit(focusId, "forward");
  visit(focusId, "backward");
  return ids;
}

function nodeIcon(type: CausalNode["type"]) {
  switch (type) {
    case "event":
      return Activity;
    case "signal":
      return GitBranch;
    case "metric":
      return CircleDot;
    case "alert":
      return AlertTriangle;
    case "counter":
      return ShieldX;
  }
}
