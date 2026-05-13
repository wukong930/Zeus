"use client";

export const WORLD_MAP_NAV_SOURCE = "world-map";

export interface WorldMapNavigationScope {
  source: typeof WORLD_MAP_NAV_SOURCE;
  symbol?: string;
  region?: string;
  event?: string;
}

export interface WorldMapHrefScope {
  symbol?: string | null;
  region?: string | null;
  mechanism?: string | null;
  source?: string | null;
  event?: string | null;
}

const WORLD_MAP_SOURCE_FILTERS = new Set([
  "weather",
  "alert",
  "news",
  "signal",
  "position",
  "event_intelligence",
]);

const WORLD_MAP_MECHANISM_ALIASES: Record<string, string> = {
  weather: "rainfall_surplus",
  climate: "rainfall_surplus",
  weather_regime: "el_nino",
  el_nino: "el_nino",
  supply: "supply_disruption",
  production: "supply_disruption",
  logistics: "logistics_disruption",
  geopolitical: "logistics_disruption",
  inventory: "inventory_pressure",
  policy: "policy_shift",
  demand: "demand_shift",
  cost: "energy_cost",
  macro: "demand_shift",
  risk_sentiment: "demand_shift",
};

export function normalizeNavigationSymbol(value: string | null | undefined) {
  return (value ?? "").replace(/\d+/g, "").trim().toUpperCase();
}

export function normalizeWorldMapSourceFilter(value: string | null | undefined) {
  const normalized = (value ?? "").trim().toLowerCase();
  return WORLD_MAP_SOURCE_FILTERS.has(normalized) ? normalized : "";
}

export function normalizeWorldMapMechanismFilter(value: string | null | undefined) {
  const normalized = (value ?? "").trim().toLowerCase();
  if (!normalized) return "";
  return WORLD_MAP_MECHANISM_ALIASES[normalized] ?? normalized;
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

export function buildWorldMapHref(scope: WorldMapHrefScope) {
  const params = new URLSearchParams();
  const symbol = normalizeNavigationSymbol(scope.symbol);
  const source = normalizeWorldMapSourceFilter(scope.source);
  const mechanism = normalizeWorldMapMechanismFilter(scope.mechanism);
  const region = scope.region?.trim();
  const event = scope.event?.trim();

  if (symbol) params.set("symbol", symbol);
  if (source) params.set("source", source);
  if (mechanism) params.set("mechanism", mechanism);
  if (region) params.set("region", region);
  if (event) params.set("event", event);

  const query = params.toString();
  return query ? `/world-map?${query}` : "/world-map";
}

export function buildCausalWebHref(scope: WorldMapHrefScope) {
  const params = new URLSearchParams();
  const symbol = normalizeNavigationSymbol(scope.symbol);
  const region = scope.region?.trim();
  const event = scope.event?.trim();
  const source = scope.source?.trim();

  if (source) params.set("source", source);
  if (symbol) params.set("symbol", symbol);
  if (region) params.set("region", region);
  if (event) params.set("event", event);

  const query = params.toString();
  return query ? `/causal-web?${query}` : "/causal-web";
}
