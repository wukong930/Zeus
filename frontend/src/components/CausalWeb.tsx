"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
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
import type { CausalEdge, CausalNode } from "@/lib/domain";
import { cn } from "@/lib/utils";
import { useI18n, type Language } from "@/lib/i18n";

type Mode = "live" | "replay" | "explorer";
type View = "all" | "portfolio" | "counter" | "alerts";
type Density = "curated" | "expanded";
type Stage = "source" | "thesis" | "validation" | "impact";
type Sector = "geo" | "energy" | "rubber" | "ferrous" | "metals" | "agri" | "precious" | "positioning";
type IconComponent = typeof Activity;

interface CausalWebProps {
  variant?: "full" | "preview";
  className?: string;
  nodes?: CausalNode[];
  edges?: CausalEdge[];
  emptyMessage?: string;
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
  density: Density;
  aggregateCount?: number;
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
  cluster: "#737373",
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
  cluster: "聚合",
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

const DENSITY_META: Record<Density, { label: string; icon: IconComponent; brief: string }> = {
  curated: {
    label: "Core",
    icon: Layers,
    brief: "核心视图：优先展示影响力、持仓、预警和高连接节点，其余按阶段聚合。",
  },
  expanded: {
    label: "Expanded",
    icon: Maximize2,
    brief: "完整视图：展示当前过滤下的所有节点，并按阶段重新排布。",
  },
};

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

const STAGE_NODE_X: Record<Stage, number> = {
  source: 70,
  thesis: 445,
  validation: 825,
  impact: 1235,
};

const STAGE_Y_OFFSET: Record<Stage, number> = {
  source: 0,
  thesis: 24,
  validation: 8,
  impact: 34,
};

const CORE_STAGE_LIMITS: Record<Stage, number> = {
  source: 4,
  thesis: 7,
  validation: 7,
  impact: 7,
};

const PREVIEW_STAGE_LIMITS: Record<Stage, number> = {
  source: 2,
  thesis: 3,
  validation: 3,
  impact: 3,
};

const SECTOR_META: Record<Sector, { label: string; color: string }> = {
  geo: { label: "地缘", color: "#38BDF8" },
  energy: { label: "能化", color: "#F97316" },
  rubber: { label: "橡胶", color: "#10B981" },
  ferrous: { label: "黑色", color: "#C084FC" },
  metals: { label: "有色", color: "#22D3EE" },
  agri: { label: "农产", color: "#84CC16" },
  precious: { label: "贵金属", color: "#FACC15" },
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
const flowProOptions = { hideAttribution: true };
const FIT_ANCHOR_TOP_ID = "__causal-fit-top";
const FIT_ANCHOR_BOTTOM_ID = "__causal-fit-bottom";

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

function CausalWebCanvas({
  variant = "full",
  className,
  nodes: runtimeNodes,
  edges: runtimeEdges,
  emptyMessage = "当前暂无运行态因果图谱",
}: CausalWebProps) {
  const flow = useReactFlow<CausalFlowNode, CausalFlowEdge>();
  const [mode, setMode] = useState<Mode>("live");
  const [view, setView] = useState<View>("all");
  const [density, setDensity] = useState<Density>("curated");
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [selectedEventIds, setSelectedEventIds] = useState<Set<string>>(new Set());
  const isFull = variant === "full";
  const rawGraphNodes = runtimeNodes ?? [];
  const rawGraphEdges = runtimeEdges ?? [];
  const normalizedGraph = useMemo(
    () => normalizeEventGraph(rawGraphNodes, rawGraphEdges),
    [rawGraphEdges, rawGraphNodes]
  );
  const graphNodes = normalizedGraph.nodes;
  const graphEdges = normalizedGraph.edges;
  const graphEmpty = graphNodes.length === 0;
  const graphNodeById = useMemo(
    () => new Map(graphNodes.map((node) => [node.id, node])),
    [graphNodes]
  );
  const metaByNodeId = useMemo(
    () => new Map(graphNodes.map((node) => [node.id, semanticMetaForNode(node)])),
    [graphNodes]
  );

  const baseViewNodeIds = useMemo(
    () => viewVisibleNodeIds(view, graphNodes, graphEdges, metaByNodeId),
    [graphEdges, graphNodes, metaByNodeId, view]
  );
  const strictViewNodeIds = useMemo(
    () => viewVisibleNodeIds(view, graphNodes, graphEdges, metaByNodeId, { allowCounterFallback: false }),
    [graphEdges, graphNodes, metaByNodeId, view]
  );
  const relationCounts = useMemo(() => {
    const counts = new Map<string, { upstream: number; downstream: number }>();
    for (const node of graphNodes) {
      counts.set(node.id, { upstream: 0, downstream: 0 });
    }
    for (const edge of graphEdges) {
      const source = counts.get(edge.source);
      const target = counts.get(edge.target);
      if (source) source.downstream += 1;
      if (target) target.upstream += 1;
    }
    return counts;
  }, [graphEdges, graphNodes]);

  const eventNodes = useMemo(
    () => {
      const unique = new Map<string, CausalNode>();
      for (const node of graphNodes) {
        if (node.type !== "event") continue;
        const key = eventDisplayKey(node);
        const current = unique.get(key);
        if (!current || nodePriority(node, metaByNodeId, relationCounts) > nodePriority(current, metaByNodeId, relationCounts)) {
          unique.set(key, node);
        }
      }
      return [...unique.values()].sort(
        (a, b) => nodePriority(b, metaByNodeId, relationCounts) - nodePriority(a, metaByNodeId, relationCounts)
      );
    },
    [graphNodes, metaByNodeId, relationCounts]
  );

  useEffect(() => {
    if (!isFull || eventNodes.length === 0) return;
    const availableIds = new Set(eventNodes.map((node) => node.id));
    setSelectedEventIds((current) => {
      const valid = new Set([...current].filter((id) => availableIds.has(id)));
      if (valid.size > 0) return valid;
      return new Set(eventNodes.slice(0, Math.min(2, eventNodes.length)).map((node) => node.id));
    });
  }, [eventNodes, isFull]);

  const selectedEventChainIds = useMemo(() => {
    const ids = new Set<string>();
    for (const eventId of selectedEventIds) {
      for (const id of downstreamChainIds(eventId, graphEdges)) {
        ids.add(id);
      }
    }
    return ids;
  }, [graphEdges, selectedEventIds]);

  const eventScopeActive =
    isFull && view !== "all" && eventNodes.length > 0 && selectedEventIds.size > 0;

  const scopedBaseNodeIds = useMemo(() => {
    if (!isFull || eventNodes.length === 0 || selectedEventIds.size === 0) {
      return baseViewNodeIds;
    }

    if (view === "all") {
      const ids = new Set<string>();
      for (const id of selectedEventChainIds) {
        if (baseViewNodeIds.has(id)) ids.add(id);
      }
      if (ids.size <= selectedEventIds.size) return baseViewNodeIds;
      return ids.size > 0 ? ids : baseViewNodeIds;
    }

    const scopedViewIds = new Set<string>();
    for (const id of selectedEventChainIds) {
      if (strictViewNodeIds.has(id)) scopedViewIds.add(id);
    }
    return scopedViewIds;
  }, [baseViewNodeIds, eventNodes.length, isFull, selectedEventChainIds, selectedEventIds.size, strictViewNodeIds, view]);

  const focusId = isFull ? selectedNode ?? hoveredNode : null;
  const activeFocusId = focusId && scopedBaseNodeIds.has(focusId) ? focusId : null;

  const highlightedNodeIds = useMemo(
    () => causalChainIds(activeFocusId, graphEdges, 2),
    [activeFocusId, graphEdges]
  );
  const displayGraph = useMemo(
    () =>
      buildDisplayGraph({
        nodes: graphNodes,
        edges: graphEdges,
        baseNodeIds: scopedBaseNodeIds,
        metaByNodeId,
        relationCounts,
        density: isFull ? density : "curated",
        variant,
        focusNodeIds: highlightedNodeIds,
      }),
    [density, graphEdges, graphNodes, highlightedNodeIds, isFull, metaByNodeId, relationCounts, scopedBaseNodeIds, variant]
  );
  const eventScopeEmpty = eventScopeActive && displayGraph.visibleRealCount === 0;
  const displayNodeById = useMemo(
    () => new Map(displayGraph.nodes.map((node) => [node.id, node])),
    [displayGraph.nodes]
  );
  const viewNodeIds = displayGraph.nodeIds;
  const displayFitNodeIds = useMemo(
    () => [...displayGraph.nodeIds].sort(),
    [displayGraph.nodeIds]
  );
  const fitViewNodeIds = useMemo(
    () => [...displayFitNodeIds, FIT_ANCHOR_TOP_ID, FIT_ANCHOR_BOTTOM_ID],
    [displayFitNodeIds]
  );
  const highlightedEdgeIds = useMemo(() => {
    if (!activeFocusId) return new Set<string>();
    return new Set(
      displayGraph.edges
        .filter((edge) => highlightedNodeIds.has(edge.source) && highlightedNodeIds.has(edge.target))
        .map((edge) => edge.id)
    );
  }, [activeFocusId, displayGraph.edges, highlightedNodeIds]);

  const nodes = useMemo<CausalFlowNode[]>(
    () => {
      const visibleNodes: CausalFlowNode[] = displayGraph.nodes.map((node): CausalFlowNode => {
        const counts = relationCounts.get(node.id) ?? { upstream: 0, downstream: 0 };
        const inView = viewNodeIds.has(node.id);
        const focused = inView && (activeFocusId === node.id || highlightedNodeIds.has(node.id));
        const dimmed = !inView || (Boolean(activeFocusId) && !focused);
        return {
          id: node.id,
          type: "causalNode",
          position: node.x !== undefined && node.y !== undefined ? { x: node.x, y: node.y } : FLOW_LAYOUT[node.id] ?? { x: 520, y: 320 },
          data: {
            causal: node,
            meta: metaByNodeId.get(node.id) ?? semanticMetaForNode(node),
            upstream: counts.upstream,
            downstream: counts.downstream,
            focused,
            dimmed,
            viewDimmed: !inView,
            variant,
            density: isFull ? density : "curated",
            aggregateCount: node.aggregateCount,
          },
          draggable: isFull && mode === "explorer" && node.type !== "cluster",
          selectable: isFull,
        };
      });
      return [
        ...visibleNodes,
        ...fitAnchorNodes(displayGraph.height, variant),
      ];
    },
    [activeFocusId, density, displayGraph.height, displayGraph.nodes, highlightedNodeIds, isFull, metaByNodeId, mode, relationCounts, variant, viewNodeIds]
  );

  const edges = useMemo<CausalFlowEdge[]>(
    () =>
      displayGraph.edges.map((edge) => {
        const inView = viewNodeIds.has(edge.source) && viewNodeIds.has(edge.target);
        const focused = inView && highlightedEdgeIds.has(edge.id);
        const dimmed = !inView || (Boolean(activeFocusId) && !focused);
        const live =
          mode === "live" &&
          inView &&
          (displayNodeById.get(edge.source)?.active || displayNodeById.get(edge.target)?.active);
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
            showLabel:
              isFull &&
              inView &&
              (focused || (mode === "explorer" && density === "expanded" && edge.confidence >= 0.82)),
          },
        };
      }),
    [activeFocusId, density, displayGraph.edges, displayNodeById, highlightedEdgeIds, isFull, mode, view, viewNodeIds]
  );

