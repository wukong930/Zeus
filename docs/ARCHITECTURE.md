# Zeus 系统架构设计报告

> 版本: 1.0 | 日期: 2026-04-30 | 状态: 已评审

## 1. 项目背景

Zeus 是 Causa（商品期货套利预警系统）的下一代演进。Causa 已实现 50+ 品种的多维信号检测、套利推荐、回测验证和风控层，但存在以下架构瓶颈：

- **线性管道**：数据采集 → 信号检测 → 评分 → 预警，刚性链路无法灵活组合
- **硬编码智能**：评分权重、监控列表、检测阈值全部写死在代码中
- **无对抗验证**：系统信任自身信号，缺乏统计层面的反向检验
- **后端分裂**：业务逻辑分散在 TypeScript 和 Python 两个运行时

Zeus 的目标是构建一个模块化、事件驱动、自校准的期货交易智能平台。

## 2. 设计哲学

**核心原则一：确定性系统做主链路决策，LLM 做边缘案例推理和叙事生成。**

- 规则引擎 + 可校准评分模型处理 90%+ 的信号检测、评分和预警分级
- LLM Agent 仅在信号矛盾、新模式发现、叙事生成、场景推演时介入
- 所有决策节点可回测、可校准、可追溯

**不让 LLM 做裁判，让它做侦探和翻译。**

**核心原则二（自我学习治理守则）：自动学习的输出永远不直接修改主链路决策。**

任何由系统自动产生的规则变更建议（无论来自统计校准、ML 模型、还是 LLM 反思）必须经过：

```
LLM/统计输出 → 写入 change_review_queue 表（仅"假设"，非"结论"）
            → 人工审阅
            → Shadow Mode 验证 30 天
            → 验证通过且性能优于现状
            → 人工批准
            → 才能进入生产
```

代码层面强制：任何修改 `signal_calibration` / `commodity_config` / 阈值参数的写入操作必须经过 `governance.review_required` 守卫。

**这是底线，不是建议。** 没有这条守则，自动学习在交易系统里是慢性自杀。有了它，自动学习才是缓慢但稳定的进步。

## 3. 技术栈

| 层级 | 技术选型 | 说明 |
|------|---------|------|
| 前端 | Next.js 16 + React 19 + Tailwind 4 | 仅做 BFF（SSR + API 代理） |
| 后端 | Python FastAPI | 全部业务逻辑、调度、信号、评分、校准 |
| 事件总线 | Redis Pub/Sub | 模块解耦，支持未来多实例部署 |
| 数据库 | PostgreSQL 16 + SQLAlchemy | 主存储 + 向量检索（pgvector），Alembic 管理迁移 |
| 向量检索 | **pgvector**（默认） | 历史类比 / 新闻去重 / 假设召回，HNSW 索引 |
| 向量库（备选） | Weaviate 1.28（**P3 评估升级**） | 仅当向量数 > 100w 或需多租户/模块化时升级，详见 §6.22 |
| 调度器 | APScheduler | 替代 Causa 的 node-cron |
| LLM | OpenAI / Anthropic / DeepSeek（多供应商） | 结构化 JSON 输出，Pydantic 校验 |
| 部署 | Docker Compose | Postgres + Redis + Weaviate + Backend + Frontend |

## 4. 系统架构总览

```
┌──────────────────────────────────────────────────────────────┐
│  FRONTEND — Next.js 16 (BFF: SSR + API proxy to Python)     │
│  Dashboard │ Alerts │ Positions │ World Map │ Cost Models   │
└─────────────────────────┬────────────────────────────────────┘
                          │ REST + SSE (proxied)
┌─────────────────────────┴────────────────────────────────────┐
│  PYTHON BACKEND — FastAPI                                    │
│  API Layer │ Scheduler │ WebSocket/SSE │ LLM Integration     │
└─────────────────────────┬────────────────────────────────────┘
                          │
┌─────────────────────────┴────────────────────────────────────┐
│  EVENT BUS — Redis Pub/Sub                                   │
│  market.update │ signal.detected │ signal.scored │           │
│  alert.created │ position.changed │ calibration.updated      │
└──┬────────┬────────┬────────┬────────┬────────┬──────────────┘
   │        │        │        │        │        │
┌──┴──┐ ┌──┴──┐ ┌──┴──┐ ┌──┴──┐ ┌──┴──┐ ┌──┴──────────┐
│ ETL │ │Signal│ │Adver│ │Score│ │Alert│ │  Scenario   │
│Layer│ │Detect│ │sarial│ │Engine│ │Agent│ │  Simulator  │
└─────┘ └─────┘ └─────┘ └─────┘ └─────┘ └─────────────┘
   │        │        │        │        │        │
┌──┴────────┴────────┴────────┴────────┴────────┴──────────────┐
│  PLATFORM — Calibration │ Risk │ Propagation Graph │ Backtest │
├──────────────────────────────────────────────────────────────┤
│  SECTOR — Ferrous │ Energy │ Agriculture │ Nonferrous │ PM   │
├──────────────────────────────────────────────────────────────┤
│  COMMODITY — per-symbol params, cost chains, thresholds      │
└──────────────────────────────────────────────────────────────┘
```

### 4.1 地理风险视图（World Risk Map）

World Risk Map 是 Causal Web 之外的空间解释层，位置为 `frontend/src/app/world-map` 与 `backend/app/api/world_map.py`。

- 前端首版使用 React + SVG 绘制 2.5D 世界风险地图，避免在业务契约未稳定前引入过重 GIS 渲染依赖。
- 后端 `/api/world-map` 聚合 `alerts`、`news_events`、`signal_track`、`positions`，按区域输出风险评分、天气 baseline、运行态计数和 Causal Web 作用域。
- 后续渲染层升级为 MapLibre GL JS + deck.gl，3D Globe 作为 three.js / React Three Fiber 增强模式。
- 与 Causal Web 的联动通过 `region_id + symbols + event_ids + time_window` 传递，未发现直接关联时必须显式展示空态。

### 4.2 事件智能引擎（Event Intelligence Engine）

Event Intelligence Engine 是 World Risk Map 与 Causal Web 之上的语义组织层，目标是把外部事件动态转成商品影响链，而不是把新闻、天气、社媒和航运信息做成固定展示卡片。

核心输入：

- 结构化新闻事件、社媒/公告文本、天气异常、航运/港口扰动、库存/持仓变化、行情异常。
- 商品属性：产区、成本链、物流节点、政策敏感度、替代关系、历史事件样例。

核心输出：

- `event_id`：可追溯的统一事件。
- `entities`：人物、国家/地区、港口、企业、商品、合约和政策关键词。
- `mechanisms`：供给、需求、物流、政策、库存、成本、风险偏好、地缘冲突。
- `impact_links`：`event -> mechanism -> symbol/region`，带方向、置信度、证据、反证和新鲜度。

Phase 10.1 已落地的运行态边界：

- 数据模型：`event_intelligence_items` 存储规范化事件，`event_impact_links` 存储事件到商品/区域/机制的候选影响链。
- 服务层：`services/event_intelligence` 先用 Commodity Lens + 规则 resolver 处理结构化新闻事件，输出可审计的证据、反证、来源可信度和新鲜度。
- 新闻管线：`record_and_publish_news_event` 写入新闻后同步生成事件智能对象，未确认新闻仍进入人工复核而不是生产预警。
- API：`/api/event-intelligence` 查询事件智能对象，`/api/event-intelligence/impact-links` 查询影响链，`POST /api/event-intelligence/from-news/{news_event_id}` 从现有新闻事件生成影响链。
- 前端：`/event-intelligence` 作为最小工作台，展示事件池、影响链、证据/反证和人工复核状态。

Phase 10.2 已落地的语义增强边界：

- LLM 语义层：`services/event_intelligence/semantic.py` 使用统一 LLM registry 生成结构化 JSON，提取实体、商品、机制、方向、证据/反证和多商品影响假设。
- 规则护栏：语义输出只接受已登记商品和允许机制，resolver 将 LLM 假设与 Commodity Lens 规则结果合并、去重并保留可解释字段。
- 显式触发：`POST /api/event-intelligence/from-news/{news_event_id}/semantic` 可用 LLM 重算/增强某条新闻事件；默认新闻入库仍走规则 resolver，避免自动消耗 LLM 配额。
- 评估样例：`/api/event-intelligence/eval-cases` 暴露特朗普关税、航母/伊朗、橡胶天气、港口洪涝和生柴政策等样例，用于后续回归评估。
- 前端：`/event-intelligence` 在事件详情中展示语义假设、模型和提示版本。

