# Zeus 设计变更说明：Causa 保留 / 删除 / 新增

> 版本: 1.0 | 日期: 2026-04-30

## 一、从 Causa 保留的设计

### 1. 六类信号评估器
`spread_anomaly`, `basis_shift`, `momentum`, `regime_shift`, `inventory_shock`, `event_driven`

**原因**：评估器的统计基础扎实——协整检验、OU 半衰期、Hurst 指数、Z-score 标准化，经过学术验证的量化方法。问题不在评估器本身，而在评估器之上的编排和权重机制。保留评估器，重构上层。

### 2. 多供应商 LLM 抽象
registry + OpenAI/Anthropic/DeepSeek/xAI 适配器

**原因**：Causa 的 LLM 抽象层设计干净——统一接口、加密存储 API Key、DB 配置优先 + 环境变量回退。只需从 TypeScript 移植到 Python。

### 3. 评分三维度
优先级评分（Z-score + 半衰期 + ADF）、组合适配评分、保证金效率评分

**原因**：三个维度的划分合理——信号强度、持仓适配度、资金效率。问题在于权重硬编码（40/30/30），不在维度划分。Zeus 保留维度，把权重交给校准循环。

### 4. 风控模块
VaR/CVaR、压力测试、相关性矩阵

**原因**：标准量化金融方法，Causa 的实现（Cornish-Fisher 展开、历史极端日提取）已经够用。

### 5. 回测框架
vectorbt 引擎 + DoWhy 因果推断 + Walk-forward 验证

**原因**：Causa 最成熟的模块之一。vectorbt 性能好，DoWhy 的安慰剂检验（50 次模拟）提供因果验证能力，在同类系统中少见。完整保留。

### 6. 调度器健康追踪
连续失败计数、降级标记、并发执行防护

**原因**：circuit breaker（数据超 48 小时不触发下游）、防并发（running flag）、失败追踪（consecutiveFailures ≥ 3 标记降级）是生产环境必需的。Zeus 用 APScheduler 重写但保留这些机制。

### 7. SSE 实时推送

**原因**：交易场景下实时性是刚需。SSE 比 WebSocket 更简单，单向推送足够。

### 8. 前端页面结构和 UI 组件
Dashboard、Alerts、Positions、Recommendations、Strategies 等页面 + Drawer 详情面板、Badge 组件、筛选器

**原因**：前端 UI 已经比较完整，交互模式合理。Zeus 保留前端，只改数据源（从 TypeScript API 改为代理到 Python）。

### 9. 品种传导图
CommodityNode + RelationshipEdge（上下游、替代品、库存传导、国内外联动、成本驱动）

**原因**：传导图是 Causa 的核心概念之一，Zeus 不仅保留还要强化——对抗引擎的结构性反驳和持仓的传导图激活都依赖这个图。

### 10. 数据库 schema 基础
market_data、alerts、positions、recommendations、strategies、research、signal_track、sector_assessments、graph、industry_data 等 18 张表

**原因**：数据模型本身合理，Zeus 在此基础上新增 7 张表、修改 3 张表，而不是推翻重来。

---

## 二、从 Causa 删除/替代的设计

### 1. TypeScript 后端业务逻辑
Causa 的 Next.js API Routes 中的全部业务逻辑（信号检测、评分、预警生成、调度）

**原因**：业务逻辑分散在 TypeScript 和 Python 两个运行时是 Causa 最大的架构债务。信号检测、统计计算、评分这些核心逻辑用 TypeScript 写，但天然依赖 numpy/scipy/pandas/statsmodels 等 Python 生态库。Causa 不得不维护两套数据处理逻辑（TypeScript 做信号检测，Python 做回测），同样的统计计算写了两遍。Zeus 统一到 Python，消除分裂。

### 2. node-cron 调度器
替代为 APScheduler

**原因**：node-cron 跑在 Next.js 进程里，与前端渲染共享资源。重型信号检测任务可能影响前端响应。APScheduler 跑在独立的 Python 后端进程中，职责分离更清晰。

### 3. 硬编码监控列表
alerts/cron/route.ts 中的 145 对硬编码 CRON_WATCHLIST

**原因**：每次增删监控品种都要改代码、重新部署。Zeus 改为 watchlist 数据库表，支持运行时增删改，持仓品种自动加入。

### 4. 硬编码评分权重
scoring.ts 中的 base 30, z-score 权重 10, half-life 权重 15 和 ensemble.ts 中的 SIGNAL_WEIGHTS

**原因**：Causa 预测准确率的最大瓶颈。硬编码权重意味着系统无法从历史表现中学习。一个在黑色系表现好但在农产品表现差的信号类型，在两个板块用同样的权重不合理。Zeus 用校准循环替代，权重按 (信号类型, 板块, 市场状态) 三元组独立调整。

