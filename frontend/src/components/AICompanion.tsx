"use client";

import { useState } from "react";
import { Sparkles, X, Send, MessageSquare } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "./Button";

const SUGGESTED_QUERIES = [
  "为什么 RB 触发了 cost_support_pressure？",
  "解释一下当前的 Drift 状态",
  "我的橡胶持仓有哪些下游风险？",
  "对比上月和本月的命中率变化",
];

const MOCK_RESPONSE = `基于当前预警 alt-001 的上下文：

**触发原因**：螺纹现货 4280 已跌破高炉成本曲线 P75 分位（4310），且持续 2 周。这意味着前 25% 高成本钢厂已处于亏损状态。

**关键传导链**（来自 Causal Web）：
1. 焦煤现货价 → P50 分位
2. 焦炭利润率连续 5 日 < -3%
3. 钢厂高炉利润降至 -2.4%
4. 螺纹现货跌破 4310

**对抗结果**：3/3 通过
- 零假设 p = 0.018（非随机）
- 历史组合命中率 0.72（强信号）
- 结构性反驳：库存低位 + 终端需求未明显回落

**建议**：可参考 Trade Plan tp-001（多 RB2510，R:R 1.85）。

> 数据基于 14s 前的快照，置信度 84%（样本 47）`;

export function AICompanion() {
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<{ role: "user" | "assistant"; content: string }[]>([]);
  const [loading, setLoading] = useState(false);

  const send = (text: string) => {
    if (!text.trim()) return;
    setMessages((m) => [...m, { role: "user", content: text }]);
    setInput("");
    setLoading(true);
    setTimeout(() => {
      setMessages((m) => [...m, { role: "assistant", content: MOCK_RESPONSE }]);
      setLoading(false);
    }, 900);
  };

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className={cn(
          "fixed bottom-5 right-5 z-50 w-12 h-12 rounded-full bg-brand-emerald shadow-glow-emerald",
          "flex items-center justify-center text-white",
          "transition-all duration-200 hover:scale-105 hover:bg-brand-emerald-hover",
          open && "scale-0 opacity-0"
        )}
        aria-label="Open AI Companion"
      >
        <Sparkles className="w-5 h-5" />
      </button>

      <div
        className={cn(
          "fixed inset-0 z-40 transition-opacity duration-300",
          open ? "opacity-100" : "opacity-0 pointer-events-none"
        )}
        style={{ background: "rgba(0,0,0,0.6)" }}
        onClick={() => setOpen(false)}
      />
      <aside
        className={cn(
          "fixed top-0 right-0 bottom-0 z-50 w-[400px] bg-bg-surface-overlay shadow-lg border-l border-border-default flex flex-col",
          "transition-transform duration-400 ease-decelerate",
          open ? "translate-x-0" : "translate-x-full"
        )}
      >
        <div className="flex items-center justify-between h-14 px-5 border-b border-border-default">
          <div className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-brand-emerald-bright" />
            <span className="text-h3 font-semibold">AI Companion</span>
          </div>
          <button
            onClick={() => setOpen(false)}
            className="text-text-muted hover:text-text-primary p-1"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          {messages.length === 0 && (
            <div className="space-y-4">
              <div className="text-sm text-text-secondary leading-relaxed">
                我是你的 Zeus 研究伙伴。我知道你当前在哪个页面、看哪个预警，可以帮你解释、对比、追问。
              </div>
              <div className="space-y-2">
                <div className="text-caption text-text-muted uppercase tracking-wider">建议提问</div>
                {SUGGESTED_QUERIES.map((q) => (
                  <button
                    key={q}
                    onClick={() => send(q)}
                    className="w-full text-left text-sm text-text-secondary bg-bg-surface hover:bg-bg-surface-raised border border-border-subtle hover:border-border-default rounded-sm px-3 py-2 transition-colors"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}
          {messages.map((m, i) => (
            <div
              key={i}
              className={cn(
                "rounded-sm p-3 text-sm leading-relaxed",
                m.role === "user"
                  ? "bg-brand-emerald/15 border border-brand-emerald/30 ml-6"
                  : "bg-bg-surface border border-border-subtle mr-6"
              )}
            >
              <div className="text-caption text-text-muted mb-1">
                {m.role === "user" ? "你" : "Zeus"}
              </div>
              <div className="text-text-primary whitespace-pre-line">{m.content}</div>
            </div>
          ))}
          {loading && (
            <div className="flex items-center gap-2 text-text-muted text-sm">
              <MessageSquare className="w-4 h-4 animate-pulse" />
              思考中...
            </div>
          )}
        </div>

        <div className="border-t border-border-default p-4">
          <div className="flex gap-2">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && send(input)}
              placeholder="问点什么..."
              className="flex-1 bg-bg-surface border border-border-default rounded-sm px-3 h-9 text-sm text-text-primary placeholder:text-text-muted focus:border-brand-emerald focus:outline-none"
            />
            <Button onClick={() => send(input)} size="md">
              <Send className="w-4 h-4" />
            </Button>
          </div>
          <div className="text-caption text-text-muted mt-2">
            上下文：当前页面 + 最近 3 条预警
          </div>
        </div>
      </aside>
    </>
  );
}
