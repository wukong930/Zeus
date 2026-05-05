"use client";

import { useState } from "react";
import { Sparkles, X, Send, MessageSquare } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "./Button";
import { useI18n } from "@/lib/i18n";
import {
  fetchAlertsFromApi,
  fetchCausalWebGraph,
  fetchLLMUsageSummary,
  fetchPortfolioSnapshot,
} from "@/lib/api";

const SUGGESTED_QUERIES = [
  "为什么 RB 触发了 cost_support_pressure？",
  "解释一下当前的 Drift 状态",
  "我的橡胶持仓有哪些下游风险？",
  "对比上月和本月的命中率变化",
];

export function AICompanion() {
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<{ role: "user" | "assistant"; content: string }[]>([]);
  const [loading, setLoading] = useState(false);
  const { text, lang } = useI18n();

  const send = async (text: string) => {
    const query = text.trim();
    if (!query || loading) return;
    setMessages((m) => [...m, { role: "user", content: query }]);
    setInput("");
    setLoading(true);
    try {
      const response = await buildRuntimeResponse(query, lang);
      setMessages((m) => [...m, { role: "assistant", content: response }]);
    } catch {
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          content:
            lang === "en"
              ? "I could not sync the backend runtime context, so I did not generate an offline demo answer."
              : "当前无法同步后端运行态上下文，因此没有生成离线演示回答。",
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className={cn(
          "fixed bottom-5 right-5 z-50 h-12 w-12 rounded-full border border-brand-emerald/40 bg-brand-emerald shadow-glow-emerald",
          "flex items-center justify-center text-white",
          "transition-all duration-200 hover:scale-105 hover:bg-brand-emerald-hover",
          open && "scale-0 opacity-0"
        )}
        aria-label={text("Open AI Companion")}
      >
        <Sparkles className="w-5 h-5" />
      </button>

      <div
        className={cn(
          "fixed inset-0 z-40 transition-opacity duration-300",
          open ? "opacity-100" : "opacity-0 pointer-events-none"
        )}
        style={{ background: "rgba(0,0,0,0.68)", backdropFilter: "blur(4px)" }}
        onClick={() => setOpen(false)}
      />
      <aside
        className={cn(
          "fixed bottom-0 right-0 top-0 z-50 flex w-[420px] flex-col border-l border-border-default bg-[linear-gradient(180deg,rgba(31,31,31,0.98),rgba(5,7,6,0.98))] shadow-data-panel",
          "transition-transform duration-400 ease-decelerate",
          open ? "translate-x-0" : "translate-x-full"
        )}
      >
        <div className="flex h-16 items-center justify-between border-b border-border-default px-5">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-sm border border-brand-emerald/30 bg-brand-emerald/10 text-brand-emerald-bright">
              <Sparkles className="h-4 w-4" />
            </div>
            <div>
              <span className="block text-h3 font-semibold">AI Companion</span>
              <span className="text-caption text-text-muted">{text("Context aware research copilot")}</span>
            </div>
          </div>
          <button
            onClick={() => setOpen(false)}
            className="rounded-sm border border-transparent p-1 text-text-muted transition-colors hover:border-border-subtle hover:bg-bg-surface-raised hover:text-text-primary"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          {messages.length === 0 && (
            <div className="space-y-4">
              <div className="rounded-sm border border-border-subtle bg-bg-base p-4 text-sm leading-relaxed text-text-secondary shadow-inner-panel">
                {text("我是你的 Zeus 研究伙伴。我知道你当前在哪个页面、看哪个预警，可以帮你解释、对比、追问。")}
              </div>
              <div className="space-y-2">
                <div className="text-caption text-text-muted uppercase tracking-wider">{text("建议提问")}</div>
                {SUGGESTED_QUERIES.map((q) => (
                  <button
                    key={q}
                    onClick={() => send(text(q))}
                    className="w-full rounded-sm border border-border-subtle bg-bg-base px-3 py-2 text-left text-sm text-text-secondary shadow-inner-panel transition-colors hover:border-border-default hover:bg-bg-surface-raised hover:text-text-primary"
                  >
                    {text(q)}
                  </button>
                ))}
              </div>
            </div>
          )}
          {messages.map((m, i) => (
            <div
              key={i}
              className={cn(
                "rounded-sm border p-3 text-sm leading-relaxed shadow-inner-panel",
                m.role === "user"
                  ? "ml-6 border-brand-emerald/30 bg-brand-emerald/15"
                  : "mr-6 border-border-subtle bg-bg-base"
              )}
            >
              <div className="text-caption text-text-muted mb-1">
                {m.role === "user" ? text("你") : "Zeus"}
              </div>
              <div className="text-text-primary whitespace-pre-line">{m.content}</div>
            </div>
          ))}
          {loading && (
            <div className="flex items-center gap-2 rounded-sm border border-border-subtle bg-bg-base px-3 py-2 text-sm text-text-muted shadow-inner-panel">
              <MessageSquare className="w-4 h-4 animate-pulse" />
              {text("思考中...")}
            </div>
          )}
        </div>

        <div className="border-t border-border-default bg-bg-base/60 p-4">
          <div className="flex gap-2">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && send(input)}
              placeholder={text("问点什么...")}
              className="h-9 flex-1 rounded-sm border border-border-default bg-bg-base px-3 text-sm text-text-primary placeholder:text-text-muted shadow-inner-panel focus:border-brand-emerald focus:outline-none focus:shadow-focus-ring"
            />
            <Button onClick={() => send(input)} size="md" disabled={loading}>
              <Send className="w-4 h-4" />
            </Button>
          </div>
          <div className="text-caption text-text-muted mt-2">
            {text("上下文：当前页面 + 最近 3 条预警")}
          </div>
        </div>
      </aside>
    </>
  );
}

