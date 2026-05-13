# Zeus 执行计划

> 版本: 1.7 | 日期: 2026-05-10 | 总工期: ~22 周

## 变更说明（v1.7 — Event Intelligence Engine）

新增 **Phase 10 Event Intelligence Engine / 事件智能引擎**，用于把新闻、社媒、公告、天气、航运、持仓和行情异常组织成可解释的事件影响链。

- 目标不是“把所有信息都塞进地图”，而是让系统能判断：信息源是什么、影响哪个商品、通过供给/需求/物流/政策/情绪哪条机制传导、方向与置信度如何。
- 引擎输出先进入治理和 Shadow 验证，不直接改生产阈值或自动发交易指令。
- World Risk Map 和 Causal Web 将消费同一个事件作用域：`event_id + entities + symbols + regions + mechanisms + evidence/counterevidence`。
- 3D Globe 路线暂缓；世界风险地图后续优先加强 2D / WebGL 信息阅读、事件组织和证据可信度。

## 变更说明（v1.6 — World Risk Map Phase C.4）

世界风险地图天气层继续从“可显示”推进到“可解释、可控额度”：

- NOAA CDO station mapping 已接入：按产区经纬度匹配 GHCND 站点，再拉取近 7 日 PRCP/TMAX/TMIN。
- AccuWeather 当前天气指标进入地图详情：当前气温、1 小时降水、湿度、风速作为实时阅读层补充。
- NOAA CDO / AccuWeather 均增加每轮地点上限配置，避免免费额度被高频调度或本地刷新消耗。
- 这些增强仍写入统一 `industry_data`，世界地图继续通过融合层读取，不让前端直接依赖外部天气服务。

## 变更说明（v1.5 — World Risk Map Phase C）

世界风险地图进入真实天气数据接入阶段：

- Open-Meteo 天气采集配置化，并扩展到主要商品区域。
- NASA POWER 日频天气客户端落地，作为历史 baseline 的公开数据源入口。
- `/api/world-map` 开始融合 `industry_data` 最新天气行；没有真实天气时仍明确标注 `regional_baseline_seed`。
- NASA POWER 历史季节 baseline 已支持按同日历窗口生成降水/温度均值，供世界风险地图计算距平。
- 天气 baseline 增加历史分位数与低频调度任务；NOAA CDO / AccuWeather 作为可选天气源进入配置层。

## 变更说明（v1.4 — World Risk Map）

新增 **Phase 9.5 World Risk Map（世界风险地图）**：在 Causal Web 之外提供地理空间风险视图，展示各地区预警、天气异常、产区暴露、持仓暴露和因果链路作用域。

- 首版采用 React + SVG 实现 2.5D 地图和运行态聚合，避免业务契约未稳定前引入过重 GIS 依赖。
- 后续升级 MapLibre GL JS + deck.gl，three.js / React Three Fiber 作为 3D Globe 增强模式。
- 数据层新增 `/api/world-map` 聚合接口，先复用现有 `alerts` / `news_events` / `signal_track` / `positions`。
- 详细设计见 `docs/WORLD_RISK_MAP.md`。

## 变更说明（v1.3 — 回测正确性 + 向量检索方向调整）

基于对回测层和 Weaviate 层的二次审查，本版本主要调整：

- **新增 Phase 8.5 回测正确性收紧**（1 周）：PIT 校准权重回放 + Deflated Sharpe & FDR 多重比较保护 + 滑点分档模型 + Live vs Backtest 背离监控
- **向量检索方案变更**：默认使用 PostgreSQL + pgvector（而非 Weaviate）。Weaviate 标记为 P3 评估升级，仅当向量数 > 100w 或需要多租户/模块化时启用
- **Phase 4.5 新闻管线**：增加 pgvector 集成（向量检索基础设施在此阶段就位）
- **Phase 9 LLM 反思 Agent**：增加向量检索 quality_status 质量门
- **数据模型新增 6 张表**：`strategy_runs` / `slippage_models` / `live_divergence_metrics` / `commodity_history` / `vector_chunks` / `vector_eval_set`

总工期：18 周 → 19 周。

## 变更说明（v1.2 — 自我学习层）

在 v1.1 基础上加入 Goal B（按系统信号交易）必需的"自我学习"基础设施。**核心治理守则**：自动学习的输出永远不直接修改主链路决策，必须经过"假设 → 人工审阅 → Shadow Mode 验证 → 人工批准 → 上生产"。

- **Phase 3 加 Concept Drift 监控**（+0.5 周）：监测市场是否还像系统校准时的市场
- **Phase 5 加用户反馈学习**（+0.5 周）：采集每个信号你的判断，季度协同分析
- **Phase 6 加推荐级归因**（+0.5 周）：信号校准 → 推荐校准（Goal B 真正的命脉）
- **Phase 9 加 LLM 反思 Agent**（+1 周）：LLM 月度生成假设，强制反证，人工评审
- **新增 governance 模块**：所有自动学习产生的规则变更经 `change_review_queue` 守卫

总工期：15.5 周 → 18 周。

## 变更说明（v1.1）

基于 Causa 仓库实地评估和深度设计审查，本版本相比 v1.0 主要调整：

- **Phase 1 扩容**：合并 PIT 数据架构 + 合约换月模块（Causa 完全没实现，重构 ETL 时一次到位更省事）
- **Phase 3 校准循环**：明确**冷启动**策略（不复用 Causa 历史数据），新增 Regime 检测 + 真贝叶斯更新（Beta 先验）
- **新增 Phase 4.5**：新闻事件管线（Causa 的 `event_driven` 是纯技术面，没有真正的事件源）
- **Phase 5 加 LLM 成本控制**：缓存 / 预算 / 调用日志 / 降级（Causa 当前 < 5 次/天且无缓存，Zeus 可能爆 10-50 倍）
- **Phase 7 拆分 7a + 7b**：成本数据管线被严重低估，付费数据源在该阶段评估再采购
- **新增 Phase 9**：Shadow Mode + 置信度阈值校准（避免 Zeus 也变成"硬编码"）

## 总览

| 阶段 | 名称 | 工期 | 风险 | 核心交付物 |
|------|------|------|------|-----------|
| P0 | 项目初始化 | 2-3 天 | 低 | 可运行的项目骨架 |
| P1 | 后端核心迁移 + PIT + 合约换月 | 2.5 周 | 中 | Python 后端 + PIT 数据 + 合约元数据 |
| P2 | 事件总线 + 监控列表 | 1 周 | 低 | 事件驱动架构 |
| P3 | 校准循环（冷启动）+ Drift 监控 | 2 周 | 中 | 影子追踪 + Regime 检测 + Beta 先验 + Drift 告警 |
| P4 | 对抗引擎 | 1 周 | 中 | 统计对抗验证（warmup 模式） |
| P4.5 | 新闻事件管线 | 1.5 周 | 高 | 结构化新闻 + `news_event` 评估器 |
| P5 | Alert Agent + 人机交互 + LLM 成本 + 用户反馈 | 2 周 | 高 | 混合决策 + 仲裁 + 缓存/预算 + 反馈采集 |
| P6 | 持仓驱动 + 推荐级归因 | 1.5 周 | 中 | 持仓感知 + 推荐 P&L / MAE / MFE 归因 |
| P7a | 成本模型（黑色系） | 2 周 | 中 | JM→J→RB 高炉链路 + 信号集成 |
| P7b | 成本模型（橡胶） | 1.5 周 | 中 | NR→RU 全链路 + 信号集成 |
| P8 | 场景推演 | 1 周 | 低 | 异步场景模拟 |
| P8.5 | 回测正确性收紧 | 1 周 | 中 | PIT 校准权重 + Deflated Sharpe + 滑点分档 + 背离监控 |
| P9 | Shadow Mode + 阈值校准 + LLM 反思 Agent | 2 周 | 中 | A/B 框架 + 阈值二级校准 + 月度假设生成 |
| P9.5 | World Risk Map | 1 周 | 中 | 地理风险地图 + 运行态聚合 + Causal Web 联动 |
| P10 | Event Intelligence Engine / 事件智能引擎 | 2 周 | 高 | 动态事件组织 + 商品影响判断 + 证据/反证链 |

## Phase 0: 项目初始化（2-3 天）

### 目标
搭建 Zeus monorepo 骨架，前后端均可启动。

### 任务清单

