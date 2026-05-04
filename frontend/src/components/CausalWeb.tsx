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
  Position,
  ReactFlow,
  ReactFlowProvider,
  ViewportPortal,
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
  Briefcase,
  CheckCircle2,
  Clock,
  CircleDot,
  GitBranch,
  Layers,
  Maximize2,
  Network,
  Play,
  RotateCcw,
  Route,
  Search,
  ShieldCheck,
  ShieldX,
  Target,
  X,
} from "lucide-react";
import { CAUSAL_EDGES, CAUSAL_NODES, type CausalEdge, type CausalNode } from "@/data/mock";
import { cn } from "@/lib/utils";

type Mode = "live" | "replay" | "explorer";
type View = "all" | "portfolio" | "counter" | "alerts";
type Stage = "source" | "thesis" | "validation" | "impact";
type Sector = "geo" | "energy" | "rubber" | "ferrous" | "positioning";
type IconComponent = typeof Activity;

interface CausalWebProps {
  variant?: "full" | "preview";
  className?: string;
}

interface CausalFlowNodeData extends Record<string, unknown> {
  causal: CausalNode;
  meta: NodeSemanticMeta;
  upstream: number;
  downstream: number;
  focused: boolean;
  dimmed: boolean;
  viewDimmed: boolean;
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

interface NodeSemanticMeta {
  stage: Stage;
  sector: Sector;
  tags: string[];
  narrative: string;
  portfolioLinked?: boolean;
  alertLinked?: boolean;
}

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

const MODE_META: Record<Mode, { label: string; icon: IconComponent }> = {
  live: { label: "Live", icon: Play },
  replay: { label: "Replay", icon: RotateCcw },
  explorer: { label: "Explorer", icon: Search },
};

const VIEW_META: Record<View, { label: string; icon: IconComponent; brief: string }> = {
  all: {
    label: "All",
    icon: Layers,
    brief: "全量因果网：适合检查跨板块传导、孤立节点和链路完整性。",
  },
  portfolio: {
    label: "Portfolio",
    icon: Briefcase,
    brief: "持仓视角：聚焦会影响当前风险暴露的 NR/RU 与黑色链路。",
  },
  counter: {
    label: "Counter",
    icon: ShieldCheck,
    brief: "反证视角：突出会压低置信度、阻止误触发的验证节点。",
  },
  alerts: {
    label: "Alert Trace",
    icon: AlertTriangle,
    brief: "预警追踪：只强化能够进入告警或人工审查的关键路径。",
  },
};

const VIEW_ORDER: View[] = ["all", "portfolio", "counter", "alerts"];

const STAGE_META: Record<Stage, { label: string; color: string; description: string }> = {
  source: { label: "事件源", color: "#38BDF8", description: "新闻、天气和外部冲击" },
  thesis: { label: "假设生成", color: "#F97316", description: "产业逻辑与方向假设" },
  validation: { label: "证据校验", color: "#A3A3A3", description: "价格、持仓与基本面验证" },
  impact: { label: "市场/预警", color: "#10B981", description: "可交易影响与告警出口" },
};

const STAGE_ORDER: Stage[] = ["source", "thesis", "validation", "impact"];

const STAGE_BANDS: Array<{ stage: Stage; x: number; width: number }> = [
  { stage: "source", x: -30, width: 410 },
  { stage: "thesis", x: 390, width: 390 },
  { stage: "validation", x: 790, width: 370 },
  { stage: "impact", x: 1170, width: 560 },
];

const SECTOR_META: Record<Sector, { label: string; color: string }> = {
  geo: { label: "地缘", color: "#38BDF8" },
  energy: { label: "能化", color: "#F97316" },
  rubber: { label: "橡胶", color: "#10B981" },
  ferrous: { label: "黑色", color: "#C084FC" },
  positioning: { label: "持仓", color: "#EF4444" },
};

const NODE_META: Record<string, NodeSemanticMeta> = {
  n1: {
    stage: "source",
    sector: "geo",
    tags: ["地缘", "原油"],
    narrative: "外部军事移动是能源风险溢价的上游扰动源。",
  },
  n2: {
    stage: "source",
    sector: "geo",
    tags: ["冲突", "航运"],
    narrative: "区域局势升级会放大航运和供应中断预期。",
  },
  n3: {
    stage: "thesis",
    sector: "energy",
    tags: ["SC", "阈值"],
    narrative: "把地缘风险和价格预期压缩成可监控的原油上涨假设。",
    alertLinked: true,
  },
  n4: {
    stage: "thesis",
    sector: "energy",
    tags: ["化工", "传导"],
    narrative: "原油假设向化工链利润和成本端继续传播。",
  },
  n5: {
    stage: "impact",
    sector: "energy",
    tags: ["PTA", "现货"],
    narrative: "PTA 现货上涨是能化链传导后的市场影响节点。",
  },
  n6: {
    stage: "impact",
    sector: "energy",
    tags: ["PP", "盘面"],
    narrative: "PP 走强验证能化链的下游盘面响应。",
  },
  n7: {
    stage: "validation",
    sector: "positioning",
    tags: ["CFTC", "反证"],
    narrative: "持仓未同步增加会削弱能源上涨信号的发射概率。",
  },
  n8: {
    stage: "source",
    sector: "rubber",
    tags: ["天气", "产区"],
    narrative: "产区天气冲击是橡胶链短期供应风险的触发源。",
  },
  n9: {
    stage: "impact",
    sector: "rubber",
    tags: ["NR/RU", "持仓"],
    narrative: "橡胶短期看涨直接关联持仓风险和交易计划。",
    portfolioLinked: true,
    alertLinked: true,
  },
  n10: {
    stage: "validation",
    sector: "ferrous",
    tags: ["焦煤", "成本"],
    narrative: "焦煤回落会削弱黑色链成本支撑的强度。",
  },
  n11: {
    stage: "validation",
    sector: "ferrous",
    tags: ["高炉", "利润"],
    narrative: "高炉利润转负提示黑色链需求与成本传导存在压力。",
  },
  n12: {
    stage: "impact",
    sector: "ferrous",
    tags: ["螺纹", "支撑"],
    narrative: "螺纹成本支撑是黑色链风险出口，适合进入预警追踪。",
    portfolioLinked: true,
    alertLinked: true,
  },
};

const FLOW_LAYOUT: Record<string, { x: number; y: number }> = {
  n1: { x: 60, y: 140 },
  n2: { x: 430, y: 130 },
  n3: { x: 820, y: 260 },
  n4: { x: 1120, y: 140 },
  n5: { x: 1490, y: 80 },
  n6: { x: 1490, y: 310 },
  n7: { x: 820, y: 470 },
  n8: { x: 60, y: 610 },
  n9: { x: 1490, y: 590 },
  n10: { x: 820, y: 800 },
  n11: { x: 1120, y: 800 },
  n12: { x: 1490, y: 760 },
};

const fitViewOptions = { padding: 0.06, duration: 500 };
const previewFitViewOptions = { padding: 0.08, duration: 500 };

const FLOW_NODE_TYPES = {
  causalNode: CausalNodeCard,
} satisfies NodeTypes;

const FLOW_EDGE_TYPES = {
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
  const [view, setView] = useState<View>("all");
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const isFull = variant === "full";

  const viewNodeIds = useMemo(() => viewVisibleNodeIds(view), [view]);
  const focusId = isFull ? selectedNode ?? hoveredNode : null;
  const activeFocusId = focusId && viewNodeIds.has(focusId) ? focusId : null;
  const highlightedNodeIds = useMemo(() => causalChainIds(activeFocusId), [activeFocusId]);
  const highlightedEdgeIds = useMemo(() => {
    if (!activeFocusId) return new Set<string>();
    return new Set(
      CAUSAL_EDGES.filter(
        (edge) =>
          viewNodeIds.has(edge.source) &&
          viewNodeIds.has(edge.target) &&
          highlightedNodeIds.has(edge.source) &&
          highlightedNodeIds.has(edge.target)
      ).map((edge) => edge.id)
    );
  }, [activeFocusId, highlightedNodeIds, viewNodeIds]);

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
        const inView = viewNodeIds.has(node.id);
        const focused = inView && (activeFocusId === node.id || highlightedNodeIds.has(node.id));
        const dimmed = !inView || (Boolean(activeFocusId) && !focused);
        return {
          id: node.id,
          type: "causalNode",
          position: FLOW_LAYOUT[node.id] ?? { x: 520, y: 320 },
          data: {
            causal: node,
            meta: NODE_META[node.id],
            upstream: counts.upstream,
            downstream: counts.downstream,
            focused,
            dimmed,
            viewDimmed: !inView,
            variant,
          },
          draggable: isFull && mode === "explorer",
          selectable: isFull,
        };
      }),
    [activeFocusId, highlightedNodeIds, isFull, mode, relationCounts, variant, viewNodeIds]
  );

  const edges = useMemo<CausalFlowEdge[]>(
    () =>
      CAUSAL_EDGES.map((edge) => {
        const inView = viewNodeIds.has(edge.source) && viewNodeIds.has(edge.target);
        const focused = inView && highlightedEdgeIds.has(edge.id);
        const dimmed = !inView || (Boolean(activeFocusId) && !focused);
        const live =
          mode === "live" &&
          inView &&
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
            showLabel: isFull && inView && (focused || mode === "explorer" || view !== "all"),
          },
        };
      }),
    [activeFocusId, highlightedEdgeIds, isFull, mode, view, viewNodeIds]
  );

  const selected =
    selectedNode && viewNodeIds.has(selectedNode)
      ? CAUSAL_NODES.find((node) => node.id === selectedNode)
      : null;

  const fitCanvas = useCallback(() => {
    const fitOptions = isFull ? fitViewOptions : previewFitViewOptions;
    void flow.fitView({
      ...fitOptions,
      nodes: Array.from(viewNodeIds).map((id) => ({ id })),
    });
  }, [flow, isFull, viewNodeIds]);

  const changeView = useCallback(
    (nextView: View) => {
      setView(nextView);
      setSelectedNode(null);
      setHoveredNode(null);
      window.setTimeout(() => {
        void flow.fitView({
          ...fitViewOptions,
          nodes: Array.from(viewVisibleNodeIds(nextView)).map((id) => ({ id })),
        });
      }, 0);
    },
    [flow]
  );

  const onInit = useCallback(
    (instance: ReactFlowInstance<CausalFlowNode, CausalFlowEdge>) => {
      window.setTimeout(() => {
        void instance.fitView(isFull ? fitViewOptions : previewFitViewOptions);
      }, 0);
    },
    [isFull]
  );

  return (
    <div
      className={cn(
        "causal-web-flow isolate flex h-full w-full flex-col overflow-hidden bg-bg-base",
        !isFull && "pointer-events-none",
        className
      )}
    >
      {isFull && (
        <div className="shrink-0 overflow-x-auto border-b border-border-subtle bg-bg-surface/80 px-3 py-2">
          <div className="flex min-w-max items-center gap-3">
            <div className="flex flex-wrap gap-2">
              <ModeToolbar mode={mode} onChange={setMode} onFit={fitCanvas} />
              <ViewToolbar view={view} onChange={changeView} />
            </div>
            <StageRail viewNodeIds={viewNodeIds} />
            <div className="hidden xl:block">
              <GraphStats
                focusId={activeFocusId}
                mode={mode}
                view={view}
                visibleCount={viewNodeIds.size}
              />
            </div>
          </div>
        </div>
      )}

      <div className="relative min-h-0 flex-1">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={FLOW_NODE_TYPES}
          edgeTypes={FLOW_EDGE_TYPES}
          onInit={onInit}
          onNodeMouseEnter={
            isFull
              ? (_, node) => {
                  if (viewNodeIds.has(node.id)) setHoveredNode(node.id);
                }
              : undefined
          }
          onNodeMouseLeave={isFull ? () => setHoveredNode(null) : undefined}
          onNodeClick={(_, node) => {
            if (isFull && viewNodeIds.has(node.id)) {
              setSelectedNode((current) => (current === node.id ? null : node.id));
            }
          }}
          onPaneClick={() => {
            setSelectedNode(null);
            setHoveredNode(null);
          }}
          fitView
          fitViewOptions={isFull ? fitViewOptions : previewFitViewOptions}
          minZoom={0.28}
          maxZoom={1.55}
          nodesDraggable={isFull && mode === "explorer"}
          nodesConnectable={false}
          edgesFocusable={isFull}
          elementsSelectable={isFull}
          nodesFocusable={isFull}
          panOnDrag={isFull}
          zoomOnScroll={isFull}
          zoomOnPinch={isFull}
          zoomOnDoubleClick={isFull}
          preventScrolling={isFull}
          proOptions={{ hideAttribution: true }}
        >
          <Background
            variant={BackgroundVariant.Dots}
            gap={30}
            size={1}
            color="rgba(115, 115, 115, 0.2)"
          />

          {isFull && (
            <>
              <SemanticBackdrop viewNodeIds={viewNodeIds} />

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
                className="causal-minimap !bottom-16 !right-4 !h-24 !w-40 !rounded-sm !border !border-border-default !bg-bg-surface-overlay"
              />
            </>
          )}
        </ReactFlow>

        {isFull && selected && (
          <NodeDetails node={selected} onClose={() => setSelectedNode(null)} />
        )}
      </div>

      {isFull && !selected && (
        <div className="shrink-0 border-t border-border-subtle bg-bg-surface/90 px-3 py-2">
          <div className="flex flex-col gap-2 xl:flex-row xl:items-center xl:justify-between">
            <ViewBrief view={view} focusId={activeFocusId} visibleCount={viewNodeIds.size} />
            <Legend />
          </div>
        </div>
      )}
    </div>
  );
}