### 5. 线性管道编排
alerts/cron/route.ts（515 行）和 pipeline/orchestrator.ts（572 行）中的同步链式调用

**原因**：数据流严格串行，一个环节卡住整条链路停摆。无法灵活组合——有些信号可以跳过评分直接进预警，有些需要先过场景推演。Zeus 用 Redis Pub/Sub 事件总线替代，模块间解耦，可并行、可跳过、可分叉。

### 6. Weaviate 作为假设记忆的主存储

**原因**：不是删除 Weaviate，而是降低角色。Causa 把结构化数据（假设、市场状态）存在向量库里，但查询模式是精确匹配（按 ID、按类型），不是语义检索。Zeus 把结构化数据回归 PostgreSQL，Weaviate 只用于真正需要语义检索的场景（历史类比检索、新闻事件匹配）。

### 7. 前端 Drizzle ORM 直连数据库

**原因**：前端直连数据库意味着业务逻辑可以绕过后端 API 直接操作数据，数据一致性难以保证。Zeus 的前端只做 BFF（代理请求到 Python 后端），所有数据操作都经过后端 API。

---

## 三、Zeus 新增的设计

### 1. 校准循环（Calibration Loop）
`backend/app/services/calibration/` — tracker、hit_rate、weight_adjuster、decay_detector

**原因**：提升预测准确率最直接的机制。Causa 的权重是人工设定的，永远不变。但市场是变化的——一个在趋势市中有效的动量信号，在震荡市中可能是噪声。校准循环让系统从历史表现中学习：哪些信号在什么条件下有效，权重自动调整。衰减检测还能发现已失效的信号，避免系统在过时的信号上浪费置信度。

### 2. 对抗引擎（Adversarial Engine）
`backend/app/services/adversarial/` — null_hypothesis、historical_combo、structural_counter

**原因**：Causa 信任自己的信号——只要评分超阈值就触发预警。但在交易中假阳性的代价很高（错误开仓 → 亏损）。对抗引擎在信号进入评分前做三道统计检验：这个信号是不是噪声？历史上这种信号组合靠谱吗？有没有反向论据？三道检验都是可回测、可量化的，不是 LLM 辩论。

### 3. 混合决策 Alert Agent
`backend/app/services/alert_agent/` — router、classifier、llm_arbiter、narrative

**原因**：Causa 的预警分级完全是规则驱动的，遇到信号矛盾（动量看多 + 状态转换看空）、无历史先例的新模式时规则引擎无法处理。Zeus 的 Alert Agent 让 90% 的常规情况走确定性路径（快、可回测），只有 10% 的边缘案例才调用 LLM。LLM 输出被 Pydantic 模型约束为结构化 JSON，不允许自由发挥。

### 4. 置信度分层路由
`auto` / `notify` / `confirm` / `arbitrate` 四级

**原因**：Causa 没有人机协作机制——所有预警都是通知性质的，系统不会暂停等人。Zeus 根据系统置信度动态决定人的介入程度。这不是静态的"模式选择"，而是由系统表现自然调节的变量：系统越准，高置信度信号越多，人需要介入越少。

### 5. 品种级成本模型框架
`backend/app/services/cost_models/` — framework、cost_chain、snapshots、per-commodity configs

**原因**：Causa 有板块级的 conviction score（成本、库存、季节、利润四个因子），但没有品种级的完整成本链。对于产业客户和专业交易员来说，"这个品种的盈亏平衡价是多少"是最基本的问题。成本模型不仅是展示工具，其输出（利润率变化、盈亏平衡线突破）直接作为信号源接入检测框架。

### 6. 持仓驱动的系统行为变化
threshold_modifier、propagation_activator、risk_recalc、数据腐烂防护

**原因**：Causa 有持仓管理，但持仓数据不改变系统行为——有没有持仓，监控逻辑完全一样。Zeus 让持仓成为系统行为的驱动变量：持仓品种更敏感（阈值 × 0.8）、关联品种自动进入监控、新建议与持仓冲突时警告。系统从"通用扫描器"变成"围绕你的持仓定制的守卫"。

### 7. Redis Pub/Sub 事件总线
替代 Causa 的同步函数调用链

**原因**：模块解耦是 Zeus 架构的基础。事件总线让每个模块只关心自己订阅的事件，不需要知道上下游是谁。三个好处：(1) 模块可以并行执行；(2) 新模块可以即插即用（订阅已有事件）；(3) 事件持久化到 event_log 表，支持审计和重放。选 Redis 而非进程内 EventEmitter，是因为支持进程重启后恢复和未来多 worker 扩展。

