import type { Metadata } from "next";
import "@xyflow/react/dist/style.css";
import "./globals.css";
import { Sidebar } from "@/components/Sidebar";
import { HeartbeatBar } from "@/components/HeartbeatBar";
import { AICompanion } from "@/components/AICompanion";
import { CommandPalette } from "@/components/CommandPalette";
import { BootSequence } from "@/components/BootSequence";
import { StatusBar } from "@/components/StatusBar";
import { I18nProvider } from "@/lib/i18n";

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
        <I18nProvider>
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
        </I18nProvider>
      </body>
    </html>
  );
}