function ModeToolbar({
  mode,
  onChange,
  onFit,
}: {
  mode: Mode;
  onChange: (mode: Mode) => void;
  onFit: () => void;
}) {
  return (
    <div className="flex items-center gap-1 rounded-sm border border-border-default bg-bg-base p-1">
      {(Object.keys(MODE_META) as Mode[]).map((item) => {
        const meta = MODE_META[item];
        const Icon = meta.icon;
        return (
          <button
            key={item}
            type="button"
            title={meta.label}
            aria-label={meta.label}
            onClick={() => onChange(item)}
            className={cn(
              "flex h-7 items-center gap-1.5 rounded-xs px-2.5 text-xs font-medium transition-colors",
              mode === item
                ? "bg-brand-emerald text-white"
                : "text-text-secondary hover:bg-bg-surface-raised hover:text-text-primary"
            )}
          >
            <Icon className="h-3 w-3" />
            <span className="hidden xl:inline">{meta.label}</span>
          </button>
        );
      })}
      <button
        type="button"
        title="Fit view"
        aria-label="Fit view"
        onClick={onFit}
        className="flex h-7 w-7 items-center justify-center rounded-xs text-text-secondary transition-colors hover:bg-bg-surface-raised hover:text-text-primary"
      >
        <Maximize2 className="h-3 w-3" />
      </button>
    </div>
  );
}