Phase 10.3 已落地的治理边界：

- 审计模型：`event_intelligence_audit_logs` 独立记录语义增强、人工确认、拒绝和转人工复核动作，不再只依赖 `source_payload` 留痕。
- 复核队列：高影响、单源、低置信或人工确认事件会进入 `change_review_queue`，`proposed_change` 保留事件作用域、原因、top links 和 `production_effect=none`。
- 决策 API：`POST /api/event-intelligence/{event_id}/decision` 支持 `confirm`、`reject`、`request_review`、`shadow_review`，同步更新事件与影响链状态。
- 链路修订：`PATCH /api/event-intelligence/impact-links/{link_id}` 支持人工修改品种、区域、机制、方向、置信度、影响分、证据和反证；修改后事件与链路回到 `human_review`，并重新进入治理队列。
- 学习记录：人工决策后会生成 `vector_chunks.chunk_type=event_intelligence_review`，用于后续回放、检索和复盘；这不会直接改生产阈值。
- 审计查询：`GET /api/event-intelligence/audit-logs` 可按事件或动作查看治理历史。
- 前端：`/event-intelligence` 详情页提供确认、拒绝、转人工复核和影响链编辑操作，所有动作写入审计日志；页面同时展示治理时间线，包含状态流转、操作者、备注、变更字段、复核原因和 `production_effect`。
- 统一队列：`GET /api/governance/reviews` 与 `POST /api/governance/reviews/{review_id}/decision` 提供跨模块 `change_review_queue` 工作台接口；通用队列动作只记录审核结论，事件智能队列项会转交事件智能专用决策服务同步事件与影响链状态。
- 前端工作台：`/governance` 展示所有待复核建议、结构化载荷、候选影响链和治理动作，作为自动学习与事件智能进入生产前的统一闸口。

Phase 10.4 已落地的联动边界：

- Causal Web：`/api/causal-web` 支持 `symbol` 与 `region` 查询参数，并把事件智能对象作为 source 节点、影响链作为 thesis 节点渲染。
- World Risk Map：`/api/world-map` 聚合 `event_intelligence_items` 与 `event_impact_links`，区域运行态新增 `eventIntelligence`，风险分、证据、动态预警和 `eventIds` 都消费同一作用域。
- 前端：世界风险地图区域档案展示事件智能运行态，因果网络入口携带 `symbol + region`，减少地图与因果图对同一事件解释不一致的问题。

Phase 10.5 已落地的阅读准确性边界：

- Causal Web 与 World Risk Map 在聚合层对事件智能对象做展示去重，合并同一事件的媒体转载、标题前缀和来源后缀差异。
- 去重只影响视图和区域运行态计数，不删除 `event_intelligence_items` 原始行，保留审计、来源追踪和后续治理能力。

Phase 10.6 已落地的 Causal Web 阅读边界：

- 事件智能源节点和影响假设节点开始输出双语 `label/narrative/tags`，把影响品种、作用机制、证据、反证、方向、置信度、影响分和周期写进节点语义层。
- Causal Web 点击事件智能节点时展示专属阅读块：源事件显示已关联影响链，影响假设回指源事件，并保留边的方向与置信度。
- 当前仍是详情面板内的解释增强；更强的路径聚焦、证据展开和多跳链路高亮留给后续 Phase 10.x。

Phase 10.7 已落地的 World Risk Map 作用域边界：

- `/api/world-map` 与 `/api/world-map/tiles` 支持 `symbol`、`mechanism`、`source` 查询参数，后端按同一作用域返回区域、风险分、证据、动态预警和瓦片。
- 返回结构新增 `filters`、`region.mechanisms`、`region.sourceKinds`，前端可以直接渲染事件源、品种和影响机制筛选，而不是只在本地按品类隐藏卡片。
- 前端筛选后会重新请求快照和瓦片，风险索引、地图热区、区域档案和打开 Causal Web 的链接保持一致作用域。
- `/api/world-map/tiles` 额外支持 `min_lat/max_lat/min_lon/max_lon` 视口裁剪；前端缩放/拖拽后只刷新当前可视范围瓦片，完整区域快照不被裁剪。

Phase 10.8 已落地的 Causal Web 路径阅读边界：

- `/api/causal-web` 的事件智能节点新增结构化 `evidence` 与 `counterEvidence`，保留双语文本和来源类型，前端不再从 narrative 中解析证据。
- Causal Web 点击事件智能源事件或影响假设后，可在详情面板展开支持证据 / 反证线索，并通过“路径聚焦”把画布收束到对应事件智能影响链。
- 路径聚焦只改变阅读视图和高亮范围，不改变事件智能治理状态、评分阈值或生产告警行为。

Phase 10.9 已落地的事件质量门边界：

- `/api/event-intelligence/quality` 实时评估事件智能质量，综合证据、反证、来源可信、新鲜度、作用域、影响链可用性和治理状态。
- 质量状态分为 `blocked`、`review`、`shadow_ready`、`decision_grade`：blocked/review 不应进入后续自动链路，shadow_ready 只允许 Shadow/阅读层使用，decision_grade 需要已确认且质量分达标。
- `/event-intelligence` 页面展示事件级质量评分、阻断原因和影响链级质量门，帮助人工确认前先看到缺证据、弱来源或无可用链路的问题。

Phase 10.10 已落地的质量门联动边界：

- Causal Web 节点携带 `qualityStatus`、`qualityScore`、`qualityIssues`，低质量事件仍可阅读追溯，但 `review/blocked` 不会被渲染为 verified 或 alert-ready 链路。
- World Risk Map 区域携带 `eventQuality` 摘要，并在区域档案中展示事件智能通过、复核、阻断和总量。
- 地图风险分对事件智能贡献做质量加权：`decision_grade` 全量参与，`shadow_ready` 只作为阅读/Shadow 信号，`review/blocked` 不放大自动风险。

Phase 10.11 已落地的 World Risk Map 证据健康边界：

- `/api/world-map` 区域新增 `evidenceHealth`，把支持证据、反证、来源数量、新鲜来源、来源可信度、数据新鲜度和证据密度汇总为前端可直接阅读的指标。
- 证据健康只服务阅读和复核，不改变事件智能质量门、生产阈值或自动告警行为。
- `/world-map` 增强阅读层和区域档案显示证据健康，帮助用户先判断“这块风险由多少可靠证据支撑”，再进入 Causal Web 追溯链路。

Phase 10.12 已落地的 World Risk Map 风险动量边界：

- `/api/world-map` 区域新增 `riskMomentum`，根据高等级预警、新闻、信号、持仓、事件智能质量门、天气新鲜度和证据健康推导 `rising/easing/steady`。
- 风险动量是阅读层指标，不是新的交易信号；低质量事件被质量门阻断时可显示降温，不会扩大地图风险分或生产阈值。
- `/world-map` 在增强阅读层、高风险索引、地图区域标签和区域档案中显示动量，并用轻量 SVG 脉冲标记正在升温或降温的区域。

Phase 10.13 已落地的 World Risk Map 风险链阅读动线：

- `/world-map` 区域档案新增“链路总览”，把 `riskMomentum`、`evidenceHealth`、`eventQuality` 和 `causalScope` 放入同一四步阅读路径。
- 该阶段只调整前端阅读组织和中英文文案，不改变 `/api/world-map` 数据契约、事件质量门、风险分或 Causal Web 作用域。
- 详情卡片顺序固定为动量、证据健康、质量门、因果网络入口，减少用户在多个信息卡之间自行拼接链路的问题。

Phase 10.14 已落地的 World Risk Map 推荐动作入口：

- `/world-map` 区域档案新增“推荐动作”，根据质量门、证据健康、风险动量和 `causalScope` 选择先复核、先补证据、追溯升温链、追溯因果链或保持观察。
- 推荐动作只改变前端导航入口，分别指向 `/event-intelligence`、`/news` 或区域 `causalScope.causalWebUrl`，不写入业务状态，也不改变风险分。
- 该入口用于把读数转成下一步操作，避免用户看完动量、证据和质量门后仍不知道应该先去哪一页。

Phase 10.15 已落地的 World Risk Map 上下文跳转：

- 推荐动作链接统一携带 `source=world-map`、`symbol`、`region`，可定位到事件智能对象时额外携带 `event`。
- `/event-intelligence` 打开后会优先选中对应事件；没有精确事件时按品种筛选队列，并显示世界风险地图来源上下文。
- `/news` 打开后会按同一品种筛选新闻事件，并保留区域上下文提示，减少用户跨页面后重新过滤的成本。
- 该阶段只同步阅读作用域，不写业务状态，也不改变事件质量门、地图风险分或生产预警。

