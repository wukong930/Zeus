"use client";

import { Badge } from "@/components/Badge";
import { useI18n } from "@/lib/i18n";

export function VintageBadge({ vintageAt }: { vintageAt?: string }) {
  const { text, lang } = useI18n();

  if (!vintageAt) {
    return <span className="text-caption text-text-muted">{text("无行情")}</span>;
  }

  return (
    <Badge variant="neutral" className="font-mono">
      vintage {formatCompactDate(vintageAt, lang)}
    </Badge>
  );
}

function formatCompactDate(value: string, lang: "zh" | "en") {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value.slice(0, 10);
  return new Intl.DateTimeFormat(lang === "zh" ? "zh-CN" : "en-US", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}