function ViewToolbar({ view, onChange }: { view: View; onChange: (view: View) => void }) {
  return (
    <div className="flex items-center gap-1 rounded-sm border border-border-default bg-bg-base p-1">
      {VIEW_ORDER.map((item) => {
        const meta = VIEW_META[item];
        const Icon = meta.icon;
        return (
          <button
            key={item}
            type="button"
            title={meta.brief}
            aria-label={meta.label}
            onClick={() => onChange(item)}
            className={cn(
              "flex h-7 items-center gap-1.5 rounded-xs px-2 text-xs font-medium transition-colors",
              view === item
                ? "bg-bg-surface-highlight text-text-primary"
                : "text-text-muted hover:bg-bg-surface-raised hover:text-text-primary"
            )}
          >
            <Icon className="h-3 w-3" />
            <span className="hidden xl:inline">{meta.label}</span>
          </button>
        );
      })}
    </div>
  );
}

function SemanticBackdrop({ viewNodeIds }: { viewNodeIds: Set<string> }) {
  const visibleStages = new Set(
    CAUSAL_NODES.filter((node) => viewNodeIds.has(node.id)).map(
      (node) => NODE_META[node.id].stage
    )
  );

  return (
    <ViewportPortal>
      <div className="causal-stage-backdrop pointer-events-none absolute" style={{ inset: 0 }}>
        {STAGE_BANDS.map((band) => {
          const meta = STAGE_META[band.stage];
          const active = visibleStages.has(band.stage);
          return (
            <div
              key={band.stage}
              className="causal-stage-band absolute rounded-sm border"
              style={{
                left: band.x,
                top: 28,
                width: band.width,
                height: 910,
                borderColor: `${meta.color}${active ? "35" : "18"}`,
                background: `linear-gradient(180deg, ${meta.color}${active ? "12" : "07"} 0%, rgba(10,10,10,0.04) 70%)`,
                opacity: active ? 1 : 0.45,
              }}
            >
              <div
                className="absolute left-3 top-3 rounded-xs border bg-black/70 px-2 py-1 text-caption font-medium"
                style={{ borderColor: `${meta.color}42`, color: meta.color }}
              >
                {meta.label}
              </div>
            </div>
          );
        })}
      </div>
    </ViewportPortal>
  );
}