Phase 10.16 已落地的 Event Intelligence 反向地图联动：

- `/event-intelligence` 影响链新增世界风险地图入口，按影响链的 `symbol`、`region_id`、`mechanism`、事件智能来源和 `event_id` 构造地图作用域。
- `/news` 的事件智能链摘要也可从单条影响链打开地图，方便从新闻证据回到空间风险视图。
- `/world-map` 支持读取 URL 中的 `symbol/source/mechanism/region`，进入页面后自动按作用域请求快照和瓦片，并聚焦对应区域档案。
- 反向联动仍只改变前端阅读与筛选，不写入事件智能治理状态，也不改变地图风险分。

Phase 10.17 已落地的 World Risk Map 事件作用域可见化：

- `/world-map` 读取 URL 中的 `event` 后，会在区域档案中显示“当前事件作用域”卡片。
- 该卡片从区域证据列表中匹配 `event_intelligence:{event_id}`，展示命中证据、证据权重、质量门分数和 `causalScope` 是否直接包含该事件。
- 若当前区域没有直接证据，页面会明确提示仅保留同品种 / 同机制观察，避免把普通筛选误解为已验证传导。
- 该阶段只增强阅读透明度，不改变事件质量门、风险分、治理状态或生产预警。

治理约束：

- 引擎判断默认只进入 Shadow / review，不直接修改生产阈值或自动发交易指令。
- 单源高影响事件必须人工确认。
- Causal Web 与 World Risk Map 必须消费同一 `event_id` 作用域，避免同一事件在不同页面被解释成不同链路。

## 5. 主链路事件流

```
Scheduler 触发 ETL
  → market.update (Redis) → 信号检测（6 个评估器并行）
    → signal.detected → 对抗引擎（3 项统计检验）
      → 通过 → 评分引擎（校准权重）
        → signal.scored → Alert Agent（路由器）
          → 90%: 确定性分级 → alert.created
          → 10%: LLM 仲裁 → alert.created
            → alert.created → 通知 + 校准追踪 + 前端 SSE
```

## 6. 模块详细设计

### 6.1 事件总线 — Redis Pub/Sub

**位置**: `backend/app/core/events.py`

事件包装器：
```python
@dataclass
class ZeusEvent:
    id: str              # UUID
    channel: str         # e.g. "signal.detected"
    timestamp: datetime
    source: str          # 发布模块名
    payload: dict
    correlation_id: str  # 全链路追踪 ID
```

设计要点：
- 每个模块通过 async Redis listener 订阅相关频道
- 失败的 handler 事件写入 `event_log` 表（死信队列），支持重试
- 相比进程内 EventEmitter：支持进程重启后恢复、未来多 worker 扩展

### 6.2 ETL 层

**位置**: `backend/app/services/etl/`

- 复用 Causa 的 tushare/akshare 数据采集逻辑（已有 Python 实现）
- APScheduler 触发采集任务 → 发布 `market.update` 事件
- 产业数据（库存、现货、基差）独立调度周期
- 数据质量检查：缺失率 > 20% 时标记降级，不触发下游信号

**Point-in-time 数据完整性**（Causa 用 `onConflictDoUpdate` 覆盖更新，Zeus 重写）：
- 写入策略改为 append-only：所有数据行新增 `vintage_at` 字段（数据进入系统的时刻）
- 查询提供两种视图：
  - `*_latest`：默认视图，返回每个 (id, date) 的最新版本（用于实时决策）
  - `*_pit(as_of)`：PIT 视图，返回截至某时刻可见的版本（用于回测、校准回放）
- 修订型数据（PMI、库存、CFTC、基差）必须 PIT，每次拉取生成新 vintage 行
- 高频价格数据（OHLCV）保留覆盖更新以节省空间，但 close/settle 加时间戳追踪
- 影响范围：回测、校准循环、对抗引擎的历史组合检验全部基于 PIT 数据

### 6.3 信号检测

**位置**: `backend/app/services/signals/`

- 移植 Causa 的 6 个 TypeScript 评估器为 Python 等价实现
- 监控列表从 `watchlist` 数据库表读取（替代硬编码的 145 对）
- 检测阈值从 `commodity_config` 表读取，持仓品种阈值乘以 0.8（更敏感）
- 所有评估器通过 `asyncio.gather` 并行执行

7 个评估器（Causa 的 6 个 → Zeus 拆分 `event_driven` 为 2 个）：
1. `spread_anomaly` — Z-score 价差偏离
2. `basis_shift` — 基差变动
3. `momentum` — 动量信号
4. `regime_shift` — 市场状态转换
5. `inventory_shock` — 库存冲击
6. `price_gap` — 价格跳空 + 成交量异常（Causa 原 `event_driven` 的纯技术面逻辑）
7. `news_event` — 新闻事件驱动（**新增**，依赖 6.13 新闻事件管线）

`event_driven` 拆分原因：Causa 的实现实际上是技术面（gap + volume），不是真正的事件驱动。Zeus 把"事件"还给真正的新闻事件，技术面逻辑独立为 `price_gap`。

### 6.4 对抗引擎（新增）

**位置**: `backend/app/services/adversarial/`

在任何预警发布前，执行三项统计对抗检验：

1. **零假设检验** (`null_hypothesis.py`)：Bootstrap 置换检验（1000 次迭代），验证信号是否可与随机噪声区分
2. **历史组合检验** (`historical_combo.py`)：对当前信号组合计算哈希，查询 `signal_calibration` 表中的历史命中率
3. **结构性反驳** (`structural_counter.py`)：遍历传导图寻找反向论据（反向传导路径、季节性反转、替代品压力）

处理规则：
- 三项全部失败 → 信号被抑制
- 部分失败 → 置信度惩罚（乘以 0.7）
- 全部通过 → 正常流转

**冷启动策略**（前 90 天 warmup period）：
- 系统上线初期，`signal_calibration` 表无历史数据
- 历史组合检验切换到"informational mode"：执行检查并记录结果，但**不阻塞信号、不施加置信度惩罚**
- 零假设检验和结构性反驳从第一天就生效（不依赖历史）
- 90 天后或样本量满足条件（每个 signal_combination_hash 累积 ≥ 20 个 outcome）后，历史组合检验切换为"enforcing mode"
- 切换时机由调度任务每日检查，可手动覆盖

**计算优化**：
- 1000 次 Bootstrap 置换太重，改为预计算策略：每个 (signal_type, category) 在每日 ETL 后预计算零分布的统计量分布并缓存
- 实时检测时只需查表对比，O(1) 复杂度
- 预计算结果存 `null_distribution_cache` 表，每日更新

**信号组合哈希的脆弱性**：
- 精确哈希在新增/删除评估器时全部失效
- 改为模糊匹配：哈希基于排序后的 `(signal_type_set, category, regime)`，新增评估器时旧哈希仍可匹配子集
- 历史组合查询使用 Jaccard 相似度（≥ 0.7 视为匹配）

### 6.5 评分引擎

**位置**: `backend/app/services/scoring/`

- 移植 Causa 的优先级/组合适配/保证金效率评分
- 权重从 `signal_calibration` 表读取（由校准循环每日更新），不再硬编码
- 公式：`score = Σ(signal_weight_i × evaluator_score_i)`

### 6.6 Alert Agent（混合决策）

**位置**: `backend/app/services/alert_agent/`

路由逻辑：
- **确定性路径**（90%+）：信号评分超阈值 + 对抗通过 → 规则分级 + 模板叙事
- **LLM 路径**（触发条件）：
  - 集成信号方向矛盾（如动量看多 + 状态转换看空）
  - 置信度落在 40-65% 模糊区间且信号数 ≥ 3
  - 信号组合哈希在 `signal_calibration` 中无历史记录
  - 传导链跨越 3+ 板块

LLM 输出约束：Pydantic 模型强制结构化 JSON，包含 `classification`、`narrative`、`risk_items`、`manual_check_items`。输出无效时回退到确定性路径。

置信度分层路由：
- \>85% → `auto`（自动执行，事后通知）
- 60-85% → `notify`（自动执行，实时通知，人可否决）
- <60% → `confirm`（暂停，等人确认）
- 信号冲突 → `arbitrate`（展示矛盾，等人仲裁）

### 6.7 校准循环（新增）

