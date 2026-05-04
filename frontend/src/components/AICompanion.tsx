"use client";

import { useState } from "react";
import { Sparkles, X, Send, MessageSquare } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "./Button";
import { useI18n } from "@/lib/i18n";

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

const MOCK_RESPONSE_EN = `Based on the current alert alt-001:

**Trigger**: Rebar spot at 4,280 has broken below the P75 blast-furnace cost curve level (4,310) and stayed there for two weeks. This means the top 25% high-cost mills are under loss pressure.

**Key propagation chain** (from Causal Web):
1. Coking coal spot -> P50 percentile
2. Coke margin < -3% for five consecutive days
3. Mill blast-furnace margin fell to -2.4%
4. Rebar spot broke below 4,310

**Adversarial result**: 3/3 passed
- Null hypothesis p = 0.018 (non-random)
- Historical bundle hit rate 0.72 (strong signal)
- Structural counterpoint: low inventory + terminal demand not clearly weakening

**Suggestion**: Reference Trade Plan tp-001 (long RB2510, R:R 1.85).

> Snapshot is 14s old, confidence 84% (sample 47)`;

export function AICompanion() {
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<{ role: "user" | "assistant"; content: string }[]>([]);
  const [loading, setLoading] = useState(false);
  const { text, lang } = useI18n();

  const send = (text: string) => {
    if (!text.trim()) return;
    setMessages((m) => [...m, { role: "user", content: text }]);
    setInput("");
    setLoading(true);
    setTimeout(() => {
      setMessages((m) => [...m, { role: "assistant", content: lang === "en" ? MOCK_RESPONSE_EN : MOCK_RESPONSE }]);
      setLoading(false);
    }, 900);
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
            <Button onClick={() => send(input)} size="md">
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
