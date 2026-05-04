"use client";

import { LanguageToggle, useI18n } from "@/lib/i18n";

export function StatusBar() {
  const { text } = useI18n();

  return (
    <div className="flex h-6 items-center justify-between border-t border-border-subtle bg-[linear-gradient(180deg,rgba(5,7,6,0.98),rgba(0,0,0,1))] px-4 text-caption text-text-muted shadow-inner-panel">
      <div className="flex items-center gap-4">
        <span>UTC+8 Asia/Shanghai</span>
        <span>•</span>
        <span>Data: 2026-04-30 22:14</span>
      </div>
      <div className="flex items-center gap-3">
        <LanguageToggle />
        <kbd className="rounded-xs border border-border-default bg-bg-base px-1.5 font-mono shadow-inner-panel">
          ⌘K
        </kbd>
        <span>{text("命令面板")}</span>
        <span>•</span>
        <span className="text-brand-emerald-bright">Nikoo</span>
      </div>
    </div>
  );
}