- [x] 初始化 Git 仓库，创建 monorepo 结构 (`frontend/` + `backend/`)
- [x] **后端骨架**
  - [x] 创建 `backend/pyproject.toml`，安装核心依赖：
    - fastapi, uvicorn, sqlalchemy[asyncio], asyncpg, alembic
    - redis[hiredis], pydantic-settings, httpx
    - pandas, numpy, scipy, statsmodels
    - vectorbt, dowhy, akshare, tushare
  - [x] 创建 `backend/app/main.py`（FastAPI 入口 + CORS + lifespan）
  - [x] 创建 `backend/app/core/config.py`（pydantic-settings 配置）
  - [x] 创建 `backend/app/core/database.py`（SQLAlchemy async engine + session）
  - [x] 创建 `backend/app/core/redis.py`（Redis 连接池）
  - [x] 创建 `backend/app/api/health.py`（健康检查端点）
  - [x] 初始化 Alembic（`alembic init`）
  - [x] 创建 `backend/Dockerfile`（Python 3.11-slim, non-root user）
- [x] **前端骨架**
  - [x] 从 Causa 复制前端代码到 `frontend/`
  - [x] 修改 `next.config.ts`：API 代理指向 Python 后端
  - [x] 验证前端可用 mock 数据正常渲染
- [x] **基础设施**
  - [x] 创建 `docker-compose.yml`：Postgres + Redis + Backend + Frontend（Weaviate 保留为可选 profile；默认 pgvector）
  - [x] 创建 `.env.example`
  - [x] 创建 `CLAUDE.md`（项目约定）
- [x] **验证**
  - [ ] `docker compose up` 全部服务健康
  - [x] `GET /api/health` 返回 200
  - [x] 前端首页可访问

### 产出文件
```
zeus/
├── backend/
│   ├── app/main.py
│   ├── app/core/{config,database,redis}.py
│   ├── app/api/health.py
│   ├── alembic/
│   ├── pyproject.toml
│   └── Dockerfile
├── frontend/ (from Causa)
├── docker-compose.yml
├── .env.example
└── CLAUDE.md
```

---

## Phase 1: 后端核心迁移 + PIT 数据 + 合约换月（2.5 周）

### 目标
将 Causa 的全部业务逻辑从 TypeScript 迁移到 Python FastAPI，**同时**重构数据层引入 PIT 架构和合约元数据——这两件事在 ETL 重写时一次到位，比之后改省事。

### 第 1 周：数据层 + 核心 API（含 PIT 改造）

- [ ] **SQLAlchemy 模型**（移植 Causa 的 18 张表 + PIT/合约改造）
  - [x] `models/market_data.py` — OHLCV + settle + OI + **vintage_at + contract_id**
  - [x] `models/contract_metadata.py` — **合约元数据表（新）**：symbol, contract_month, expiry_date, is_main, main_until, volume, open_interest
  - [x] `models/alert.py` — 预警（含 spread_info, trigger_chain）
  - [x] `models/position.py` — 持仓（含 legs）
  - [x] `models/recommendation.py` — 交易建议
  - [x] `models/strategy.py` — 策略池
  - [x] `models/research.py` — 研究报告
  - [x] `models/signal.py` — 信号追踪（含 forward_return_1d/5d/20d）
  - [x] `models/sector.py` — 板块评估
  - [x] `models/graph.py` — 品种关系图
  - [x] `models/industry_data.py` — 产业数据 + **vintage_at**
  - [x] `models/llm_config.py` — LLM 配置（加密存储字段占位）
  - [x] 生成 Alembic 迁移：`20260503_0001_phase1_core_schema.py`
  - [x] 运行 `alembic upgrade head` 创建表（已在 backend 容器内连接 compose Postgres 验证）
- [ ] **PIT 数据架构**（Causa 用覆盖更新，Zeus 重写为 append-only）
  - [x] ETL 写入策略改造：所有数据行附 `vintage_at`，修订型数据每次拉取生成新 vintage 行
  - [x] 创建数据库视图 `market_data_latest`、`industry_data_latest`（默认查询使用）
  - [x] 实现 PIT 查询函数：`get_market_data_pit(symbol, as_of)`, `get_industry_data_pit(symbol, as_of)`
  - [x] 所有下游模块约定：实时决策用 `_latest`，回测/校准用 PIT 函数
- [ ] **合约元数据初始化**
  - [x] 主力合约切换规则：成交量 + 持仓量综合排名第一，连续 3 天领先则切换
  - [x] `services/contracts/main_contract_detector.py`：每日识别主力合约
  - [x] `services/contracts/continuous.py`：拼接 `continuous_main_adjusted`（带跳空调整）和 `continuous_main_raw`
- [ ] **核心 API 路由**
  - [x] `api/market_data.py` — 行情数据 CRUD + 查询（可选 as_of 参数）
  - [x] `api/contracts.py` — 合约元数据查询
  - [x] `api/alerts.py` — 预警列表/详情/SSE 流
  - [x] `api/positions.py` — 持仓 CRUD（create/list/detail）
  - [x] `api/recommendations.py` — 建议列表/详情
  - [x] `api/strategies.py` — 策略 CRUD（create/list/detail）

### 第 2 周：信号检测 + 调度器 + LLM

- [x] **信号检测**（移植 Causa 的 6 个 evaluator，注意 `event_driven` 在 Phase 4.5 才会拆分）
  - [x] `services/signals/evaluators/spread_anomaly.py`
  - [x] `services/signals/evaluators/basis_shift.py`
  - [x] `services/signals/evaluators/momentum.py`
  - [x] `services/signals/evaluators/regime_shift.py`
  - [x] `services/signals/evaluators/inventory_shock.py`
  - [x] `services/signals/evaluators/event_driven.py`（保留 Causa 原逻辑，Phase 4.5 重命名为 `price_gap` 并新增 `news_event`）
  - [x] `services/signals/detector.py`（编排器，asyncio.gather 并行）
  - [x] 信号检测在换月窗口期（前后 5 天）自动降级 `spread_anomaly` / `basis_shift`
- [x] **评分引擎**（移植 scoring.ts，权重暂硬编码，Phase 3 接入校准）
  - [x] `services/scoring/priority.py`
  - [x] `services/scoring/portfolio_fit.py`
  - [x] `services/scoring/margin_efficiency.py`
  - [x] `services/scoring/engine.py`（组合评分）
- [x] **调度器**（替代 node-cron）
  - [x] `scheduler/manager.py`（APScheduler 封装 + 健康追踪）
  - [x] `scheduler/jobs.py`（8 个定时任务定义 + 主力合约日检任务）
  - [x] `api/scheduler.py`（调度器管理 API）
- [x] **LLM 集成**（移植多供应商抽象）
  - [x] `services/llm/registry.py`（供应商工厂，DB 配置优先 + 环境变量回退）
  - [x] `services/llm/openai.py`（Responses API + `store=false`）
  - [x] `services/llm/anthropic.py`
  - [x] `services/llm/deepseek.py`
- [x] **风控**（移植 risk 模块）
  - [x] `services/risk/var.py`
  - [x] `services/risk/stress.py`
  - [x] `services/risk/correlation.py`
  - [x] `api/risk.py`（VaR / 压力测试 / 相关性矩阵）

### 第 3 周（半周收尾）：前端对接 + 验证

- [ ] **前端对接**
  - [x] 更新 `frontend/` 的 API proxy 指向 Python 后端
  - [ ] 验证所有页面数据正常加载（Alerts / Portfolio 已接真实 API，其他 mock 页面待逐步替换）
  - [x] 行情数据展示加上"vintage" 标签（Portfolio 持仓行展示 latest market data vintage）
- [ ] **性能基线**
  - [x] 信号检测全流程（6 评估器并行）耗时基线测试
    - 2026-05-03 Docker backend：200 次迭代，mean 0.244ms，p95 0.278ms
  - [x] PIT 查询性能测试（带 `as_of` 参数 vs 默认 latest）
    - 2026-05-03 Docker Postgres：250 行 × 2 vintages，100 次迭代；latest mean 2.079ms，as_of mean 1.899ms

### 验证
- [x] `pytest` 全部通过
- [ ] 前端所有已实现页面数据正常
- [x] 调度器可启动/停止/手动触发任务
- [x] LLM 调用正常（至少一个供应商；MockTransport 覆盖 OpenAI/Anthropic/DeepSeek 请求与响应解析）
  - [x] **PIT 查询验证**：插入修订数据后，`get_market_data_pit(as_of=昨天)` 返回原始版本，`market_data_latest` 返回修订版本
- [x] **合约换月验证**：`contract_metadata` 表有数据，主力合约判断正确

---

## Phase 2: 事件总线 + DB 驱动监控列表（1 周）

### 目标
将线性管道重构为事件驱动架构。

### 任务清单

- [x] **事件总线**
  - [x] `core/events.py` — Redis Pub/Sub 封装
    - ZeusEvent dataclass（id, channel, timestamp, source, payload, correlation_id）
    - `publish(channel, payload)` — 发布事件
    - `subscribe(channel, handler)` — 订阅事件（async handler）
    - 死信队列：handler 异常时写入 `event_log` 表
  - [x] `models/event_log.py` — 事件审计表
  - [x] Alembic 迁移：创建 `event_log` 表