function StageRail({ viewNodeIds }: { viewNodeIds: Set<string> }) {
  const activeStages = new Set(
    CAUSAL_NODES.filter((node) => viewNodeIds.has(node.id)).map(
      (node) => NODE_META[node.id].stage
    )
  );

  return (
    <div className="hidden min-w-[336px] justify-center gap-1 rounded-sm border border-border-default bg-bg-base px-2 py-1 xl:flex">
      {STAGE_ORDER.map((stage, index) => {
        const meta = STAGE_META[stage];
        const active = activeStages.has(stage);
        return (
          <div key={stage} className="flex items-center gap-1">
            <div
              className={cn(
                "rounded-xs border px-1.5 py-0.5 text-caption transition-opacity",
                active ? "opacity-100" : "opacity-35"
              )}
              style={{ borderColor: `${meta.color}55`, color: meta.color }}
              title={meta.description}
            >
              {meta.label}
            </div>
            {index < STAGE_ORDER.length - 1 && (
              <Route className="h-3 w-3 text-text-disabled" />
            )}
          </div>
        );
      })}
    </div>
  );
}

function ViewBrief({
  view,
  focusId,
  visibleCount,
}: {
  view: View;
  focusId: string | null;
  visibleCount: number;
}) {
  const meta = VIEW_META[view];
  const Icon = meta.icon;
  const focusNode = focusId ? CAUSAL_NODES.find((node) => node.id === focusId) : null;
  const focusMeta = focusNode ? NODE_META[focusNode.id] : null;

  return (
    <div className="min-w-0 flex-1 rounded-sm border border-border-default bg-bg-base px-2.5 py-1.5 xl:max-w-[560px]">
      <div className="flex items-center gap-2 text-caption text-text-muted">
        <Icon className="h-3.5 w-3.5" />
        <span className="text-text-secondary">{meta.label}</span>
        <span className="font-mono">{visibleCount}/{CAUSAL_NODES.length}</span>
        {focusNode && (
          <>
            <span className="text-text-disabled">·</span>
            <span className="truncate text-text-primary">{focusNode.label}</span>
          </>
        )}
      </div>
      <div className="mt-1 line-clamp-1 text-xs text-text-secondary">
        {focusMeta?.narrative ?? meta.brief}
      </div>
    </div>
  );
}