async function buildRuntimeResponse(query: string, lang: string): Promise<string> {
  const [alertsResult, portfolioResult, causalResult, usageResult] = await Promise.allSettled([
    fetchAlertsFromApi(),
    fetchPortfolioSnapshot(),
    fetchCausalWebGraph(),
    fetchLLMUsageSummary(),
  ]);
  const alerts = settledValue(alertsResult) ?? [];
  const portfolio = settledValue(portfolioResult);
  const causal = settledValue(causalResult);
  const usage = settledValue(usageResult);

  if (!alerts.length && !portfolio && !causal && !usage) {
    throw new Error("runtime context unavailable");
  }

  const topAlert = alerts[0];
  const positions = portfolio?.positions ?? [];
  const totalPnl = positions.reduce((sum, position) => sum + position.pnl, 0);
  const activeSignals = causal?.nodes.filter((node) => node.type === "signal" && node.active).length ?? 0;
  const nodeCount = causal?.nodes.length ?? 0;
  const edgeCount = causal?.edges.length ?? 0;

  if (lang === "en") {
    return [
      "Runtime context summary",
      `Question: ${query}`,
      "",
      topAlert
        ? `Alerts: ${alerts.length} active rows. Top alert is ${topAlert.symbol} / ${topAlert.title}, confidence ${Math.round(topAlert.confidence * 100)}%.`
        : "Alerts: no active alert rows returned by the API.",
      `Portfolio: ${positions.length} open positions, floating PnL ${formatCurrency(totalPnl)}${portfolio?.degraded ? " (partially degraded)" : ""}.`,
      `Causal Web: ${nodeCount} nodes, ${edgeCount} edges, ${activeSignals} active signal nodes.`,
      usage
        ? `LLM usage: ${usage.calls} calls this month, estimated cost $${usage.estimated_cost_usd.toFixed(2)}.`
        : "LLM usage: unavailable from the backend.",
      "",
      "Next step: open the related alert or Causal Web node before making a trading decision; this answer is composed from live runtime context, not a fixed demo script.",
    ].join("\n");
  }

  return [
    "运行态上下文摘要",
    `问题：${query}`,
    "",
    topAlert
      ? `预警：接口返回 ${alerts.length} 条；最高优先为 ${topAlert.symbol} / ${topAlert.title}，置信度 ${Math.round(topAlert.confidence * 100)}%。`
      : "预警：接口当前没有返回活跃预警。",
    `持仓：${positions.length} 个开放持仓，浮动盈亏 ${formatCurrency(totalPnl)}${portfolio?.degraded ? "（部分降级）" : ""}。`,
    `因果网络：${nodeCount} 个节点、${edgeCount} 条边，其中 ${activeSignals} 个活跃信号节点。`,
    usage
      ? `LLM 用量：本月 ${usage.calls} 次调用，估算成本 $${usage.estimated_cost_usd.toFixed(2)}。`
      : "LLM 用量：后端暂未返回。",
    "",
    "下一步：进入相关预警或 Causal Web 节点继续追溯；这条回答来自实时运行态上下文，不是固定演示脚本。",
  ].join("\n");
}

function settledValue<T>(result: PromiseSettledResult<T>): T | null {
  return result.status === "fulfilled" ? result.value : null;
}

function formatCurrency(value: number): string {
  const sign = value >= 0 ? "+" : "";
  return `${sign}¥${value.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}