### 8. 人工仲裁记录表
`human_decisions` — decision、confidence_override、reasoning

**原因**：Causa 没有记录人的决策。Zeus 记录每一次人工审批/拒绝/修改，两个用途：(1) 作为校准循环的额外输入，评估人机协作效果；(2) 长期积累后可以分析"人在什么情况下比系统判断更准"，指导置信度阈值调整。

### 9. 事件审计日志
`event_log` 表 + 死信队列

**原因**：Causa 的信号处理是黑盒——一个预警是怎么从原始数据一步步变成最终输出的，没有完整追踪链。Zeus 的每个事件都带 correlation_id，可以从 `market.update` 一路追踪到 `alert.created`，完整还原决策过程。死信队列确保失败的事件不会丢失。

---

## 四、变更总结

| 类型 | 数量 | 说明 |
|------|------|------|
| 保留 | 10 项 | 统计评估器、LLM 抽象、评分维度、风控、回测、调度健康、SSE、前端 UI、传导图、DB schema |
| 删除/替代 | 7 项 | TS 后端、node-cron、硬编码监控列表/权重、线性管道、Weaviate 过度使用、前端直连 DB |
| 新增 | 9 项 | 校准循环、对抗引擎、混合决策、置信度分层、成本模型、持仓驱动行为、事件总线、人工仲裁、审计日志 |

**设计哲学**：保留 Causa 中统计基础扎实的计算模块，删除架构层面的刚性和分裂，新增让系统能自我校准、自我质疑、与人协作的机制。
# 2026-05-08 — World Risk Map 模块

- 新增 `docs/WORLD_RISK_MAP.md`，明确世界风险地图的产品定位、分期技术方案和 `/api/world-map` 数据契约。
- 架构文档补充 World Risk Map 作为 Causal Web 之外的空间解释层。
- 执行计划升级为 v1.4，新增 Phase 9.5。

# 2026-05-08 — World Risk Map 自适应风险故事

- `/api/world-map` 增加 `story`、`adaptiveAlerts`、`evidence`、`counterEvidence`，让区域弹窗展示动态商品传导链。
- 增加 Commodity Lens：同一因素会按橡胶、原油、黑色、农产、农能联动生成不同解释路径。
- 前端 `/world-map` 改成地图主视觉，区域详情改为点击弹窗，不再常驻右侧挤占地图面积。

# 2026-05-08 — World Risk Map Phase B 真实地图层

- 前端地图从手写大陆轮廓升级为 `world-atlas` Natural Earth 国家边界，并使用 `d3-geo` Equal Earth 投影。
- 区域 polygon、热力圈、风险标签和同商品/同合约风险飞线统一由经纬度投影生成，视觉表达与真实地理位置对齐。
- MapLibre/deck.gl 调整为 Phase B.2，用于后续天气栅格、瓦片热力和大规模交互增强。

# 2026-05-09 — World Risk Map Phase B.1 轻动态交互

- `/world-map` 增加 30 秒自动轮询、实时/手动切换、最后更新时间和局部刷新，不再依赖整页 reload。
- 地图增加风险热力脉冲、风险变化闪环、风险 delta 标记和流动飞线，让运行态变化有明确视觉反馈。
- SVG 世界地图增加滚轮缩放、拖拽平移、按钮缩放和重置视图，在保持轻资源占用的前提下补齐地图基本交互。

# 2026-05-09 — World Risk Map Phase B.1.1 沉浸式 HUD

- `/world-map` 移除常规页面头部占位，标题、摘要、运行态统计、商品筛选和刷新控制改为地图上的玻璃态 HUD。
- 地图容器改为基于视口高度的主画布，避免统计卡片把地图压成普通内容区。
- 增加低透明扫描网格与更轻的底部提示条，保持 Shadowbroker 方向的科技态势屏观感，同时不改变后端数据契约。

# 2026-05-09 — World Risk Map Phase B.1.2 区域情报抽屉

- 区域详情从居中大弹窗改为桌面右侧情报抽屉、移动端底部情报抽屉，地图上下文保持可见。
- 情报抽屉增加区域档案头、风险评分、运行态指标、因果网络入口、动态预警、证据/反证和天气指标。
- 商品传导链从横向卡片改为纵向时间线，更适合窄面板阅读，也减少弹窗内容拥挤。

# 2026-05-09 — World Risk Map Phase B.1.3 可控风险图层

- 地图 HUD 新增可交互视觉图层开关，可独立控制天气、热力、飞线和地图标签。
- 新增轻量天气异常 halo，用降水距平和洪涝风险表达天气影响范围，为后续瓦片天气栅格打底。
- 关闭热力或标签后仍保留可点击风险节点，避免清理画面时失去区域交互能力。