function CausalNodeCard({ data, selected }: NodeProps<CausalFlowNode>) {
  const node = data.causal;
  const meta = data.meta;
  const stage = STAGE_META[meta.stage];
  const sector = SECTOR_META[meta.sector];
  const color = NODE_COLORS[node.type];
  const compact = data.variant === "preview";
  const Icon = nodeIcon(node.type);

  return (
    <div
      className={cn(
        "group relative rounded-sm border bg-bg-surface-overlay shadow-md transition duration-200",
        compact ? "w-[148px] px-3 py-2" : "w-[196px] px-3.5 py-3",
        data.viewDimmed ? "scale-[0.96] opacity-20 grayscale" : data.dimmed && "scale-[0.98] opacity-35",
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
      <div
        className="absolute inset-x-0 top-0 h-0.5 rounded-t-sm"
        style={{
          background: `linear-gradient(90deg, ${stage.color}, ${sector.color})`,
        }}
      />

      {node.active && (
        <>
          <span
            className="pointer-events-none absolute -inset-1 rounded-sm border opacity-40 animate-heartbeat"
            style={{ borderColor: color }}
          />
          <span
            className="causal-node-scan pointer-events-none absolute left-3 right-3 top-2 h-px opacity-70"
            style={{ background: `linear-gradient(90deg, transparent, ${color}, transparent)` }}
          />
        </>
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
          {!compact && (
            <div className="mt-2 flex flex-wrap gap-1">
              <span
                className="rounded-xs border px-1.5 py-0.5 text-[10px] leading-none"
                style={{ borderColor: `${stage.color}55`, color: stage.color }}
              >
                {stage.label}
              </span>
              <span
                className="rounded-xs border px-1.5 py-0.5 text-[10px] leading-none"
                style={{ borderColor: `${sector.color}55`, color: sector.color }}
              >
                {sector.label}
              </span>
              {meta.portfolioLinked && (
                <span className="inline-flex items-center gap-1 rounded-xs border border-brand-emerald/40 px-1.5 py-0.5 text-[10px] leading-none text-brand-emerald-bright">
                  <Briefcase className="h-2.5 w-2.5" />
                  Position
                </span>
              )}
              {meta.alertLinked && (
                <span className="inline-flex items-center gap-1 rounded-xs border border-brand-orange/40 px-1.5 py-0.5 text-[10px] leading-none text-brand-orange">
                  <Target className="h-2.5 w-2.5" />
                  Alert
                </span>
              )}
            </div>
          )}
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
            <span className="font-mono">{Math.round(edge.hitRate * 100)}% hit</span>
            <span className="mx-1 text-text-muted">·</span>
            <span className="font-mono">{Math.round(edge.confidence * 100)}% conf</span>
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}

function GraphStats({
  focusId,
  mode,
  view,
  visibleCount,
}: {
  focusId: string | null;
  mode: Mode;
  view: View;
  visibleCount: number;
}) {
  const activeNodes = CAUSAL_NODES.filter((node) => node.active).length;
  const verifiedEdges = CAUSAL_EDGES.filter((edge) => edge.verified).length;
  const ModeIcon = mode === "live" ? Activity : mode === "replay" ? RotateCcw : Search;
  const ViewIcon = VIEW_META[view].icon;

  return (
    <div className="flex flex-wrap items-stretch gap-1.5 rounded-sm border border-border-default bg-bg-base p-1">
      <StatCell icon={ModeIcon} label="Mode" value={mode} />
      <StatCell icon={ViewIcon} label="View" value={VIEW_META[view].label} />
      <StatCell icon={CircleDot} label="Active" value={`${activeNodes}/${CAUSAL_NODES.length}`} />
      <StatCell icon={CheckCircle2} label="Verified" value={`${verifiedEdges}/${CAUSAL_EDGES.length}`} />
      <div className="min-w-[96px] rounded-xs bg-bg-surface-raised px-2 py-1 text-caption text-text-muted">
        <span>Visible</span>
        <span className="ml-2 font-mono text-xs text-text-primary">{visibleCount}/{CAUSAL_NODES.length}</span>
        {focusId && (
          <div className="mt-1 max-w-40 truncate text-text-secondary">
            {CAUSAL_NODES.find((node) => node.id === focusId)?.label}
          </div>
        )}
      </div>
    </div>
  );
}

function StatCell({
  icon: Icon,
  label,
  value,
}: {
  icon: IconComponent;
  label: string;
  value: string;
}) {
  return (
    <div className="min-w-14 rounded-xs bg-bg-surface-raised px-2 py-1">
      <div className="flex items-center gap-1.5 text-caption text-text-muted">
        <Icon className="h-3 w-3" />
        {label}
      </div>
      <div className="mt-0.5 max-w-16 truncate font-mono text-xs text-text-primary">{value}</div>
    </div>
  );
}

function NodeDetails({ node, onClose }: { node: CausalNode; onClose: () => void }) {
  const upstream = CAUSAL_EDGES.filter((edge) => edge.target === node.id);
  const downstream = CAUSAL_EDGES.filter((edge) => edge.source === node.id);
  const meta = NODE_META[node.id];
  const stage = STAGE_META[meta.stage];
  const sector = SECTOR_META[meta.sector];
  const color = NODE_COLORS[node.type];
  const Icon = nodeIcon(node.type);

  return (
    <div className="absolute inset-x-4 bottom-20 top-4 z-[1100] flex min-h-0 flex-col overflow-hidden rounded-sm border border-border-default bg-bg-surface-overlay shadow-xl animate-fade-in sm:left-auto sm:w-[380px]">
      <div className="shrink-0 border-b border-border-subtle p-4">
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
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-4">
        <div className="rounded-xs border border-border-subtle bg-bg-base p-3 text-sm text-text-secondary">
          {meta.narrative}
        </div>

        <div className="mt-3 flex flex-wrap gap-1.5">
          <span
            className="rounded-xs border px-2 py-1 text-caption"
            style={{ borderColor: `${stage.color}55`, color: stage.color }}
          >
            {stage.label}
          </span>
          <span
            className="rounded-xs border px-2 py-1 text-caption"
            style={{ borderColor: `${sector.color}55`, color: sector.color }}
          >
            {sector.label}
          </span>
          {meta.tags.map((tag) => (
            <span key={tag} className="rounded-xs border border-border-subtle px-2 py-1 text-caption text-text-muted">
              {tag}
            </span>
          ))}
          {meta.portfolioLinked && (
            <span className="inline-flex items-center gap-1 rounded-xs border border-brand-emerald/40 px-2 py-1 text-caption text-brand-emerald-bright">
              <Briefcase className="h-3 w-3" />
              Position
            </span>
          )}
          {meta.alertLinked && (
            <span className="inline-flex items-center gap-1 rounded-xs border border-brand-orange/40 px-2 py-1 text-caption text-brand-orange">
              <Target className="h-3 w-3" />
              Alert
            </span>
          )}
        </div>

        <div className="mt-4 grid grid-cols-3 gap-2">
          <DetailMetric label="Fresh" value={`${Math.round(node.freshness * 100)}%`} />
          <DetailMetric label="Impact" value={`${node.influence}/4`} />
          <DetailMetric label="State" value={node.active ? "Active" : "Quiet"} />
        </div>

        <EdgeList title="上游" edges={upstream} side="source" />
        <EdgeList title="下游" edges={downstream} side="target" />
      </div>
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
                <span className="inline-flex items-center gap-1">
                  <Clock className="h-3 w-3" />
                  {edge.lag}
                </span>
                <span className="font-mono">hit {Math.round(edge.hitRate * 100)}%</span>
              </div>
              <div className="mt-1 flex items-center justify-between text-caption text-text-muted">
                <span style={{ color }}>{edge.direction}</span>
                <span className={cn("inline-flex items-center gap-1", edge.verified ? "text-brand-emerald-bright" : "text-text-muted")}>
                  <CheckCircle2 className="h-3 w-3" />
                  {edge.verified ? "verified" : "unverified"}
                </span>
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
    <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1.5 rounded-sm border border-border-default bg-bg-base px-2.5 py-1.5">
      <div className="flex items-center gap-2 text-caption font-medium text-text-secondary">
        <Network className="h-3.5 w-3.5" />
        Causal Layers
      </div>
      {(Object.keys(NODE_LABELS) as CausalNode["type"][]).map((type) => {
        const Icon = nodeIcon(type);
        return (
          <div key={type} className="flex items-center gap-1.5 text-caption text-text-muted">
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
      <div className="hidden h-5 w-px bg-border-subtle xl:block" />
      <div className="flex items-center gap-2 text-caption font-medium text-text-secondary">
        <Layers className="h-3.5 w-3.5" />
        Semantic Stages
      </div>
      {STAGE_ORDER.map((stage) => {
        const meta = STAGE_META[stage];
        return (
          <div key={stage} className="flex items-center gap-1.5 text-caption text-text-muted">
            <span
              className="h-1.5 w-5 rounded-full"
              style={{ backgroundColor: meta.color }}
            />
            {meta.label}
          </div>
        );
      })}
    </div>
  );
}

function viewVisibleNodeIds(view: View): Set<string> {
  if (view === "all") return new Set(CAUSAL_NODES.map((node) => node.id));

  const rootIds = CAUSAL_NODES.filter((node) => {
    const meta = NODE_META[node.id];
    if (view === "portfolio") return Boolean(meta.portfolioLinked);
    if (view === "counter") return node.type === "counter";
    return Boolean(meta.alertLinked) || node.type === "alert";
  }).map((node) => node.id);

  const ids = new Set<string>();
  for (const rootId of rootIds) {
    for (const id of causalChainIds(rootId)) {
      ids.add(id);
    }
  }
  return ids;
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
