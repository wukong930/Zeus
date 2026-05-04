"use client";

import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { Languages } from "lucide-react";
import { cn } from "@/lib/utils";

export type Language = "zh" | "en";

interface I18nContextValue {
  lang: Language;
  setLang: (lang: Language) => void;
  toggleLang: () => void;
  text: (source: string) => string;
}

const STORAGE_KEY = "zeus-language";

const I18nContext = createContext<I18nContextValue | null>(null);

const EN: Record<string, string> = {
  "命令中心": "Command Center",
  "预警": "Alerts",
  "交易计划": "Trade Plans",
  "持仓地图": "Portfolio Map",
  "因果网络": "Causal Web",
  "新闻事件": "News Events",
  "产业透镜": "Industry Lens",
  "板块": "Sectors",
  "未来实验室": "Future Lab",
  "策略锻造": "Strategy Forge",
  "笔记本": "Notebook",
  "分析": "Analytics",
  "设置": "Settings",
  "跳转": "Navigation",
  "品种": "Symbols",
  "操作": "Actions",
  "询问 AI Companion": "Ask AI Companion",
  "创建笔记": "Create Note",
  "搜索品种 / 跳转 / 执行...": "Search symbols / navigate / run...",
  "没找到匹配项": "No matches",
  "命令面板": "Command Palette",
  "数据": "Data",
  "活跃": "Active",
  "漂移": "Drift",
  "校准": "Calibration",
  "状态": "Regime",
  "正常": "Normal",
  "震荡 · 高波动": "Range · High Vol",
  "震荡 · 低波动": "Range · Low Vol",
  "趋势上行 · 低波动": "Trend Up · Low Vol",
  "趋势下行 · 低波动": "Trend Down · Low Vol",
  "晚上好": "Good evening",
  "距上次访问": "Since last visit",
  "小时。期间发生：": " hours. During this period:",
  "条预警": "alerts",
  "其中": "including",
  "与你持仓相关": "relevant to your positions",
  "重点：": "Focus:",
  "展开全图": "Open Full Map",
  "实时活跃因果链": "Live causal chain",
  "当日预警流": "Today Alerts",
  "查看全部": "View All",
  "持仓概览": "Portfolio Overview",
  "个持仓": "positions",
  "总浮动盈亏": "floating PnL",
  "详情": "Details",
  "多": "Long",
  "空": "Short",
  "手": "lots",
  "板块热力图": "Sector Heatmap",
  "橙点 = 信号活跃": "Orange dot = active signal",
  "活跃信号": "Active Signals",
  "过去 24h": "Last 24h",
  "本月预警": "Monthly Alerts",
  "vs 上月": "vs last month",
  "校准进度": "Calibration",
  "样本量": "samples",
  "LLM 月度成本": "LLM Monthly Cost",
  "预算": "Budget",
  "黑色": "Ferrous",
  "橡胶": "Rubber",
  "能化": "Energy/Chem",
  "有色": "Base Metals",
  "农产": "Agriculture",
  "贵金属": "Precious Metals",
  "螺纹钢": "Rebar",
  "热卷": "Hot-rolled Coil",
  "铁矿石": "Iron Ore",
  "焦炭": "Coke",
  "焦煤": "Coking Coal",
  "天然橡胶": "Natural Rubber",
  "20号胶": "No.20 Rubber",
  "顺丁橡胶": "BR Rubber",
  "原油": "Crude Oil",
  "甲醇": "Methanol",
  "聚丙烯": "Polypropylene",
  "铜": "Copper",
  "铝": "Aluminum",
  "锌": "Zinc",
  "镍": "Nickel",
  "豆粕": "Soymeal",
  "豆油": "Soybean Oil",
  "棕榈油": "Palm Oil",
  "黄金": "Gold",
  "白银": "Silver",
  "系统配置 · LLM 供应商 · 通知渠道": "System configuration · LLM providers · notification channels",
  "LLM 供应商": "LLM Providers",
  "多供应商支持，按场景路由": "Multi-provider routing by scenario",
  "主力": "Primary",
  "本月成本 / 预算": "Monthly cost / budget",
  "配置": "Configure",
  "通知渠道": "Notification Channels",
  "前端实时推送与外部 Webhook": "Realtime frontend push and external webhooks",
  "实时 SSE 推送（前端）": "Realtime SSE Push (Frontend)",
  "飞书 Webhook": "Feishu Webhook",
  "Email 通知": "Email Notification",
  "自定义 Webhook": "Custom Webhook",
  "预警去重设置": "Alert Deduplication",
  "控制重复预警与升级重发": "Control duplicates and severity upgrade resends",
  "同品种同方向 N 小时内只发一次": "Same symbol and direction only once per N hours",
  "同信号组合 N 小时内只发一次": "Same signal bundle only once per N hours",
  "每日预警上限": "Daily alert limit",
  "允许严重度升级时重新发送": "Resend when severity upgrades",
  "12 小时": "12 hours",
  "24 小时": "24 hours",
  "50 条": "50 alerts",
  "是": "Yes",
  "关于 Zeus": "About Zeus",
  "这个版本是纯前端原型，所有数据为模拟。后端 Python 服务（事件总线、信号检测、校准循环、对抗引擎、Alert Agent）将在 Phase 1 开始构建。":
    "This version is a frontend prototype with simulated data. Backend Python services (event bus, signal detection, calibration loop, adversarial engine, Alert Agent) begin in Phase 1.",
  "实时观察事件间的因果传导。点击节点追溯上游 / 预测下游。":
    "Observe causal propagation between events in realtime. Click nodes to trace upstream and forecast downstream.",
  "事件": "Event",
  "信号": "Signal",
  "指标": "Metric",
  "反证": "Counter",
  "事件源": "Event Source",
  "假设生成": "Hypothesis",
  "证据校验": "Validation",
  "市场/预警": "Market/Alert",
  "新闻、天气和外部冲击": "News, weather, and external shocks",
  "产业逻辑与方向假设": "Industrial logic and directional hypotheses",
  "价格、持仓与基本面验证": "Price, positioning, and fundamental validation",
  "可交易影响与告警出口": "Tradable impact and alert outlet",
  "地缘": "Geopolitics",
  "持仓": "Positioning",
  "全量因果网：适合检查跨板块传导、孤立节点和链路完整性。":
    "Full causal network for cross-sector propagation, isolated nodes, and path integrity.",
  "持仓视角：聚焦会影响当前风险暴露的 NR/RU 与黑色链路。":
    "Portfolio view focused on NR/RU and ferrous paths affecting current exposure.",
  "反证视角：突出会压低置信度、阻止误触发的验证节点。":
    "Counter view highlights validation nodes that reduce confidence and prevent false triggers.",
  "预警追踪：只强化能够进入告警或人工审查的关键路径。":
    "Alert trace emphasizes paths entering alerts or manual review.",
  "上游": "upstream",
  "下游": "downstream",
  "全量": "All",
  "，": ", ",
  "。": ".",
  "Nodes": "Nodes",
  "Verified": "Verified",
  "Mode": "Mode",
  "View": "View",
  "Visible": "Visible",
  "Fit view": "Fit view",
  "Close": "Close",
  "Close node details": "Close node details",
  "Fresh": "Fresh",
  "Impact": "Impact",
  "State": "State",
  "Quiet": "Quiet",
  "Propagation": "Propagation",
  "Causal Layers": "Causal Layers",
  "Semantic Stages": "Semantic Stages",
  "Position": "Position",
  "Alert": "Alert",
  "All": "All",
  "all": "all",
  "Portfolio": "Portfolio",
  "Counter": "Counter",
  "Alert Trace": "Alert Trace",
  "live": "live",
  "replay": "replay",
  "explorer": "explorer",
  "bullish": "bullish",
  "bearish": "bearish",
  "neutral": "neutral",
  "verified": "verified",
  "unverified": "unverified",
  "RB 触发了 cost_support_pressure": "RB triggered cost_support_pressure",
  "螺纹钢主力": "Rebar Main",
  "20号胶主力": "No.20 Rubber Main",
  "沪铜主力": "SHFE Copper Main",
  "铁矿主力": "Iron Ore Main",
  "棕榈油主力": "Palm Oil Main",
  "原油主力": "Crude Oil Main",
  "螺纹跌破 P75 边际成本支撑": "Rebar broke below P75 marginal cost support",
  "泰国天胶产区遭遇暴雨": "Heavy rain hits Thai natural rubber regions",
  "沪伦比价 Z-score 突破 +2.1": "SHFE/LME copper ratio Z-score breaks +2.1",
  "铁矿 ATR 放大，趋势进入震荡": "Iron ore ATR expands, trend shifts to range",
  "马来棕榈油库存意外增加": "Malaysian palm oil inventory rises unexpectedly",
  "原油动量信号触发但置信度偏低": "Crude oil momentum signal triggered with low confidence",
  "螺纹现货价 4280 已触及高炉成本曲线 P75 分位（4310），连续 2 周持续。结合焦炭弱势 + 钢厂利润率转负 → 触发产能收缩预期。":
    "Rebar spot at 4,280 has reached the P75 blast-furnace cost curve level (4,310) for two straight weeks. Weak coke plus negative mill margins trigger capacity-cut expectations.",
  "泰国南部主产区（合艾、宋卡）出现持续强降雨，未来 7 天预报维持。历史 5 次类似事件 4 次推升 NR 短期上涨 3-7%。":
    "Sustained heavy rainfall hit key southern Thai producing areas (Hat Yai and Songkhla), with forecasts persisting for seven days. Four of five similar historical events lifted NR by 3-7% short term.",
  "近月沪伦比价偏离 90 日均值 2.1 个标准差，历史回归概率 0.78。结合人民币汇率边际转强 → 套利窗口出现。":
    "The near-month SHFE/LME copper ratio is 2.1 standard deviations above its 90-day mean, with a historical mean-reversion probability of 0.78. A firmer RMB opens an arbitrage window.",
  "铁矿过去 10 日 ATR 百分位升至 78，ADX 跌至 18，从 trend_down 切换至 range_high_vol。":
    "Iron ore's 10-day ATR percentile rose to 78 while ADX fell to 18, shifting from trend_down to range_high_vol.",
  "MPOB 月报显示库存环比 +5.8%，超预期 +2.1%。供给压力释放，价格短期承压。":
    "The MPOB monthly report showed inventory up 5.8% month over month, 2.1 points above expectations. Supply pressure weighs on near-term prices.",
  "5 日动量突破 +2.3%，但波动率扩大 + 历史命中率仅 0.52。建议观察 1-2 个交易日确认。":
    "Five-day momentum broke +2.3%, but volatility expanded and the historical hit rate is only 0.52. Watch one to two sessions for confirmation.",
  "做多": "Long",
  "做空": "Short",
  "止损": "Stop",
  "入场": "Entry",
  "当前": "Current",
  "目标": "Target",
  "保证金占用": "Margin Usage",
  "组合风险": "Portfolio Risk",
  "信号摘要": "Signal Summary",
  "采纳建议": "Accept",
  "修改": "Edit",
  "拒绝": "Reject",
  "成本支撑 + 库存低位 + 历史类比命中率 0.72": "Cost support + low inventory + 0.72 historical analogue hit rate",
  "产区暴雨 + 历史 4/5 命中 + 保税区报价跟涨": "Producing-region rain + 4/5 historical hits + bonded-zone quotes following higher",
  "沪伦比 Z=+2.1 + 历史回归概率 0.78": "SHFE/LME ratio Z=+2.1 + 0.78 historical reversion probability",
  "待人工确认": "Manual Review",
  "通过": "Approve",
  "已提交": "Submitted",
  "提交失败": "Submit failed",
  "触发新闻": "Triggering News",
  "反馈": "Feedback",
  "同意": "Agree",
  "不确定": "Uncertain",
  "不同意": "Disagree",
  "已记录": "Recorded",
  "稍后重试": "Retry later",
  "当前可见": "Visible Now",
  "已验证": "Verified",
  "搜索预警...": "Search alerts...",
  "严重度": "Severity",
  "预警流": "Alert Stream",
  "按严重度、板块和人工确认状态扫描当前事件。": "Scan current events by severity, sector, and manual review state.",
  "预警加载中": "Loading alerts",
  "没有匹配的预警": "No matching alerts",
  "无行情": "No quote",
  "Open AI Companion": "Open AI Companion",
  "Context aware research copilot": "Context-aware research copilot",
  "我是你的 Zeus 研究伙伴。我知道你当前在哪个页面、看哪个预警，可以帮你解释、对比、追问。":
    "I am your Zeus research partner. I know the current page and alert context, and can help explain, compare, and follow up.",
  "建议提问": "Suggested Questions",
  "为什么 RB 触发了 cost_support_pressure？": "Why did RB trigger cost_support_pressure?",
  "解释一下当前的 Drift 状态": "Explain the current drift state",
  "我的橡胶持仓有哪些下游风险？": "What downstream risks affect my rubber positions?",
  "对比上月和本月的命中率变化": "Compare hit-rate changes month over month",
  "你": "You",
  "思考中...": "Thinking...",
  "问点什么...": "Ask anything...",
  "上下文：当前页面 + 最近 3 条预警": "Context: current page + latest 3 alerts",
  "总数": "Total",
  "交叉验证": "Cross-Verified",
  "人工确认": "Manual Review",
  "品种 / 标题 / 摘要": "Symbol / title / summary",
  "新闻事件加载中": "Loading news events",
  "没有匹配的新闻事件": "No matching news events",
  "OPEC+ 宣布延长自愿减产，原油短线走强": "OPEC+ extends voluntary cuts, crude strengthens short term",
  "OPEC+ 延长自愿减产安排，市场重新评估二季度供应缺口，对 SC 原油形成偏多冲击。":
    "OPEC+ extended voluntary cuts. The market is reassessing Q2 supply gaps, creating a bullish shock for SC crude.",
  "泰国南部橡胶主产区连续强降雨": "Continuous heavy rain in southern Thai rubber regions",
  "合艾和宋卡降雨持续，割胶节奏受扰，NR/RU 近端供应预期收紧。":
    "Rainfall continues in Hat Yai and Songkhla, disrupting tapping and tightening near-end NR/RU supply expectations.",
  "交易所提示铁矿石合约交易风险": "Exchange warns of iron ore contract trading risk",
  "交易所发布铁矿石波动风险提示，单源高严重度事件等待人工确认后再进入评估。":
    "The exchange issued an iron ore volatility risk notice. This single-source high-severity event waits for manual confirmation before evaluation.",
  "类型": "Type",
  "时效": "Horizon",
  "来源数": "Sources",
  "置信度": "Confidence",
  "影响品种": "Affected Symbols",
  "质量门槛": "Quality Gates",
  "严重度 ≥ 3": "Severity >= 3",
  "跨源验证": "Cross-source",
  "无需确认": "No manual gate",
  "原文链接": "Original Link",
  "policy": "policy",
  "supply": "supply",
  "demand": "demand",
  "inventory": "inventory",
  "weather": "weather",
  "breaking": "breaking",
  "mixed": "mixed",
  "unclear": "unclear",
  "short": "short",
  "medium": "medium",
  "immediate": "immediate",
  "ferrous": "Ferrous",
  "rubber": "Rubber",
  "energy": "Energy/Chem",
  "metals": "Base Metals",
  "agri": "Agriculture",
  "precious": "Precious Metals",
  "每条建议是一份完整的飞行计划——入场、止损、目标、保证金、组合风险一目了然。":
    "Each recommendation is a complete flight plan: entry, stop, target, margin, and portfolio risk at a glance.",
  "计划数": "Plans",
  "平均置信度": "Avg Confidence",
  "平均保证金": "Avg Margin",
  "板块层方向判断 + 各品种活跃度 + conviction 因子":
    "Sector direction, symbol activity, and conviction factors",
  "板块数": "Sectors",
  "平均 conviction": "Avg Conviction",
  "方向状态": "Bias State",
  "橙色脉动 = 信号活跃 · 颜色亮度 = 涨跌幅":
    "Orange pulse = active signal · color intensity = price move",
  "核心因子（4 维 conviction）": "Core Factors (4D Conviction)",
  "成本": "Cost",
  "库存": "Inventory",
  "季节": "Seasonality",
  "利润": "Margin",
  "可视化展示持仓在传导图中的位置 + 组合风险":
    "Visualize where positions sit in the propagation map plus portfolio risk.",
  "组合 P&L": "Portfolio P&L",
  "添加持仓": "Add Position",
  "当日浮动": "Intraday Floating",
  "日 95% 置信": "day 95% confidence",
  "压力损失": "Stress Loss",
  "个场景": "scenarios",
  "持仓列表": "Position List",
  "笔持仓": "positions",
  "包含传导图激活范围": "includes propagation-map activation",
  "方向": "Direction",
  "手数": "Lots",
  "入场均价": "Avg Entry",
  "现价": "Last Price",
  "浮动盈亏": "Floating PnL",
  "收益率": "Return",
  "数据版本": "Data Vintage",
  "开仓日期": "Open Date",
  "减半": "Halve",
  "平仓": "Close",
  "持仓加载中": "Loading positions",
  "当前没有开放持仓": "No open positions",
  "传导图激活范围": "Propagation Activation",
  "持仓自动激活的关联品种监控": "Related-symbol monitoring activated by positions",
  "暂无开放持仓，传导图保持待机。": "No open positions. Propagation monitoring stays on standby.",
  "板块集中度提示": "Sector Concentration Notice",
  "当前保证金占用": "Current margin usage",
  "高相关或高占用持仓会在建议生成时降级。":
    "Highly correlated or high-usage positions are downgraded when recommendations are generated.",
  "激活监控品种": "Activated Symbols",
  "替代品": "Substitute",
  "下游替代": "Downstream substitute",
  "链路锚点": "Path anchor",
  "下游化工": "Downstream chemical",
  "上游原料": "Upstream input",
  "二级原料": "Secondary input",
  "美国航母移动": "US carrier movement",
  "中东局势升级": "Middle East escalation",
  "原油 SC 上涨预期": "SC crude upside thesis",
  "化工链上行": "Chemical chain rising",
  "PTA 现货上涨": "PTA spot rising",
  "PP 走强": "PP strengthening",
  "CFTC 持仓未增": "CFTC positions not rising",
  "产区暴雨": "Producing-region rainstorm",
  "NR/RU 短期看涨": "NR/RU short-term bullish",
  "焦煤价格回落": "Coking coal price pullback",
  "高炉利润转负": "Blast-furnace margin turns negative",
  "螺纹成本支撑": "Rebar cost support",
  "外部军事移动是能源风险溢价的上游扰动源。":
    "External military movement is an upstream disturbance for energy risk premium.",
  "区域局势升级会放大航运和供应中断预期。":
    "Regional escalation amplifies shipping and supply-disruption expectations.",
  "把地缘风险和价格预期压缩成可监控的原油上涨假设。":
    "Compress geopolitical risk and price expectations into a monitorable crude-oil upside thesis.",
  "原油假设向化工链利润和成本端继续传播。":
    "The crude thesis propagates into chemical-chain margins and cost inputs.",
  "PTA 现货上涨是能化链传导后的市场影响节点。":
    "PTA spot strength is a market-impact node after energy/chemical propagation.",
  "PP 走强验证能化链的下游盘面响应。":
    "PP strength validates downstream screen response in the energy/chemical chain.",
  "持仓未同步增加会削弱能源上涨信号的发射概率。":
    "Positions failing to rise in sync reduce the emission probability of the energy upside signal.",
  "产区天气冲击是橡胶链短期供应风险的触发源。":
    "Producing-region weather shock is the trigger source for short-term rubber supply risk.",
  "橡胶短期看涨直接关联持仓风险和交易计划。":
    "Short-term rubber upside directly links to position risk and trade plans.",
  "焦煤回落会削弱黑色链成本支撑的强度。":
    "Coking coal pullback weakens cost-support strength in the ferrous chain.",
  "高炉利润转负提示黑色链需求与成本传导存在压力。":
    "Negative blast-furnace margins indicate pressure in ferrous demand and cost propagation.",
  "螺纹成本支撑是黑色链风险出口，适合进入预警追踪。":
    "Rebar cost support is the ferrous-chain risk outlet and fits alert tracing.",
  "冲突": "Conflict",
  "航运": "Shipping",
  "阈值": "Threshold",
  "化工": "Chemical",
  "传导": "Propagation",
  "现货": "Spot",
  "盘面": "Screen",
  "天气": "Weather",
  "产区": "Producing Area",
  "支撑": "Support",
};

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Language>("zh");

  useEffect(() => {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored === "zh" || stored === "en") setLangState(stored);
  }, []);

  const setLang = (nextLang: Language) => {
    setLangState(nextLang);
    window.localStorage.setItem(STORAGE_KEY, nextLang);
    document.documentElement.lang = nextLang === "zh" ? "zh-CN" : "en";
  };

  useEffect(() => {
    document.documentElement.lang = lang === "zh" ? "zh-CN" : "en";
  }, [lang]);

  const value = useMemo<I18nContextValue>(
    () => ({
      lang,
      setLang,
      toggleLang: () => setLang(lang === "zh" ? "en" : "zh"),
      text: (source: string) => (lang === "en" ? EN[source] ?? source : source),
    }),
    [lang]
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n() {
  const context = useContext(I18nContext);
  if (!context) throw new Error("useI18n must be used within I18nProvider");
  return context;
}

export function LanguageToggle({ className }: { className?: string }) {
  const { lang, toggleLang } = useI18n();

  return (
    <button
      type="button"
      onClick={toggleLang}
      className={cn(
        "inline-flex h-6 items-center gap-1.5 rounded-sm border border-border-default bg-bg-base px-2 font-mono text-caption text-text-secondary shadow-inner-panel transition-colors hover:border-brand-emerald/40 hover:text-text-primary focus-visible:shadow-focus-ring focus-visible:outline-none",
        className
      )}
      aria-label={lang === "zh" ? "Switch to English" : "切换到中文"}
      title={lang === "zh" ? "Switch to English" : "切换到中文"}
    >
      <Languages className="h-3.5 w-3.5 text-brand-emerald-bright" />
      <span className={lang === "zh" ? "text-text-primary" : ""}>中</span>
      <span className="text-text-disabled">/</span>
      <span className={lang === "en" ? "text-text-primary" : ""}>EN</span>
    </button>
  );
}