# 2026-05-09 — World Risk Map Phase B.1.4 区域风险索引与聚焦

- 地图底部新增高风险区域索引，按当前商品筛选后的区域风险分排序，降低区域多时的查找成本。
- 点击索引项会选中区域、打开区域情报抽屉，并自动把地图平移/放大到目标区域。
- 地图节点点击也复用同一聚焦逻辑，保持地图交互、索引交互和情报抽屉状态一致。

# 2026-05-09 — World Risk Map Phase B.2.1 WebGL 图层准备层

- 新增风险密度图层，把区域风险分、天气异常和风险等级聚合为网格热力单元，为后续 deck.gl HeatmapLayer / TileLayer 准备稳定的数据形态。
- 风险密度图层接入现有视觉图层开关，保持天气、热力、飞线和标签的独立开关能力。
- 当前仍用轻量 SVG 渲染密度单元，避免在 MapLibre/deck.gl 完整接入前影响已稳定的地图交互链路。

# 2026-05-09 — World Risk Map Phase B.2.2 渲染模式护栏

- 顶部控制区新增“轻量 / 增强”渲染模式切换，默认继续使用稳定的 SVG 主渲染。
- 增强模式下展示 WebGL 准备面板，按 deck.gl 目标层统计 GeoJson 区域、Heatmap 密度、Arc 飞线和待接入天气瓦片。
- 该阶段只增加可见的渲染能力探测与回退入口，不替换现有地图交互，降低后续 MapLibre/deck.gl 接入风险。

# 2026-05-09 — World Risk Map Phase B.2.3 deck.gl 预览层

- 安装 `maplibre-gl` 与 `@deck.gl/*` 渲染依赖，为 Phase B.2 真正 WebGL 化建立构建链路。
- 增强模式下新增 `world-map-webgl-preview` 叠加层，用 deck.gl `PolygonLayer`、`ScatterplotLayer`、`ArcLayer` 复用现有区域、风险密度和飞线数据。
- WebGL 预览层禁用事件接管并保持 `pointer-events: none`，默认 SVG 地图仍负责拖拽、缩放、点击和详情抽屉。

# 2026-05-09 — World Risk Map Phase B.2.4 MapLibre 离线底图壳层

- 增强模式新增 `world-map-maplibre-basemap`，动态初始化 MapLibre canvas，避免默认 SVG 页面承担额外 WebGL 成本。
- MapLibre 使用本地 `world-atlas` 国家边界和当前风险区域 GeoJSON，不依赖外部瓦片、token 或第三方地图服务。
- 底图壳层保持 `pointer-events: none`，仅验证 MapLibre 运行链路和离线 source/layer 契约，现有地图交互仍由 SVG 负责。

# 2026-05-09 — World Risk Map Phase B.2.5 WebGL 视图同步

- 将 MapLibre 底图壳层和 deck.gl 预览层移入 SVG `viewBox` 坐标系内，通过同一个 `translate/scale` 变换跟随地图拖拽与缩放。
- WebGL 预览层继续保持 `pointer-events: none`，不接管节点点击、区域索引、详情抽屉或缩放控件。
- WebGL 准备面板新增“视图同步”状态，明确增强层已与 SVG 主地图共享视图变换。

# 2026-05-09 — World Risk Map Phase B.2.6 增强层图层联动

- deck.gl 预览层开始服从现有视觉图层开关：热力控制 PolygonLayer，密度控制 ScatterplotLayer，飞线控制 ArcLayer。
- MapLibre 离线底图保留国家边界作为增强模式底座，风险区域 fill/line 会跟随热力图层开关隐藏或恢复。
- WebGL 准备面板新增“图层联动”状态，显示当前启用的增强图层数量，方便排查 SVG 与增强层显示是否一致。

# 2026-05-09 — World Risk Map Phase B.2.7 增强模式阅读层

- 增强模式新增“增强阅读层”浮动面板，基于当前筛选后的区域数据生成主读区、跨区传导、证据密度和联动区域摘要。
- 跨区传导逻辑沉淀为 `RiskBridge`，同时服务 SVG 飞线和阅读摘要，避免视觉链路与文字说明各算一套。
- 面板只在增强模式展示，不改变默认轻量 SVG 模式，也不接管地图点击、缩放或详情弹窗。

# 2026-05-09 — World Risk Map Phase B.2.8 天气瓦片预览层