  const selected =
    selectedNode && viewNodeIds.has(selectedNode)
      ? graphNodeById.get(selectedNode)
      : null;
  const showEventPool = isFull && eventNodes.length > 0 && !selected;

  const fitCanvas = useCallback(() => {
    const fitOptions = isFull ? fitViewOptions : previewFitViewOptions;
    void flow.fitView({
      ...fitOptions,
      nodes: fitViewNodeIds.map((id) => ({ id })),
    });
  }, [fitViewNodeIds, flow, isFull]);
  const flowNodeTypes = useMemo(() => FLOW_NODE_TYPES, []);
  const flowEdgeTypes = useMemo(() => FLOW_EDGE_TYPES, []);

  const changeView = useCallback(
    (nextView: View) => {
      setView(nextView);
      setSelectedNode(null);
      setHoveredNode(null);
      window.setTimeout(() => {
        void flow.fitView(fitViewOptions);
      }, 0);
    },
    [flow]
  );

  const changeDensity = useCallback(
    (nextDensity: Density) => {
      setDensity(nextDensity);
      setSelectedNode(null);
      setHoveredNode(null);
      window.setTimeout(() => {
        void flow.fitView(fitViewOptions);
      }, 0);
    },
    [flow]
  );

  const toggleEvent = useCallback((eventId: string) => {
    setSelectedEventIds((current) => {
      const next = new Set(current);
      if (next.has(eventId)) {
        if (next.size > 1) next.delete(eventId);
      } else {
        next.add(eventId);
      }
      return next;
    });
  }, []);

