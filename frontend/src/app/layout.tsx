import type { Metadata } from "next";
import "@xyflow/react/dist/style.css";
import "./globals.css";
import { Sidebar } from "@/components/Sidebar";
import { HeartbeatBar } from "@/components/HeartbeatBar";
import { AICompanion } from "@/components/AICompanion";
import { CommandPalette } from "@/components/CommandPalette";
import { BootSequence } from "@/components/BootSequence";

export const metadata: Metadata = {
  title: "Zeus — Futures Intelligence",
  description: "商品期货研究与决策平台 · Prototype Demo",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN">
      <body>
        <BootSequence>
          <div className="flex flex-col h-screen overflow-hidden">
            <HeartbeatBar />
            <div className="flex flex-1 overflow-hidden">
              <Sidebar />
              <main className="flex-1 overflow-y-auto">{children}</main>
            </div>
            <StatusBar />
          </div>
          <CommandPalette />
          <AICompanion />
        </BootSequence>
      </body>
    </html>
  );
}

function StatusBar() {
  return (
    <div className="flex h-6 items-center justify-between border-t border-border-subtle bg-[linear-gradient(180deg,rgba(5,7,6,0.98),rgba(0,0,0,1))] px-4 text-caption text-text-muted shadow-inner-panel">
      <div className="flex items-center gap-4">
        <span>UTC+8 Asia/Shanghai</span>
        <span>•</span>
        <span>Data: 2026-04-30 22:14</span>
      </div>
      <div className="flex items-center gap-4">
        <kbd className="rounded-xs border border-border-default bg-bg-base px-1.5 font-mono shadow-inner-panel">
          ⌘K
        </kbd>
        <span>命令面板</span>
        <span>•</span>
        <span className="text-brand-emerald-bright">Nikoo</span>
      </div>
    </div>
  );
}