- 增强模式新增 deck.gl 天气 tile-like 栅格层，使用区域降水距平、洪涝风险和干旱风险生成局部天气压力网格。
- WebGL 预备面板的 “Tile天气” 从 planned 改为 ready 计数，并把图层联动口径扩展为天气、热力、密度、飞线 4 个增强图层。
- 天气瓦片继续使用现有天气图层开关，不改变默认 SVG 交互，也为后续 Open-Meteo / NASA POWER 栅格接入预留承载结构。

# 2026-05-09 — World Risk Map Phase B.2.9 天气/风险瓦片后端契约

- 后端新增 `GET /api/world-map/tiles`，支持 `layer=all|weather|risk` 与 `resolution=coarse|medium`，返回经纬度 tile polygon、强度、指标、数据质量和来源。
- 前端增强模式优先使用后端 weather/risk tile 数据；接口失败时保留上一版本地生成回退，避免世界地图因为瓦片服务异常整体不可用。
- 新增 world map tile 契约单测，覆盖天气/风险双层输出、polygon 结构、强度范围和天气层过滤。

# 2026-05-12 — World Risk Map Phase B.2.10 视口瓦片裁剪

- `/api/world-map/tiles` 新增 `min_lat/max_lat/min_lon/max_lon` 可选查询参数，用于按当前地图视口裁剪天气/风险瓦片。
- 前端地图缩放或拖拽后会 debounce 请求当前可视范围瓦片；缩放到 135% 以上自动切换 medium resolution，保持放大阅读时的细节密度。
- 全局区域快照仍保持完整，视口裁剪只影响 WebGL / tile 图层，避免大数据量时把不可见瓦片全部送到浏览器渲染。

# 2026-05-09 — World Risk Map Phase C.1 真实天气接入准备

- Open-Meteo 采集配置化，并把默认天气地点扩展到橡胶、原油、黑色、农产和农能区域。
- 新增 NASA POWER 日频 point API 客户端，输出统一的 `weather_precip_7d` / `weather_temp_max_7d` / `weather_temp_min_7d` 行，后续可沉淀历史 baseline。
- `/api/world-map` 优先融合 `industry_data` 最新天气行，驱动区域天气、天气 tile 来源和风险故事；缺数据时继续显式回退 `regional_baseline_seed`。

# 2026-05-09 — World Risk Map Phase C.2 历史季节 baseline

- NASA POWER 增加同日历窗口历史 baseline 采集，输出 `weather_baseline_precip_7d` 和 `weather_baseline_temp_mean_7d`。
- baseline 采集新增独立开关与年份/窗口配置，避免高频 ingest 默认重复拉取历史大窗口。
- 世界地图天气融合改为按站点区域作用域优先匹配，并按来源站点聚合，降低跨区域商品代码造成的天气污染。

# 2026-05-09 — World Risk Map Phase C.3 异常分位数与低频调度

- NASA POWER baseline 增加降水/温度历史分位数，世界地图天气风险评分开始吸收极端分位信息。
- 新增 `weather-baseline` 低频调度任务，默认关闭，避免高频行情 ingest 重复拉取历史窗口。
- 新增 NOAA CDO 与 AccuWeather 配置/数据源状态入口；AccuWeather 当前天气客户端接入 free ingest，NOAA 等 token 限额保护后再深接。

# 2026-05-10 — World Risk Map Phase C.4 NOAA/AccuWeather 深接

- NOAA CDO 新增 station mapping 客户端：按默认产区经纬度搜索 GHCND 站点，再拉取近 7 日 PRCP/TMAX/TMIN，输出统一天气行业数据。
- free ingest 接入 NOAA CDO，并为 NOAA/AccuWeather 增加每轮地点上限配置，保护免费额度和本地开发体验。
- World Risk Map 天气卡片新增当前气温、1 小时降水、湿度和风速字段；当前天气可增强可读性，但不会替代 NASA POWER 历史 baseline。

# 2026-05-10 — World Risk Map 玻璃态收敛与事件智能计划

- 世界风险地图移除重复“实时”状态提示，增强模式不再展示右侧 WebGL 预备和增强阅读两块信息卡。
- 左侧导航栏收起/展开按钮改为内嵌玻璃态侧边把手，并统一导航栏、地图 HUD、索引、标签和详情卡片的半透明毛玻璃质感。
- Event Intelligence Engine / 事件智能引擎正式列入 Phase 10，用于把外部信息动态组织为商品影响链，并与 Causal Web / World Risk Map 共用事件作用域。

# 2026-05-09 — Shell Navigation Phase 1

- 全局侧边栏升级为半透明玻璃态外壳，保留 Zeus 现有导航信息架构，不改业务页面和世界风险地图数据逻辑。
- 新增展开/收起状态、`localStorage` 偏好记忆、收起态图标导航、告警角标和运行态状态灯。
- 该阶段只处理全局导航容器；地图页默认沉浸模式、tooltip 增强和移动端抽屉导航留到后续阶段。