  const onInit = useCallback(
    (instance: ReactFlowInstance<CausalFlowNode, CausalFlowEdge>) => {
      window.setTimeout(() => {
        void instance.fitView(isFull ? fitViewOptions : previewFitViewOptions);
      }, 0);
    },
    [isFull]
  );

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void flow.fitView({
        ...(isFull ? fitViewOptions : previewFitViewOptions),
        nodes: fitViewNodeIds.map((id) => ({ id })),
      });
    }, isFull ? 80 : 120);
    return () => window.clearTimeout(timer);
  }, [displayGraph.height, fitViewNodeIds, flow, isFull]);

  return (
    <div
      className={cn(
        "causal-web-flow isolate flex h-full w-full flex-col overflow-hidden bg-[linear-gradient(180deg,rgba(5,7,6,0.98),rgba(0,0,0,1))]",
        !isFull && "pointer-events-none",
        className
      )}
    >
      {isFull && (
        <div className="shrink-0 overflow-x-auto border-b border-border-subtle bg-[linear-gradient(180deg,rgba(20,20,20,0.78),rgba(5,7,6,0.96))] px-3 py-2 shadow-inner-panel">
          <div className="flex min-w-max items-center gap-3">
            <div className="flex flex-wrap gap-2">
              <ModeToolbar mode={mode} onChange={setMode} onFit={fitCanvas} />
              <ViewToolbar view={view} onChange={changeView} />
              <DensityToolbar density={density} onChange={changeDensity} />
            </div>
            <StageRail viewNodeIds={viewNodeIds} nodes={displayGraph.nodes} metaByNodeId={metaByNodeId} />
            <div className="hidden xl:block">
              <GraphStats
                focusId={activeFocusId}
                mode={mode}
                view={view}
                visibleCount={displayGraph.visibleRealCount}
                hiddenCount={displayGraph.hiddenCount}
                nodes={graphNodes}
                edges={graphEdges}
              />
            </div>
          </div>
        </div>
      )}

      <div className={cn("min-h-0 flex-1", showEventPool ? "grid grid-cols-[276px_minmax(0,1fr)]" : "relative")}>
        {showEventPool && (
          <EventPoolPanel
            events={eventNodes}
            selectedIds={selectedEventIds}
            onToggle={toggleEvent}
          />
        )}

        <div className="relative h-full min-h-0">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={flowNodeTypes}
            edgeTypes={flowEdgeTypes}
            onInit={onInit}
            onNodeMouseEnter={
              isFull
                ? (_, node) => {
                    if (viewNodeIds.has(node.id) && node.data.causal.type !== "cluster") {
                      setHoveredNode(node.id);
                    }
                  }
                : undefined
            }
            onNodeMouseLeave={isFull ? () => setHoveredNode(null) : undefined}
            onNodeClick={(_, node) => {
              if (isFull && node.data.causal.type === "cluster") {
                changeDensity("expanded");
                return;
              }
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
            proOptions={flowProOptions}
          >
            <Background
              variant={BackgroundVariant.Dots}
              gap={30}
              size={1}
              color="rgba(115, 115, 115, 0.2)"
            />

            {isFull && (
              <>
                <SemanticBackdrop
                  viewNodeIds={viewNodeIds}
                  nodes={displayGraph.nodes}
                  metaByNodeId={metaByNodeId}
                  height={displayGraph.height}
                />

                <Controls
                  position="bottom-right"
                  showInteractive={false}
                  fitViewOptions={fitViewOptions}
                />

                {!showEventPool && (
                  <MiniMap
                    position="bottom-right"
                    pannable
                    zoomable
                    nodeColor={(node) => NODE_COLORS[(node.data as CausalFlowNodeData).causal.type]}
                    nodeStrokeWidth={2}
                    className="causal-minimap !bottom-16 !right-4 !h-20 !w-32 !rounded-sm !border !border-border-default !bg-bg-surface-overlay"
                  />
                )}
              </>
            )}
          </ReactFlow>

          {isFull && viewNodeIds.size === 0 && (
            <EmptyGraphState
              view={view}
              eventScoped={eventScopeEmpty}
              message={graphEmpty ? emptyMessage : undefined}
            />
          )}
          {!isFull && graphEmpty && (
            <PreviewEmptyGraphState message={emptyMessage} />
          )}
        </div>

        {isFull && selected && (
          <NodeDetails
            node={selected}
            nodes={graphNodes}
            edges={graphEdges}
            meta={metaByNodeId.get(selected.id) ?? semanticMetaForNode(selected)}
            onClose={() => setSelectedNode(null)}
          />
        )}
      </div>

      {isFull && !selected && (
        <div className="shrink-0 border-t border-border-subtle bg-[linear-gradient(180deg,rgba(5,7,6,0.92),rgba(15,17,16,0.98))] px-3 py-2 shadow-inner-panel">
          <div className="flex flex-col gap-2 xl:flex-row xl:items-center xl:justify-between">
            <ViewBrief
              view={view}
              focusId={activeFocusId}
              visibleCount={displayGraph.visibleRealCount}
              hiddenCount={displayGraph.hiddenCount}
              nodes={graphNodes}
              metaByNodeId={metaByNodeId}
              eventScoped={eventScopeActive}
            />
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
  const { text } = useI18n();

  return (
    <div className="flex items-center gap-1 rounded-sm border border-border-default bg-[linear-gradient(180deg,rgba(15,17,16,0.98),rgba(0,0,0,0.98))] p-1 shadow-inner-panel">
      {(Object.keys(MODE_META) as Mode[]).map((item) => {
        const meta = MODE_META[item];
        const Icon = meta.icon;
        return (
          <button
            key={item}
            type="button"
            title={text(meta.label)}
            aria-label={text(meta.label)}
            onClick={() => onChange(item)}
            className={cn(
              "flex h-7 items-center gap-1.5 rounded-xs border px-2.5 text-xs font-medium transition-colors",
              mode === item
                ? "border-brand-emerald/45 bg-brand-emerald text-white shadow-glow-emerald"
                : "border-transparent text-text-secondary hover:border-border-subtle hover:bg-bg-surface-raised hover:text-text-primary"
            )}
          >
            <Icon className="h-3 w-3" />
            <span className="hidden xl:inline">{text(meta.label)}</span>
          </button>
        );
      })}
      <button
        type="button"
        title={text("Fit view")}
        aria-label={text("Fit view")}
        onClick={onFit}
        className="flex h-7 w-7 items-center justify-center rounded-xs border border-transparent text-text-secondary transition-colors hover:border-border-subtle hover:bg-bg-surface-raised hover:text-text-primary"
      >
        <Maximize2 className="h-3 w-3" />
      </button>
    </div>
  );
}

function ViewToolbar({ view, onChange }: { view: View; onChange: (view: View) => void }) {
  const { text } = useI18n();

  return (
    <div className="flex items-center gap-1 rounded-sm border border-border-default bg-[linear-gradient(180deg,rgba(15,17,16,0.98),rgba(0,0,0,0.98))] p-1 shadow-inner-panel">
      {VIEW_ORDER.map((item) => {
        const meta = VIEW_META[item];
        const Icon = meta.icon;
        return (
          <button
            key={item}
            type="button"
            title={text(meta.brief)}
            aria-label={text(meta.label)}
            onClick={() => onChange(item)}
            className={cn(
              "flex h-7 items-center gap-1.5 rounded-xs border px-2 text-xs font-medium transition-colors",
              view === item
                ? "border-border-strong bg-bg-surface-highlight text-text-primary shadow-inner-panel"
                : "border-transparent text-text-muted hover:border-border-subtle hover:bg-bg-surface-raised hover:text-text-primary"
            )}
          >
            <Icon className="h-3 w-3" />
            <span className="hidden xl:inline">{text(meta.label)}</span>
          </button>
        );
      })}
    </div>
  );
}

function DensityToolbar({
  density,
  onChange,
}: {
  density: Density;
  onChange: (density: Density) => void;
}) {
  const { text } = useI18n();

  return (
    <div className="flex items-center gap-1 rounded-sm border border-border-default bg-[linear-gradient(180deg,rgba(15,17,16,0.98),rgba(0,0,0,0.98))] p-1 shadow-inner-panel">
      {(Object.keys(DENSITY_META) as Density[]).map((item) => {
        const meta = DENSITY_META[item];
        const Icon = meta.icon;
        return (
          <button
            key={item}
            type="button"
            title={text(meta.brief)}
            aria-label={text(meta.label)}
            onClick={() => onChange(item)}
            className={cn(
              "flex h-7 items-center gap-1.5 rounded-xs border px-2 text-xs font-medium transition-colors",
              density === item
                ? "border-brand-cyan/45 bg-brand-cyan/12 text-brand-cyan shadow-inner-panel"
                : "border-transparent text-text-muted hover:border-border-subtle hover:bg-bg-surface-raised hover:text-text-primary"
            )}
          >
            <Icon className="h-3 w-3" />
            <span className="hidden 2xl:inline">{text(meta.label)}</span>
          </button>
        );
      })}
    </div>
  );
}

function EventPoolPanel({
  events,
  selectedIds,
  onToggle,
}: {
  events: CausalNode[];
  selectedIds: Set<string>;
  onToggle: (id: string) => void;
}) {
  const { lang, text } = useI18n();

  return (
    <aside className="z-[20] m-3 mr-0 flex min-h-0 w-[252px] min-w-0 max-w-[252px] flex-col overflow-hidden rounded-sm border border-border-default bg-[linear-gradient(180deg,rgba(18,20,19,0.96),rgba(3,5,4,0.98))] shadow-data-panel">
      <div className="shrink-0 border-b border-border-subtle px-3 py-2 shadow-inner-panel">
        <div className="flex items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-2 text-sm font-semibold text-text-primary">
            <Layers className="h-4 w-4 text-brand-cyan" />
            <span className="truncate">{text("事件池")}</span>
          </div>
          <div className="font-mono text-caption text-text-muted">
            {selectedIds.size}/{events.length}
          </div>
        </div>
        <div className="mt-1 text-caption text-text-muted">
          {text("默认展示优先级最高的事件，可手动加入图谱。")}
        </div>
      </div>
      <div className="min-h-0 overflow-y-auto p-2">
        {events.map((event, index) => {
          const selected = selectedIds.has(event.id);
          return (
            <button
              key={event.id}
              type="button"
              onClick={() => onToggle(event.id)}
              className={cn(
                "mb-1.5 flex w-full items-start gap-2 rounded-xs border px-2 py-2 text-left transition-colors last:mb-0",
                selected
                  ? "border-brand-cyan/45 bg-brand-cyan/10 text-text-primary"
                  : "border-border-subtle bg-bg-base/70 text-text-secondary hover:border-border-strong hover:bg-bg-surface-raised"
              )}
            >
              <span
                className={cn(
                  "mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-xs border text-[10px]",
                  selected ? "border-brand-cyan text-brand-cyan" : "border-border-strong text-text-muted"
                )}
              >
                {selected ? "✓" : "+"}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-xs font-medium">{nodeLabel(event, lang, text)}</span>
                <span className="mt-1 flex min-w-0 items-center gap-2 text-caption text-text-muted">
                  {index < 3 && <span className="text-brand-orange">Top {index + 1}</span>}
                  <span className="font-mono">{Math.round(event.freshness * 100)}%</span>
                  <span>I{event.influence}</span>
                  {event.aggregateCount && event.aggregateCount > 1 && (
                    <span className="ml-auto shrink-0 rounded-xs border border-border-subtle px-1 font-mono">
                      {event.aggregateCount} {text("源")}
                    </span>
                  )}
                </span>
              </span>
            </button>
          );
        })}
      </div>
    </aside>
  );
}

function EmptyGraphState({
  view,
  eventScoped = false,
  message,
}: {
  view: View;
  eventScoped?: boolean;
  message?: string;
}) {
  const { text } = useI18n();
  const meta = VIEW_META[view];
  const Icon = meta.icon;
  const title = message ? "暂无运行态因果图谱" : eventScoped ? eventScopedEmptyTitle(view) : "当前视图暂无节点";
  const body = eventScoped
    ? "此视图现在只显示当前事件源直接或间接传导到的下游节点。"
    : message
      ? message
    : view === "counter"
      ? "当前样本暂无反证节点，已建议改用证据/反证视图。"
      : "请调整筛选或选择更多事件。";
  return (
    <div className="pointer-events-none absolute inset-0 z-[850] flex items-center justify-center p-8">
      <div className="max-w-sm rounded-sm border border-border-default bg-bg-surface-overlay/95 p-5 text-center shadow-data-panel backdrop-blur-sm">
        <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-sm border border-border-subtle bg-bg-base text-text-secondary">
          <Icon className="h-5 w-5" />
        </div>
        <div className="mt-3 text-sm font-semibold text-text-primary">{text(title)}</div>
        <div className="mt-1 text-xs text-text-secondary">
          {text(body)}
        </div>
      </div>
    </div>
  );
}

function PreviewEmptyGraphState({ message }: { message: string }) {
  const { text } = useI18n();

  return (
    <div className="pointer-events-none absolute inset-0 z-[50] flex items-center justify-center p-6">
      <div className="max-w-[260px] rounded-sm border border-border-default bg-bg-surface-overlay/90 px-4 py-3 text-center text-xs text-text-secondary shadow-inner-panel backdrop-blur-sm">
        <div className="mb-1 text-sm font-semibold text-text-primary">{text("暂无运行态因果图谱")}</div>
        <div>{text(message)}</div>
      </div>
    </div>
  );
}

function SemanticBackdrop({
  viewNodeIds,
  nodes,
  metaByNodeId,
  height,
}: {
  viewNodeIds: Set<string>;
  nodes: CausalNode[];
  metaByNodeId: Map<string, NodeSemanticMeta>;
  height: number;
}) {
  const { lang, text } = useI18n();
  const visibleStages = useMemo(() => {
    const stages = new Set<Stage>();
    for (const node of nodes) {
      if (!viewNodeIds.has(node.id)) continue;
      stages.add((metaByNodeId.get(node.id) ?? semanticMetaForNode(node)).stage);
    }
    return stages;
  }, [metaByNodeId, nodes, viewNodeIds]);

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
                top: 12,
                width: band.width,
                height,
                borderColor: `${meta.color}${active ? "35" : "18"}`,
                background: `linear-gradient(180deg, ${meta.color}${active ? "12" : "07"} 0%, rgba(10,10,10,0.04) 70%)`,
                opacity: active ? 1 : 0.45,
              }}
            >
              <div
                className="absolute left-1/2 top-3 -translate-x-1/2 rounded-xs border bg-black/70 px-2 py-1 text-caption font-medium shadow-inner-panel"
                style={{ borderColor: `${meta.color}42`, color: meta.color }}
              >
                {text(meta.label)}
              </div>
            </div>
          );
        })}
      </div>
    </ViewportPortal>
  );
}

