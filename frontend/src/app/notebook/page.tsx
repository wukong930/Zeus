"use client";

import { useEffect, useMemo, useState } from "react";
import type { ComponentType } from "react";
import {
  AlertTriangle,
  BookOpen,
  Database,
  FileText,
  GitBranch,
  Plus,
  Search,
  Tag,
} from "lucide-react";

import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { DataSourceBadge, type DataSourceState } from "@/components/DataSourceBadge";
import { fetchNotebookSnapshot, type NotebookEntry, type NotebookSnapshot } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { cn, timeAgo } from "@/lib/utils";

export default function NotebookPage() {
  const { text } = useI18n();
  const [snapshot, setSnapshot] = useState<NotebookSnapshot | null>(null);
  const [source, setSource] = useState<DataSourceState>("loading");
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchNotebookSnapshot()
      .then((runtimeSnapshot) => {
        if (cancelled) return;
        setSnapshot(runtimeSnapshot);
        setSource("api");
        setSelectedId(runtimeSnapshot.notes[0]?.id ?? null);
      })
      .catch(() => {
        if (cancelled) return;
        setSnapshot(null);
        setSource("fallback");
        setSelectedId(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const notes = snapshot?.notes ?? [];
  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return notes;
    return notes.filter((note) =>
      [
        note.title,
        note.summary,
        note.body,
        note.status,
        note.folder,
        ...note.tags,
        ...note.symbols,
      ]
        .join(" ")
        .toLowerCase()
        .includes(needle)
    );
  }, [notes, query]);
  const selected = filtered.find((note) => note.id === selectedId) ?? filtered[0] ?? null;
  const linkedCount = notes.reduce((total, note) => total + note.references.length, 0);
  const hypothesisCount = notes.filter((note) => note.kind !== "report").length;
  const folders =
    snapshot?.folders.length ? snapshot.folders : [{ name: "运行态笔记", count: notes.length }];

  useEffect(() => {
    if (selected && selected.id !== selectedId) {
      setSelectedId(selected.id);
    }
  }, [selected, selectedId]);

  return (
    <div className="flex h-full min-w-0 bg-[radial-gradient(circle_at_50%_-20%,rgba(16,185,129,0.08),transparent_34%)]">
      <aside className="hidden w-72 shrink-0 space-y-4 overflow-y-auto border-r border-border-subtle bg-bg-panel/70 p-4 shadow-inner-panel xl:block">
        <div className="flex items-center justify-between gap-3">
          <Button variant="primary" size="sm" className="flex-1 opacity-70" disabled>
            <Plus className="h-3.5 w-3.5" />
            {text("新建笔记")}
          </Button>
          <Badge variant="neutral">{text("只读")}</Badge>
        </div>
        <div className="grid grid-cols-3 gap-2">
          <NotebookStat label="笔记" value={notes.length} icon={BookOpen} />
          <NotebookStat label="关联" value={linkedCount} icon={GitBranch} />
          <NotebookStat label="假设" value={hypothesisCount} icon={Tag} />
        </div>
        <div className="relative">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-muted" />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={text("搜索笔记 / 假设 / 预警")}
            className="h-9 w-full rounded-sm border border-border-default bg-bg-base pl-9 pr-3 text-sm text-text-primary focus:border-brand-emerald focus:outline-none focus:shadow-focus-ring"
          />
        </div>
        <div className="space-y-2">
          {folders.map((folder) => (
            <div
              key={folder.name}
              className="flex items-center justify-between rounded-sm border border-border-subtle bg-bg-base/70 px-3 py-2 text-sm shadow-inner-panel"
            >
              <span className="text-text-secondary">{text(folder.name)}</span>
              <span className="font-mono text-text-muted">{folder.count}</span>
            </div>
          ))}
        </div>
      </aside>

      <main className="min-w-0 flex-1 overflow-y-auto">
        <div className="mx-auto max-w-6xl space-y-5 px-6 py-6">
          <header className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <div className="flex items-center gap-3">
                <h1 className="text-h1 text-text-primary">{text("笔记本")}</h1>
                <DataSourceBadge state={source} compact />
              </div>
              <p className="mt-1 text-sm text-text-secondary">
                {text("运行态研究报告、学习假设与预警引用。")}
              </p>
            </div>
            <div className="grid grid-cols-3 gap-2 sm:w-[360px]">
              <NotebookStat label="笔记" value={notes.length} icon={FileText} />
              <NotebookStat label="预警引用" value={snapshot?.referenceCounts.alerts ?? 0} icon={AlertTriangle} />
              <NotebookStat label="文件夹" value={snapshot?.folders.length ?? 0} icon={Database} />
            </div>
          </header>

          <div className="grid min-h-[620px] gap-5 lg:grid-cols-[minmax(320px,0.88fr)_minmax(420px,1.12fr)]">
            <section className="space-y-3 overflow-y-auto rounded-sm border border-border-subtle bg-bg-panel/45 p-3 shadow-inner-panel">
              {filtered.map((note) => (
                <button
                  key={note.id}
                  onClick={() => setSelectedId(note.id)}
                  className={cn(
                    "w-full rounded-sm border p-4 text-left transition-colors",
                    selected?.id === note.id
                      ? "border-brand-emerald/70 bg-brand-emerald/10 shadow-focus-ring"
                      : "border-border-subtle bg-bg-base/70 hover:border-border-default hover:bg-bg-surface"
                  )}
                >
                  <NoteMeta note={note} />
                  <div className="mt-3 line-clamp-2 text-h3 text-text-primary">{text(note.title)}</div>
                  <p className="mt-2 line-clamp-2 text-sm leading-relaxed text-text-secondary">
                    {text(note.summary)}
                  </p>
                  <TagRow note={note} />
                </button>
              ))}
              {filtered.length === 0 && source !== "loading" && (
                <Card variant="flat" className="py-12 text-center text-sm text-text-secondary">
                  {text(emptyNotebookMessage(source, notes.length, query))}
                </Card>
              )}
              {source === "loading" && (
                <Card variant="flat" className="py-12 text-center text-sm text-text-secondary">
                  {text("正在加载运行态笔记")}
                </Card>
              )}
            </section>

            <section className="min-w-0">
              {selected ? (
                <NotebookDetail note={selected} />
              ) : (
                <Card variant="data" className="flex min-h-[420px] items-center justify-center text-sm text-text-secondary">
                  {text(emptyNotebookMessage(source, notes.length, query))}
                </Card>
              )}
            </section>
          </div>
        </div>
      </main>

      <aside className="hidden w-80 shrink-0 space-y-4 overflow-y-auto border-l border-border-subtle bg-bg-panel/70 p-5 shadow-inner-panel 2xl:block">
        <ReferencePanel note={selected} />
      </aside>
    </div>
  );
}

function NotebookDetail({ note }: { note: NotebookEntry }) {
  const { text } = useI18n();

  return (
    <Card variant="data" className="min-h-[620px] space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-border-subtle pb-4">
        <div className="min-w-0">
          <NoteMeta note={note} />
          <h2 className="mt-3 text-h1 text-text-primary">{text(note.title)}</h2>
          <p className="mt-2 max-w-2xl text-sm leading-relaxed text-text-secondary">
            {text(note.summary)}
          </p>
        </div>
        {note.confidence !== null && (
          <div className="rounded-sm border border-border-subtle bg-bg-base px-3 py-2 text-right shadow-inner-panel">
            <div className="text-caption text-text-muted">{text("置信度")}</div>
            <div className="font-mono text-xl text-brand-emerald-bright">
              {Math.round(note.confidence * 100)}%
            </div>
          </div>
        )}
      </div>

      <div className="whitespace-pre-wrap text-sm leading-7 text-text-secondary">
        {text(note.body || note.summary)}
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        <InfoBlock label="笔记状态" value={note.status} />
        <InfoBlock label="更新" value={timeAgo(note.updatedAt ?? note.createdAt)} />
      </div>

      <div>
        <div className="mb-2 text-caption uppercase tracking-wider text-text-muted">
          {text("引用关系")}
        </div>
        {note.references.length > 0 ? (
          <div className="space-y-2">
            {note.references.map((reference) => (
              <div
                key={`${reference.type}-${reference.id}`}
                className="rounded-sm border border-border-subtle bg-bg-base px-3 py-2 shadow-inner-panel"
              >
                <div className="flex items-center justify-between gap-3">
                  <span className="text-sm text-text-primary">{text(reference.title)}</span>
                  <Badge variant="orange">{referenceLabel(reference.type)}</Badge>
                </div>
                <div className="mt-1 text-caption text-text-muted">
                  {reference.status ? text(reference.status) : text("无状态")}
                  {reference.timestamp ? ` · ${timeAgo(reference.timestamp)}` : ""}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="rounded-sm border border-border-subtle bg-bg-base px-3 py-2 text-sm text-text-muted shadow-inner-panel">
            {text("暂无运行态关联")}
          </div>
        )}
      </div>
    </Card>
  );
}

function ReferencePanel({ note }: { note: NotebookEntry | null }) {
  const { text } = useI18n();

  if (!note) {
    return (
      <div className="rounded-sm border border-border-subtle bg-bg-base px-3 py-2 text-sm text-text-muted shadow-inner-panel">
        {text("请选择笔记")}
      </div>
    );
  }

  return (
    <>
      <EmptyReferenceSection title="引用此笔记" value={note.references.length} />
      <EmptyReferenceSection title="提及的假设" value={note.kind !== "report" ? 1 : 0} />
      <EmptyReferenceSection title="提及的预警" value={note.references.filter((item) => item.type === "alert").length} />
      <div>
        <div className="mb-2 text-caption uppercase tracking-wider text-text-muted">{text("标签")}</div>
        <div className="flex flex-wrap gap-2">
          {note.tags.length ? (
            note.tags.map((tag) => (
              <Badge key={tag} variant="neutral">
                {tag}
              </Badge>
            ))
          ) : (
            <span className="text-sm text-text-muted">{text("暂无标签")}</span>
          )}
        </div>
      </div>
    </>
  );
}

function NoteMeta({ note }: { note: NotebookEntry }) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Badge variant={kindVariant(note.kind)}>{kindLabel(note.kind)}</Badge>
      <Badge variant={statusVariant(note.status)}>{note.status}</Badge>
      <span className="font-mono text-caption text-text-muted">{timeAgo(note.createdAt)}</span>
    </div>
  );
}

function TagRow({ note }: { note: NotebookEntry }) {
  if (note.tags.length === 0 && note.references.length === 0) return null;
  return (
    <div className="mt-3 flex flex-wrap gap-1.5">
      {note.tags.slice(0, 3).map((tag) => (
        <span
          key={tag}
          className="inline-flex h-5 items-center rounded-xs border border-border-subtle bg-bg-base px-1.5 text-caption text-text-secondary"
        >
          {tag}
        </span>
      ))}
      {note.references.length > 0 && (
        <span className="inline-flex h-5 items-center rounded-xs border border-brand-orange/25 bg-brand-orange/10 px-1.5 text-caption text-brand-orange">
          {note.references.length} 引用
        </span>
      )}
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
  icon: ComponentType<{ className?: string }>;
}) {
  const { text } = useI18n();

  return (
    <div className="rounded-sm border border-border-subtle bg-bg-base p-2 shadow-inner-panel">
      <div className="flex items-center justify-between gap-2 text-caption text-text-muted">
        <span>{text(label)}</span>
        <Icon className="h-3.5 w-3.5" />
      </div>
      <div className="mt-1 font-mono text-lg tabular-nums text-text-primary">{value}</div>
    </div>
  );
}

function InfoBlock({ label, value }: { label: string; value: string }) {
  const { text } = useI18n();

  return (
    <div className="rounded-sm border border-border-subtle bg-bg-base p-3 shadow-inner-panel">
      <div className="text-caption text-text-muted">{text(label)}</div>
      <div className="mt-1 text-sm text-text-primary">{text(value)}</div>
    </div>
  );
}

function EmptyReferenceSection({ title, value }: { title: string; value: number }) {
  const { text } = useI18n();

  return (
    <div>
      <div className="mb-2 text-caption uppercase tracking-wider text-text-muted">{text(title)}</div>
      <div className="rounded-sm border border-border-subtle bg-bg-base px-3 py-2 font-mono text-sm text-text-primary shadow-inner-panel">
        {value}
      </div>
    </div>
  );
}

function emptyNotebookMessage(source: DataSourceState, total: number, query: string): string {
  if (source === "fallback") return "笔记本接口暂不可用";
  if (total > 0 && query.trim()) return "没有匹配的运行态笔记";
  return "当前暂无运行态笔记";
}

function kindLabel(kind: NotebookEntry["kind"]): string {
  if (kind === "learning_hypothesis") return "学习假设";
  if (kind === "research_hypothesis") return "研究假设";
  return "研究报告";
}

function referenceLabel(type: string): string {
  if (type === "alert") return "预警";
  if (type === "hypothesis") return "假设";
  return "报告";
}

function kindVariant(kind: NotebookEntry["kind"]) {
  if (kind === "learning_hypothesis") return "violet" as const;
  if (kind === "research_hypothesis") return "blue" as const;
  return "emerald" as const;
}

function statusVariant(status: string) {
  if (["applied", "validated", "published", "active"].includes(status)) return "emerald" as const;
  if (["rejected", "failed"].includes(status)) return "down" as const;
  if (["shadow_testing", "reviewed"].includes(status)) return "orange" as const;
  return "neutral" as const;
}