# 2026-05-09 — Shell Navigation Phase 2

- 侧边栏偏好升级为 `auto / collapsed / expanded` 三态；没有用户显式偏好时采用路由默认策略。
- `/world-map` 与 `/causal-web` 默认进入沉浸式收起导航，普通后台页面默认展开，避免大画布页面被导航压缩。
- 用户手动展开或收起后会保存显式偏好，后续页面继续尊重用户选择。

# 2026-05-09 — Shell Navigation Phase 3

- 收起态侧边栏新增自定义玻璃态提示层，鼠标悬停或键盘聚焦图标时显示导航名称。
- 告警图标提示同步展示当前告警角标，避免收起后只剩数字而无法理解上下文。
- 该阶段只增强收起态可读性，不改变路由、业务页面和世界风险地图数据逻辑。

# 2026-05-09 — Shell Navigation Phase 4

- 移动端不再常驻占宽侧边栏，改为顶部悬浮菜单按钮 + 左侧玻璃态抽屉导航。
- 抽屉内保留完整导航、告警角标和运行态状态，点击导航项或遮罩会自动关闭。
- 桌面端仍沿用 `auto / collapsed / expanded` 侧栏偏好，不改变世界风险地图、因果网络和其它业务页面数据逻辑。

# 2026-05-09 — Shell Navigation Phase 5

- 移动端抽屉升级为完整模态导航：打开时锁定页面滚动，关闭后恢复原焦点。
- 支持 `Esc` 关闭和 `Tab` 焦点限制，键盘用户不会误跳到抽屉背后的地图、图表或命令按钮。
- 监听桌面断点变化，窗口从移动宽度切回桌面时自动清理移动抽屉状态，避免残留遮罩影响大画布交互。

# 2026-05-10 — Event Intelligence Engine Phase 10.1

- 新增 `event_intelligence_items` 与 `event_impact_links`，把结构化新闻事件持久化为统一事件智能对象和商品/区域影响链。
- 新增 `services/event_intelligence`：首版 Commodity Lens 覆盖橡胶、原油、黑色、农产和有色，按天气、供应、物流、政策、库存、成本、宏观、地缘等机制生成候选链路。
- 新增 `/api/event-intelligence`、`/api/event-intelligence/impact-links` 与 `/api/event-intelligence/from-news/{news_event_id}`，事件影响判断默认进入 Shadow / review，高影响单源或低置信事件进入人工复核。
- 新闻事件写入后会同步生成事件智能对象，避免新新闻只停留在 `news_events` 表而没有 Phase 10 作用域。
- 新增 `/event-intelligence` 前端工作台，并同步侧边栏、命令面板和中英文文案，用于查看事件池、影响链、证据和反证。

# 2026-05-12 — Event Intelligence Engine Phase 10.2

- 新增 `services/event_intelligence/semantic.py`：通过统一 LLM registry 进行结构化语义抽取，输出实体、商品、机制、方向和多商品影响假设。
- resolver 支持把 LLM 语义假设与 Commodity Lens 规则链路合并，语义输出必须通过已登记商品、允许机制和方向枚举校验后才会入库。
- 新增 `/api/event-intelligence/from-news/{news_event_id}/semantic` 显式语义增强接口；默认新闻写入仍走规则 resolver，避免自动消耗 LLM 配额。
- 新增 `/api/event-intelligence/eval-cases` 与评估样例集，覆盖特朗普关税、航母/伊朗、橡胶天气、港口洪涝和生柴政策等场景。
- `/event-intelligence` 事件详情新增语义假设展示，显示 LLM 候选影响、模型和提示版本。

# 2026-05-12 — Event Intelligence Engine Phase 10.3

- 新增 `event_intelligence_audit_logs`，把事件智能语义增强、人工确认、拒绝和转人工复核动作写入独立审计表。
- 新增事件智能治理服务：人工决策会同步更新事件对象和所有影响链状态，并保留前后状态、操作者、备注和决策 payload。
- 高影响、单源、低置信或需要人工确认的事件智能对象会自动进入 `change_review_queue`；入队审计明确标记 `production_effect=none`。
- 人工确认、拒绝或回到 Shadow 后会关闭待复核项，并写入 `event_intelligence_review` 向量学习记录，支持后续回放与复盘。
- 新增 `/api/event-intelligence/{event_id}/decision` 与 `/api/event-intelligence/audit-logs`，用于事件智能确认/拒绝/复核和治理历史查询。
- `/event-intelligence` 详情页增加确认、拒绝、转人工复核操作按钮，前端动作通过 API 写入审计日志。
- 语义增强接口现在也会写入 `semantic_enhanced` 审计记录，记录模型、提示版本、语义置信度和假设数量。