**位置**: `backend/app/services/calibration/`

这是系统持续提升准确率的核心机制。Zeus 采用**冷启动**策略——不复用 Causa 历史数据（auto-evaluate 规则不一致、outcome-tracker 存在 bug 数据可能不完整、缺 forward_return 字段），从零开始积累。

#### 6.7.1 Ground truth 定义（每个评估器独立）

Causa 的 auto-evaluate 对所有信号统一用"≥20% 回归算 hit"，对均值回归类合理，对趋势类完全错误。Zeus 每个评估器自带 `evaluate_outcome(signal, market_data, horizon)` 方法：

| 评估器 | 命中规则 | 评估窗口 |
|--------|---------|---------|
| `spread_anomaly` | Z-score 在窗口内回归到 ±0.5 内 | 5 / 10 / 20 天 |
| `basis_shift` | 基差变动方向在窗口内被价格证实 | 3 / 7 / 14 天 |
| `momentum` | 前向收益与信号方向一致 | 1 / 5 / 20 天 |
| `regime_shift` | 后续 N 天波动率/趋势特征匹配预测 regime | 10 / 30 天 |
| `inventory_shock` | 现货价格在窗口内出现预测方向变动 | 5 / 15 / 30 天 |
| `price_gap` | 跳空方向延续 vs 回补 | 1 / 3 / 5 天 |
| `news_event` | 标的品种在窗口内出现预测方向变动 | 1 / 5 / 10 天 |

`signal_track` 表新增 `forward_return_1d / 5d / 20d` 字段，存储多窗口前向收益（不只是二元 hit/miss）。

#### 6.7.2 影子追踪器（避免幸存者偏差）

每个信号触发的瞬间启动影子追踪——不依赖用户是否采纳：
- 调度器每日扫描达到评估窗口的 pending 信号
- 自动调用对应评估器的 `evaluate_outcome` 方法
- 记录前向收益到 `signal_track`，标记 outcome
- 用户实际持仓的结果作为**补充质量数据**（评估"人采纳后的实际表现"），不替代影子追踪

#### 6.7.3 Regime 分类与检测

校准按 (signal_type, category, regime) 三元组——regime 必须显式定义：

**分类（先用粗粒度 4 状态）**：
- `trend_up_low_vol`：趋势上行 + 低波动（ADX > 25 + ATR 百分位 < 50）
- `trend_down_low_vol`：趋势下行 + 低波动
- `range_high_vol`：震荡 + 高波动（ADX < 20 + ATR 百分位 > 70）
- `range_low_vol`：震荡 + 低波动

**检测方法**：
- 主方法：ADX + ATR 百分位规则（确定性、可解释、可回测）
- 备选：HMM（hmmlearn 库）作为对比 baseline，不进主链路
- regime 在每日 ETL 后按板块计算并写入 `regime_state` 表
- 信号触发时关联当日 regime；regime 切换日的信号特殊标记（避免污染统计）

#### 6.7.4 真贝叶斯更新（Beta 先验）

原设计 `new_weight = base_weight × (0.5 + hit_rate)` 不是贝叶斯（不考虑样本量）。改为：

```
posterior_mean = (α₀ + hits) / (α₀ + β₀ + total)
effective_weight = base_weight × (posterior_mean / 0.5)
```

参数：
- `α₀ = β₀ = 4`（弱先验，相当于"虚拟"看到 4 次命中 + 4 次未命中）
- 样本量 < 10 时权重接近 base_weight（先验主导）
- 样本量 > 100 时权重接近观测命中率
- 权重范围约束：[0.1, 2.0]
- 冷启动期权重全部为 base_weight（先验主导，符合预期）

#### 6.7.5 衰减检测（变点检测）

不是简单的"命中率 < 0.3 持续 30 天"，而是基于 CUSUM 或 Bayesian online change point detection：
- 检测命中率序列的统计显著性变化
- 触发衰减后权重 × 0.5，并标记 `decay_detected = true`
- 前端展示衰减警告，等待人工评审是否永久禁用该信号

#### 6.7.6 置信度阈值的二级校准

`auto / notify / confirm / arbitrate` 阈值（85% / 60%）本身需要校准——避免 Zeus 也变成"硬编码"。

机制：
- 每月统计 `预测置信度 vs 实际命中率` 的 reliability diagram
- 用 isotonic regression 或 Platt scaling 学习单调映射
- 系统报告校准曲线，**人工评审后才更新阈值**（不自动调整，避免反馈循环不稳定）

#### 6.7.7 人工反馈

`human_decisions` 表的审批/拒绝/修改记录作为校准的额外维度：
- 用于评估"人 + 系统"的协作命中率 vs 系统单独
- 长期数据可分析"人在什么类型信号上比系统判断更准"
- 不直接修改信号权重，但作为置信度阈值校准的输入

### 6.8 持仓管理

**位置**: `backend/app/services/positions/`

- 最小录入：品种、方向、手数、均价、开仓日期（5 个字段）
- 持仓品种检测阈值 × 0.8（更敏感）
- 传导图自动激活：持仓橡胶 → 自动监控天胶产区天气、轮胎开工率、合成胶价差
- 组合风控：VaR、相关性暴露、板块集中度，持仓变动时重算
- 数据腐烂防护：N 天未更新 → 提醒 → 降级为无持仓模式

### 6.9 成本模型框架

**位置**: `backend/app/services/cost_models/`

每个品种的完整成本链：原料 → 加工 → 物流 → 税费 → 单位成本 → 毛利 → 盈亏平衡

#### 6.9.1 数据来源策略（暂未购买付费源）

第一阶段采用**降级方案**——卓创/SMM/Mysteel 等付费源在 Phase 7 进入实际开发时再评估是否采购：
- 公开信息源：交易所原料价格、统计局月度数据、企业财报、行业协会公开报告
- LLM 辅助提取：定期从行业新闻中抽取成本数据点（炼焦煤现货均价、加工费区间等）
- 手动维护：低频参数（人工水电、税率）放运营后台手动配置
- 数据质量较粗，盈亏平衡价误差可能在 ±5%——前端必须明示数据来源和不确定度
- Phase 7 阶段评估降级方案的信号质量，决定是否采购付费源

#### 6.9.2 数据更新频率

| 组件 | 频率 | 来源（免费阶段） |
|------|------|------|
| 原料价格 | 日频 | 交易所数据 |
| 加工费 | 月/季度 | 行业报告 + LLM 提取 |
| 运费 | 周频 | BDI / 公路运价指数 |
| 人工/水电 | 季度/年度 | 手动输入 |
| 税费 | 事件驱动 | 政策变动 |

#### 6.9.3 成本曲线分位数（不是单一数字）

真正决定价格地板的是**边际成本**——高成本产能的成本，不是平均成本。Zeus 输出成本曲线分位数：
- P25（低成本产能）/ P50（中位数）/ P75（高成本产能）/ P90（边际产能）
- 盈亏平衡线用 P75 或 P90，不是平均值
- 价格跌破 P50 触发"中位数压力"，跌破 P75 触发"边际产能减产预期"

#### 6.9.4 信号集成

成本模型输出接入信号系统：
- 利润率 < -5% 持续 2 周 → 触发"产能收缩预期"信号
- 利润率由负转正 → 触发"复产预期"信号
- 价格触及 P75/P90 分位数 → 触发"成本支撑/压力"信号

优先品种：黑色系（JM→J→RB 高炉链路，Phase 7a）+ 橡胶（NR→RU 全链路，Phase 7b）

### 6.10 板块模型

**位置**: `backend/app/services/sectors/`

三层模型体系：
- **平台层**：通用信号检测框架、评分引擎、预警管道（所有品种共享）
- **板块层**：板块专用模型
  - 黑色系：高炉利润 = 螺纹钢价 - 1.6×铁矿 - 0.5×焦炭 - 加工费
  - 能化：裂解价差、炼厂利润（后续阶段）
  - 农产品：压榨利润、种植周期（后续阶段）
- **品种层**：品种级参数 + 成本模型（`commodity_config` 表）

### 6.11 场景推演

**位置**: `backend/app/services/scenarios/`

- 独立重型模块，不在主预警链路上
- 触发方式：用户手动、Alert Agent 请求（置信度模糊时）、特定条件自动触发
- Monte Carlo 价格路径模拟
- What-if 假设检验
- 人机协作：推演结果需人工审核反馈

### 6.12 合约换月模块（新增）

**位置**: `backend/app/services/contracts/`

