"use client";

import { useState } from "react";
import { Card } from "@/components/Card";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { cn } from "@/lib/utils";
import { FileText, Plus, Tag } from "lucide-react";

const NOTES = [
  {
    id: "1",
    title: "RB 螺纹复盘 2026-04-28",
    folder: "黑色",
    tags: ["@RB2510", "#cost_pressure"],
    preview: "今日 RB 触发 cost_support_pressure，验证我上周的判断——前期跟踪的高炉利润 5 日内由正转负，叠加焦煤现货...",
    updatedAt: "2h ago",
  },
  {
    id: "2",
    title: "橡胶产区季节性框架",
    folder: "橡胶",
    tags: ["@NR2509", "#hypothesis:rubber_seasonality"],
    preview: "东南亚天胶产区每年 2-4 月停割期 + 5-6 月开割初期供给低位，叠加产区天气，是 NR/RU 季节性多头核心...",
    updatedAt: "Yesterday",
  },
  {
    id: "3",
    title: "假设：焦煤 → 螺纹利润传导",
    folder: "假设库",
    tags: ["#hypothesis:jm_to_rb_profit", "@JM2509"],
    preview: "假设：焦煤现货价跌至 P50 + 持续 5d → 钢厂高炉利润转负概率 0.71（基于过去 3 年 18 次类似事件）...",
    updatedAt: "3d ago",
  },
  {
    id: "4",
    title: "本月交易归因",
    folder: "交易日志",
    tags: ["#monthly_review"],
    preview: "本月共 8 笔交易，胜率 62.5%。Long signals 命中率高于 Short（72% vs 50%），需要审视短信号的逻辑...",
    updatedAt: "5d ago",
  },
];

export default function NotebookPage() {
  const [active, setActive] = useState("1");
  const note = NOTES.find((n) => n.id === active)!;

  return (
    <div className="flex h-full">
      {/* Note tree */}
      <aside className="w-60 border-r border-border-subtle p-4 space-y-3 overflow-y-auto">
        <Button variant="primary" size="sm" className="w-full">
          <Plus className="w-3.5 h-3.5" />
          新建笔记
        </Button>
        <div>
          {["黑色", "橡胶", "假设库", "交易日志"].map((folder) => (
            <div key={folder} className="mb-3">
              <div className="text-caption text-text-muted uppercase tracking-wider px-2 py-1">{folder}</div>
              {NOTES.filter((n) => n.folder === folder).map((n) => (
                <button
                  key={n.id}
                  onClick={() => setActive(n.id)}
                  className={cn(
                    "w-full flex items-start gap-2 px-2 py-2 rounded-sm text-left text-sm transition-colors",
                    active === n.id
                      ? "bg-brand-emerald/15 text-text-primary"
                      : "text-text-secondary hover:bg-bg-surface-raised"
                  )}
                >
                  <FileText className="w-3.5 h-3.5 shrink-0 mt-0.5" />
                  <div className="flex-1 min-w-0">
                    <div className="line-clamp-1">{n.title}</div>
                    <div className="text-caption text-text-muted">{n.updatedAt}</div>
                  </div>
                </button>
              ))}
            </div>
          ))}
        </div>
      </aside>

      {/* Editor */}
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-3xl mx-auto px-8 py-8 space-y-5">
          <div>
            <input
              defaultValue={note.title}
              className="bg-transparent text-h1 font-semibold text-text-primary w-full focus:outline-none"
            />
            <div className="flex items-center gap-2 mt-3">
              <Tag className="w-3.5 h-3.5 text-text-muted" />
              {note.tags.map((t) => (
                <Badge key={t} variant={t.startsWith("#") ? "emerald" : "orange"}>
                  {t}
                </Badge>
              ))}
              <Badge>+ 添加</Badge>
              <span className="ml-auto text-caption text-text-muted">{note.updatedAt} · 自动保存</span>
            </div>
          </div>

          <div className="text-sm text-text-secondary leading-relaxed space-y-3">
            <p>{note.preview}</p>
            <p>系统在 09:42 触发 cost_support_pressure 预警，置信度 0.84，对抗引擎 3/3 通过。我自己的判断是认同（与 1 周前的研究一致），但仓位偏小（3 手），原因是仍担心终端建材采购可能在五一前后回落。</p>
            <p>
              <strong className="text-text-primary">关联</strong>：参见 #hypothesis:jm_to_rb_profit（焦煤→钢厂利润传导假设）。今天的 cost_support_pressure 实际上是这个假设的 18 次历史事件中第 19 次。
            </p>
            <p>
              <strong className="text-text-primary">下一步行动</strong>：
            </p>
            <ul className="list-disc pl-5 space-y-1">
              <li>明早查看终端建材采购数据（中物联日报）</li>
              <li>关注焦煤现货价格是否企稳（重要！）</li>
              <li>如果焦煤反弹 + 钢厂利润修复，考虑加仓至 5 手</li>
            </ul>
          </div>

          <Card variant="elevated">
            <div className="text-caption text-text-muted uppercase mb-2">关联预警 · 关联假设</div>
            <div className="grid grid-cols-2 gap-2">
              <div className="text-sm">
                <Badge variant="critical">CRITICAL</Badge>
                <span className="ml-2 text-text-secondary">RB cost_support_pressure (alt-001)</span>
              </div>
              <div className="text-sm">
                <Badge variant="emerald">假设</Badge>
                <span className="ml-2 text-text-secondary">jm_to_rb_profit · 0.71 命中率</span>
              </div>
            </div>
          </Card>
        </div>
      </div>

      {/* Right sidebar: backlinks */}
      <aside className="w-72 border-l border-border-subtle p-5 space-y-4 overflow-y-auto">
        <div>
          <div className="text-caption text-text-muted uppercase mb-2">引用此笔记</div>
          <div className="space-y-1.5">
            <RefItem title="2026-04-30 复盘" type="note" />
            <RefItem title="本月交易归因" type="note" />
          </div>
        </div>
        <div>
          <div className="text-caption text-text-muted uppercase mb-2">提及的假设</div>
          <div className="space-y-1.5">
            <RefItem title="jm_to_rb_profit" type="hypothesis" />
          </div>
        </div>
        <div>
          <div className="text-caption text-text-muted uppercase mb-2">提及的预警</div>
          <div className="space-y-1.5">
            <RefItem title="alt-001 RB cost_pressure" type="alert" />
          </div>
        </div>
      </aside>
    </div>
  );
}

function RefItem({ title, type }: { title: string; type: "note" | "hypothesis" | "alert" }) {
  const colorMap = { note: "text-text-secondary", hypothesis: "text-brand-emerald-bright", alert: "text-brand-orange" };
  return (
    <div className={cn("text-sm hover:text-text-primary cursor-pointer transition-colors", colorMap[type])}>
      ◇ {title}
    </div>
  );
}
