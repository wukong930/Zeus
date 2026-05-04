"use client";

import { useState } from "react";
import { Card } from "@/components/Card";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { cn } from "@/lib/utils";
import { BookOpen, Clock3, FileText, GitBranch, Plus, Tag } from "lucide-react";
import { useI18n } from "@/lib/i18n";

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
  const { text } = useI18n();

  return (
    <div className="flex h-full min-w-0 bg-[radial-gradient(circle_at_50%_-20%,rgba(16,185,129,0.08),transparent_34%)]">
      {/* Note tree */}
      <aside className="hidden w-64 shrink-0 space-y-4 overflow-y-auto border-r border-border-subtle bg-bg-panel/70 p-4 shadow-inner-panel xl:block">
        <Button variant="primary" size="sm" className="w-full">
          <Plus className="w-3.5 h-3.5" />
          新建笔记
        </Button>
        <div className="grid grid-cols-2 gap-2">
          <NotebookStat label="Notes" value={NOTES.length} icon={BookOpen} />
          <NotebookStat label="Linked" value={7} icon={GitBranch} />
        </div>
        <div>
          {["黑色", "橡胶", "假设库", "交易日志"].map((folder) => (
            <div key={folder} className="mb-3">
              <div className="flex items-center justify-between px-2 py-1 text-caption uppercase tracking-wider text-text-muted">
                <span>{text(folder)}</span>
                <span>{NOTES.filter((n) => n.folder === folder).length}</span>
              </div>
              {NOTES.filter((n) => n.folder === folder).map((n) => (
                <button
                  key={n.id}
                  onClick={() => setActive(n.id)}
                  className={cn(
                    "w-full flex items-start gap-2 rounded-sm border px-2 py-2 text-left text-sm transition-all",
                    active === n.id
                      ? "border-brand-emerald/35 bg-brand-emerald/12 text-text-primary shadow-data-panel"
                      : "border-transparent text-text-secondary hover:border-border-subtle hover:bg-bg-surface-raised"
                  )}
                >
                  <FileText className={cn("w-3.5 h-3.5 shrink-0 mt-0.5", active === n.id ? "text-brand-emerald-bright" : "text-text-muted")} />
                  <div className="flex-1 min-w-0">
                    <div className="line-clamp-1 font-medium">{text(n.title)}</div>
                    <div className="mt-1 flex items-center gap-1 text-caption text-text-muted">
                      <Clock3 className="h-3 w-3" />
                      {text(n.updatedAt)}
                    </div>
                  </div>
                </button>
              ))}
            </div>
          ))}
        </div>
      </aside>

      {/* Editor */}
      <div className="min-w-0 flex-1 overflow-y-auto">
        <div className="max-w-3xl mx-auto px-8 py-8 space-y-5">
          <div className="rounded-sm border border-border-default bg-[linear-gradient(180deg,rgba(15,17,16,0.9),rgba(3,5,4,0.72))] p-5 shadow-data-panel">
            <input
              defaultValue={text(note.title)}
              className="bg-transparent text-h1 font-semibold text-text-primary w-full focus:outline-none"
            />
            <div className="flex items-center gap-2 mt-3">
              <Tag className="w-3.5 h-3.5 text-text-muted" />
              {note.tags.map((t) => (
                <Badge key={t} variant={t.startsWith("#") ? "emerald" : "orange"}>
                  {t}
                </Badge>
              ))}
              <Badge>+ {text("添加")}</Badge>
              <span className="ml-auto text-caption text-text-muted">{text(note.updatedAt)} · {text("自动保存")}</span>
            </div>
          </div>

          <div className="rounded-sm border border-border-subtle bg-bg-base/70 p-5 text-sm text-text-secondary leading-relaxed space-y-3 shadow-inner-panel">
            <p>{text(note.preview)}</p>
            <p>{text("系统在 09:42 触发 cost_support_pressure 预警，置信度 0.84，对抗引擎 3/3 通过。我自己的判断是认同（与 1 周前的研究一致），但仓位偏小（3 手），原因是仍担心终端建材采购可能在五一前后回落。")}</p>
            <p>
              <strong className="text-text-primary">{text("关联")}</strong>：{text("参见 #hypothesis:jm_to_rb_profit（焦煤→钢厂利润传导假设）。今天的 cost_support_pressure 实际上是这个假设的 18 次历史事件中第 19 次。")}
            </p>
            <p>
              <strong className="text-text-primary">{text("下一步行动")}</strong>：
            </p>
            <ul className="list-disc pl-5 space-y-1">
              <li>{text("明早查看终端建材采购数据（中物联日报）")}</li>
              <li>{text("关注焦煤现货价格是否企稳（重要！）")}</li>
              <li>{text("如果焦煤反弹 + 钢厂利润修复，考虑加仓至 5 手")}</li>
            </ul>
          </div>

          <Card variant="data">
            <div className="text-caption text-text-muted uppercase mb-2">{text("关联预警 · 关联假设")}</div>
            <div className="grid grid-cols-2 gap-2">
              <div className="rounded-sm border border-border-subtle bg-bg-base p-3 text-sm shadow-inner-panel">
                <Badge variant="critical">CRITICAL</Badge>
                <div className="mt-2 text-text-secondary">RB cost_support_pressure (alt-001)</div>
              </div>
              <div className="rounded-sm border border-border-subtle bg-bg-base p-3 text-sm shadow-inner-panel">
                <Badge variant="emerald">{text("假设")}</Badge>
                <div className="mt-2 text-text-secondary">jm_to_rb_profit · 0.71 {text("命中率")}</div>
              </div>
            </div>
          </Card>
        </div>
      </div>

      {/* Right sidebar: backlinks */}
      <aside className="hidden w-80 shrink-0 space-y-4 overflow-y-auto border-l border-border-subtle bg-bg-panel/70 p-5 shadow-inner-panel 2xl:block">
        <div>
          <div className="text-caption text-text-muted uppercase mb-2">{text("引用此笔记")}</div>
          <div className="space-y-1.5">
            <RefItem title="2026-04-30 复盘" type="note" />
            <RefItem title="本月交易归因" type="note" />
          </div>
        </div>
        <div>
          <div className="text-caption text-text-muted uppercase mb-2">{text("提及的假设")}</div>
          <div className="space-y-1.5">
            <RefItem title="jm_to_rb_profit" type="hypothesis" />
          </div>
        </div>
        <div>
          <div className="text-caption text-text-muted uppercase mb-2">{text("提及的预警")}</div>
          <div className="space-y-1.5">
            <RefItem title="alt-001 RB cost_pressure" type="alert" />
          </div>
        </div>
      </aside>
    </div>
  );
}

function NotebookStat({
  label,
  value,
  icon: Icon,
}: {
  label: string;
  value: number;
  icon: React.ComponentType<{ className?: string }>;
}) {
  const { text } = useI18n();

  return (
    <div className="rounded-sm border border-border-subtle bg-bg-base p-2 shadow-inner-panel">
      <div className="flex items-center justify-between text-caption text-text-muted">
        <span>{text(label)}</span>
        <Icon className="h-3.5 w-3.5" />
      </div>
      <div className="mt-1 font-mono text-lg text-text-primary tabular-nums">{value}</div>
    </div>
  );
}

function RefItem({ title, type }: { title: string; type: "note" | "hypothesis" | "alert" }) {
  const { text } = useI18n();
  const colorMap = { note: "border-border-subtle text-text-secondary", hypothesis: "border-brand-emerald/30 text-brand-emerald-bright", alert: "border-brand-orange/30 text-brand-orange" };
  return (
    <div className={cn("cursor-pointer rounded-sm border bg-bg-base px-3 py-2 text-sm shadow-inner-panel transition-colors hover:border-border-strong hover:text-text-primary", colorMap[type])}>
      {text(title)}
    </div>
  );
}