Causa 把 contractMonth 硬编码为 'main'，Zeus 必须正式处理换月——这是期货系统区别于股票系统的核心问题。

**数据模型**：
- `contract_metadata` 表：symbol, exchange, contract_month, expiry_date, is_main, main_until, volume, open_interest, updated_at
- 主力合约规则：成交量 + 持仓量综合排名第一，连续 3 天领先则切换主力

**价格序列拼接**：
- `continuous_main_adjusted`：换月时按价差调整，用于回测和趋势信号（避免假跳空）
- `continuous_main_raw`：不调整，反映实际换月成本，用于成本类信号
- `actual_contract`：单合约真实价格，用于交割相关分析

**信号检测特殊处理**：
- 换月窗口期（前后 5 天）：`spread_anomaly` / `basis_shift` 类信号自动降级
- 主力切换日：信号源标记 `regime_transition = true`，校准统计中归到独立桶或排除
- 临近交割（< 15 天）：流动性预警，新建议自动转移到次月合约

### 6.13 新闻事件管线（新增）

**位置**: `backend/app/services/news/`

Causa 的 GDELT 集成只用于"预警发出后展示新闻"，不进决策。Zeus 把"事件"真正还给事件——`news_event` 评估器从这个管线取数。

**数据源**：
- 中文：财联社快讯（电报源）、上海钢联资讯、卓创资讯（公开部分）、新浪财经期货频道
- 英文：GDELT（已接入，扩展使用）、Reuters Commodities、Bloomberg Commodity Wire（如可获取）
- 政策源：交易所公告（API）、海关总署公告、发改委政策

**处理流程**：
```
原始新闻 → 去重（标题哈希 + 语义相似度）
       → LLM 结构化抽取（事件类型 / 影响品种 / 方向 / 严重度 / 时效性）
       → 写入 news_events 表
       → 发布 news.event 事件到事件总线
       → news_event 评估器订阅，结合品种传导图生成信号
```

**LLM 抽取的输出结构**（Pydantic 强制）：
- `event_type`：政策 / 供给 / 需求 / 库存 / 地缘 / 天气 / 突发事件
- `affected_symbols`：受影响品种（含传导图衍生的次级品种）
- `direction`：bullish / bearish / mixed / unclear
- `severity`：1-5 级
- `time_horizon`：immediate / short / medium / long
- `confidence`：LLM 自评抽取置信度

**质量控制**：
- 同事件多源交叉验证：≥ 2 个独立源覆盖才进入评估
- 严重度 ≥ 3 才生成预警，< 3 仅记录
- 假新闻防御：对单源未交叉验证的高严重度事件强制人工确认

### 6.14 LLM 成本控制（新增）

Causa 当前 LLM 调用 < 5 次/天且无缓存，Zeus 的 Alert Agent + News Pipeline + Scenario + Research Agent 可能让这个数字增长 10-50 倍。必须做成本控制。

**位置**: `backend/app/services/llm/`（扩展现有模块）

**机制**：

1. **Anthropic prompt caching**：系统提示和工具定义使用 cache_control，命中时输入成本降低 90%
2. **结果缓存**（`llm_cache` 表）：
   - 缓存键：`hash(provider + model + system + user_message)`
   - TTL：24 小时（可按场景配置）
   - 命中率指标暴露到监控
3. **预算上限**：
   - `llm_budgets` 表配置每月预算（按模块：alert_agent / news / scenario / research）
   - 超 80% 预算告警，超 100% 自动降级到确定性路径
4. **调用日志**（`llm_usage_log` 表）：
   - 每次调用记录：模块、模型、输入/输出 token、成本估算、是否缓存命中
   - 月度成本归因报表

**降级策略**：
- LLM 调用失败 / 超时（> 30 秒）/ 输出无效 JSON → 自动回退到确定性路径
- 长期不可用 → 报警 + 整个 LLM 路径切到 bypass mode

### 6.15 Shadow Mode / A/B 框架（新增）

**位置**: `backend/app/services/shadow/`

校准算法、对抗引擎规则、新评估器——这些核心逻辑变更前必须验证不会让系统变差。

**机制**：
- `shadow_runs` 表：记录每个 shadow 配置（algorithm_version, config_diff, started_at, ended_at）
- 新逻辑订阅相同事件，跑出"假信号"写入 `shadow_signals` 表，**不发预警**
- 每日生成对比报告：
  - 信号数量差异
  - 命中率差异（30 天滑窗）
  - 关键样本案例（生产路径触发但 shadow 没触发，反之亦然）
- 30-90 天后人工评审决定是否切换为生产逻辑

**适用场景**：
- 校准公式变更
- 对抗引擎规则调整
- 新评估器上线
- 阈值参数批量调整

### 6.16 预警去重与限流（新增）

**位置**: `backend/app/services/alert_agent/dedup.py`

避免预警疲劳——这是产品体验的关键，不只是技术问题。

**规则**：
- 同 (品种, 方向, 评估器) 在 N 小时内只发一次（默认 N=12），除非严重度升级
- 同信号组合在 24 小时内只发一次
- 用户级别的过滤偏好：仅持仓相关、仅 L3 建议、仅特定板块
- 每日预警上限（默认 50），超限后只保留 top-K 高分

**实现**：
- `alert_dedup_cache` 表：(symbol, direction, evaluator, last_emitted_at, last_severity)
- 发预警前先查缓存，命中则比较严重度
- 缓存按品种 TTL 自动清理

### 6.17 推荐级归因系统（新增）

**位置**: `backend/app/services/learning/recommendation_attribution.py`

Zeus 的校准循环是**信号级别**的，但用户做的是 Goal B（按推荐交易）——推荐才是真正要学习的对象。信号级校准只看"信号方向是否被验证"，推荐级归因看"按这条建议交易实际赚钱了吗"。

**数据模型**（`recommendations` 表新增字段）：
- `entry_price` / `stop_loss` / `take_profit` — 推荐时定的价位
- `actual_entry` / `actual_exit` / `actual_exit_reason` — 实际执行（hit_target / hit_stop / time_exit / manual_close）
- `pnl_realized` — 实际盈亏（按手数 + 合约乘数计算）
- `mae` (Maximum Adverse Excursion) — 持仓期间最大不利偏移
- `mfe` (Maximum Favorable Excursion) — 持仓期间最大有利偏移
- `holding_period_days`

**自动归因报表**（每月生成 + 前端可查）：

按维度切片胜率和期望收益：
- 信号组合 × 胜率 × 期望收益 × 样本量
- Regime × 胜率
- 板块 × 胜率
- 季节（月份）× 胜率
- 持仓时长 × 胜率
- 入场时段（开盘/盘中/收盘前）× 胜率

风控参数评估：
- Stop loss 设置评估：MAE 分布看止损是太紧还是太松（如果 P50 MAE 是 1%，止损设 0.8% 就太紧）
- Take profit 评估：MFE 分布看止盈是否过早（如果 80% 推荐 MFE > target，target 太低）
- 持仓时长分布：哪个时长区间的胜率最高

**关键约束**：归因系统**只产生报表**，不自动调整任何参数。改不改止损、止盈由你决定。

### 6.18 用户反馈学习（新增）

**位置**: `backend/app/services/learning/user_feedback.py`

每次系统给信号或推荐时，**强制采集你的判断**——这是单用户系统能拿到的最高质量数据。

**采集机制**（`user_feedback` 表）：
- 每个信号/推荐发出时附一个简短表单：
  - 你同意系统判断吗？（agree / disagree / uncertain）
  - 不同意的理由（自由文本，可空）
  - 你会按这个建议交易吗？（will_trade / will_not_trade / partial）
- 不强制填写，但前端在用户未填写时持续提醒
- 用户的判断**本身不影响信号是否触发或权重**，只用作学习数据

**协同分析报表**（季度生成）：
- 你和系统判断不一致时，谁对的次数多？（按信号类型切片）
- 你的判断在什么场景下比系统更准？
- 系统在什么场景下比你更准？
- 输出：建议哪些类型的信号可以"信你"、哪些可以"信系统"

**集成到 Alert Agent**：
- 系统识别出"这类信号你过去判断更准"时，预警附加提示："此类信号你历史上判断准确率 70%，建议慎重审视"
- 这是软性引导，不是硬性规则

**关键约束**：用户反馈数据**不直接修改信号权重**。如果某个信号你长期不同意，输出到 `change_review_queue` 让你决定是否调整规则，而不是系统自动降权。

### 6.19 Concept Drift 监控（新增）