- [x] **DB 驱动监控列表**
  - [x] `models/watchlist.py` — 监控列表表
  - [x] Alembic 迁移：创建 `watchlist` 表
  - [x] 种子数据：从 Causa 当前硬编码清单迁移（脚本核对为 102 条；文档早期写的 145 条待产品侧补充）
  - [x] `services/signals/watchlist.py` — 从 DB 读取监控列表
- [x] **管道重构**
  - [x] 调度器触发 ingest job → 发布 `market.update`
  - [x] 信号检测订阅 `market.update` → 发布 `signal.detected`
  - [x] 评分引擎订阅 `signal.detected` → 发布 `signal.scored`
  - [x] 预警创建订阅 `signal.scored` → 发布 `alert.created`
- [x] **验证**
  - [x] 手动触发 ingest job，检查 `event_log` 表中的 `market.update` 事件
  - [x] 预警生成行为与 Phase 1 一致（Docker smoke：合成 `market.update` 生成 2 条 `alert.created`，对应 `spread_anomaly` / `basis_shift`）

---

## Phase 3: 校准循环 — 冷启动 + Concept Drift 监控（2 周）

### 目标
实现信号权重的自动校准机制 + 市场漂移监测。**冷启动策略**——不复用 Causa 历史数据（auto-evaluate 规则不一致、outcome-tracker 存在 bug、缺 forward_return 字段），从零开始积累。**Drift 监控**只告警，不自动调整。

### 任务清单

- [x] **数据模型**
  - [x] `models/calibration.py` — signal_calibration 表（含 alpha_prior, beta_prior 字段）
  - [x] `models/regime_state.py` — 每日板块 regime 表
  - [x] Alembic 迁移
  - [x] **`signal_track` 表新增字段**：
    - [x] `calibration_weight_at_emission` — 触发时使用的权重
    - [x] `signal_combination_hash` — 组合哈希
    - [x] `forward_return_1d / 5d / 20d` — 多窗口前向收益（取代 Causa 单一的 outcome）
    - [x] `regime_at_emission` — 触发时的 regime
- [ ] **Regime 检测**
  - [x] `services/calibration/regime_detector.py`
    - [x] ADX + ATR 百分位规则法（确定性主方法）
    - [x] 分类：trend_up_low_vol / trend_down_low_vol / range_high_vol / range_low_vol
    - [x] 每日 ETL 后按板块计算 regime 并写入 `regime_state` 表
  - [ ] HMM baseline（hmmlearn）作为对比，不进主链路
- [x] **影子追踪器**（避免幸存者偏差，Zeus 核心机制）
  - [x] `services/calibration/shadow_tracker.py`
    - [x] 每个信号触发瞬间启动影子追踪，不依赖用户行为
    - [x] 调度器每日扫描达到评估窗口的 pending 信号
    - [x] 调用对应评估器的 `evaluate_outcome` 方法标记 outcome
  - [x] **每个评估器实现 `evaluate_outcome(signal, market_data, horizon)` 方法**：
    - [x] `spread_anomaly`：Z-score 在窗口内回归到 ±0.5 内 → hit
    - [x] `basis_shift`：基差变动方向被价格证实 → hit
    - [x] `momentum`：前向收益与信号方向一致 → hit
    - [x] `regime_shift`：后续波动率/趋势特征匹配预测 → hit
    - [x] `inventory_shock`：现货价格在窗口内出现预测方向变动 → hit
    - [x] `event_driven`（Phase 4.5 拆为 `price_gap` / `news_event`）：跳空延续 vs 回补 / 标的方向变动
- [ ] **校准模块**
  - [x] `services/calibration/tracker.py`
    - [x] 信号触发时记录：信号类型、板块、regime、当前权重、组合哈希
  - [x] `services/calibration/hit_rate.py`
    - [x] 按 (signal_type, category, regime) 计算 90 天滚动精确率/召回率
    - [x] **使用影子追踪结果，不使用持仓平仓**（用户实际持仓只作为补充质量数据）
  - [x] `services/calibration/weight_adjuster.py`
    - [x] **真贝叶斯更新（Beta 先验）**：
      ```
      posterior_mean = (α₀ + hits) / (α₀ + β₀ + total)
      effective_weight = base_weight × (posterior_mean / 0.5)
      ```
    - [x] 默认 α₀ = β₀ = 4（弱先验）
    - [x] 权重范围约束：[0.1, 2.0]
    - [x] 冷启动期权重 ≈ base_weight（先验主导）
  - [x] `services/calibration/decay_detector.py`
    - [x] CUSUM 或 Bayesian online change point detection
    - [x] 触发衰减后权重 × 0.5，标记 `decay_detected = true`
    - 前端展示衰减警告
- [x] **集成**
  - [x] 评分引擎从 `signal_calibration` 表读取权重（替代硬编码）
  - [x] 调度器加每日校准任务（凌晨执行）
  - [x] 调度器加每日 regime 检测任务（ETL 后执行）
- [ ] **冷启动监控**
  - [ ] 前端"校准仪表盘"页面：展示各 (signal_type, regime) 的样本量、当前权重、置信带
  - [ ] 样本量 < 10 时显示"先验主导"提示
  - [ ] 样本量积累到 100+ 之前不要过度信任权重调整
- [ ] **Concept Drift 监控（新增 6.19）**
  - [x] `models/drift_metrics.py` — Drift 指标表
  - [x] Alembic 迁移
  - [x] `services/learning/drift_monitor.py`
    - [x] **特征分布漂移**（PSI / KL divergence）：波动率、价差、基差、成交量、持仓量。当前 30 天 vs 历史 90 天，PSI > 0.25 告警
    - [x] **相关性结构漂移**：板块内品种相关性矩阵 Frobenius 距离突变检测
    - [x] **信号命中率突变**：滚动 30 天 vs 90 天基线，z-score > 2 告警
    - [x] **Regime 频繁切换检测**：月切换次数 > 3 告警
  - [x] 调度任务：每日 ETL 后运行 Drift 批处理并写入 `drift_metrics`
  - [ ] 前端：Dashboard 顶部 "Drift Alert" 指示器（红/黄/绿三档）
  - [ ] 通知：漂移告警时推送到飞书（建议本周谨慎按系统信号交易）
  - [ ] **关键约束**：Drift 监控**只告警**，不自动调整任何权重或阈值
- [x] **治理基础设施（governance）**
  - [x] `models/change_review_queue.py` — 变更审核队列表
  - [x] `services/governance/review_queue.py` — 守卫装饰器
    - [x] 任何修改 `signal_calibration` / `commodity_config` / 阈值参数的写入必须通过此守卫
    - [x] 守卫检查调用方是否有 `human_approved=True` 标记
    - [x] 失败则写入审核队列等人工批准
  - [x] 单元测试：直接尝试改 calibration 表会被拒绝
- [x] **验证**
  - [x] 模拟数据测试：构造 200 个已知 outcome 的信号，验证 Bayesian 更新公式正确
  - [x] 验证影子追踪器在每日调度中正确标记 outcome
  - [x] 验证 regime 检测对明确市场状态的判断正确
  - [x] 验证 Drift 监控：注入分布偏移数据，PSI 应触发告警
  - [x] 验证治理守卫：尝试绕过审核直接改 calibration 应失败

---

## Phase 4: 对抗引擎（1 周）

### 目标
在信号进入评分前增加统计对抗验证。冷启动期采用 **warmup mode**（informational only，不阻塞信号）。

### 任务清单

- [x] **数据模型**
  - [x] `models/adversarial.py` — adversarial_results 表
  - [x] `models/null_distribution_cache.py` — 零分布预计算缓存表
  - [x] Alembic 迁移
- [x] **对抗模块**
  - [x] `services/adversarial/null_hypothesis.py`
    - [x] 改为**预计算策略**：每日 ETL 后按 (signal_type, category) 预计算零分布统计量
    - [x] 实时检测 O(1) 查表对比，避免每个信号都跑 1000 次 Bootstrap
    - [x] 预计算结果存 `null_distribution_cache`
    - [x] 输出：p-value，p < 0.05 为通过
  - [x] `services/adversarial/historical_combo.py`
    - [x] **模糊哈希**：基于排序后的 (signal_type_set, category, regime)，新增评估器时旧哈希可匹配子集
    - [x] Jaccard 相似度 ≥ 0.7 视为匹配
    - [x] 查询 `signal_calibration` 中相似组合的历史命中率
    - [x] 命中率 < 0.3 且样本 > 20 为失败
  - [x] `services/adversarial/structural_counter.py`
    - [x] 遍历传导图寻找反向路径
    - [x] 检查季节性反转因素
    - [x] 检查替代品压力
    - [x] 输出：反驳论据列表 + 数量
