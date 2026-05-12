"use client";

export const WORLD_MAP_NAV_SOURCE = "world-map";

export interface WorldMapNavigationScope {
  source: typeof WORLD_MAP_NAV_SOURCE;
  symbol?: string;
  region?: string;
  event?: string;
}

export function normalizeNavigationSymbol(value: string | null | undefined) {
  return (value ?? "").replace(/\d+/g, "").trim().toUpperCase();
}

export function readWorldMapNavigationScope(
  search: string | URLSearchParams
): WorldMapNavigationScope | null {
  const params = search instanceof URLSearchParams ? search : new URLSearchParams(search);
  const source = params.get("source");
  const symbol = normalizeNavigationSymbol(params.get("symbol"));
  const region = params.get("region")?.trim();
  const event = params.get("event")?.trim();

  if (source !== WORLD_MAP_NAV_SOURCE && !symbol && !region && !event) return null;

  return {
    source: WORLD_MAP_NAV_SOURCE,
    ...(symbol ? { symbol } : {}),
    ...(region ? { region } : {}),
    ...(event ? { event } : {}),
  };
}

export function appendWorldMapNavigationScope(
  href: string,
  scope: Omit<WorldMapNavigationScope, "source">
) {
  const [path, queryString = ""] = href.split("?");
  const params = new URLSearchParams(queryString);
  const symbol = normalizeNavigationSymbol(scope.symbol);

  params.set("source", WORLD_MAP_NAV_SOURCE);
  if (symbol) params.set("symbol", symbol);
  if (scope.region) params.set("region", scope.region);
  if (scope.event) params.set("event", scope.event);

  const nextQuery = params.toString();
  return nextQuery ? `${path}?${nextQuery}` : path;
}