**位置**: `backend/app/services/learning/drift_monitor.py`

不是学习新规则，是**监测当前市场是否还像系统校准时的市场**。当市场结构性变化（regime 切换、流动性变化、相关性矩阵变化）时主动告警，让你知道"系统的判断现在可能不可靠"。

**监测指标**：

1. **特征分布漂移**（PSI / KL divergence）：
   - 关键特征：波动率、价差水平、基差、成交量、持仓量
   - 当前 30 天分布 vs 训练数据 90 天分布
   - PSI > 0.25 → 显著漂移告警

2. **相关性结构漂移**：
   - 板块内品种相关性矩阵的 Frobenius 距离
   - 历史相关性 vs 当前相关性
   - 突变即告警（如黑色系内部相关性骤降）

3. **信号命中率突变**：
   - 滚动 30 天命中率 vs 90 天基线
   - 显著差异（z-score > 2）→ 告警

4. **Regime 频繁切换**：
   - 正常情况 regime 切换月均 < 2 次
   - 高频切换说明市场无清晰主线 → 系统判断置信度普遍降低

**响应机制**：
- 漂移告警**只警告**，不自动调整
- 前端 Dashboard 顶部显示"Drift Alert"指示器
- 推送通知：建议本周谨慎按系统信号交易
- 人工评估后可手动启动新一轮校准（重新计算权重，但保留历史样本）

**为什么不自动调整**：自动调整 + 漂移检测会形成反馈循环——市场只是短期异常，系统永久性改了权重，下个月反弹时反应迟钝。**漂移期人优于机器，是常识。**

### 6.20 LLM 反思 Agent（新增，严守约束）

**位置**: `backend/app/services/learning/reflection_agent.py`

LLM 真正擅长的是**模式识别和假设生成**——读历史数据找出人没注意的关联。但这恰恰是它最容易翻车的地方（幻觉 + 过拟合）。所以本模块的设计哲学是：**让 LLM 做研究员，不让它做决策者**。

**调度**：每月一次（不是每日，避免过度拟合短期噪声）。

**输入**：
- 上月所有信号 + 触发上下文（regime、行情、新闻）
- 上月所有推荐 + 实际结果（来自 6.17 归因系统）
- 用户反馈数据（来自 6.18）
- Concept Drift 状态（来自 6.19）

**任务**：
- 识别表现异常的信号类型（明显高于或低于先验）
- 寻找规则层面没编码的关联（如"周一开盘的 momentum 信号胜率明显低"）
- 假设当前 regime 下哪些评估器/参数不适用

**输出（强制结构化 Pydantic）**：

```python
class LearningHypothesis(BaseModel):
    hypothesis: str  # 假设描述
    supporting_evidence: list[str]  # 数据证据
    proposed_change: str | None  # 建议的规则修改（可为空）
    confidence: float  # LLM 自评（0-1）
    counterevidence_considered: list[str]  # LLM 自己想到的反证
    sample_size: int  # 假设依据的样本数
```

**强制约束**（这是 6.20 设计的核心）：

1. **永远不修改任何运行参数**——所有输出写入 `learning_hypotheses` 表，标记为 `status='proposed'`
2. **强制反证**——LLM 必须自己列出至少 2 个反证或替代解释（防过拟合）
3. **样本量门槛**——`sample_size < 30` 的假设直接打 `weak_evidence` 标签
4. **生命周期**：
   ```
   proposed (LLM 提出)
   → reviewed (人工评审，approve / reject / refine)
   → shadow_testing (Shadow Mode 验证 30 天)
   → validated (验证通过)
   → applied (人工最终批准后才进生产)
   ```
5. **任何 status != applied 的假设不影响主链路**

**前端**：每月生成"假设报告"页面，列出本月所有假设 + 状态。你审阅、决定、推进。

**最低要求实现**：
- 输入数据脱敏（不传交易金额，只传相对收益和命中标记）
- LLM 输出过滤：含"立即"、"自动"、"无需审核"等词的假设直接拒绝
- 月度成本上限：单次反思调用 token 上限（避免 LLM 失控烧钱）

### 6.21 回测正确性约束（新增）

**位置**: `backend/app/services/backtest/`

回测的存在意义是**预测系统在未见过数据上的表现**——但回测在金融领域是出名的"易出伪精度"。Zeus 不仅要做回测，更要在回测框架里硬编码 4 项防御机制，否则所有 Sharpe 都是镜花水月。

#### 6.21.1 PIT 校准权重回放（必修）

**问题**：Phase 1 做了 PIT 市场数据，但**校准权重的 PIT 没有保证**。如果 2026-05 的回测复现 2025-09 的信号但用 2026-05 的权重——系统"知道"哪些信号在未来会被证明有效，回测漂亮但毫无意义。

**改造**：
- `signal_calibration` 表新增 `effective_from` / `effective_to` 字段
- 每次校准更新时插入新行（不覆盖），形成权重时间序列
- `backtest/calibration_replay.py`：回测时按时点切片读取历史权重
- 回测元数据强制记录 `calibration_strategy`：`pit`（默认）/ `frozen`（用回测开始日权重，用于诊断）/ `current`（用当前权重，**仅用于 quick-check，结果不可信**）

#### 6.21.2 多重比较保护（必修）

**问题**：试 100 个策略组合，5 个会因纯运气达到 p < 0.05。这是金融定量最经典的死法。

**改造**：所有策略筛选必须经过多重比较检验。`backtest/multiple_testing.py` 实现：

1. **Deflated Sharpe Ratio**（Bailey & Lopez de Prado 2014）
   - 输入：策略 Sharpe + 试过的策略数 + 收益率分布矩 / 偏度 / 峰度
   - 输出：调整后 Sharpe + 显著性
   - 任何单策略输出必须同时给出 raw Sharpe 和 deflated Sharpe
2. **Bonferroni / Benjamini-Hochberg FDR**
   - 多策略横向比较时强制使用
   - 控制族错误率（FWER）或错误发现率（FDR）
3. **Strategy registry**（`strategy_runs` 表）
   - 记录每次回测：策略哈希、参数、数据范围、运行时间、运行人
   - **同一策略空间内总试验数**作为 deflated Sharpe 的输入
   - 防止"我换了一个参数就当成新实验"的自欺

**强制约束**：策略上线（进入生产 watchlist）前必须 Deflated Sharpe > 1.0 且 deflated p-value < 0.05。**raw Sharpe 不作为单一上线门槛**。

#### 6.21.3 滑点模型分档（必修）

**问题**：现有"成本模型：手续费、滑点、保证金成本"暗示滑点是常数。这对大宗商品**严重低估实际成本**。

**改造**：滑点是函数：
```
slippage_bps = base_slippage(symbol, contract_tier) 
             × volatility_multiplier(rolling_atr)
             × liquidity_multiplier(order_size / avg_volume)
             × time_of_day_multiplier(session)
```

`slippage_models` 表配置：

| 维度 | 取值 | 滑点系数 |
|------|------|----------|
| `contract_tier` | main / second / third | 1.0 / 2.5 / 8.0 |
| `volatility` | 低/中/高（按 ATR 百分位） | 0.7 / 1.0 / 1.8 |
| `liquidity` | < 1% / 1-5% / 5%+ ADV | 1.0 / 1.4 / 2.5 |
| `time_of_day` | 主交易时段 / 开盘 15min / 收盘 15min / 夜盘 | 1.0 / 1.5 / 1.4 / 1.2 |

每个品种、每个合约月份独立标定基准滑点（`base_slippage`），数据来源：Phase 7a 成本模型阶段顺便采集的成交量/深度数据。

**特殊场景**：
- 临近交割 < 15 天：滑点 × 3，且新建议自动转移到次月合约
- 涨跌停板：默认无法成交（除非在板上挂单）

#### 6.21.4 Live vs Backtest 背离监控（必修）

**问题**：策略上线后，怎么判断真的失效了 vs 只是连续运气差？没有这套机制就只能拍脑袋。

**改造**：`backtest/live_divergence.py` 实现：

1. **Tracking error**：用实盘成交数据"回放"重建一个理论回测曲线 → 与真实曲线对比，差异说明执行问题（滑点低估、时段偏差、订单类型差异等）
2. **Live vs Backtest Sharpe 偏离检验**：
   - 输入：回测 Sharpe + 标准差 + 当前实盘 Sharpe + 样本量
   - 检验：当前实盘 Sharpe 是否落在 95% 置信区间外
   - 落外 → 标记 `strategy_decay`，写入 `change_review_queue`