- [ ] **冷启动 warmup 模式**
  - [x] 历史组合检验添加 `mode` 字段：`informational` / `enforcing`
  - [x] 系统上线前 90 天默认 `informational`：执行检查并记录，**不阻塞信号、不施加置信度惩罚**
  - [x] 样本量达到阈值（sample_size ≥ 20）后自动按 `enforcing` 处理
  - [ ] 切换可手动覆盖（运营后台开关）
  - [x] 零假设检验 + 结构性反驳从第一天就 `enforcing`（不依赖历史）
- [x] **集成**
  - [x] 在事件流中插入：`signal.detected` → 对抗引擎 → 通过后才进入评分
  - [x] 三项全失败 → 抑制信号（warmup 模式下例外：历史组合检验失败仅记录）
  - [x] 部分失败 → 置信度 × 0.7
  - [x] `alerts` 表新增 `adversarial_passed` 字段
- [x] **验证**
  - [x] 构造已知噪声信号，验证零假设检验能拦截
  - [x] 构造历史低命中率组合，验证历史检验能降级（enforcing 模式）
  - [x] 验证 warmup 模式下不阻塞信号
  - [x] 检查 `adversarial_results` 表记录完整

---

## Phase 4.5: 新闻事件管线（1.5 周）

### 目标
Causa 的 `event_driven` 评估器实际上是纯技术面（gap + volume），**没有真正的事件源**。Zeus 把"事件"还给真正的新闻事件，让 `news_event` 评估器有数据可用。

### 任务清单

- [x] **数据模型**
  - [x] `models/news_events.py` — 结构化新闻事件表
    - 字段：source, raw_url, published_at, event_type, affected_symbols, direction, severity, time_horizon, llm_confidence
  - [x] Alembic 迁移
- [x] **新闻采集**
  - [x] `services/news/collectors/cailianshe.py` — 财联社快讯（电报源）collector 接口（真实电报源解析后续接入）
  - [x] `services/news/collectors/sina_futures.py` — 新浪财经期货频道 collector 接口（真实页面解析后续接入）
  - [x] `services/news/collectors/gdelt.py` — GDELT 扩展使用（Causa 已接入）
  - [x] `services/news/collectors/exchange_announcements.py` — 交易所公告 API collector 接口（交易所适配后续接入）
  - [ ] 后续可扩展：上海钢联、卓创资讯（公开部分）
- [x] **向量检索基础设施（pgvector）**
  - [x] PostgreSQL 启用 `pgvector` 扩展（`CREATE EXTENSION vector`）
  - [x] `models/vector_chunks.py` — 向量主表（id, chunk_type, content_text, embedding vector(1024), embedding_model, metadata, quality_status, created_at）
  - [x] HNSW 索引：m=16 / ef_construction=64 / ef_search=40
  - [x] Alembic 迁移
  - [x] `services/vector_search/embedder.py` — Embedding 服务封装
    - 主选 Voyage-3，备选 BGE-M3（开源本地）
    - 维度 1024
    - `embedding_model` 字段记录版本，支持双版本并存
    - 当前实现含 `local-hash-1024` 开发/测试 fallback；Voyage/BGE Provider 凭证接入留到 LLM 成本控制阶段统一配置
  - [x] `services/vector_search/hybrid_search.py` — 混合检索
    - `final_score = α × cosine + β × bm25 + γ × time_decay`（默认 α=0.6, β=0.3, γ=0.1）
    - 元数据预过滤（chunk_type / sector / date_range）
    - time_decay half_life 按事件类型差异化（政策 180d / 季节性 365d / 突发 30d / 假设 ∞）
- [x] **去重与质量控制**
  - [x] `services/news/dedup.py` — 标题哈希 + 语义相似度（pgvector 检索近 24h）去重
  - [x] 同事件多源交叉验证：≥ 2 个独立源覆盖才进入评估
- [x] **LLM 结构化抽取**
  - [x] `services/news/extractor.py` — Pydantic 结构化抽取接口 + 确定性 fallback（真实 LLM Provider 后续接入）
  - [x] Pydantic 模型强制输出结构：
    - `event_type`：政策 / 供给 / 需求 / 库存 / 地缘 / 天气 / 突发事件
    - `affected_symbols`：受影响品种（含传导图衍生的次级品种）
    - `direction`：bullish / bearish / mixed / unclear
    - `severity`：1-5 级
    - `time_horizon`：immediate / short / medium / long
- [x] **拆分原 event_driven 评估器**
  - [x] 重命名 `services/signals/evaluators/event_driven.py` → `price_gap.py`（保留 Causa 原逻辑；`event_driven` 作为兼容别名保留）
  - [x] 新建 `services/signals/evaluators/news_event.py`：订阅 `news.event` 事件，结合品种传导图生成信号
- [x] **事件总线接入**
  - [x] 新闻入库后发布 `news.event` 事件
  - [x] `news_event` 评估器订阅，触发信号检测
- [x] **质量门槛**
  - [x] 严重度 ≥ 3 才生成预警，< 3 仅记录
  - [x] 单源未交叉验证的高严重度事件强制人工确认
- [x] **前端**
  - [x] 新闻事件流页面：展示已抽取的结构化事件
  - [x] 预警详情面板增加"触发新闻"链接（如果由 news_event 触发）
- [x] **验证**
  - [x] 手动注入若干已知重大事件（OPEC 减产、产区天气、政策变动），验证 LLM 抽取准确率
  - [x] 验证去重正常（同事件多源不会重复触发）
  - [x] 验证 `news_event` 评估器正确生成信号

---

## Phase 5: Alert Agent + 人机交互 + LLM 成本控制 + 用户反馈学习（2 周）

### 目标
实现混合决策路由和人工仲裁机制。**同时建立 LLM 成本控制基础设施**——Phase 4.5 + 5 + 8 的 LLM 调用如不控制可能爆增 10-50 倍。**新增用户反馈采集**——这是单用户系统能拿到的最高质量学习数据。

### 任务清单

- [x] **Alert Agent 模块**
  - [x] `services/alert_agent/router.py`
    - 判断走确定性路径还是 LLM 路径
    - LLM 触发条件：信号方向矛盾、置信度 40-65%、无历史先例、跨 3+ 板块
  - [x] `services/alert_agent/classifier.py`
    - 规则分级：L0 全景 / L1 板块 / L2 品种 / L3 交易建议
  - [x] `services/alert_agent/llm_arbiter.py`
    - 矛盾信号仲裁：结构化 JSON 输出（Pydantic 模型）
    - 新模式分析：历史类比检索
    - 输出无效时回退确定性路径
  - [x] `services/alert_agent/narrative.py`
    - 高/危急预警的叙事生成
    - 30 字以内的 one-liner 摘要
  - [x] `services/alert_agent/dedup.py` — **预警去重与限流（新）**
    - `alert_dedup_cache` 表：(symbol, direction, evaluator, last_emitted_at, last_severity)
    - 同 (品种, 方向, 评估器) 12 小时内只发一次（除非严重度升级）
    - 同信号组合 24 小时内只发一次
    - 每日预警上限（默认 50），超限保留 top-K 高分
- [x] **置信度分层**
  - [x] `alerts` 表新增：`confidence_tier`, `human_action_required`, `human_action_deadline`, `dedup_suppressed`
  - [x] 路由逻辑：>85% auto / 60-85% notify / <60% confirm / 冲突 arbitrate
  - [x] **置信度阈值标记为"可校准"**：阈值存配置表而非硬编码常量，Phase 9 接入校准
- [x] **LLM 成本控制基础设施（新）**
  - [x] `models/llm_cache.py`、`models/llm_usage_log.py`、`models/llm_budgets.py`
  - [x] Alembic 迁移
  - [x] `services/llm/cache.py` — 结果缓存
    - 缓存键：`hash(provider + model + system + user_message)`
    - TTL：24 小时（可按场景配置）
    - 缓存命中/未命中指标暴露到监控
  - [x] `services/llm/cost_tracker.py` — 调用日志 + 预算追踪
    - 每次调用记录：模块、模型、输入/输出 token、估算成本（USD）、是否缓存命中
    - 月度成本归因报表 API
  - [x] `services/llm/budget_guard.py` — 预算上限
    - 按模块预算（alert_agent / news / scenario / research）
    - 超 80% 预算告警
    - 超 100% 自动降级到确定性路径
  - [x] **Anthropic prompt caching 启用**：系统提示使用 cache_control（当前未引入 Anthropic tool schema）
  - [x] LLM 调用统一通过 `llm/registry.py` 入口，所有调用经过 cache + cost_tracker + budget_guard 三层
  - [x] 失败/超时（>30s）/ 输出无效 JSON → 自动回退确定性路径
- [x] **人工仲裁**
  - [x] `models/human_decision.py` — human_decisions 表（模型落在 `models/alert_agent.py`）
  - [x] `api/arbitration.py` — 仲裁 API（审批/拒绝/修改）
  - [x] 前端：仲裁界面（展示矛盾信号 + 对抗结果 + 操作按钮）