# 2026-05-12 — Event Intelligence Engine Phase 10.3.2

- 新增 `/api/event-intelligence/impact-links/{link_id}` PATCH 接口，支持人工修订影响链的品种、区域、机制、方向、置信度、影响分、周期、证据和反证。
- 影响链修订会把事件与链路重新置为 `human_review`，写入 `impact_link.updated` 审计，并重新进入 `change_review_queue`；审计 payload 明确标记 `production_effect=none`。
- `/event-intelligence` 详情页新增“修改链路”表单，保存前只提交真实变更字段，并提示修改后需要重新复核。

# 2026-05-12 — Event Intelligence Engine Phase 10.3.3

- `/event-intelligence` 详情页新增治理时间线，按事件读取 `/api/event-intelligence/audit-logs` 并展示规则解析、语义增强、进入治理队列、人工决策和影响链修改。
- 审计时间线展示状态流转、操作者、备注、变更字段、复核原因、语义假设数量和生产影响，帮助人工复核时直接看到“为什么这条链变成现在这样”。
- 前端决策和影响链编辑成功后会把返回的审计记录即时插入时间线，减少操作后必须刷新页面才能看到留痕的问题。

# 2026-05-12 — Governance Queue Workbench Phase 10.3.4

- 新增 `/api/governance/reviews` 与 `/api/governance/reviews/{review_id}/decision`，统一读取和处理 `change_review_queue`。
- 通用治理动作支持批准、驳回、转影子复核和标记已审查，都会在 `proposed_change.review_decision` 中保留操作者、时间、备注和 `production_effect=none`。
- 事件智能来源的队列项在批准 / 驳回 / 转影子复核时会走事件智能专用决策服务，同步事件对象、影响链、审计日志和学习记录；其它模块仍只关闭队列项，不越权写业务参数。
- 新增 `/governance` 前端工作台，并同步侧边栏、命令面板和中英文文案，便于跨模块查看待复核建议、入队原因和候选影响链。

# 2026-05-12 — Event Intelligence Engine Phase 10.4

- `/api/causal-web` 新增 `symbol` 与 `region` 作用域参数，并把 `event_intelligence_items` 渲染为事件源、`event_impact_links` 渲染为影响假设节点。
- `/api/world-map` 开始聚合事件智能对象和影响链，区域运行态新增 `eventIntelligence`，风险分、证据、动态预警和 `eventIds` 共用 `event_intelligence:{event_id}` 作用域。
- `/world-map` 区域档案展示事件智能运行态，打开因果网络时携带同一 `symbol + region`，减少地图和因果网络各自解释同一事件的问题。
- 新增 Causal Web 与 World Risk Map 回归测试，覆盖事件智能源节点、链路边、区域证据和同一事件作用域。

# 2026-05-12 — Event Intelligence Engine Phase 10.5

- Causal Web 与 World Risk Map 聚合层新增事件智能展示去重，折叠媒体转载标题、`Feature:` 前缀和来源后缀导致的重复事件。
- 去重只影响页面阅读密度、区域运行态计数和影响链入口，不删除原始事件智能对象，保留审计与来源追踪。
- 新增回归测试，覆盖事件智能标题归一化和同一事件只展示一次的行为。

# 2026-05-12 — Event Intelligence Engine Phase 10.6

- 事件智能源节点和影响假设节点新增双语语义字段，详情面板可直接展示品种、机制、证据、反证、方向、置信度、影响分和周期。
- Causal Web 节点详情新增事件智能阅读块：源事件展示关联影响链，影响假设展示回指源事件，并保留边方向与置信度。
- 这一步优先解决“看得懂为什么关联”的问题，路径高亮和证据展开作为后续增强继续推进。

# 2026-05-12 — Event Intelligence Engine Phase 10.7

- World Risk Map API 新增 `symbol`、`mechanism`、`source` 筛选作用域，快照与瓦片接口使用同一过滤逻辑。
- 区域返回新增 `mechanisms` 与 `sourceKinds`，前端可以明确展示当前区域由哪些机制和事件源驱动。
- `/world-map` 顶部筛选从单一品类按钮升级为事件源 / 品种 / 机制三行紧凑控件，筛选后地图、热力瓦片、高风险索引和区域详情同步更新。

# 2026-05-12 — Event Intelligence Engine Phase 10.8