3. **回归测试**：每月跑一次"如果用今天的算法，能否复现历史回测结果"，差异 > 5% 触发警告（说明算法已悄悄漂移）

**与 Phase 3 衰减检测的关系**：Phase 3 的 `decay_detector` 是**信号级**的衰减；本节是**策略级**的衰减。两者独立运作，但都通过 `change_review_queue` 走人工审核。

#### 6.21.5 应修但不强制的几项

下列改进放在 Phase 8.5 实施时一并完成：

- **Walk-forward 参数硬性规范**：默认 3 年训练 / 3 月测试 / 1 月步长，rolling window。所有策略必须用此默认值，否则结果不可比
- **Regime profile 分解**：每个回测输出按 regime 切片的 Sharpe / 胜率 / 最大回撤 / 样本量
- **路径相关指标**：Underwater duration、Pain ratio、Recovery factor、CVaR(95%) 实际值、MAE/MFE 分布（与 Phase 6 推荐归因用同一指标体系）
- **Survivorship bias 处理**：`commodity_history` 表记录每个品种的"曾经活跃"时间窗，回测必须基于该宇宙
- **执行延迟分布**：用户配置延迟分布（不是常数），订单实际成交价 = 信号生成后 N 秒的市价
- **订单类型与部分成交**：支持 limit / stop / market 三种 + 按当根 K 线成交量按比例填充

#### 6.21.6 实现优先级映射

| 项 | Phase | 强制 |
|----|-------|------|
| PIT 校准权重回放 | 8.5 | ✓ |
| Deflated Sharpe + FDR | 8.5 | ✓ |
| 滑点分档模型 | 8.5（基础） / 7a 顺带采集深度数据 | ✓ |
| Live vs Backtest 背离 | 8.5 | ✓ |
| Walk-forward 规范 | 8.5 | ✓ |
| Regime profile | 8.5 | 应 |
| 路径相关指标 | 8.5 | 应 |
| Survivorship 处理 | 8.5 | 应 |
| 延迟分布 / 订单类型 | 后续 | 可 |

### 6.22 向量检索（pgvector 默认 / Weaviate 评估升级）（新增）

**位置**: `backend/app/services/vector_search/`

#### 6.22.1 决策：默认用 PostgreSQL + pgvector，Weaviate 标记为 P3 评估升级

**为什么不用 Weaviate**（Causa 用了，Zeus 砍掉）：

- Zeus 是单用户系统，向量量级 < 100k（10w 条新闻 × 1024 维 ≈ 400MB）
- pgvector 在这个规模性能完全够用（HNSW 索引 < 50ms QPS）
- 少一个服务 = 少一组监控、备份、升级负担
- Weaviate 的强项（GraphQL、模块化、多租户）你都用不上
- 数据和 Postgres 的其他表在同一事务里，一致性更好

**真升级 Weaviate 的临界点**：
- 向量数 > 100w
- 需要 Weaviate 模块化生态（如 ref2vec / generative）
- 多租户

第一年不太可能到这个规模。Phase 9 之后定期评估。

#### 6.22.2 用例（必须先操作化定义）

**用例 A：历史类比检索**
- 输入：当前预警的 (signal_combination + regime + 板块 + narrative_text)
- 输出：top-K 历史类似预警 + 各自实际 outcome
- 用途：Alert Agent 决策时附带历史类比；Notebook 快速回顾

**用例 B：新闻事件去重 + 关联**
- 输入：新到达的新闻文本
- 输出：(a) 是否与近 24h 已收新闻语义重复（去重）；(b) 与历史同类事件的相似度
- 用途：news 管线去重 + LLM 抽取时给出"前次类似事件结果"作为上下文

**用例 C：假设库快速召回**
- 输入：当前市场状态描述
- 输出：相关假设（来自 `learning_hypotheses` 和 Notebook）
- 用途：Notebook 边写边推荐相关假设

**禁止用例**：
- 不要用向量库做精确匹配（用主键查询）
- 不要存储数值结构化数据（如品种价格）
- 不要存 LLM 的 free-form 输出未经审核

#### 6.22.3 技术细节

**Embedding 模型**：
- 主选：**Voyage-3**（中文期货语料质量优于 OpenAI text-embedding-3-small）
- 备选：BGE-M3（开源，可本地部署，零成本）
- 维度：1024
- 升级策略：双版本并存 30 天 → Shadow Mode 评测 → 切换

**索引**：
- HNSW（pgvector 0.5+），m=16 / ef_construction=64 / ef_search=40
- 按 (chunk_type, sector, date_range) 建复合 B-tree 用于 metadata 预过滤

**混合检索**（必须）：
```
final_score = α × cosine_sim + β × bm25_score + γ × time_decay
```
- α=0.6, β=0.3, γ=0.1（默认权重，可按用例调整）
- BM25 对品种代码/政策关键词检索强于 vector
- time_decay = exp(-age_days / half_life)，half_life 按事件类型差异：
  - 政策事件 180d / 季节性事件 365d / 突发事件 30d / 假设记忆 永久（half_life=∞）

**质量门**（防 LLM 幻觉污染）：
- 每条向量记录附 `quality_status` 字段：`unverified` / `human_reviewed` / `validated`
- 检索时按状态加权：unverified × 0.5 / reviewed × 1.0 / validated × 1.2
- LLM 反思 Agent（Phase 9）的输出默认 `unverified`，只有走完 `change_review_queue` 才升级

**评测框架**：
- `vector_eval_set` 表存 50 条手工标注的 query → relevant_doc 对
- 每月跑一次 NDCG@10 / Recall@10
- 模型/参数变更时通过 Phase 9 Shadow Mode 对比 → 评测通过才切换

#### 6.22.4 冷启动

向量库前 3-6 个月几乎没有可用数据（与校准、对抗引擎同样问题）。明确预期：
- 用例 A（历史类比）：前 6 个月无效，前端展示"积累中（17/100）"
- 用例 B（新闻去重）：从 Phase 4.5 上线即可用（去重不需要历史，只需要近 24h）
- 用例 C（假设召回）：从 Notebook（Phase 6）开始可用，但前期假设少召回价值有限

#### 6.22.5 实现优先级

| 项 | Phase | 优先 |
|----|-------|------|
| pgvector + 基础检索 | Phase 4.5（新闻去重） | P1 |
| 混合检索（BM25 + vector + 时间衰减） | Phase 4.5 | P1 |
| 质量门 + status 字段 | Phase 9（LLM 反思 Agent 落地后） | P1 |
| 评测框架 | Phase 9 | P2 |
| Voyage-3 vs BGE-M3 选型对比 | Phase 4.5 实施时 | P2 |
| Weaviate 升级评估 | Phase 9 之后定期 | P3 |

## 7. 数据模型

### 7.1 新增表

**核心模块表**：

| 表名 | 用途 | 关键字段 |
|------|------|---------|
| `watchlist` | DB 驱动的监控列表 | symbol1, symbol2, category, custom_thresholds(jsonb) |
| `signal_calibration` | 校准权重 | signal_type, regime, rolling_hit_rate, effective_weight, alpha_prior, beta_prior |
| `adversarial_results` | 对抗检验结果 | null_hypothesis_pvalue, historical_combo_hit_rate, passed |
| `commodity_config` | 品种参数 | symbol, sector, cost_formula(jsonb), cost_chain(jsonb) |
| `cost_snapshots` | 每日成本快照 | symbol, total_unit_cost, breakeven_p25/p50/p75/p90, inputs(jsonb) |
| `human_decisions` | 人工仲裁记录 | alert_id, decision, confidence_override, reasoning |
| `event_log` | 事件审计 + 死信队列 | channel, payload(jsonb), status, error |

**新增基础设施表**（基于 Causa 评估后补充）：

| 表名 | 用途 | 关键字段 |
|------|------|---------|
| `contract_metadata` | 合约元数据 + 主力切换 | symbol, contract_month, expiry_date, is_main, main_until, volume, oi |
| `regime_state` | 每日板块 regime | category, date, regime, adx, atr_pct |
| `news_events` | 结构化新闻事件 | source, raw_url, event_type, affected_symbols, direction, severity, llm_confidence |
| `null_distribution_cache` | 零分布预计算缓存 | signal_type, category, distribution_stats(jsonb), computed_at |
| `llm_cache` | LLM 调用缓存 | cache_key, response, ttl, hit_count |
| `llm_usage_log` | LLM 调用日志 | module, model, input_tokens, output_tokens, cost_usd, cache_hit |
| `llm_budgets` | 月度预算配置 | module, monthly_budget_usd, current_spend, alert_threshold |
| `shadow_runs` | Shadow 配置追踪 | algorithm_version, config_diff(jsonb), started_at, ended_at |
| `shadow_signals` | Shadow 影子信号 | shadow_run_id, signal_type, would_emit, score, outcome |
| `alert_dedup_cache` | 预警去重缓存 | symbol, direction, evaluator, last_emitted_at, last_severity |
| `alert_agent_config` | Alert Agent 可校准配置 | key, value(jsonb), updated_at |