- [x] **用户反馈学习（新增 6.18）**
  - [x] `models/user_feedback.py` — 用户反馈表
  - [x] Alembic 迁移
  - [x] `services/learning/user_feedback.py`
    - 每个信号/推荐发出时附简短反馈表单
    - 字段：agree（agree / disagree / uncertain）、disagreement_reason（自由文本）、will_trade（will_trade / will_not_trade / partial）
    - 反馈数据**本身不影响信号触发或权重**，只用作学习数据
  - [x] 前端：预警面板加反馈采集组件（不强制，但持续提醒）
  - [x] 季度协同分析报表（生成到 `learning/feedback_report.py`）：
    - 用户和系统判断不一致时谁对得多（按信号类型切片）
    - 用户判断更准的场景 / 系统判断更准的场景
    - 输出建议：哪些类型信号"信你"、哪些"信系统"
  - [x] 集成到 Alert Agent：当系统识别"此类信号你历史判断更准"，预警附软性提示
  - [x] **关键约束**：用户反馈**不直接修改信号权重**，只产出 `change_review_queue` 建议
- [x] **验证**
  - [x] 构造矛盾信号，验证 LLM 路径触发
  - [x] 验证 confirm 级别预警暂停等待人工
  - [x] 验证人工决策记录写入 `human_decisions` 表
  - [x] 验证缓存命中：相同信号组合二次触发应命中缓存
  - [x] 验证预算超限自动降级
  - [x] 验证去重：同品种同方向连续触发只发一次预警
  - [x] 验证用户反馈采集 + 反馈不修改信号权重

---

## Phase 6: 持仓驱动行为 + 推荐级归因（1.5 周）

### 目标
持仓数据改变系统的监控和建议行为。**同时建立推荐级归因系统**——Goal B（按信号交易）的命脉。Zeus 当前是信号级校准，但用户做的是按推荐交易，推荐才是真正要追踪的对象。

### 任务清单

- [x] **持仓录入**
  - [x] `positions` 表新增：`manual_entry`, `avg_entry_price`, `monitoring_priority`, `propagation_nodes`
  - [x] `api/positions.py` 扩展：最小录入（5 字段）、快捷操作（平仓/加仓/减半）
  - [x] 交易建议采纳时自动预填持仓
- [x] **监控升级**
  - [x] `services/positions/threshold_modifier.py`
    - 持仓品种阈值 × 0.8
    - 订阅 `position.changed` 事件，维护内存阈值缓存
  - [x] `services/positions/propagation_activator.py`
    - 查询传导图，激活关联品种
    - 在 `watchlist` 表中添加 `position_linked=true` 的条目
    - 持仓平仓时移除关联条目
- [x] **风控联动**
  - [x] `services/positions/risk_recalc.py`
    - `position.changed` 时重算 VaR、相关性、集中度
    - 超限时降级新建议
  - [x] 新建议与持仓方向冲突 → 标记警告
  - [x] 持仓品种出现反向信号 → 优先推送
- [x] **数据腐烂防护**
  - [x] 定时检查：持仓 N 天未更新 → 推送提醒
  - [x] 长期不更新 → 降级为无持仓模式
- [x] **推荐级归因（新增 6.17）**
  - [x] `recommendations` 表新增字段：
    - `entry_price`, `stop_loss`, `take_profit`（推荐时定的）
    - `actual_entry`, `actual_exit`, `actual_exit_reason`（实际执行）
    - `pnl_realized` — 按手数 × 合约乘数计算
    - `mae`（最大不利偏移）, `mfe`（最大有利偏移）
    - `holding_period_days`
  - [x] Alembic 迁移
  - [x] `services/learning/recommendation_attribution.py`
    - 持仓变动时自动更新对应推荐的执行字段
    - 持仓平仓时计算最终 P&L
    - 持仓持续期间每日更新 MAE / MFE
  - [x] 月度归因报表（`learning/attribution_report.py`）：
    - 信号组合 × 胜率 × 期望收益 × 样本量
    - Regime × 胜率
    - 板块 × 胜率
    - 季节（月份）× 胜率
    - 持仓时长 × 胜率
    - 入场时段 × 胜率
  - [x] 风控参数评估报表：
    - Stop loss：基于 MAE 分布判断止损是太紧还是太松
    - Take profit：基于 MFE 分布判断止盈是否过早
    - 持仓时长：哪个区间胜率最高
  - [x] 前端：归因报表页面
  - [x] **关键约束**：归因系统**只产生报表**，不自动调整任何止损止盈或推荐参数
- [x] **验证**
  - [x] 录入橡胶持仓，验证 RU 阈值降低 + 关联品种进入监控
  - [x] 验证持仓冲突检测
  - [x] 验证数据腐烂提醒
  - [x] 验证推荐归因：模拟一个完整交易周期（开仓 → 持仓 → 平仓），验证 MAE/MFE/PnL 计算正确
  - [x] 验证月度报表生成正确

---

## Phase 7a: 成本模型 — 黑色系（2 周）

### 目标
构建成本模型框架 + 黑色系产业链（JM→J→RB）成本智能。**优先黑色系**因为产业链关系明确、公开数据相对充分。


#### 数据来源策略（暂未购买付费源）

进入此 Phase 时先评估降级方案的信号质量：
- 公开源：交易所原料价格、统计局月度数据、企业财报、行业协会公开报告
- LLM 辅助提取（接入 Phase 4.5 新闻管线）：从行业新闻抽取成本数据点
- 手动维护：低频参数（人工水电、税率）放运营后台手动配置
- 数据质量较粗，盈亏平衡价误差可能在 ±5%——前端必须明示数据来源和不确定度
- **本 Phase 末尾评估**：若降级方案信号质量不足，再决定是否采购卓创/SMM/Mysteel

#### 第 1 周：框架 + 黑色系成本配置

- [x] **数据模型**
  - [x] `models/commodity_config.py` — 品种配置表
  - [x] `models/cost_snapshot.py` — 成本快照表（含 P25/P50/P75/P90 分位数字段）
  - [x] Alembic 迁移
- [x] **成本模型框架**
  - [x] `services/cost_models/framework.py`
    - `CostFormula` 基类：定义输入参数、计算逻辑、输出格式
    - 支持链式计算（上游输出作为下游输入）
    - **支持成本曲线分位数计算**：基于产能分布数据输出 P25/P50/P75/P90，不只是平均值
  - [x] `services/cost_models/cost_chain.py`
    - 产业链计算：JM → J → RB 逐级计算
    - 每一步：原料成本 + 加工费 + 损耗 + 运输 + 税费 = 单位成本
  - [x] `services/cost_models/snapshots.py`
    - 每日快照调度任务
    - 高频变量（原料价格）实时更新，低频变量（人工）季度更新
  - [x] `services/cost_models/news_extractor.py` — LLM 辅助从新闻抽取成本数据点
- [x] **黑色系成本配置**
  - [x] `services/cost_models/configs/coking_coal.py` — 焦煤成本
  - [x] `services/cost_models/configs/coke.py` — 焦炭成本（配煤比、炼焦、副产品）
  - [x] `services/cost_models/configs/iron_ore.py` — 铁矿石到岸成本（普氏/麦克 + 运费）
  - [x] `services/cost_models/configs/rebar.py` — 螺纹钢（高炉利润模型）
  - [x] `services/cost_models/configs/hot_coil.py` — 热卷（热轧加工费差异）
- [x] **板块模型**
  - [x] `services/sectors/ferrous.py` — 高炉利润 = RB - 1.6×I - 0.5×J - 加工费

#### 第 2 周：信号集成 + 前端 + 数据源评估

- [x] **信号集成**
  - [x] 成本模型输出接入信号检测：
    - 利润率 < -5% 持续 2 周 → `capacity_contraction` 信号
    - 利润率由负转正 → `restart_expectation` 信号
    - 价格跌破 P50 分位 → `median_pressure` 信号
    - 价格跌破 P75/P90 分位 → `marginal_capacity_squeeze` 信号
  - [x] 新信号类型注册到评估器框架
- [x] **API**
  - [x] `api/cost_models.py`
    - GET /cost-models/{symbol} — 当前成本分解 + 分位数
    - GET /cost-models/{symbol}/history — 历史成本快照
    - POST /cost-models/{symbol}/simulate — 动态调价计算
    - GET /cost-models/{symbol}/chain — 产业链全景
- [x] **前端（黑色系）**
  - [x] 成本分解瀑布图组件
  - [x] 利润率趋势图组件 + 当前位置标注
  - [x] 盈亏平衡线（P75/P90）标注在价格图上
  - [x] 动态调价计算器（滑块/输入框，实时重算）
  - [x] 数据来源透明度：每个成本组件标注数据源 + 更新时间 + 不确定度
