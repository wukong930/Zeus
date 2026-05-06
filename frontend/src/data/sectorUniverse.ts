import type { SectorData } from "@/lib/domain";

export const SECTORS: SectorData[] = [
  {
    id: "ferrous",
    name: "黑色",
    conviction: 0.42,
    symbols: [
      { code: "RB", name: "螺纹钢", change: 1.24, signalActive: true },
      { code: "HC", name: "热卷", change: 0.86, signalActive: false },
      { code: "I", name: "铁矿石", change: -0.32, signalActive: true },
      { code: "J", name: "焦炭", change: 0.51, signalActive: false },
      { code: "JM", name: "焦煤", change: -0.18, signalActive: false },
    ],
  },
  {
    id: "rubber",
    name: "橡胶",
    conviction: -0.31,
    symbols: [
      { code: "RU", name: "天然橡胶", change: -0.92, signalActive: true },
      { code: "NR", name: "20号胶", change: -1.15, signalActive: true },
      { code: "BR", name: "顺丁橡胶", change: 0.21, signalActive: false },
    ],
  },
  {
    id: "energy",
    name: "能化",
    conviction: 0.18,
    symbols: [
      { code: "SC", name: "原油", change: 0.74, signalActive: true },
      { code: "TA", name: "PTA", change: -0.12, signalActive: false },
      { code: "MA", name: "甲醇", change: -0.45, signalActive: false },
      { code: "PP", name: "聚丙烯", change: 0.33, signalActive: false },
    ],
  },
  {
    id: "metals",
    name: "有色",
    conviction: 0.65,
    symbols: [
      { code: "CU", name: "铜", change: 1.42, signalActive: true },
      { code: "AL", name: "铝", change: 0.81, signalActive: false },
      { code: "ZN", name: "锌", change: -0.24, signalActive: false },
      { code: "NI", name: "镍", change: 2.15, signalActive: true },
    ],
  },
  {
    id: "agri",
    name: "农产",
    conviction: -0.12,
    symbols: [
      { code: "M", name: "豆粕", change: -0.41, signalActive: false },
      { code: "Y", name: "豆油", change: 0.18, signalActive: false },
      { code: "P", name: "棕榈油", change: -0.62, signalActive: true },
    ],
  },
  {
    id: "precious",
    name: "贵金属",
    conviction: 0.21,
    symbols: [
      { code: "AU", name: "黄金", change: 0.42, signalActive: false },
      { code: "AG", name: "白银", change: 0.78, signalActive: false },
    ],
  },
];