**自我学习层表**（6.17-6.20）：

| 表名 | 用途 | 关键字段 |
|------|------|---------|
| `user_feedback` | 用户对每个信号/推荐的判断 | alert_id, agree, disagreement_reason, will_trade, recorded_at |
| `drift_metrics` | Concept Drift 监控指标 | metric_type, current_value, baseline_value, psi, drift_severity, computed_at |
| `learning_hypotheses` | LLM 反思 Agent 输出 | hypothesis, evidence(jsonb), proposed_change, confidence, sample_size, status, created_at |
| `change_review_queue` | 自动学习产生的变更建议队列 | source(calibration/feedback/llm_agent), proposed_change(jsonb), status, reviewed_by, reviewed_at |

**回测正确性表**（6.21）：

| 表名 | 用途 | 关键字段 |
|------|------|---------|
| `strategy_runs` | 回测试验注册表（防多重比较自欺） | strategy_hash, params(jsonb), data_range, raw_sharpe, deflated_sharpe, deflated_pvalue, run_at, run_by |
| `slippage_models` | 分档滑点配置 | symbol, contract_tier, base_slippage_bps, vol_multiplier(jsonb), liquidity_multiplier(jsonb), tod_multiplier(jsonb) |
| `live_divergence_metrics` | 策略级 Live vs Backtest 监控 | strategy_id, period, live_sharpe, expected_sharpe, divergence_zscore, status, computed_at |
| `commodity_history` | Survivorship bias 防御 | symbol, contract_month, active_from, active_to, exchange |

**向量检索表**（6.22）：

| 表名 | 用途 | 关键字段 |
|------|------|---------|
| `vector_chunks` | pgvector 主表 | id, chunk_type(alert/news/note/hypothesis), content_text, embedding vector(1024), embedding_model, metadata(jsonb), quality_status, created_at |
| `vector_eval_set` | 检索质量评测集 | query_text, relevant_chunk_ids(jsonb), labeled_at, labeler |

### 7.2 修改表

- **`alerts`** — 新增: `adversarial_passed`, `llm_involved`, `confidence_tier`, `human_action_required`, `dedup_suppressed`
- **`positions`** — 新增: `manual_entry`, `avg_entry_price`, `monitoring_priority`, `propagation_nodes(jsonb)`
- **`signal_track`** — 新增: `adversarial_passed`, `calibration_weight_at_emission`, `signal_combination_hash`, `forward_return_1d`, `forward_return_5d`, `forward_return_20d`, `regime_at_emission`
- **`market_data`** — 新增: `vintage_at`（PIT 数据），`contract_id`（关联 contract_metadata）
- **`industry_data`** — 新增: `vintage_at`（PIT 数据，修订型数据多 vintage 行）
- **`recommendations`** — 新增（推荐级归因，6.17）: `entry_price`, `stop_loss`, `take_profit`, `actual_entry`, `actual_exit`, `actual_exit_reason`, `pnl_realized`, `mae`, `mfe`, `holding_period_days`

## 8. 项目目录结构

```
zeus/
├── frontend/                    # Next.js 16 (BFF only)
│   ├── src/app/                 # Pages + API proxy routes
│   ├── src/components/          # React components
│   ├── src/hooks/               # Client hooks (SSE, refresh)
│   └── src/lib/                 # Frontend-only utils
│
├── backend/                     # Python FastAPI (all business logic)
│   ├── app/
│   │   ├── main.py              # FastAPI app entry
│   │   ├── api/                 # API routes
│   │   ├── core/                # Config, DB, Redis, Events
│   │   ├── models/              # SQLAlchemy ORM models
│   │   ├── services/            # Business logic modules
│   │   │   ├── etl/             # 数据采集（PIT 数据架构）
│   │   │   ├── contracts/       # 合约元数据 + 换月（新）
│   │   │   ├── signals/         # 信号检测（7 evaluators，含 news_event）
│   │   │   ├── news/            # 新闻事件管线（新）
│   │   │   ├── adversarial/     # 对抗引擎
│   │   │   ├── scoring/         # 评分引擎
│   │   │   ├── alert_agent/     # 混合决策（规则 + LLM + 去重）
│   │   │   ├── calibration/     # 校准循环（含 regime 检测）
│   │   │   ├── positions/       # 持仓管理
│   │   │   ├── cost_models/     # 成本模型（成本曲线分位数）
│   │   │   ├── sectors/         # 板块模型
│   │   │   ├── scenarios/       # 场景推演
│   │   │   ├── risk/            # 风控（VaR, 压力测试）
│   │   │   ├── backtest/        # 回测框架（PIT 校准权重）
│   │   │   ├── llm/             # 多供应商 LLM（缓存 + 预算）
│   │   │   ├── shadow/          # Shadow / A/B 框架（新）
│   │   │   ├── learning/        # 自我学习层（新）
│   │   │   │   ├── recommendation_attribution.py  # 6.17 推荐归因
│   │   │   │   ├── user_feedback.py               # 6.18 用户反馈学习
│   │   │   │   ├── drift_monitor.py               # 6.19 Concept Drift
│   │   │   │   └── reflection_agent.py            # 6.20 LLM 反思 Agent
│   │   │   ├── governance/      # 治理守则强制（新）
│   │   │   │   └── review_queue.py  # change_review_queue 守卫
│   │   │   └── propagation/     # 品种传导图
│   │   └── scheduler/           # APScheduler 任务管理
│   ├── alembic/                 # DB migrations
│   ├── tests/
│   └── pyproject.toml
│
├── docker-compose.yml
└── docs/
    ├── ARCHITECTURE.md          # 本文档
    ├── PRD.md                   # 产品需求文档
    └── EXECUTION_PLAN.md        # 执行计划
```

## 9. Phase 10 事件作用域联动

- Event Intelligence、World Risk Map、News Events 与 Causal Web 统一使用 `event_intelligence:{event_id}` 作为跨页面事件作用域。
- `/api/causal-web` 支持 `symbol`、`region` 和 `event` 三个读取作用域；`event` 会固定带回指定事件智能对象，用于深链定位和路径聚焦。
- 前端跨页跳转保留 `source`、`symbol`、`region`、`mechanism`、`event` 查询参数，页面只能把这些参数解释为读取上下文，不直接写入生产阈值或治理状态。
- Event Intelligence 的事件详情、影响链、证据和反证入口使用同一个 Causal Web 深链构造器，避免人工复核时丢失事件、商品和区域上下文。
- Causal Web 的事件智能节点详情也能反向打开 Event Intelligence 与 World Risk Map；`source=causal-web` 会被识别为浏览来源，而不是误标为世界地图来源。
- News Events 也接入同一导航作用域；当 URL 带 `event` 时会按事件智能对象的来源新闻自动定位，并能继续打开同一 Causal Web / Event Intelligence / World Map 作用域。
- Causal Web 读取 `source` 后只作为前端阅读上下文展示，不参与后端图谱计算；实际过滤仍由 `symbol`、`region`、`event` 控制。

## 10. World Risk Map 增强渲染护栏

- `/api/world-map/tiles` 负责按 `symbol`、`mechanism`、`source`、`viewport` 和 `resolution` 输出天气 / 风险瓦片。
- 前端增强层用筛选条件、分辨率和近似视口生成瓦片缓存键；用户缩放或拖拽回到同一视口时优先复用缓存，避免大画布重复请求。
- 视口瓦片请求使用去抖和请求序号保护：后发请求代表当前视图，旧请求晚返回时会被丢弃；自动运行态刷新仍强制更新瓦片缓存。
- 增强模式只用顶部窄状态芯片暴露瓦片预算、缓存条目和请求状态，不再增加右侧大卡片；地图主体阅读空间优先级高于诊断面板。
- 瓦片预算也参与渲染降载：轻负载完整渲染，标准 / 密集负载会限制天气瓦片、风险密度点和跨区飞线数量，并按强度排序优先保留最高风险信息。