- [x] **数据质量评估**（本 Phase 关键产出）
  - [x] 对比成本模型计算的盈亏平衡价 vs 行业公开数据
  - [x] 评估信号触发的真实性（验证已知历史时点的成本压力是否被正确识别）
  - [x] 输出报告：决定是否采购付费数据源（卓创/SMM/Mysteel），以及优先采购哪个

#### 验证
- [x] `cost_snapshots` 表每日有新记录，含完整分位数
- [x] 高炉利润模型与行业公开计算结果偏差 < 5%
- [x] 成本信号在历史关键时点（如 2021 年限产、2024 年产能调整）能正确触发
- [x] 前端成本页面数据正确展示

---

## Phase 7b: 成本模型 — 橡胶（1.5 周）

### 目标
基于 Phase 7a 的框架扩展橡胶（NR→RU）成本链。框架已就绪，主要工作是数据采集和品种特化。

### 任务清单

- [x] **橡胶成本配置**
  - [x] `services/cost_models/configs/natural_rubber.py` — 天然胶（产区价格 + 运费 + 关税）
  - [x] `services/cost_models/configs/rubber_processed.py` — RU 加工成本
    - 分级：乳胶 / 烟片 / 标胶
    - 加工费 + 损耗率 + 仓储 + 税费
  - [x] 上下游链路：NR（产区现货）→ 进口加工 → RU（沪胶交割品）
- [x] **数据采集 Bootstrap**
  - [x] 公开回退种子：青岛保税区、海南/云南天胶、泰国口径、进口运费、税费
- [x] **生产级数据采集接口骨架**
  - [x] 生产源目录：青岛保税区、海南/云南、东南亚出口价、进口运费
  - [x] 新闻/公开文本抽取映射：RU/NR + 产区价格、青岛升水、收胶成本、运费
- [ ] **生产级数据采集上线**
  - [ ] 产区现货价格采集（青岛保税区、海南天胶、云南天胶）
  - [ ] 泰国、印尼、马来西亚出口价（公开数据 + LLM 提取）
  - [ ] 进口运费（Drewry、CCFI 公开指数）
- [x] **品种特化**
  - [x] 橡胶产能分布（东南亚为主）→ 成本分位数计算
  - [x] 季节性因素：开割/停割期对成本的影响
- [x] **前端**
  - [x] 橡胶成本页面（同黑色系结构）
  - [x] 增加产区季节性提示
- [ ] **信号集成**
  - [x] 橡胶利润率信号
  - [x] 产区供给信号（与 Phase 4.5 新闻事件管线联动：产区天气、出口政策）
  - [x] GDELT 公开新闻橡胶供给采集器：泰国/印尼/马来西亚/海南/云南 + 天气/出口/政策关键词
- [x] **验证**
  - [x] 橡胶盈亏平衡价合理性验证
  - [x] 历史几次明显的产区供给冲击（如 2019 年泰国干旱、2020 年疫情期间割胶停滞）能在系统中体现

---

## Phase 8: 场景推演（1 周）

### 目标
构建独立的异步场景模拟模块。

### 任务清单

- [x] **推演引擎**
  - [x] `services/scenarios/monte_carlo.py`
    - 基于传导图的价格路径模拟
    - 参数：模拟次数、时间跨度、波动率假设
  - [x] `services/scenarios/what_if.py`
    - 用户定义假设条件（如：铁矿石价格 +10%）
    - 沿传导图计算下游影响
  - [x] `services/scenarios/simulator.py`
    - 编排器：接收推演请求 → 执行模拟 → 生成报告
    - 异步执行（不阻塞主链路）
- [x] **触发机制**
  - [x] 手动触发：`api/scenarios.py` POST 端点
  - [x] 条件触发：Alert Agent 在 `arbitrate` 级别时可请求推演
  - [x] 订阅 `scenario.requested` 事件
- [x] **报告生成**
  - [x] LLM 将数值结果翻译为可读的情景描述（无 LLM 配置时稳定回退到本地确定性叙事）
  - [x] 输出：概率分布、关键路径、风险点、建议行动
- [x] **前端**
  - [x] 场景配置界面（选择品种、设定假设）
  - [x] 推演结果展示（概率分布图、传导路径图）
  - [x] 迭代式推演（调整假设 → 重新推演）
- [x] **验证**
  - [x] 手动触发橡胶场景推演，验证结果合理
  - [x] 验证异步执行不阻塞主预警流程

---

## Phase 8.5: 回测正确性收紧（1 周）

### 目标
回测在金融领域出名的"易出伪精度"——本 Phase 在回测框架里硬编码 4 项防御机制，避免所有 Sharpe 都是镜花水月。详见 ARCHITECTURE.md §6.21。

### 任务清单

- [x] **必修 1：PIT 校准权重回放**
  - [x] `signal_calibration` 表加 `effective_from` / `effective_to` 字段
  - [x] Alembic 迁移
  - [x] 重写校准更新逻辑：插入新行（不覆盖），形成权重时间序列
  - [x] `services/backtest/calibration_replay.py`：按时点切片读取历史权重
  - [x] 回测元数据强制记录 `calibration_strategy` 字段（pit / frozen / current）
  - [x] 默认 `pit`；`current` 的回测结果必须明确标注"不可作为决策依据"

- [x] **必修 2：多重比较保护（Deflated Sharpe + FDR）**
  - [x] `models/strategy_runs.py` — 策略试验注册表
  - [x] Alembic 迁移
  - [x] `services/backtest/multiple_testing.py`
    - 实现 Deflated Sharpe Ratio（Bailey & Lopez de Prado 2014）
    - 实现 Bonferroni / Benjamini-Hochberg FDR 校正
    - 单策略输出强制同时给 raw Sharpe 和 deflated Sharpe
  - [x] 策略上线门槛：deflated Sharpe > 1.0 且 deflated p-value < 0.05
  - [x] **raw Sharpe 不再作为单一上线门槛**

- [x] **必修 3：滑点分档模型**
  - [x] `models/slippage_models.py` — 分档滑点配置表
  - [x] Alembic 迁移
  - [x] `services/backtest/slippage.py`
    - 函数式滑点：`slippage_bps = base × vol_mult × liquidity_mult × tod_mult`
    - 按合约层级：main 1.0 / second 2.5 / third 8.0
    - 按波动率：低 0.7 / 中 1.0 / 高 1.8（基于 ATR 百分位）
    - 按订单大小：< 1% ADV 1.0 / 1-5% 1.4 / 5%+ 2.5
    - 按时段：主交易 1.0 / 开盘 15min 1.5 / 收盘 15min 1.4 / 夜盘 1.2
  - [x] 临近交割 < 15 天：滑点 × 3，新建议自动转移到次月合约
  - [x] 涨跌停板：默认无法成交（除非板上挂单）
  - [x] 基准滑点数据：复用 Phase 7a 期间采集的成交量/深度数据（当前以 tier bootstrap + 表配置承载）

- [x] **必修 4：Live vs Backtest 背离监控**
  - [x] `models/live_divergence_metrics.py` — 监控指标表
  - [x] Alembic 迁移
  - [x] `services/backtest/live_divergence.py`
    - **Tracking error**：实盘成交"回放"重建理论曲线，对比真实曲线
    - **Sharpe 偏离检验**：实盘 Sharpe 是否落在回测 95% 置信区间外
    - **算法漂移检测**：每月用今天的算法重跑历史回测，差异 > 5% 触发警告
  - [x] 偏离触发时写入 `change_review_queue`（接 Phase 3 治理基础设施）
  - [x] 与 Phase 3 信号级 `decay_detector` 区分：本 Phase 是策略级

- [x] **应修：Walk-forward 参数硬性规范**
  - [x] 默认 3 年训练 / 3 月测试 / 1 月步长，rolling window
  - [x] 写入 `services/backtest/walk_forward.py` 作为常量
  - [x] 所有策略回测必须使用此默认参数，覆盖需写入策略元数据

- [x] **应修：Regime profile 分解**
  - [x] 每个回测输出按 regime 切片：Sharpe / 胜率 / 最大回撤 / 样本量
  - [x] 前端：策略详情页加 regime profile 表（Strategy Forge 回测可信度面板）

- [x] **应修：路径相关指标**
  - [x] Underwater duration（峰值到回归峰值的天数分布）
  - [x] Pain ratio（累积 drawdown / 平均回报）
  - [x] Recovery factor（总回报 / 最大回撤）
  - [x] CVaR(95%) 实际值
  - [x] MAE / MFE 分布（与 Phase 6 推荐归因用同一指标体系）

- [x] **应修：Survivorship bias 处理**
  - [x] `models/commodity_history.py` — 品种宇宙历史快照表
  - [x] Alembic 迁移
  - [x] 种子数据：从 Causa 数据 + 公开退市记录补全（Phase 8.5 核心品种 bootstrap，生产前继续扩充退市记录）
  - [x] 回测必须基于 PIT 品种宇宙

