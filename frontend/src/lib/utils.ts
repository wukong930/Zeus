import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatNumber(value: number, options: { decimals?: number; signed?: boolean; suffix?: string } = {}) {
  const { decimals = 2, signed = false, suffix = "" } = options;
  const formatted = value.toLocaleString("en-US", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
  if (signed && value > 0) return `+${formatted}${suffix}`;
  return `${formatted}${suffix}`;
}

export function formatPercent(value: number, decimals = 2, signed = true) {
  return formatNumber(value, { decimals, signed, suffix: "%" });
}

export function timeAgo(date: Date | string) {
  const now = Date.now();
  const then = typeof date === "string" ? new Date(date).getTime() : date.getTime();
  const diff = Math.floor((now - then) / 1000);
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}
