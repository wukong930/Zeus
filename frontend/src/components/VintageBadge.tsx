import { Badge } from "@/components/Badge";

export function VintageBadge({ vintageAt }: { vintageAt?: string }) {
  if (!vintageAt) {
    return <span className="text-caption text-text-muted">无行情</span>;
  }

  return (
    <Badge variant="neutral" className="font-mono">
      vintage {formatCompactDate(vintageAt)}
    </Badge>
  );
}

function formatCompactDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value.slice(0, 10);
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}
