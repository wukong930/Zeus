"use client";

import { useEffect, useMemo, useState } from "react";
import { Activity, AlertCircle, Clock, Database, TrendingDown, TrendingUp } from "lucide-react";
import { SECTORS } from "@/data/sectorUniverse";
import { fetchMarketQuotes, type MarketQuote } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { cn, formatNumber, formatPercent } from "@/lib/utils";

const DEFAULT_QUOTE_SYMBOLS = ["RB", "RU", "NR", "SC", "I", "CU", "AU", "AG"];
const SYMBOL_NAMES = new Map(
  SECTORS.flatMap((sector) => sector.symbols.map((symbol) => [symbol.code, symbol.name] as const))
);

type QuoteLoadState = "loading" | "ready" | "error";

interface MarketQuoteStripProps {
  symbols?: readonly string[];
  title?: string;
  className?: string;
  compact?: boolean;
  maxItems?: number;
  refreshMs?: number;
}

export function MarketQuoteStrip({
  symbols = DEFAULT_QUOTE_SYMBOLS,
  title = "商品报价",
  className,
  compact = false,
  maxItems = compact ? 6 : 10,
  refreshMs = 60_000,
}: MarketQuoteStripProps) {
  const { text } = useI18n();
  const [quotes, setQuotes] = useState<MarketQuote[]>([]);
  const [state, setState] = useState<QuoteLoadState>("loading");
  const visibleSymbols = useMemo(() => normalizeSymbols(symbols).slice(0, maxItems), [maxItems, symbols]);

  useEffect(() => {
    let mounted = true;

    const loadQuotes = () => {
      if (visibleSymbols.length === 0) {
        setQuotes([]);
        setState("ready");
        return;
      }
      setState((current) => (current === "ready" ? current : "loading"));
      fetchMarketQuotes(visibleSymbols)
        .then((nextQuotes) => {
          if (!mounted) return;
          setQuotes(nextQuotes);
          setState("ready");
        })
        .catch(() => {
          if (!mounted) return;
          setQuotes(visibleSymbols.map((symbol) => missingQuote(symbol)));
          setState("error");
        });
    };

    loadQuotes();
    if (refreshMs <= 0) {
      return () => {
        mounted = false;
      };
    }
    const timer = window.setInterval(loadQuotes, refreshMs);
    return () => {
      mounted = false;
      window.clearInterval(timer);
    };
  }, [refreshMs, visibleSymbols]);

  const quoteBySymbol = useMemo(
    () => new Map(quotes.map((quote) => [quote.symbol, quote])),
    [quotes]
  );
  const orderedQuotes = visibleSymbols.map((symbol) => quoteBySymbol.get(symbol) ?? missingQuote(symbol));
  const latestTimestamp = latestQuoteTimestamp(orderedQuotes);

  return (
    <section
      className={cn(
        "rounded-sm border border-white/[0.10] bg-black/34 shadow-data-panel backdrop-blur-2xl",
        compact ? "px-2.5 py-2" : "px-3 py-2.5",
        className
      )}
      aria-label={text(title)}
    >
      <div className={cn("flex min-w-0 items-center gap-3", compact ? "flex-wrap" : "flex-col lg:flex-row")}>
        <div className="flex min-w-0 shrink-0 items-center gap-2">
          <Database className="h-4 w-4 text-brand-emerald-bright" />
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold text-text-primary">{text(title)}</div>
            {!compact && (
              <div className="truncate text-caption text-text-muted">
                {state === "error" ? text("行情暂不可用") : text("最新行情快照")}
              </div>
            )}
          </div>
        </div>

        <div className="flex min-w-0 flex-1 items-stretch gap-1.5 overflow-x-auto pb-0.5">
          {orderedQuotes.map((quote) => (
            <QuotePill key={quote.symbol} quote={quote} compact={compact} loading={state === "loading"} />
          ))}
        </div>

        <div className="ml-auto flex shrink-0 items-center gap-1.5 text-caption text-text-muted">
          {state === "loading" ? (
            <>
              <Activity className="h-3.5 w-3.5 animate-pulse text-brand-emerald-bright" />
              <span>{text("行情加载中")}</span>
            </>
          ) : state === "error" ? (
            <>
              <AlertCircle className="h-3.5 w-3.5 text-brand-orange" />
              <span>{text("接口暂不可用")}</span>
            </>
          ) : (
            <>
              <Clock className="h-3.5 w-3.5" />
              <span>{latestTimestamp ? formatQuoteTime(latestTimestamp) : "--"}</span>
            </>
          )}
        </div>
      </div>
    </section>
  );
}

function QuotePill({
  quote,
  compact,
  loading,
}: {
  quote: MarketQuote;
  compact: boolean;
  loading: boolean;
}) {
  const { text } = useI18n();
  const name = SYMBOL_NAMES.get(quote.symbol) ?? quote.symbol;
  const isMissing = quote.status === "missing" || quote.price === null;
  const isUp = (quote.changePct ?? 0) >= 0;
  const TrendIcon = quote.changePct === null ? Activity : isUp ? TrendingUp : TrendingDown;

  return (
    <div
      className={cn(
        "min-w-[128px] rounded-xs border bg-bg-base/66 px-2 py-1.5 shadow-inner-panel",
        compact ? "min-w-[112px]" : "min-w-[136px]",
        isMissing
          ? "border-white/[0.08] text-text-muted"
          : isUp
            ? "border-brand-emerald/20 text-data-up"
            : "border-data-down/25 text-data-down"
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="font-mono text-sm font-semibold text-text-primary">{quote.symbol}</div>
        <TrendIcon className={cn("h-3.5 w-3.5", loading && "animate-pulse")} />
      </div>
      <div className="truncate text-caption text-text-muted">{text(name)}</div>
      <div className="mt-1 flex items-baseline justify-between gap-2">
        <span className="font-mono text-sm tabular-nums text-text-primary">
          {isMissing ? "--" : formatQuotePrice(quote.price)}
        </span>
        <span className={cn("font-mono text-caption tabular-nums", isMissing && "text-text-muted")}>
          {quote.changePct === null ? text("暂无行情") : formatPercent(quote.changePct)}
        </span>
      </div>
    </div>
  );
}

function normalizeSymbols(symbols: readonly string[]): string[] {
  return Array.from(
    new Set(
      symbols
        .map((symbol) => symbol.trim().toUpperCase())
        .filter((symbol) => symbol.length > 0)
    )
  );
}

function missingQuote(symbol: string): MarketQuote {
  return {
    symbol,
    price: null,
    changePct: null,
    timestamp: null,
    status: "missing",
  };
}

function latestQuoteTimestamp(quotes: MarketQuote[]): string | null {
  const timestamps = quotes
    .map((quote) => quote.timestamp)
    .filter((timestamp): timestamp is string => Boolean(timestamp))
    .sort((left, right) => new Date(right).getTime() - new Date(left).getTime());
  return timestamps[0] ?? null;
}

function formatQuotePrice(value: number | null): string {
  if (value === null) return "--";
  return formatNumber(value, { decimals: Math.abs(value) >= 100 ? 0 : 2 });
}

function formatQuoteTime(timestamp: string): string {
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "--";
  return new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}
