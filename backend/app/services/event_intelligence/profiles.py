from dataclasses import dataclass


@dataclass(frozen=True)
class CommodityIntelligenceProfile:
    symbol: str
    name_zh: str
    sector: str
    regions: tuple[str, ...]
    mechanism_weights: dict[str, float]
    keywords: tuple[str, ...]


DEFAULT_COMMODITY_PROFILES: dict[str, CommodityIntelligenceProfile] = {
    "RU": CommodityIntelligenceProfile(
        symbol="RU",
        name_zh="天然橡胶",
        sector="rubber",
        regions=("southeast_asia_rubber",),
        mechanism_weights={
            "weather": 0.95,
            "supply": 0.9,
            "logistics": 0.72,
            "policy": 0.64,
            "inventory": 0.58,
            "demand": 0.5,
        },
        keywords=("rubber", "natural rubber", "latex", "橡胶", "天然橡胶", "胶水", "割胶"),
    ),
    "NR": CommodityIntelligenceProfile(
        symbol="NR",
        name_zh="20号胶",
        sector="rubber",
        regions=("southeast_asia_rubber",),
        mechanism_weights={
            "weather": 0.95,
            "supply": 0.9,
            "logistics": 0.72,
            "policy": 0.64,
            "inventory": 0.58,
            "demand": 0.5,
        },
        keywords=("nr", "tsr20", "20号胶", "天然橡胶", "橡胶"),
    ),
    "BR": CommodityIntelligenceProfile(
        symbol="BR",
        name_zh="顺丁橡胶",
        sector="rubber",
        regions=("southeast_asia_rubber", "china_chemical_supply"),
        mechanism_weights={
            "supply": 0.72,
            "cost": 0.7,
            "logistics": 0.58,
            "weather": 0.42,
            "demand": 0.5,
        },
        keywords=("br", "butadiene rubber", "顺丁橡胶", "丁二烯", "橡胶"),
    ),
    "SC": CommodityIntelligenceProfile(
        symbol="SC",
        name_zh="原油",
        sector="energy",
        regions=("middle_east_crude",),
        mechanism_weights={
            "geopolitical": 0.95,
            "supply": 0.88,
            "logistics": 0.78,
            "inventory": 0.72,
            "macro": 0.62,
            "risk_sentiment": 0.58,
            "demand": 0.5,
        },
        keywords=("crude", "oil", "brent", "wti", "原油", "石油", "航母", "伊朗", "opec"),
    ),
    "I": CommodityIntelligenceProfile(
        symbol="I",
        name_zh="铁矿石",
        sector="ferrous",
        regions=("australia_iron_ore",),
        mechanism_weights={
            "supply": 0.84,
            "logistics": 0.8,
            "weather": 0.66,
            "policy": 0.58,
            "demand": 0.54,
        },
        keywords=("iron ore", "铁矿", "矿山", "澳洲", "巴西"),
    ),
    "RB": CommodityIntelligenceProfile(
        symbol="RB",
        name_zh="螺纹钢",
        sector="ferrous",
        regions=("north_china_ferrous",),
        mechanism_weights={
            "demand": 0.76,
            "inventory": 0.72,
            "cost": 0.7,
            "policy": 0.66,
            "supply": 0.58,
        },
        keywords=("rebar", "螺纹", "螺纹钢", "地产", "基建"),
    ),
    "HC": CommodityIntelligenceProfile(
        symbol="HC",
        name_zh="热卷",
        sector="ferrous",
        regions=("north_china_ferrous",),
        mechanism_weights={
            "demand": 0.74,
            "inventory": 0.68,
            "cost": 0.68,
            "policy": 0.6,
            "supply": 0.56,
        },
        keywords=("hot coil", "hot rolled", "热卷", "板材", "制造业"),
    ),
    "J": CommodityIntelligenceProfile(
        symbol="J",
        name_zh="焦炭",
        sector="ferrous",
        regions=("north_china_ferrous",),
        mechanism_weights={
            "cost": 0.76,
            "supply": 0.72,
            "inventory": 0.64,
            "policy": 0.62,
            "demand": 0.52,
        },
        keywords=("coke", "焦炭", "钢厂", "焦化"),
    ),
    "JM": CommodityIntelligenceProfile(
        symbol="JM",
        name_zh="焦煤",
        sector="ferrous",
        regions=("north_china_ferrous",),
        mechanism_weights={
            "supply": 0.76,
            "cost": 0.74,
            "logistics": 0.62,
            "policy": 0.58,
            "demand": 0.5,
        },
        keywords=("coking coal", "焦煤", "煤矿", "蒙煤", "澳煤"),
    ),
    "M": CommodityIntelligenceProfile(
        symbol="M",
        name_zh="豆粕",
        sector="agri",
        regions=("brazil_soy_agri", "us_grains_energy"),
        mechanism_weights={
            "weather": 0.86,
            "supply": 0.8,
            "logistics": 0.68,
            "demand": 0.62,
            "policy": 0.58,
        },
        keywords=("soymeal", "soybean meal", "豆粕", "大豆", "巴西", "阿根廷"),
    ),
    "Y": CommodityIntelligenceProfile(
        symbol="Y",
        name_zh="豆油",
        sector="agri",
        regions=("brazil_soy_agri", "us_grains_energy"),
        mechanism_weights={
            "weather": 0.82,
            "supply": 0.76,
            "demand": 0.68,
            "policy": 0.62,
            "logistics": 0.58,
        },
        keywords=("soybean oil", "豆油", "大豆", "生柴", "biofuel"),
    ),
    "P": CommodityIntelligenceProfile(
        symbol="P",
        name_zh="棕榈油",
        sector="agri",
        regions=("southeast_asia_palm",),
        mechanism_weights={
            "weather": 0.86,
            "supply": 0.8,
            "policy": 0.66,
            "demand": 0.62,
            "logistics": 0.52,
        },
        keywords=("palm oil", "棕榈油", "马来西亚", "印尼", "厄尔尼诺"),
    ),
    "CU": CommodityIntelligenceProfile(
        symbol="CU",
        name_zh="铜",
        sector="metals",
        regions=("global_base_metals",),
        mechanism_weights={
            "macro": 0.82,
            "supply": 0.7,
            "demand": 0.7,
            "policy": 0.58,
            "inventory": 0.56,
        },
        keywords=("copper", "铜", "智利", "秘鲁", "lme"),
    ),
    "AL": CommodityIntelligenceProfile(
        symbol="AL",
        name_zh="铝",
        sector="metals",
        regions=("global_base_metals",),
        mechanism_weights={
            "cost": 0.78,
            "supply": 0.72,
            "macro": 0.68,
            "policy": 0.6,
            "demand": 0.54,
        },
        keywords=("aluminum", "aluminium", "铝", "电解铝", "电力"),
    ),
    "ZN": CommodityIntelligenceProfile(
        symbol="ZN",
        name_zh="锌",
        sector="metals",
        regions=("global_base_metals",),
        mechanism_weights={
            "supply": 0.72,
            "inventory": 0.66,
            "macro": 0.64,
            "demand": 0.54,
        },
        keywords=("zinc", "锌", "矿山", "冶炼"),
    ),
    "NI": CommodityIntelligenceProfile(
        symbol="NI",
        name_zh="镍",
        sector="metals",
        regions=("global_base_metals",),
        mechanism_weights={
            "policy": 0.78,
            "supply": 0.76,
            "demand": 0.62,
            "macro": 0.58,
        },
        keywords=("nickel", "镍", "印尼", "不锈钢", "新能源"),
    ),
}


def profile_for_symbol(symbol: str) -> CommodityIntelligenceProfile | None:
    return DEFAULT_COMMODITY_PROFILES.get(symbol.upper())


def symbols_matching_text(text: str) -> list[str]:
    haystack = text.lower()
    matches: list[str] = []
    for symbol, profile in DEFAULT_COMMODITY_PROFILES.items():
        if any(keyword.lower() in haystack for keyword in profile.keywords):
            matches.append(symbol)
    return matches
