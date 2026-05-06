"use client";

import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { useI18n } from "@/lib/i18n";
import { BookOpen, Database, FileText, GitBranch, Plus, Tag } from "lucide-react";

const NOTE_FOLDERS = ["黑色", "橡胶", "假设库", "交易日志"];

export default function NotebookPage() {
  const { text } = useI18n();

  return (
    <div className="flex h-full min-w-0 bg-[radial-gradient(circle_at_50%_-20%,rgba(16,185,129,0.08),transparent_34%)]">
      <aside className="hidden w-64 shrink-0 space-y-4 overflow-y-auto border-r border-border-subtle bg-bg-panel/70 p-4 shadow-inner-panel xl:block">
        <Button variant="primary" size="sm" className="w-full opacity-70" disabled>
          <Plus className="h-3.5 w-3.5" />
          {text("新建笔记")}
        </Button>
        <div className="grid grid-cols-2 gap-2">
          <NotebookStat label="Notes" value={0} icon={BookOpen} />
          <NotebookStat label="Linked" value={0} icon={GitBranch} />
        </div>
        <div>
          {NOTE_FOLDERS.map((folder) => (
            <div key={folder} className="mb-3">
              <div className="flex items-center justify-between px-2 py-1 text-caption uppercase tracking-wider text-text-muted">
                <span>{text(folder)}</span>
                <span>0</span>
              </div>
              <div className="rounded-sm border border-border-subtle bg-bg-base/70 px-3 py-2 text-sm text-text-muted shadow-inner-panel">
                {text("暂无笔记")}
              </div>
            </div>
          ))}
        </div>
      </aside>

      <main className="min-w-0 flex-1 overflow-y-auto">
        <div className="mx-auto max-w-3xl space-y-5 px-8 py-8">
          <section className="rounded-sm border border-border-default bg-[linear-gradient(180deg,rgba(15,17,16,0.9),rgba(3,5,4,0.72))] p-6 shadow-data-panel">
            <div className="flex items-center gap-2">
              <Badge variant="orange">{text("未接入")}</Badge>
              <Badge variant="neutral">{text("无本地示例数据")}</Badge>
            </div>
            <h1 className="mt-4 text-h1 text-text-primary">
              {text("研究笔记暂未接入运行态存储")}
            </h1>
            <p className="mt-3 text-sm leading-relaxed text-text-secondary">
              {text("当前页面不再展示固定示例笔记；接入 Notebook API 后会显示用户保存的研究、假设和交易日志。")}
            </p>
          </section>

          <Card variant="data" className="space-y-4">
            <div className="flex items-center gap-3">
              <div className="flex h-9 w-9 items-center justify-center rounded-sm border border-brand-emerald/30 bg-brand-emerald/10 text-brand-emerald-bright">
                <Database className="h-4 w-4" />
              </div>
              <div>
                <div className="text-h3 text-text-primary">{text("当前状态")}</div>
                <div className="text-sm text-text-secondary">{text("不会显示固定演示内容")}</div>
              </div>
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              <StatusItem icon={FileText} title="暂无运行态笔记" body="等待后端笔记存储接口接入。" />
              <StatusItem icon={Tag} title="暂无运行态关联" body="预警、假设和交易归因暂未生成真实引用关系。" />
            </div>
          </Card>

          <Card variant="flat">
            <div className="text-caption uppercase tracking-wider text-text-muted">
              {text("下一步行动")}
            </div>
            <ul className="mt-3 space-y-2 text-sm text-text-secondary">
              <li>{text("接入笔记 CRUD API 与持久化存储。")}</li>
              <li>{text("将笔记与预警、假设和交易归因建立真实关联。")}</li>
              <li>{text("启用搜索、标签和自动保存后再开放新建入口。")}</li>
            </ul>
          </Card>
        </div>
      </main>

      <aside className="hidden w-80 shrink-0 space-y-4 overflow-y-auto border-l border-border-subtle bg-bg-panel/70 p-5 shadow-inner-panel 2xl:block">
        <EmptyReferenceSection title="引用此笔记" />
        <EmptyReferenceSection title="提及的假设" />
        <EmptyReferenceSection title="提及的预警" />
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
      <div className="mt-1 font-mono text-lg tabular-nums text-text-primary">{value}</div>
    </div>
  );
}

function StatusItem({
  icon: Icon,
  title,
  body,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  body: string;
}) {
  const { text } = useI18n();

  return (
    <div className="rounded-sm border border-border-subtle bg-bg-base p-3 shadow-inner-panel">
      <div className="flex items-center gap-2 text-sm text-text-primary">
        <Icon className="h-3.5 w-3.5 text-brand-emerald-bright" />
        {text(title)}
      </div>
      <p className="mt-2 text-sm leading-relaxed text-text-secondary">{text(body)}</p>
    </div>
  );
}

function EmptyReferenceSection({ title }: { title: string }) {
  const { text } = useI18n();

  return (
    <div>
      <div className="mb-2 text-caption uppercase tracking-wider text-text-muted">{text(title)}</div>
      <div className="rounded-sm border border-border-subtle bg-bg-base px-3 py-2 text-sm text-text-muted shadow-inner-panel">
        {text("暂无运行态关联")}
      </div>
    </div>
  );
}