- [ ] **验证**
  - [x] PIT 校准回放正确性：用人工构造的"已知未来"权重验证不会泄露
  - [x] Deflated Sharpe 拒绝过拟合策略：构造 100 个随机策略，验证多数被拒
  - [x] 滑点模型在主力 vs 次主力上有显著差异
  - [x] 注入实盘虚假数据，背离监控正确触发
  - [x] Walk-forward 结果可重现

---

## Phase 9: Shadow Mode + 阈值校准 + LLM 反思 Agent（2 周）

### 目标
建立 A/B 框架（用于后续核心逻辑变更的安全验证）+ 完成置信度阈值的二级校准 + 上线 LLM 反思 Agent（月度生成假设，强制反证，人工评审）。

### 第 1 周：Shadow Mode + 阈值校准

- [x] **Shadow Mode 基础设施**
  - [x] `models/shadow_runs.py` — Shadow 配置追踪表
  - [x] `models/shadow_signals.py` — Shadow 影子信号表
  - [x] Alembic 迁移
  - [x] `services/shadow/runner.py`
    - 新逻辑订阅相同事件，跑出"假信号"写入 `shadow_signals` 表
    - **不发预警**，只记录
    - 支持配置：算法版本、参数 diff
  - [x] `services/shadow/comparator.py`
    - 每日生成对比报告：信号数量差异、命中率差异（30 天滑窗）、关键样本案例
    - 生产路径触发但 shadow 没触发，反之亦然
  - [x] `api/shadow.py` — Shadow 配置管理 + 报告查询
- [x] **置信度阈值二级校准**
  - [x] `services/calibration/threshold_calibrator.py`
    - 每月统计 `预测置信度 vs 实际命中率` 的 reliability diagram
    - 用 isotonic regression 或 Platt scaling 学习单调映射
    - 输出建议的新阈值（85% / 60%）
  - [x] **不自动调整**：阈值变更走 `change_review_queue`，人工评审 + 确认后才生效
  - [x] 前端：校准曲线可视化页面
- [x] **首批 Shadow 应用场景**
  - [x] 校准公式参数变更（α₀ / β₀ 不同先验值的对比）
  - [x] 对抗引擎历史组合检验阈值（Jaccard 相似度 0.6 vs 0.7 vs 0.8）
  - [x] news_event 评估器的严重度门槛（≥3 vs ≥2）

### 第 2 周：LLM 反思 Agent（新增 6.20）

- [x] **数据模型**
  - [x] `models/learning_hypotheses.py` — 假设追踪表
    - 字段：hypothesis, supporting_evidence(jsonb), proposed_change, confidence, sample_size, counterevidence(jsonb), status, created_at
    - status：proposed / reviewed / shadow_testing / validated / applied / rejected
  - [x] Alembic 迁移
- [x] **反思 Agent 实现**
  - [x] `services/learning/reflection_agent.py`
    - 每月调度一次（**不是每日**，避免拟合短期噪声）
    - 输入数据脱敏：不传交易金额，只传相对收益和命中标记
  - [x] 输入聚合：
    - 上月所有信号 + 触发上下文（regime、行情、新闻）
    - 上月所有推荐 + 实际结果（来自 Phase 6 归因）
    - 用户反馈数据（来自 Phase 5 用户反馈）
    - Concept Drift 状态（来自 Phase 3 drift_monitor）
  - [x] LLM Prompt：
    - 任务：识别表现异常的信号、寻找未编码关联、假设当前 regime 下不适用的评估器
    - **强制反证**：每个假设必须列出至少 2 个反证或替代解释
  - [x] 输出 Pydantic 模型强制：
    ```python
    class LearningHypothesis(BaseModel):
        hypothesis: str
        supporting_evidence: list[str]
        proposed_change: str | None
        confidence: float
        counterevidence_considered: list[str]
        sample_size: int
    ```
  - [x] 输出过滤：含"立即"、"自动"、"无需审核"等词的假设直接拒绝
  - [x] 样本量门槛：`sample_size < 30` 标 `weak_evidence`
  - [x] 月度成本上限：单次反思调用 token 上限（避免烧钱）
- [x] **假设生命周期工作流**
  - [x] LLM 输出 → status=`proposed`，写入 `learning_hypotheses`
  - [x] 同时写入 `change_review_queue`（接 Phase 3 治理基础设施）
  - [x] 前端"假设报告"页面：列出本月所有假设 + 反证 + 状态
  - [x] 人工评审：approve / reject / refine
  - [x] approve 后转 status=`shadow_testing`，自动配置 Shadow Mode 跑 30 天
  - [x] Shadow 验证通过 + 性能优于现状 → status=`validated`
  - [x] **最终人工批准** → status=`applied`，进入生产
- [x] **关键约束验证**
  - [x] 任何 status != applied 的假设不影响主链路
  - [x] 单元测试：尝试用 status=proposed 的假设修改 calibration 表应失败
  - [x] 单元测试：LLM 直接修改任何主链路参数应失败
- [x] **向量检索质量门 + 评测框架**
  - [x] `vector_chunks` 表 `quality_status` 字段三档生效：unverified（× 0.5）/ human_reviewed（× 1.0）/ validated（× 1.2）
  - [x] LLM 反思 Agent 的输出默认 `unverified`，走完 `change_review_queue` 才升级
  - [x] `models/vector_eval_set.py` — 检索质量评测集
  - [x] 手工标注 50 条 query → relevant_chunk_ids 对作为种子
  - [x] `services/vector_search/eval.py` — 月度跑 NDCG@10 / Recall@10
  - [x] Embedding 模型/参数变更走 Shadow Mode 对比
- [ ] **验证**
  - [x] 同一信号事件被生产和 shadow 同时处理
  - [x] 30 天后能产出有效对比报告
  - [x] 置信度阈值校准在 reliability diagram 上明显改善
  - [x] 反思 Agent 月度调度正常，输出符合 Pydantic 结构
  - [x] 强制反证机制生效（无反证的假设被拒绝）
  - [x] 治理守卫拦截绕过审核的修改尝试
  - [x] LLM 写入向量库时 quality_status 默认 unverified
  - [x] 检索时不同 quality_status 的加权差异生效

---

## Phase 10: Event Intelligence Engine / 事件智能引擎（2 周）

### 目标

建立动态事件组织能力，让 Zeus 不只“展示新闻/天气/航运/社媒”，而是能把外部信息转成可审计的商品影响判断：

- 信息源识别：新闻、社媒、公告、天气、航运、库存、持仓、行情异常。
- 实体抽取：人物、国家/地区、港口、产区、企业、商品、合约、政策关键词。
- 影响机制：供给、需求、物流、政策、库存、成本、风险偏好、地缘冲突。
- 方向判断：看多 / 看空 / 双向不确定 / 仅需观察。
- 证据与反证：每条事件影响链必须带支持证据、反证、数据新鲜度和置信度。

### 开发任务

- [x] **Phase 10.1 事件规范化层**
  - [x] 定义 `event_intelligence_items` / `event_impact_links` 数据模型。
  - [x] 将新闻事件映射为统一事件智能对象，并保留 `source_type/source_id` 去重约束。
  - [x] 新闻写入链路自动生成事件智能对象，历史新闻可通过 `/from-news/{news_event_id}` 回放生成。
  - [x] 建立 source reliability、新鲜度、人工复核和影响分字段。
- [x] **商品影响引擎**
  - [x] 基于 Commodity Lens 维护首批商品属性：产区、成本、物流、政策和天气敏感度。
  - [x] 首版规则 resolver 输出 `event -> mechanism -> symbol/region` 影响链。
  - [x] LLM 负责语义抽取与假设生成，规则层负责边界约束和可解释字段校验。
  - [x] 同一因素可影响多个商品，输出多条 `event → mechanism → symbol/region` 链路。
- [ ] **治理与安全**
  - [x] 事件影响判断默认进入 Shadow / review，不直接改生产阈值。
  - [x] 高影响、单源、低置信度事件必须要求人工确认。
  - [x] 每条链路保留原始证据引用、反证、数据新鲜度和置信度。
  - [x] 模型版本、LLM 提示版本和治理审计表。
    - [x] Phase 10.2 先在 `source_payload` 记录 `semantic_model` / `semantic_prompt_version`。
    - [x] Phase 10.3 补独立治理审计表与人工确认流。
    - [x] Phase 10.3.1 高影响 / 单源 / 低置信事件自动写入 `change_review_queue`，人工决策后关闭复核项并生成 `event_intelligence_review` 学习记录。
    - [x] Phase 10.3.2 支持人工修改单条影响链，修改后事件与链路回到 `human_review`，审计记录标记 `production_effect=none` 并重新进入治理队列。
    - [x] Phase 10.3.3 Event Intelligence 页面展示治理时间线，确认、复核、语义增强、规则解析和影响链修改均可追溯。
    - [x] Phase 10.3.4 新增统一治理队列工作台，支持查看 `change_review_queue`、批准 / 驳回 / 转影子复核 / 标记已审查；通用队列只记录治理结论，事件智能队列项通过专用决策服务同步状态。