function StageRail({
  viewNodeIds,
  nodes,
  metaByNodeId,
}: {
  viewNodeIds: Set<string>;
  nodes: CausalNode[];
  metaByNodeId: Map<string, NodeSemanticMeta>;
}) {
  const { lang, text } = useI18n();
  const activeStages = useMemo(() => {
    const stages = new Set<Stage>();
    for (const node of nodes) {
      if (!viewNodeIds.has(node.id)) continue;
      stages.add((metaByNodeId.get(node.id) ?? semanticMetaForNode(node)).stage);
    }
    return stages;
  }, [metaByNodeId, nodes, viewNodeIds]);

  return (
    <div className="hidden min-w-[360px] justify-center gap-1 rounded-sm border border-border-default bg-[linear-gradient(180deg,rgba(15,17,16,0.98),rgba(0,0,0,0.98))] px-2 py-1 shadow-inner-panel xl:flex">
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
              title={text(meta.description)}
            >
              {text(meta.label)}
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
  hiddenCount,
  nodes,
  metaByNodeId,
  eventScoped,
}: {
  view: View;
  focusId: string | null;
  visibleCount: number;
  hiddenCount: number;
  nodes: CausalNode[];
  metaByNodeId: Map<string, NodeSemanticMeta>;
  eventScoped: boolean;
}) {
  const { lang, text } = useI18n();
  const meta = VIEW_META[view];
  const Icon = meta.icon;
  const focusNode = focusId ? nodes.find((node) => node.id === focusId) : null;
  const focusMeta = focusNode ? metaByNodeId.get(focusNode.id) ?? semanticMetaForNode(focusNode) : null;

  return (
    <div className="min-w-0 flex-1 rounded-sm border border-border-default bg-[linear-gradient(180deg,rgba(15,17,16,0.98),rgba(0,0,0,0.98))] px-3 py-2 shadow-inner-panel xl:max-w-[620px]">
      <div className="flex items-center gap-2 text-caption text-text-muted">
        <Icon className="h-3.5 w-3.5" />
        <span className="text-text-secondary">{text(meta.label)}</span>
        <span className="font-mono">{visibleCount}/{nodes.length}</span>
        {hiddenCount > 0 && (
          <>
            <span className="text-text-disabled">·</span>
            <span className="font-mono text-brand-cyan">{text("聚合")} {hiddenCount}</span>
          </>
        )}
        {focusNode && (
          <>
            <span className="text-text-disabled">·</span>
            <span className="truncate text-text-primary">{nodeLabel(focusNode, lang, text)}</span>
          </>
        )}
      </div>
      <div className="mt-1 line-clamp-1 text-xs text-text-secondary">
        {focusNode && focusMeta
          ? nodeNarrative(focusNode, focusMeta, lang, text)
          : text(eventScoped ? "事件源作用域：仅展示当前事件源直接或间接传导到的下游节点。" : meta.brief)}
      </div>
    </div>
  );
}