- `/api/causal-web` 事件智能节点新增结构化支持证据与反证线索，前端可直接展开阅读，不再依赖叙事文本中的拼接片段。
- Causal Web 详情面板新增“聚焦此路径”，点击事件智能源事件或影响假设后，画布会收束到相关影响链并显示路径聚焦状态。
- 事件源聚合保留合并后的证据去重，避免同源转载折叠后丢失可审计证据。

# 2026-05-12 — Event Intelligence Engine Phase 10.9

- 新增事件智能质量门服务，按证据、反证、来源可信、新鲜度、作用域、治理状态和影响链质量实时评估事件可用性。
- 新增 `/api/event-intelligence/quality`，返回 `blocked / review / shadow_ready / decision_grade`、事件级问题和影响链级问题。
- `/event-intelligence` 页面新增质量评分、阻断原因和影响链质量状态，避免人工确认时只依赖置信度和影响分。

# 2026-05-12 — Event Intelligence Engine Phase 10.10

- Causal Web 事件智能节点新增质量门状态、质量分和问题摘要；`review/blocked` 可阅读但不会显示为 verified/alert-ready。
- World Risk Map 区域新增 `eventQuality` 摘要，展示事件智能的通过、复核、阻断和总数。
- 地图风险分与事件智能传导故事按质量门降权：未通过质量门的事件保留为阅读复核材料，但不放大自动风险。

# 2026-05-13 — World Risk Map Phase D.1 证据健康层

- `/api/world-map` 区域新增 `evidenceHealth`，汇总支持证据、反证、来源数、新鲜来源、来源可信度、数据新鲜度和证据密度。
- `/world-map` 增强阅读层从单纯“证据数量”升级为“密度 / 可信度 / 新鲜度”三维摘要，区域档案新增证据健康卡片和低覆盖提示。
- 新增 World Risk Map 回归断言，覆盖运行态证据健康升高与 baseline 场景不误判为实时新鲜。

# 2026-05-13 — World Risk Map Phase D.2 风险动量层

- `/api/world-map` 区域新增 `riskMomentum`，输出升温 / 降温 / 稳定、动量强度、推导原因、主驱动和最新触发时间。
- `/world-map` 增强阅读层、高风险索引、地图区域标签和区域档案新增风险动量读取入口；升温 / 降温区域会显示轻量 SVG 脉冲。
- 新增 World Risk Map 回归断言，覆盖运行态风险升温、低质量事件质量门阻断后的降温，以及纯 baseline 稳定场景。

# 2026-05-13 — World Risk Map Phase D.3 风险链阅读动线

- `/world-map` 区域档案新增“链路总览”，四格展示风险动量、证据健康、事件质量门和因果网络作用域。
- 区域详情卡片顺序调整为动量、证据健康、质量门、因果网络入口，和链路总览保持一致。
- 该阶段仅调整前端阅读组织和中英文文案，不改变后端风险分、事件质量门或生产阈值。

# 2026-05-13 — World Risk Map Phase D.4 推荐动作入口

- `/world-map` 区域档案新增“推荐动作”卡片，根据质量门、证据健康、风险动量和事件作用域给出下一步导航。
- 待复核 / 阻断事件优先进入事件智能，证据薄弱优先进入新闻事件，升温且有直接作用域优先进入关联因果网络。
- 该阶段只增加前端工作流入口和中英文文案，不写入治理状态，不改变风险分或生产阈值。

# 2026-05-13 — World Risk Map Phase D.5 上下文跳转

- 世界风险地图推荐动作链接统一携带 `source=world-map`、`symbol`、`region`，可定位事件智能对象时额外携带 `event`。
- `/event-intelligence` 支持从地图上下文打开后自动选中事件或按品种筛选，并显示“来自世界风险地图”的作用域提示。
- `/news` 支持同一上下文打开后按品种筛选新闻事件，保留区域提示，减少跨页面后的重复过滤。

# 2026-05-13 — Event Intelligence Phase 10.16 反向地图联动

- `/event-intelligence` 影响链新增“打开世界风险地图”入口，按单条影响链的品种、区域、机制、来源和事件作用域打开地图。
- `/news` 的事件智能链摘要新增地图小入口，支持从新闻证据直接回到对应区域风险视图。
- `/world-map` 支持 URL 初始筛选与区域聚焦，进入页面后会按 `symbol/source/mechanism/region` 自动请求作用域数据并打开区域档案。

# 2026-05-13 — World Risk Map Phase 10.17 事件作用域可见化

- `/world-map` 从事件智能或新闻链路进入时，区域档案新增“当前事件作用域”卡片。
- 该卡片展示事件短 ID、命中证据、证据权重、质量门分数和该事件是否直接存在于区域 `causalScope`。
- 未命中时会明确提示只是同品种 / 同机制观察，不把筛选结果误写成已验证因果传导。