- [ ] **前端联动**
  - [x] Phase 10.4 最小联动：Causal Web 可按 `symbol + region` 加载事件智能链路，并把 `event_intelligence_items -> event_impact_links` 显示为源事件到影响假设。
  - [x] Phase 10.4 最小联动：World Risk Map 聚合事件智能对象和影响链，区域运行态、证据、风险分和 Causal Web URL 使用同一 `event_id` 作用域。
  - [x] Phase 10.5 聚合去重：Causal Web / World Risk Map 对同源转写、媒体转载和标题前后缀做展示层去重，保留数据库原始审计记录。
  - [x] Phase 10.6 Causal Web 阅读层：事件智能节点提供双语证据摘要，点击源事件/影响假设时展示关联链路和方向置信。
  - [x] Phase 10.8 Causal Web 路径聚焦：点击事件智能节点后可收束到相关影响链，并展开结构化支持证据 / 反证线索。
  - [x] Phase 10.7 World Risk Map 显式筛选：按事件源、品种和影响机制请求同一后端作用域，地图、瓦片、索引、详情和 Causal Web URL 保持一致。
  - [x] Phase 10.9 事件智能质量门：按证据、反证、来源可信、新鲜度、作用域和影响链完整性输出 `blocked/review/shadow_ready/decision_grade`。
  - [x] Phase 10.10 质量门联动：Causal Web / World Risk Map 显示质量门状态，并对地图风险分做质量加权。
  - [x] Phase 10.11 World Risk Map 证据健康层：区域接口输出 `evidenceHealth`，前端展示证据密度、来源可信度、新鲜度和反证覆盖，避免只看风险分。
  - [x] Phase 10.12 World Risk Map 风险动量层：区域接口输出 `riskMomentum`，前端把升温 / 降温 / 稳定、动量原因和脉冲动效纳入阅读路径。
  - [x] Phase 10.13 World Risk Map 风险链阅读动线：区域档案新增“链路总览”，将动量、证据健康、质量门和因果网络入口组织成同一阅读路径。
  - [x] Phase 10.14 World Risk Map 推荐动作入口：区域档案按质量门、证据健康、动量和作用域生成下一步动作，指向事件智能、新闻证据或因果网络。
  - [x] Phase 10.15 World Risk Map 上下文跳转：推荐动作携带 `source=world-map`、`symbol`、`region` 和可用的 `event` 作用域，事件智能 / 新闻页自动带入筛选上下文。
  - [x] Phase 10.16 Event Intelligence 反向地图联动：事件智能影响链和新闻事件智能链可按 `symbol/source/mechanism/region/event` 打开世界风险地图，并自动聚焦区域档案。
  - [x] Phase 10.17 World Risk Map 事件作用域可见化：地图从事件智能进入时，在区域档案中显示当前事件作用域、命中证据、质量门和直接作用域命中状态。
  - [x] 新增 Event Intelligence 页面：事件池、影响链、证据/反证、人工确认队列。
  - [x] Event Intelligence 页面展示 LLM 语义假设与模型/提示版本。
  - [x] Event Intelligence 页面支持确认、拒绝、转人工复核，并写入审计日志。
  - [x] Event Intelligence 页面支持编辑影响链的品种、区域、机制、方向、置信度、证据和反证；保存后必须重新复核。
  - [x] Event Intelligence 页面展示审计历史摘要，包含状态流转、操作者、备注、变更字段、复核原因和生产影响。

### 验证

- [x] 特朗普社媒、航母移动、极端天气、港口拥堵、政策公告等样例能生成不同机制链。
- [x] 同一事件影响多个商品时，方向、机制和置信度可以不同。
- [x] 单源高影响事件不会自动进入生产预警。
- [x] 人工确认 / 拒绝 / 转人工复核会写入独立治理审计日志。
- [x] 高影响、单源或低置信事件智能对象会进入治理队列；复核结果会保留为可检索学习材料，不改变生产阈值。
- [x] 人工修改影响链会写入 `impact_link.updated` 审计、重新打开复核队列，并保留为学习材料。
- [x] 前端可直接查看事件级治理时间线，避免审计信息只留在后端接口里。
- [x] 前端可查看跨模块治理队列，确认每条自动学习或事件智能建议是否仍停留在 Shadow / review 作用域。
- [x] Phase 10.4：Causal Web / World Risk Map 使用同一 `event_intelligence:{event_id}` 作用域，不出现各讲各的情况。

---

## 依赖关系

```
P0 ──→ P1 ──→ P2 ──→ P3 ──→ P4 ──→ P4.5 [pgvector] ──→ P5
                │       │                                  │
                │       └─[governance]────────────────────┐│
                │                                          ↓↓
                └──→ P6 [推荐归因]───────────────────────→ │
                │                                          │
                └──→ P7a [滑点深度数据] ──→ P7b ─────────→ │
                                                           │
                                                           └─→ P8 ──→ P8.5 [回测正确性] ──→ P9 [反思 + 向量质量门]
                                                                                               │
                                                                                               └─→ P10 [事件智能引擎]
```

- P0 → P1：后端骨架是迁移的前提
- P1 → P2：核心 API + PIT 数据 + 合约元数据就绪后才能重构为事件驱动
- P2 → P3：事件总线就绪后校准循环才能订阅信号事件
- **P3 → 全局**：治理守卫（governance）在 P3 建立后，所有后续阶段的自动学习模块都依赖它
- P3 → P4：校准数据 + Drift 监控为对抗引擎提供数据源（P4 冷启动期 warmup 模式）
- P4 → P4.5：对抗引擎接入后才有清洁的事件流接 news_event 评估器
- P4.5 → P5：news_event 评估器 + pgvector 检索基础设施就绪后 Alert Agent 才能处理事件类信号
- P5 → P6：用户反馈采集就绪后，推荐归因可以关联反馈数据
- P6 推荐归因 → P9：反思 Agent 需要推荐 P&L / MAE / MFE 数据
- P6 和 P7a/P7b 可与 P3-P5 并行开发（仅依赖 P2 的事件总线）
- P7a 顺带采集成交量/深度数据 → P8.5 滑点模型标定输入
- P8 依赖 P5（Alert Agent 可触发推演）和 P7b（成本模型提供推演参数）
- **P8 → P8.5**：场景推演就绪后才进入回测正确性收紧（PIT 校准依赖 P3 校准基础设施）
- **P8.5 → P9**：回测正确性是 LLM 反思 Agent 评估策略级假设的前提（避免基于不可信回测做假设）
- P9 依赖 P3 (治理) + P5 (反馈) + P6 (归因) + P7a/b（成本信号）+ P8.5（可信回测）—— 所有数据源就绪后才能做反思
- P10 依赖 P4.5（结构化新闻）、P9（治理与质量门）、World Risk Map（区域/商品作用域）和 Causal Web（因果链展示）

## 里程碑

| 里程碑 | 时间点 | 标志 |
|--------|--------|------|
| M1: 功能对等 | P1 完成（~3 周） | Zeus 后端完全替代 Causa TypeScript 后端，PIT + 合约元数据就绪 |
| M2: 架构升级 | P2 完成（~4 周） | 事件驱动 + DB 驱动监控列表 |
| M3: 自校准基础 | P3 完成（~6 周） | 校准 + Drift 监控 + 治理守卫就绪 |
| M4: 智能升级 | P5 完成（~10 周） | 校准 + 对抗 + 新闻 + 混合决策 + 人机交互 + LLM 成本 + 用户反馈 + pgvector |
| M5: 推荐归因 | P6 完成（~11.5 周） | 推荐级 P&L / MAE / MFE 追踪，Goal B 数据基础就绪 |
| M6: 产业智能 | P7b 完成（~15 周） | 成本模型完整接入信号系统 |
| M6.5: 回测可信 | P8.5 完成（~17 周） | PIT 校准 + Deflated Sharpe + 滑点分档 + Live 背离监控，所有 backtest 输出可作决策依据 |
| M7: 自我学习闭环 | P9 完成（~19 周） | Shadow Mode + 阈值校准 + LLM 反思 Agent + 向量质量门，自我学习闭环全部就绪 |
| M8: 事件智能 | P10 完成（~22 周） | 外部事件可动态组织为商品影响链，并进入 Causal Web / World Risk Map 同一作用域 |

## 每阶段验证清单

每个阶段完成后必须通过：

1. `pytest` — 全部测试通过
2. `docker compose up` — 所有服务健康（health 端点返回 200）
3. 前端加载正常，数据从 Python 后端获取
4. 新增功能的手动验证（具体项见各阶段）
5. 无回归：之前阶段的功能仍然正常