function CausalNodeCard({ data, selected }: NodeProps<CausalFlowNode>) {
  const { lang, text } = useI18n();
  const node = data.causal;
  if (node.type === "cluster") {
    return <ClusterNodeCard data={data} selected={selected} />;
  }
  const meta = data.meta;
  const stage = STAGE_META[meta.stage];
  const sector = SECTOR_META[meta.sector];
  const color = NODE_COLORS[node.type];
  const compact = data.variant === "preview" || (data.density === "curated" && !data.focused && !selected);
  const Icon = nodeIcon(node.type);

  return (
    <div
      className={cn(
        "group relative rounded-sm border bg-[linear-gradient(180deg,rgba(31,31,31,0.94),rgba(8,10,9,0.98))] shadow-data-panel transition duration-200",
        data.variant === "preview" ? "w-[148px] px-3 py-2" : compact ? "w-[176px] px-3 py-2.5" : "w-[196px] px-3.5 py-3",
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
            <span className="truncate text-sm font-semibold text-text-primary">{nodeLabel(node, lang, text)}</span>
            {node.active && (
              <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-brand-emerald-bright" />
            )}
            {node.aggregateCount && node.aggregateCount > 1 && (
              <span className="shrink-0 rounded-xs border border-border-subtle px-1 font-mono text-[10px] leading-4 text-text-secondary">
                {node.aggregateCount} {text("源")}
              </span>
            )}
          </div>
          <div className="mt-1 flex items-center gap-2 text-caption text-text-muted">
            <span style={{ color }}>{text(NODE_LABELS[node.type])}</span>
            <span className="font-mono">{Math.round(node.freshness * 100)}%</span>
            {!compact && <span className="font-mono">I{node.influence}</span>}
          </div>
          {!compact && (
            <div className="mt-2 flex flex-wrap gap-1">
              <span
                className="rounded-xs border px-1.5 py-0.5 text-[10px] leading-none"
                style={{ borderColor: `${stage.color}55`, color: stage.color }}
              >
                {text(stage.label)}
              </span>
              <span
                className="rounded-xs border px-1.5 py-0.5 text-[10px] leading-none"
                style={{ borderColor: `${sector.color}55`, color: sector.color }}
              >
                {text(sector.label)}
              </span>
              {meta.portfolioLinked && (
                <span className="inline-flex items-center gap-1 rounded-xs border border-brand-emerald/40 px-1.5 py-0.5 text-[10px] leading-none text-brand-emerald-bright">
                  <Briefcase className="h-2.5 w-2.5" />
                  {text("Position")}
                </span>
              )}
              {meta.alertLinked && (
                <span className="inline-flex items-center gap-1 rounded-xs border border-brand-orange/40 px-1.5 py-0.5 text-[10px] leading-none text-brand-orange">
                  <Target className="h-2.5 w-2.5" />
                  {text("Alert")}
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
            <span>{text("上游")}</span>
          </div>
          <div className="flex items-center justify-end gap-1.5 text-text-muted">
            <span>{text("下游")}</span>
            <span className="font-mono">{data.downstream}</span>
            <Network className="h-3 w-3" />
          </div>
        </div>
      )}
    </div>
  );
}

function ClusterNodeCard({
  data,
  selected,
}: {
  data: CausalFlowNodeData;
  selected?: boolean;
}) {
  const { lang, text } = useI18n();
  const meta = data.meta;
  const stage = STAGE_META[meta.stage];
  const count = data.aggregateCount ?? data.causal.aggregateCount ?? 0;

  return (
    <div
      className={cn(
        "group relative w-[176px] rounded-sm border border-dashed bg-[linear-gradient(180deg,rgba(25,25,25,0.86),rgba(5,7,6,0.94))] px-3 py-2.5 shadow-inner-panel transition duration-200 hover:border-brand-cyan/55 hover:bg-bg-surface-raised",
        data.dimmed && "opacity-40",
        selected && "ring-1 ring-brand-cyan"
      )}
      style={{
        borderColor: `${stage.color}55`,
      }}
    >
      <Handle type="target" position={Position.Left} className="!h-2 !w-2 !opacity-0" />
      <Handle type="source" position={Position.Right} className="!h-2 !w-2 !opacity-0" />
      <div className="flex items-center gap-3">
        <div
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xs border bg-bg-base"
          style={{ borderColor: `${stage.color}66`, color: stage.color }}
        >
          <Layers className="h-4 w-4" />
        </div>
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-mono text-sm text-text-primary">+{count}</span>
            <span className="truncate text-xs text-text-secondary">{text("更多节点")}</span>
          </div>
          <div className="mt-1 text-caption text-text-muted">
            {text(stage.label)} · {text("点击展开")}
          </div>
        </div>
      </div>
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
  const { text } = useI18n();
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
            className="nodrag nopan absolute rounded-xs border border-border-default bg-bg-surface-overlay/95 px-2 py-1 text-caption text-text-secondary shadow-data-panel backdrop-blur-sm"
            style={{
              transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
              borderColor: `${color}55`,
            }}
          >
            <span className="font-mono text-text-primary">{edge.lag}</span>
            <span className="mx-1 text-text-muted">·</span>
            <span className="font-mono">{Math.round(edge.hitRate * 100)}% {text("hit")}</span>
            <span className="mx-1 text-text-muted">·</span>
            <span className="font-mono">{Math.round(edge.confidence * 100)}% {text("conf")}</span>
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
  hiddenCount,
  nodes,
  edges,
}: {
  focusId: string | null;
  mode: Mode;
  view: View;
  visibleCount: number;
  hiddenCount: number;
  nodes: CausalNode[];
  edges: CausalEdge[];
}) {
  const { lang, text } = useI18n();
  const { activeNodes, focusNode, verifiedEdges } = useMemo(() => {
    let active = 0;
    let focused: CausalNode | null = null;
    let verified = 0;

    for (const node of nodes) {
      if (node.active) active += 1;
      if (focusId && node.id === focusId) focused = node;
    }
    for (const edge of edges) {
      if (edge.verified) verified += 1;
    }

    return {
      activeNodes: active,
      focusNode: focused,
      verifiedEdges: verified,
    };
  }, [edges, focusId, nodes]);
  const ModeIcon = mode === "live" ? Activity : mode === "replay" ? RotateCcw : Search;
  const ViewIcon = VIEW_META[view].icon;

  return (
    <div className="flex flex-wrap items-stretch gap-1.5 rounded-sm border border-border-default bg-[linear-gradient(180deg,rgba(15,17,16,0.98),rgba(0,0,0,0.98))] p-1 shadow-inner-panel">
      <StatCell icon={ModeIcon} label={text("Mode")} value={text(mode)} />
      <StatCell icon={ViewIcon} label={text("View")} value={text(VIEW_META[view].label)} />
      <StatCell icon={CircleDot} label={text("Active")} value={`${activeNodes}/${nodes.length}`} />
      <StatCell icon={CheckCircle2} label={text("Verified")} value={`${verifiedEdges}/${edges.length}`} />
      <div className="min-w-[108px] rounded-xs border border-border-subtle bg-bg-base px-2 py-1 text-caption text-text-muted shadow-inner-panel">
        <span>{text("Visible")}</span>
        <span className="ml-2 font-mono text-xs text-text-primary">{visibleCount}/{nodes.length}</span>
        {hiddenCount > 0 && (
          <span className="ml-2 font-mono text-xs text-brand-cyan">+{hiddenCount}</span>
        )}
        {focusId && (
          <div className="mt-1 max-w-40 truncate text-text-secondary">
            {focusNode ? nodeLabel(focusNode, lang, text) : ""}
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
    <div className="min-w-14 rounded-xs border border-border-subtle bg-bg-base px-2 py-1 shadow-inner-panel">
      <div className="flex items-center gap-1.5 text-caption text-text-muted">
        <Icon className="h-3 w-3" />
        {label}
      </div>
      <div className="mt-0.5 max-w-16 truncate font-mono text-xs text-text-primary">{value}</div>
    </div>
  );
}

function NodeDetails({
  node,
  nodes,
  edges,
  meta,
  onClose,
}: {
  node: CausalNode;
  nodes: CausalNode[];
  edges: CausalEdge[];
  meta: NodeSemanticMeta;
  onClose: () => void;
}) {
  const { lang, text } = useI18n();
  const { downstream, upstream } = useMemo(() => {
    const nextUpstream: CausalEdge[] = [];
    const nextDownstream: CausalEdge[] = [];
    for (const edge of edges) {
      if (edge.target === node.id) nextUpstream.push(edge);
      if (edge.source === node.id) nextDownstream.push(edge);
    }
    return {
      downstream: nextDownstream,
      upstream: nextUpstream,
    };
  }, [edges, node.id]);
  const stage = STAGE_META[meta.stage];
  const sector = SECTOR_META[meta.sector];
  const color = NODE_COLORS[node.type];
  const Icon = nodeIcon(node.type);

  return (
    <div className="absolute inset-x-4 bottom-4 top-4 z-[1100] flex min-h-0 flex-col overflow-hidden rounded-sm border border-border-default bg-[linear-gradient(180deg,rgba(31,31,31,0.98),rgba(3,5,4,0.98))] shadow-data-panel animate-fade-in sm:left-auto sm:w-[396px]">
      <div className="shrink-0 border-b border-border-subtle bg-bg-base/40 p-4 shadow-inner-panel">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-3">
            <div
              className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-sm border shadow-inner-panel"
              style={{ borderColor: color, backgroundColor: `${color}22`, color }}
            >
              <Icon className="h-4 w-4" />
            </div>
            <div>
              <div className="text-h3 text-text-primary">{nodeLabel(node, lang, text)}</div>
              <div className="mt-1 text-caption" style={{ color }}>
                {text(NODE_LABELS[node.type])}
              </div>
            </div>
          </div>
          <button
            type="button"
            title={text("Close")}
            aria-label={text("Close node details")}
            onClick={onClose}
            className="flex h-7 w-7 items-center justify-center rounded-xs border border-transparent text-text-muted transition-colors hover:border-border-subtle hover:bg-bg-surface-raised hover:text-text-primary"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-4">
        <div className="rounded-xs border border-border-subtle bg-bg-base p-3 text-sm text-text-secondary shadow-inner-panel">
          {nodeNarrative(node, meta, lang, text)}
        </div>

        <div className="mt-3 flex flex-wrap gap-1.5">
          <span
            className="rounded-xs border px-2 py-1 text-caption"
            style={{ borderColor: `${stage.color}55`, color: stage.color }}
          >
            {text(stage.label)}
          </span>
          <span
            className="rounded-xs border px-2 py-1 text-caption"
            style={{ borderColor: `${sector.color}55`, color: sector.color }}
          >
            {text(sector.label)}
          </span>
          {nodeTags(node, meta, lang).map((tag) => (
            <span key={tag} className="rounded-xs border border-border-subtle px-2 py-1 text-caption text-text-muted">
              {text(tag)}
            </span>
          ))}
          {meta.portfolioLinked && (
            <span className="inline-flex items-center gap-1 rounded-xs border border-brand-emerald/40 px-2 py-1 text-caption text-brand-emerald-bright">
              <Briefcase className="h-3 w-3" />
              {text("Position")}
            </span>
          )}
          {meta.alertLinked && (
            <span className="inline-flex items-center gap-1 rounded-xs border border-brand-orange/40 px-2 py-1 text-caption text-brand-orange">
              <Target className="h-3 w-3" />
              {text("Alert")}
            </span>
          )}
        </div>

        <div className="mt-4 grid grid-cols-3 gap-2">
          <DetailMetric label={text("Fresh")} value={`${Math.round(node.freshness * 100)}%`} />
          <DetailMetric label={text("Impact")} value={`${node.influence}/4`} />
          <DetailMetric label={text("State")} value={node.active ? text("Active") : text("Quiet")} />
        </div>

        <div className="mt-3 rounded-xs border border-border-subtle bg-bg-base p-3 shadow-inner-panel">
          <div className="mb-2 flex items-center justify-between text-caption text-text-muted">
            <span>{text("Propagation")}</span>
            <span className="font-mono text-text-secondary">
              {upstream.length} {text("upstream")} / {downstream.length} {text("downstream")}
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="h-1.5 flex-1 rounded-full" style={{ backgroundColor: `${stage.color}CC` }} />
            <div className="h-1.5 flex-1 rounded-full bg-border-strong" />
            <div className="h-1.5 flex-1 rounded-full" style={{ backgroundColor: `${sector.color}CC` }} />
          </div>
        </div>

        <EdgeList title="上游" edges={upstream} side="source" nodes={nodes} />
        <EdgeList title="下游" edges={downstream} side="target" nodes={nodes} />
      </div>
    </div>
  );
}

function DetailMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xs border border-border-subtle bg-bg-base p-2 shadow-inner-panel">
      <div className="text-caption text-text-muted">{label}</div>
      <div className="mt-1 font-mono text-sm text-text-primary">{value}</div>
    </div>
  );
}

function EdgeList({
  title,
  edges,
  side,
  nodes,
}: {
  title: string;
  edges: CausalEdge[];
  side: "source" | "target";
  nodes: CausalNode[];
}) {
  const { lang, text } = useI18n();
  if (edges.length === 0) return null;
  return (
    <div className="mt-4">
      <div className="mb-2 text-caption uppercase tracking-wide text-text-muted">
        {text(title)} {edges.length}
      </div>
      <div className="space-y-2">
        {edges.map((edge) => {
          const peer = nodes.find((node) => node.id === edge[side]);
          const color = EDGE_COLORS[edge.direction];
          return (
            <div key={edge.id} className="rounded-xs border border-border-subtle bg-bg-base p-2 shadow-inner-panel">
              <div className="flex items-center justify-between gap-2">
                <span className="truncate text-sm text-text-secondary">{peer ? nodeLabel(peer, lang, text) : ""}</span>
                <span className="font-mono text-caption" style={{ color }}>
                  {Math.round(edge.confidence * 100)}%
                </span>
              </div>
              <div className="mt-1 flex items-center justify-between text-caption text-text-muted">
                <span className="inline-flex items-center gap-1">
                  <Clock className="h-3 w-3" />
                  {edge.lag}
                </span>
                <span className="font-mono">{text("hit")} {Math.round(edge.hitRate * 100)}%</span>
              </div>
              <div className="mt-1 flex items-center justify-between text-caption text-text-muted">
                <span style={{ color }}>{text(edge.direction)}</span>
                <span className={cn("inline-flex items-center gap-1", edge.verified ? "text-brand-emerald-bright" : "text-text-muted")}>
                  <CheckCircle2 className="h-3 w-3" />
                  {edge.verified ? text("verified") : text("unverified")}
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
  const { text } = useI18n();

  return (
    <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1.5 rounded-sm border border-border-default bg-[linear-gradient(180deg,rgba(15,17,16,0.98),rgba(0,0,0,0.98))] px-3 py-2 shadow-inner-panel">
      <div className="flex items-center gap-2 text-caption font-medium text-text-secondary">
        <Network className="h-3.5 w-3.5" />
        {text("Causal Layers")}
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
            {text(NODE_LABELS[type])}
          </div>
        );
      })}
      <div className="hidden h-5 w-px bg-border-subtle xl:block" />
      <div className="flex items-center gap-2 text-caption font-medium text-text-secondary">
        <Layers className="h-3.5 w-3.5" />
        {text("Semantic Stages")}
      </div>
      {STAGE_ORDER.map((stage) => {
        const meta = STAGE_META[stage];
        return (
          <div key={stage} className="flex items-center gap-1.5 text-caption text-text-muted">
            <span
              className="h-1.5 w-5 rounded-full"
              style={{ backgroundColor: meta.color }}
            />
            {text(meta.label)}
          </div>
        );
      })}
    </div>
  );
}

interface DisplayGraph {
  nodes: CausalNode[];
  edges: CausalEdge[];
  nodeIds: Set<string>;
  hiddenCount: number;
  visibleRealCount: number;
  height: number;
}

function normalizeEventGraph(nodes: CausalNode[], edges: CausalEdge[]) {
  const eventGroups = new Map<string, CausalNode[]>();
  for (const node of nodes) {
    if (node.type !== "event") continue;
    const key = eventDisplayKey(node);
    eventGroups.set(key, [...(eventGroups.get(key) ?? []), node]);
  }

  if (![...eventGroups.values()].some((group) => group.length > 1)) {
    return { nodes, edges };
  }

  const representativeByEventId = new Map<string, string>();
  const mergedByKey = new Map<string, CausalNode>();
  for (const [key, group] of eventGroups) {
    const merged = mergeEventGroup(group);
    mergedByKey.set(key, merged);
    for (const node of group) {
      representativeByEventId.set(node.id, merged.id);
    }
  }

  const emittedEventKeys = new Set<string>();
  const normalizedNodes: CausalNode[] = [];
  for (const node of nodes) {
    if (node.type !== "event") {
      normalizedNodes.push(node);
      continue;
    }
    const key = eventDisplayKey(node);
    if (emittedEventKeys.has(key)) continue;
    emittedEventKeys.add(key);
    normalizedNodes.push(mergedByKey.get(key) ?? node);
  }

  const normalizedEdges = new Map<string, CausalEdge>();
  for (const edge of edges) {
    const source = representativeByEventId.get(edge.source) ?? edge.source;
    const target = representativeByEventId.get(edge.target) ?? edge.target;
    if (source === target) continue;

    const mergeKey = `${source}->${target}`;
    const current = normalizedEdges.get(mergeKey);
    const candidate: CausalEdge = {
      ...edge,
      id: current?.id ?? (source === edge.source && target === edge.target ? edge.id : `edge-event-merged-${source}-${target}`),
      source,
      target,
    };
    if (!current) {
      normalizedEdges.set(mergeKey, candidate);
      continue;
    }
    normalizedEdges.set(mergeKey, {
      ...candidate,
      id: current.id,
      confidence: Math.max(current.confidence, candidate.confidence),
      hitRate: Math.max(current.hitRate, candidate.hitRate),
      verified: current.verified || candidate.verified,
      direction: current.confidence >= candidate.confidence ? current.direction : candidate.direction,
      lag: current.confidence >= candidate.confidence ? current.lag : candidate.lag,
    });
  }

  return {
    nodes: normalizedNodes,
    edges: [...normalizedEdges.values()],
  };
}

function mergeEventGroup(group: CausalNode[]): CausalNode {
  const representative = [...group].sort((a, b) => {
    if (Number(b.active) !== Number(a.active)) return Number(b.active) - Number(a.active);
    if (b.influence !== a.influence) return b.influence - a.influence;
    return b.freshness - a.freshness;
  })[0];
  const tags = uniqueStrings(group.flatMap((node) => node.tags ?? [])).slice(0, 6);
  const tagsZh = uniqueStrings(group.flatMap((node) => node.tagsZh ?? [])).slice(0, 6);
  const tagsEn = uniqueStrings(group.flatMap((node) => node.tagsEn ?? [])).slice(0, 6);
  const narrativeZh = representative.narrativeZh ?? representative.narrative;
  const narrativeEn = representative.narrativeEn ?? representative.narrative;

  return {
    ...representative,
    freshness: Math.max(...group.map((node) => node.freshness)),
    influence: Math.max(...group.map((node) => node.influence)) as CausalNode["influence"],
    active: group.some((node) => node.active),
    tags,
    tagsZh,
    tagsEn,
    narrativeZh: group.length > 1 && narrativeZh ? `已合并 ${group.length} 条同类事件源。${narrativeZh}` : narrativeZh,
    narrativeEn: group.length > 1 && narrativeEn ? `Merged ${group.length} related event sources. ${narrativeEn}` : narrativeEn,
    portfolioLinked: group.some((node) => node.portfolioLinked),
    alertLinked: group.some((node) => node.alertLinked),
    aggregateCount: group.length,
  };
}

function uniqueStrings(items: string[]) {
  const seen = new Set<string>();
  const result: string[] = [];
  for (const item of items) {
    const trimmed = item.trim();
    if (!trimmed) continue;
    const key = trimmed.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    result.push(trimmed);
  }
  return result;
}

function fitAnchorNodes(height: number, variant: "full" | "preview"): CausalFlowNode[] {
  const width = variant === "preview" ? 1660 : 1780;
  const bottom = Math.max(variant === "preview" ? 560 : 760, height + 24);
  return [
    fitAnchorNode(FIT_ANCHOR_TOP_ID, { x: -42, y: 0 }),
    fitAnchorNode(FIT_ANCHOR_BOTTOM_ID, { x: width, y: bottom }),
  ];
}

function fitAnchorNode(id: string, position: { x: number; y: number }): CausalFlowNode {
  const causal: CausalNode = {
    id,
    type: "cluster",
    label: "",
    freshness: 0,
    influence: 1,
    active: false,
    stage: "source",
    sector: "geo",
    tags: [],
    narrative: "",
  };
  return {
    id,
    type: "causalNode",
    position,
    data: {
      causal,
      meta: {
        stage: "source",
        sector: "geo",
        tags: [],
        narrative: "",
      },
      upstream: 0,
      downstream: 0,
      focused: false,
      dimmed: false,
      viewDimmed: false,
      variant: "full",
      density: "curated",
    },
    draggable: false,
    selectable: false,
    focusable: false,
    style: {
      opacity: 0,
      pointerEvents: "none",
    },
  };
}

function buildDisplayGraph({
  nodes,
  edges,
  baseNodeIds,
  metaByNodeId,
  relationCounts,
  density,
  variant,
  focusNodeIds,
}: {
  nodes: CausalNode[];
  edges: CausalEdge[];
  baseNodeIds: Set<string>;
  metaByNodeId: Map<string, NodeSemanticMeta>;
  relationCounts: Map<string, { upstream: number; downstream: number }>;
  density: Density;
  variant: "full" | "preview";
  focusNodeIds: Set<string>;
}): DisplayGraph {
  const baseNodes: CausalNode[] = [];
  const baseNodesByStage = new Map<Stage, CausalNode[]>(
    STAGE_ORDER.map((stage) => [stage, []])
  );
  for (const node of nodes) {
    if (!baseNodeIds.has(node.id)) continue;
    baseNodes.push(node);
    const stage = (metaByNodeId.get(node.id) ?? semanticMetaForNode(node)).stage;
    baseNodesByStage.get(stage)?.push(node);
  }
  const limits = variant === "preview" ? PREVIEW_STAGE_LIMITS : CORE_STAGE_LIMITS;
  const selected: CausalNode[] = [];
  let hiddenCount = 0;

  if (density === "expanded") {
    selected.push(...baseNodes);
  } else {
    for (const stage of STAGE_ORDER) {
      const stageNodes = (baseNodesByStage.get(stage) ?? []).sort(
        (a, b) => nodePriority(b, metaByNodeId, relationCounts) - nodePriority(a, metaByNodeId, relationCounts)
      );
      const keep = new Map<string, CausalNode>();
      for (const node of stageNodes.slice(0, limits[stage])) {
        keep.set(node.id, node);
      }
      for (const node of stageNodes) {
        if (focusNodeIds.has(node.id)) keep.set(node.id, node);
      }
      selected.push(...keep.values());
      const stageHiddenCount = stageNodes.length - keep.size;
      hiddenCount += stageHiddenCount;
      if (stageHiddenCount > 0) {
        selected.push(clusterNodeForStage(stage, stageHiddenCount));
      }
    }
  }

  const laidOutNodes = layoutDisplayNodes(selected, metaByNodeId, relationCounts, density, variant);
  const nodeIds = new Set<string>();
  const realNodeIds = new Set<string>();
  const laidOutStageCounts = new Map<Stage, number>();
  for (const node of laidOutNodes) {
    nodeIds.add(node.id);
    const stage = (metaByNodeId.get(node.id) ?? semanticMetaForNode(node)).stage;
    laidOutStageCounts.set(stage, (laidOutStageCounts.get(stage) ?? 0) + 1);
    if (node.type !== "cluster") realNodeIds.add(node.id);
  }
  const displayEdges = edges.filter((edge) => realNodeIds.has(edge.source) && realNodeIds.has(edge.target));
  const maxStageCount = Math.max(
    1,
    ...STAGE_ORDER.map((stage) => laidOutStageCounts.get(stage) ?? 0)
  );
  const yStep = nodeYStep(density, variant);

  return {
    nodes: laidOutNodes,
    edges: displayEdges,
    nodeIds,
    hiddenCount,
    visibleRealCount: realNodeIds.size,
    height: Math.max(830, 112 + maxStageCount * yStep + 120),
  };
}

function layoutDisplayNodes(
  nodes: CausalNode[],
  metaByNodeId: Map<string, NodeSemanticMeta>,
  relationCounts: Map<string, { upstream: number; downstream: number }>,
  density: Density,
  variant: "full" | "preview"
): CausalNode[] {
  const yStep = nodeYStep(density, variant);
  const yStart = variant === "preview" ? 58 : 76;
  return STAGE_ORDER.flatMap((stage) => {
    const stageNodes = nodes
      .filter((node) => (metaByNodeId.get(node.id) ?? semanticMetaForNode(node)).stage === stage)
      .sort((a, b) => {
        if (a.type === "cluster") return 1;
        if (b.type === "cluster") return -1;
        return nodePriority(b, metaByNodeId, relationCounts) - nodePriority(a, metaByNodeId, relationCounts);
      });
    return stageNodes.map((node, index) => ({
      ...node,
      x: STAGE_NODE_X[stage],
      y: yStart + STAGE_Y_OFFSET[stage] + index * yStep,
    }));
  });
}

function nodeYStep(density: Density, variant: "full" | "preview") {
  if (variant === "preview") return 116;
  return density === "expanded" ? 154 : 128;
}

function clusterNodeForStage(stage: Stage, count: number): CausalNode {
  return {
    id: `cluster-${stage}`,
    type: "cluster",
    label: `+${count}`,
    freshness: 0,
    influence: 1,
    active: false,
    stage,
    sector: stage === "impact" ? "positioning" : "geo",
    tags: [STAGE_META[stage].label],
    narrative: "该阶段还有更多节点，切换完整视图后展开。",
    aggregateCount: count,
  };
}

function nodePriority(
  node: CausalNode,
  metaByNodeId: Map<string, NodeSemanticMeta>,
  relationCounts: Map<string, { upstream: number; downstream: number }>
) {
  const meta = metaByNodeId.get(node.id) ?? semanticMetaForNode(node);
  const degree = relationCounts.get(node.id) ?? { upstream: 0, downstream: 0 };
  const typeWeight: Record<CausalNode["type"], number> = {
    event: 4,
    signal: 7,
    metric: 3,
    alert: 9,
    counter: 5,
    cluster: 0,
  };
  return (
    node.influence * 14 +
    node.freshness * 10 +
    (node.active ? 6 : 0) +
    (degree.upstream + degree.downstream) * 4 +
    (meta.alertLinked ? 10 : 0) +
    (meta.portfolioLinked ? 8 : 0) +
    typeWeight[node.type]
  );
}

function eventDisplayKey(node: CausalNode) {
  const symbols = (node.tags ?? []).filter((tag) => /^[A-Z]{1,3}$/.test(tag)).join("|");
  return `${node.labelZh || node.label}|${symbols}`;
}

function eventScopedEmptyTitle(view: View) {
  if (view === "portfolio") return "当前事件源暂无持仓下游";
  if (view === "counter") return "当前事件源暂无反证下游";
  if (view === "alerts") return "当前事件源暂无预警下游";
  return "当前事件源暂无下游节点";
}

function nodeLabel(node: CausalNode, lang: Language, text: (source: string) => string) {
  if (lang === "zh") return text(node.labelZh || node.label || "");
  return text(node.labelEn || node.label || "");
}

function nodeNarrative(
  node: CausalNode,
  meta: NodeSemanticMeta,
  lang: Language,
  text: (source: string) => string
) {
  if (lang === "zh") return text(node.narrativeZh || meta.narrative);
  return text(node.narrativeEn || meta.narrative);
}

function nodeTags(node: CausalNode, meta: NodeSemanticMeta, lang: Language) {
  if (lang === "zh" && node.tagsZh?.length) return node.tagsZh;
  if (lang === "en" && node.tagsEn?.length) return node.tagsEn;
  return meta.tags;
}

function viewVisibleNodeIds(
  view: View,
  nodes: CausalNode[],
  edges: CausalEdge[],
  metaByNodeId: Map<string, NodeSemanticMeta>,
  options: { allowCounterFallback?: boolean } = {}
): Set<string> {
  if (view === "all") return new Set(nodes.map((node) => node.id));
  const allowCounterFallback = options.allowCounterFallback ?? true;

  const rootIds = nodes.filter((node) => {
    const meta = metaByNodeId.get(node.id) ?? semanticMetaForNode(node);
    if (view === "portfolio") return Boolean(meta.portfolioLinked);
    if (view === "counter") return node.type === "counter";
    return Boolean(meta.alertLinked) || node.type === "alert";
  }).map((node) => node.id);

  if (view === "counter" && rootIds.length === 0 && allowCounterFallback) {
    return new Set(
      nodes
        .filter((node) => {
          const meta = metaByNodeId.get(node.id) ?? semanticMetaForNode(node);
          return node.type === "metric" || meta.stage === "validation";
        })
        .map((node) => node.id)
    );
  }

  const ids = new Set<string>();
  for (const rootId of rootIds) {
    for (const id of causalChainIds(rootId, edges)) {
      ids.add(id);
    }
  }
  return ids;
}

function causalChainIds(focusId: string | null, edges: CausalEdge[], maxDepth = Number.POSITIVE_INFINITY): Set<string> {
  if (!focusId) return new Set<string>();
  const ids = new Set<string>([focusId]);
  const visit = (id: string, direction: "forward" | "backward", depth: number) => {
    if (depth >= maxDepth) return;
    for (const edge of edges) {
      if (direction === "forward" && edge.source === id && !ids.has(edge.target)) {
        ids.add(edge.target);
        visit(edge.target, "forward", depth + 1);
      }
      if (direction === "backward" && edge.target === id && !ids.has(edge.source)) {
        ids.add(edge.source);
        visit(edge.source, "backward", depth + 1);
      }
    }
  };
  visit(focusId, "forward", 0);
  visit(focusId, "backward", 0);
  return ids;
}

function downstreamChainIds(focusId: string, edges: CausalEdge[], maxDepth = Number.POSITIVE_INFINITY): Set<string> {
  const ids = new Set<string>([focusId]);
  const visit = (id: string, depth: number) => {
    if (depth >= maxDepth) return;
    for (const edge of edges) {
      if (edge.source === id && !ids.has(edge.target)) {
        ids.add(edge.target);
        visit(edge.target, depth + 1);
      }
    }
  };
  visit(focusId, 0);
  return ids;
}

function semanticMetaForNode(node: CausalNode): NodeSemanticMeta {
  const fallback = NODE_META[node.id];
  if (fallback && !node.stage && !node.sector && !node.narrative) return fallback;
  const stage = node.stage ?? fallback?.stage ?? stageForNodeType(node.type);
  const sector = node.sector ?? fallback?.sector ?? sectorForLabel(node.label);
  return {
    stage,
    sector,
    tags: node.tags ?? fallback?.tags ?? [],
    narrative: node.narrative ?? fallback?.narrative ?? "运行态事件链路节点。",
    portfolioLinked: node.portfolioLinked ?? fallback?.portfolioLinked,
    alertLinked: node.alertLinked ?? fallback?.alertLinked,
  };
}

function stageForNodeType(type: CausalNode["type"]): Stage {
  if (type === "event") return "source";
  if (type === "alert") return "impact";
  if (type === "cluster") return "validation";
  if (type === "metric" || type === "counter") return "validation";
  return "thesis";
}

function sectorForLabel(label: string): Sector {
  const value = label.toLowerCase();
  if (/(sc|原油|pta|pp|energy|eia|fred|oil)/i.test(value)) return "energy";
  if (/(ru|nr|br|橡胶|rubber|latex)/i.test(value)) return "rubber";
  if (/(rb|hc|jm|焦|铁|螺纹|ferrous)/i.test(value)) return "ferrous";
  if (/(cu|al|zn|ni|铜|铝|锌|镍|metals)/i.test(value)) return "metals";
  if (/(^|\b)(m|y|p)(\b|$)|豆|棕榈|agri/i.test(value)) return "agri";
  if (/(au|ag|黄金|白银|precious)/i.test(value)) return "precious";
  if (/(position|持仓|cftc)/i.test(value)) return "positioning";
  return "geo";
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
    case "cluster":
      return Layers;
  }
}
